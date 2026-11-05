# Published experiment files

This directory publishes the formal per-frame CSV logs, frozen release plans,
profiling records, summaries, figures, representative lossless PNG images,
simulated-display MP4 videos and measured source snapshot. The sibling
`deadline_readiness_xavier_20261104` directory preserves the cold-start diagnostic
and matched Numba/CUDA control separately.

The large `replay/*.bgr.gz` lossless frame streams and redundant `repro_bundle.zip`
remain on the experiment host, outside Git. The dataset clips are also external;
their provenance and hashes are in `profile_input.json` and `evaluation_input.json`.
`files_sha256.json` describes the complete local run, including those unpublished
frame streams. Replaying the experiment regenerates them.

The published CSV files suffice to regenerate all statistical figures with
`deadline_experiments/analyze.py`. The independent pixel audit and video renderer
require the lossless frame streams; their completed audit results and rendered
outputs are published here.
