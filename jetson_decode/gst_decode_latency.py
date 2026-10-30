"""Measure serial HEVC AU input -> NVDEC NVMM-output availability on Jetson.

Requires system Python's gi/GStreamer, h265parse and nvv4l2decoder. No raw-image
mapping or color conversion occurs. Each compressed AU is fully in host memory
before measurement. This is application-observed latency, not pure NVDEC time.
"""
import argparse
import csv
import hashlib
import json
import time
from pathlib import Path
from statistics import mean

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst


def check_error(pipeline):
    message = pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR)
    if message:
        error, debug = message.parse_error()
        raise RuntimeError('%s: %s (%s)' % (message.src.get_name(), error, debug))


def has_vcl(payload):
    # HEVC VCL NAL-unit types are 0..31. Headers may arrive separately from AU.
    i = 0
    while i < len(payload) - 4:
        if payload[i:i + 3] == b'\x00\x00\x01':
            start = i + 3
        elif payload[i:i + 4] == b'\x00\x00\x00\x01':
            start = i + 4
        else:
            i += 1
            continue
        if (payload[start] >> 1) & 63 <= 31:
            return True
        i = start + 2
    return False


def extract_aus(path, timeout):
    pipeline = Gst.parse_launch(
        'filesrc name=source ! qtdemux ! h265parse ! '
        'video/x-h265,stream-format=byte-stream,alignment=au ! '
        'appsink name=sink sync=false max-buffers=8 drop=false')
    pipeline.get_by_name('source').set_property('location', str(path.resolve()))
    sink = pipeline.get_by_name('sink')
    frames = []
    headers = b''
    caps = None
    last_progress = time.perf_counter()
    try:
        assert pipeline.set_state(Gst.State.PLAYING) != Gst.StateChangeReturn.FAILURE
        while True:
            sample = sink.emit('try-pull-sample', int(0.2 * Gst.SECOND))
            check_error(pipeline)
            if sample is None:
                if sink.get_property('eos'):
                    break
                if time.perf_counter() - last_progress > timeout:
                    raise TimeoutError('MP4 parsing made no progress within %.1fs' % timeout)
                continue
            last_progress = time.perf_counter()
            buffer = sample.get_buffer()
            payload = buffer.extract_dup(0, buffer.get_size())
            caps = sample.get_caps().copy()
            if not has_vcl(payload):
                headers += payload
                continue
            if buffer.pts == Gst.CLOCK_TIME_NONE:
                raise RuntimeError('VCL AU has no PTS; cannot match decoded output')
            frames.append(dict(payload=headers + payload, pts=buffer.pts,
                               dts=buffer.dts, duration=buffer.duration,
                               flags=int(buffer.get_flags())))
            headers = b''
        if not frames or caps is None:
            raise RuntimeError('No HEVC video access units found')
        pts = [f['pts'] for f in frames]
        if len(set(pts)) != len(pts) or pts != sorted(pts):
            raise RuntimeError('Requires unique, increasing PTS and no B-frame reordering')
        return frames, caps
    finally:
        pipeline.set_state(Gst.State.NULL)


def decode_once(frames, caps, timeout, repeat, writer, max_performance=False):
    pipeline = Gst.parse_launch(
        'appsrc name=source format=time block=true is-live=false ! '
        'nvv4l2decoder name=decoder disable-dpb=true ! '
        'appsink name=sink sync=false max-buffers=1 drop=false')
    source = pipeline.get_by_name('source')
    pipeline.get_by_name('decoder').set_property('enable-max-performance', max_performance)
    source.set_property('caps', caps)
    sink = pipeline.get_by_name('sink')
    latencies = []
    output_caps = None
    try:
        assert pipeline.set_state(Gst.State.PLAYING) != Gst.StateChangeReturn.FAILURE
        for index, frame in enumerate(frames):
            buffer = Gst.Buffer.new_allocate(None, len(frame['payload']), None)
            buffer.fill(0, frame['payload'])
            buffer.pts, buffer.dts = frame['pts'], frame['dts']
            buffer.duration = frame['duration']
            buffer.set_flags(Gst.BufferFlags(frame['flags']))
            # Buffer allocation/copy above is excluded. No second AU is pushed
            # until this AU's output is available, so queue depth stays one.
            start = time.perf_counter_ns()
            flow = source.emit('push-buffer', buffer)
            if flow != Gst.FlowReturn.OK:
                check_error(pipeline)
                raise RuntimeError('push-buffer failed: %s' % flow)
            sample = sink.emit('try-pull-sample', int(timeout * Gst.SECOND))
            end = time.perf_counter_ns()
            check_error(pipeline)
            if sample is None:
                raise TimeoutError('No output for AU %d after %.1fs. '
                                   'Serial low-latency decoding did not complete.' % (index, timeout))
            decoded = sample.get_buffer()
            if decoded.pts != frame['pts']:
                raise RuntimeError('PTS mismatch at AU %d: %s != %s' %
                                   (index, decoded.pts, frame['pts']))
            if output_caps is None:
                output_caps = sample.get_caps().to_string()
            ms = (end - start) / 1e6
            latencies.append(ms)
            writer.writerow(dict(repeat=repeat, frame_index=index, pts_ns=frame['pts'],
                                 latency_ms=ms, compressed_bytes=len(frame['payload']),
                                 initial_10_frames=int(index < 10)))
            # Release the decoded surface before asking for the next frame.
            del decoded, sample, buffer
        flow = source.emit('end-of-stream')
        if flow != Gst.FlowReturn.OK:
            raise RuntimeError('end-of-stream failed: %s' % flow)
        deadline = time.perf_counter() + timeout
        while not sink.get_property('eos'):
            extra = sink.emit('try-pull-sample', int(0.1 * Gst.SECOND))
            check_error(pipeline)
            if extra is not None:
                raise RuntimeError('Unexpected extra decoded frame after EOS')
            if time.perf_counter() > deadline:
                raise TimeoutError('Decoder EOS did not complete')
        return latencies, output_caps
    finally:
        pipeline.set_state(Gst.State.NULL)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--outdir', type=Path, required=True)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--timeout', type=float, default=10)
    p.add_argument('--expected-frames', type=int)
    p.add_argument('--max-performance', action='store_true',
                   help='Set nvv4l2decoder enable-max-performance=true')
    args = p.parse_args()
    if args.repeats < 1 or args.timeout <= 0:
        p.error('Positive repeats/timeout required')
    args.outdir.mkdir(parents=True, exist_ok=False)
    Gst.init(None)
    frames, caps = extract_aus(args.input, args.timeout)
    if args.expected_frames is not None and len(frames) != args.expected_frames:
        raise RuntimeError('AU count %d differs from expected %d' % (len(frames), args.expected_frames))
    all_values, after10 = [], []
    runs = []
    with (args.outdir / 'latencies.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['repeat', 'frame_index', 'pts_ns', 'latency_ms',
                                              'compressed_bytes', 'initial_10_frames'])
        writer.writeheader()
        for repeat in range(args.repeats):
            values, output_caps = decode_once(frames, caps, args.timeout, repeat, writer, args.max_performance)
            f.flush()
            all_values.extend(values)
            after10.extend(values[10:])
            runs.append(dict(repeat=repeat, frames=len(values), mean_all_ms=mean(values),
                             mean_after_initial10_ms=mean(values[10:]) if len(values) > 10 else None,
                             first_frame_ms=values[0]))
            print('repeat=%d frames=%d mean_all_ms=%.6f mean_after_initial10_ms=%s' %
                  (repeat, len(values), mean(values), runs[-1]['mean_after_initial10_ms']), flush=True)
    result = dict(input=str(args.input.resolve()), sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                  gstreamer=Gst.version_string(), frames_per_run=len(frames), repeats=args.repeats,
                  samples=len(all_values), mean_all_ms=mean(all_values),
                  mean_after_initial10_ms=mean(after10) if after10 else None, runs=runs,
                  input_caps=caps.to_string(), output_caps=output_caps,
                  decoder='nvv4l2decoder', disable_dpb=True, serial_inflight_access_units=1,
                  enable_max_performance=args.max_performance,
                  scope='Compressed AU already in host memory, push-buffer before to matching '
                        'decoded NVMM sample availability. Includes Python/GStreamer calls, queue '
                        'and decoder work. Excludes file I/O, MP4 demux/parse, input buffer copy, '
                        'NV12-to-BGR conversion, CPU download, reconstruction and display.',
                  statistic='arithmetic mean', fps_inverse_is_latency=False)
    (args.outdir / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (args.outdir / 'COMPLETE').write_text('All AU PTS matched decoded output; frame counts verified.\n')


if __name__ == '__main__':
    main()
