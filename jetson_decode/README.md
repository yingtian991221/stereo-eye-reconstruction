# Jetson HEVC decode latency

Measured four-video results and exact encoding settings are in
[the experiment report](../results/hevc_decode_xavier_20261029/README.md).
`encode_driving.py` encodes original left-eye PNGs at 90 FPS, HEVC 8 Mbps,
YUV420p, no B frames, GOP 90. It requires an FFmpeg build with libx265:

```bash
python encode_driving.py --ffmpeg /path/to/ffmpeg --data-root /path/to/driving_forward_speed --out /new/video/directory
```

`benchmark_ffmpeg.py` validates frame counts and measures full-process decode
throughput. On the tested Jetson, NVIDIA FFmpeg was extracted into
`/home/yingtian/stereo-decode-20261029/tools/runtime`, with its libraries under
`usr/lib/aarch64-linux-gnu`; set LD_LIBRARY_PATH to that directory. This does
not install system packages. Its hardware wrapper returned 294/300 frames in
the initial test and that result was rejected. GStreamer below passed full
frame-count validation. Software throughput can be reproduced with
`--decoders hevc`.

`gst_decode_latency.py` measures compressed HEVC access-unit submission to a
matching decoded output sample using NVIDIA's `nvv4l2decoder`. It requires the
Jetson system Python with `gi` and the installed GStreamer NVIDIA plugins.

```bash
python3 jetson_decode/gst_decode_latency.py \
  --input driving_15_300.mp4 --outdir results/new_decode_run \
  --expected-frames 300 --repeats 3 --timeout 10
```

The output directory must be new. Each repeat starts a fresh decoder pipeline.
All compressed frames are demuxed/parsed into host memory before timing. The
script submits one access unit and waits for its matching output PTS before
submitting the next. The input must have no B-frame reordering. `disable-dpb=true`
enables this serial low-latency path; the script reports a bounded timeout if a
decoder cannot produce an output under these conditions.

Timing starts immediately before `appsrc.push-buffer` and ends when the matching
`appsink` decoded sample becomes available. Input buffer allocation and copying
are outside the interval. The interval includes Python/GStreamer call overhead,
queueing and decoder work. Output remains in the decoder's native memory and
format. It excludes raw-image download/mapping, NV12-to-BGR conversion, file I/O,
MP4 demux/parse, reconstruction, network and display. This is application-observed
decode availability latency, not a hardware-cycle measurement.

`latencies.csv` retains every measured frame, including the first frame. JSON
reports the arithmetic mean of all samples and, separately, the arithmetic mean
after the first ten frames of each repeat. First-frame latency remains explicit.
Only `COMPLETE` confirms that all expected frames and PTS matches passed.

Frames per second from a fully pipelined decoder measures throughput. Its inverse
is the average output interval, not automatically the serial per-frame latency
reported by this script.

Both scripts accept `--max-performance`, which sets the decoder's
`enable-max-performance=true` property. It defaults to false and is recorded in
each result. Power mode and observed clocks still need to be recorded separately.
Use independent output directories for the two settings.

## Whole-pipeline throughput

```bash
python3 jetson_decode/gst_decode_throughput.py \
  --input driving_15_300.mp4 --outdir results/new_throughput_run \
  --expected-frames 300 --repeats 3 --timeout 120 --max-performance
```

This test streams the MP4 through `filesrc`, `qtdemux`, `h265parse`,
`nvv4l2decoder disable-dpb=true`, and `fakesink sync=false`. It counts every output
frame, verifies unique increasing PTS, and requires EOS. `outputs.csv` preserves
the arrival timestamp of each output frame. The pipeline wall interval runs from
the PLAYING request to EOS and includes startup/drain, I/O, parsing, decode and
Python handoff callbacks. Output-span throughput uses `(N-1)/(last-first)`.
Neither its inverse nor whole-pipeline wall time divided by frame count measures
individual input-to-output latency. The summary reports arithmetic means over
the completed repeated runs.
