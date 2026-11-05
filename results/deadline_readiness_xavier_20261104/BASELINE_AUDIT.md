# Baseline and metric audit, 2026-11-04

## Existing progress checked before implementation

- Local and GitHub code HEAD: `31cba0e82e7f50d0533f799e30eefd0dfd2c2f4a`.
  GitHub has only `master`; no newer remote deadline implementation was found.
  Local uncommitted FOV-only-clear work was preserved. Xavier's older checkout
  was at `b8ea953`; new runs use a separate `deadline-20261104` directory.
- Paper repository `main`: `a82f36b9f8e603d553fe70435d3695f9773087c0`.
  `src/05-fov-reconstruction.tex` and `src/08-jitter-evaluation.tex` still say
  development outline and contain no new measured results. No paper claims
  were silently updated.
- Reviewed full 1068-frame 2026-10-27 runs, 2026-10-29 four-scale full runs,
  stopped 2026-10-30 partial outputs, Numba smoke tests and CUDA stage breakdown.
  None logs a live input-release/deadline/display-history experiment.

## Metric correction

`jetson_cuda/pirate_bench.cu::legacyPSNR` deliberately performs wrapped uint8
subtraction/squaring. It remains available to reproduce historical numbers.
`evaluate_levels.py::metrics/region_metrics` already computes float64 standard
MSE/PSNR, so existing saved standard metrics did not need a repeat sweep.
Previous presentation loss figures nevertheless came from the legacy column.

For example, the historical 2026-10-27 resident 160x90/full row has standard
right-eye PSNR about 18.869 dB. The 2026-10-29 96x54 Half row has standard
right-eye PSNR 19.422 dB versus its paired Full 18.869 dB. These are historical
diagnostics, not pooled with the new timing/quality experiment. They already
show why Full or a larger ROI cannot be assumed to have better PSNR.

The new runner computes errors in floating point before squaring and pools
both actual eyes. It reports generated and simulated-display quality separately.
No legacy PSNR or dB-loss-divided-by-two number supports a new claim.

## Fairness and boundaries

- New Full/Half/FoV use exactly the same decoded inputs, buffers, geometry
  arithmetic, full scratch clearing, coalesced-clear flag and fast-resample flag.
  The historical FOV-only-clear path is not used. No Graph or cross-refresh
  feature/RGB cache is introduced.
- All new formal trials use the same Xavier mode 5 (30W 4CORE), same executable,
  preallocated resources, sequences and release schedules. Clocks are not
  manually locked; telemetry is retained. No two GPU benchmarks run concurrently.
- The live timer includes host selection/queue effects and device input binding,
  history orientation, reconstruction, upsampling/blending, output orientation
  and synchronization. Disk I/O, initial allocation/upload, evaluation and
  image saving are outside playback. Inputs are already decoded and GPU resident.
- Figure 14's 9.4ms is decoding 3.2ms plus reconstruction stages 6.2ms. Neither
  its total nor its reconstruction subtotal is used as a speedup baseline.
- The previously presented 7.996ms Full and fixed 2ms allowance are not used.

## Alternation and known inherited limitations

The old `.pir` sweep contains odd right-eye frames only, with decoded previous
right-eye input. The source top-level even-eye path is commented out, references
missing `7_depth_right`, and casts depth to uint8. The new continuous experiment
uses available symmetric uint16 gray-depth/flow maps and 8_left/8_right for both
directions. Horizontal reflection implements left reconstruction without changing
the core right reconstruction kernels. This is a documented restoration of
alternation, not a claim that the archived top-level script was complete.

The original non-atomic disparity collision rule and uint8 z buffer remain.
Numerical outputs are not guaranteed bitwise deterministic. Baseline comparisons
retain these algorithms; correcting their geometry is beyond this bounded audit.
Repeated runs and raw outputs expose variation instead of hiding it.

Profiling (frames 7–22) and held-out evaluation (39–134) are disjoint. Per-frame
content and clock behavior can change execution time. The fixed estimator is
not retuned against formal-test misses. There is no claim that a mean-based
profile guarantees a deadline.
