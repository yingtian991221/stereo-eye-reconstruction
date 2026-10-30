"""Measure whole-pipeline NVDEC throughput; inverse FPS is not frame latency."""
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


def run(path, expected, timeout, max_performance, repeat, writer):
    pipeline = Gst.parse_launch(
        'filesrc name=source ! qtdemux ! h265parse ! '
        'video/x-h265,stream-format=byte-stream,alignment=au ! '
        'nvv4l2decoder name=decoder disable-dpb=true ! '
        'fakesink name=sink sync=false signal-handoffs=true')
    pipeline.get_by_name('source').set_property('location', str(path.resolve()))
    pipeline.get_by_name('decoder').set_property('enable-max-performance', max_performance)
    outputs = []
    errors = []
    output_format = []
    started = time.perf_counter_ns()

    def handoff(sink, buffer, pad):
        try:
            now = time.perf_counter_ns()
            if not output_format:
                output_format.append(pad.get_current_caps().to_string())
            outputs.append((now, int(buffer.pts)))
            writer.writerow(dict(repeat=repeat, frame_index=len(outputs)-1,
                                 pts_ns=buffer.pts, elapsed_from_start_ms=(now-started)/1e6))
        except Exception as error:
            errors.append(str(error))

    pipeline.get_by_name('sink').connect('handoff', handoff)
    try:
        started = time.perf_counter_ns()
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError('Could not set pipeline PLAYING')
        message = pipeline.get_bus().timed_pop_filtered(
            int(timeout * Gst.SECOND), Gst.MessageType.ERROR | Gst.MessageType.EOS)
        ended = time.perf_counter_ns()
        if message is None:
            raise TimeoutError('No pipeline EOS within %.1fs' % timeout)
        if message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            raise RuntimeError('%s: %s (%s)' % (message.src.get_name(), error, debug))
        if errors:
            raise RuntimeError('Output callback failed: ' + '; '.join(errors))
        if len(outputs) != expected:
            raise RuntimeError('Decoded %d frames; expected %d' % (len(outputs), expected))
        if not output_format or 'memory:NVMM' not in output_format[0]:
            raise RuntimeError('Expected native NVMM output, got %s' % output_format)
        pts = [p for _, p in outputs]
        if len(set(pts)) != expected or pts != sorted(pts):
            raise RuntimeError('Output PTS are not unique and increasing')
        wall_ms = (ended-started)/1e6
        span_ms = (outputs[-1][0]-outputs[0][0])/1e6
        return dict(repeat=repeat, frames=len(outputs), pipeline_wall_ms=wall_ms,
                    output_caps=output_format[0],
                    pipeline_fps=len(outputs)*1000/wall_ms,
                    amortized_wall_ms_per_frame=wall_ms/len(outputs),
                    first_output_ms=(outputs[0][0]-started)/1e6,
                    first_to_last_output_ms=span_ms,
                    output_span_fps=(len(outputs)-1)*1000/span_ms if span_ms > 0 else None,
                    mean_output_interval_ms=span_ms/(len(outputs)-1) if len(outputs)>1 else None)
    finally:
        pipeline.set_state(Gst.State.NULL)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--outdir', type=Path, required=True)
    p.add_argument('--expected-frames', type=int, required=True)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--timeout', type=float, default=120)
    p.add_argument('--max-performance', action='store_true')
    args = p.parse_args()
    if args.expected_frames < 2 or args.repeats < 1 or args.timeout <= 0:
        p.error('At least two expected frames, positive repeats and timeout required')
    args.outdir.mkdir(parents=True, exist_ok=False)
    Gst.init(None)
    runs = []
    with (args.outdir/'outputs.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['repeat','frame_index','pts_ns','elapsed_from_start_ms'])
        writer.writeheader()
        for repeat in range(args.repeats):
            value = run(args.input, args.expected_frames, args.timeout,
                        args.max_performance, repeat, writer)
            runs.append(value)
            f.flush()
            print(json.dumps(value), flush=True)
    result = dict(input=str(args.input.resolve()), sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                  gstreamer=Gst.version_string(), decoder='nvv4l2decoder', disable_dpb=True,
                  enable_max_performance=args.max_performance, runs=runs,
                  mean_pipeline_fps=mean(r['pipeline_fps'] for r in runs),
                  mean_amortized_wall_ms_per_frame=mean(r['amortized_wall_ms_per_frame'] for r in runs),
                  mean_output_span_fps=mean(r['output_span_fps'] for r in runs),
                  mean_output_interval_ms=mean(r['mean_output_interval_ms'] for r in runs),
                  statistic='arithmetic mean across runs',
                  scope='PLAYING call to pipeline EOS includes file I/O, MP4 demux/HEVC parse, '
                        'hardware decode, startup/drain, and Python output callbacks. '
                        'Output remains NVMM, without color conversion/download or display.',
                  inverse_fps_is_frame_latency=False,
                  warning='Amortized wall/frame and output intervals measure pipelined throughput, '
                          'not individual input-to-output decode latency.')
    (args.outdir/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (args.outdir/'COMPLETE').write_text('EOS and expected decoded frame counts verified on every repeat.\n')


if __name__ == '__main__':
    main()
