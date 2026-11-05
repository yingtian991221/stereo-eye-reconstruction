# Deadline-aware reconstruction experiments

This is a **synthetic decoded-input-readiness experiment on a real GPU**.
The release plan is synthetic; actual producer releases, FIFO scheduling,
reconstruction starts and completions are measured with `steady_clock`.
The display sequence is simulated from those measurements and actual images.
There is no Wi-Fi, decoder or physical scan-out measurement in this framework.

## Reproduce

1. Export disjoint clips from the existing 15mm forward / 300-frame dataset:

   ```bash
   python deadline_experiments/export_clip.py --folder /path/to/15mm_focallength/scene_forwards/aaa --out profile.gz --start 7 --count 16
   python deadline_experiments/export_clip.py --folder /path/to/15mm_focallength/scene_forwards/aaa --out evaluation.gz --start 39 --count 96
   ```

2. On Xavier, choose a new output directory and run:

   ```bash
   bash deadline_experiments/run_xavier.sh NEW_RUN profile.gz evaluation.gz
   ```

   The script does not change the power mode or clocks. Keep the same settings
   for all strategies. It requires the CUDA toolkit, zlib and Python standard
   library. Plotting is done separately, after playback, using NumPy, pandas
   and matplotlib. Never compare this timing boundary with the old 9.4ms
   decode-plus-reconstruction number. Figure 14 assigns 3.2ms to decoding and
   6.2ms to the reconstruction stages, in a different experiment/environment.

3. Copy outputs to the host and run:

   ```bash
   python deadline_experiments/analyze.py NEW_RUN
   python deadline_experiments/audit_images.py NEW_RUN --clip evaluation.gz
   python deadline_experiments/visualize_outputs.py NEW_RUN --clip evaluation.gz --ffmpeg /path/to/ffmpeg
   python deadline_experiments/test_protocol.py
   ```

`prepare.py` freezes the independent profile, cost/quality estimates and all
release sequences before formal evaluation. There are seven fixed-budget
conditions (including already expired and impossibly tight budgets), four-phase
late-arrival/recovery, short bursts, and seeded random variation. All eight
strategies receive the same 96 input frames and plan, repeated three times in
rotating order. Both Full and Half are always retained in reporting.

An additional fixed 19ms control uses the entire modeled readiness-to-completion
allowance. It was introduced as a diagnostic after the first cold-start sweep,
and is included from the outset in the warmed repeat. The original cold-start
measurements remain in their own result directory. Controller formula and safety
margin are unchanged.

## Time model and policy

- Frame period is 1000/90 ms. Modeled display time is `epoch + i*period + 20ms`.
- Reserve 1ms for hypothetical display submission; the measured completion
  deadline is `epoch + i*period + 19ms`. This offset/reserve is an experimental
  assumption. It is not the frame period and is not measured end-to-end latency.
- Release is `deadline - planned_budget`. Changing release never changes the
  deadline. Inputs are preloaded decoded GPU arrays; reconstruction starts
  with input/history binding, orientation and device copies included.
- A separate producer thread timestamps actual releases. The worker is FIFO.
  Expired jobs skip reconstruction, but received decoded-eye state is updated.
  Otherwise the selected implementation runs to completion, including queue
  and scheduler effects in observed deadline misses.
- Full, Half and FoV 0.1/0.25/0.5/0.7 share the same source kernels, precision,
  full scratch initialization, contiguous-clear optimization and resampling.
  The old FOV-only-clear asymmetry is not used. No CUDA Graph is added.
- The two predeclared selectors use independent **pooled standard MSE quality**:
  global stereo quality (primary) or a fixed central 0.25-width/height region
  (secondary). They choose the highest-scoring feasible configuration,
  including Half and Full; there is no assumed ROI-size ordering. When none
  fits positive time, attempt the least-cost setting. Nonpositive time skips.
- Cost estimate is profiling mean + two sample standard deviations + 0.2ms.
  This formula is fixed before evaluation. No per-condition tuning, oracle,
  future release lookup, future execution-time lookup, or hysteresis is used.

## Stereo history, fallbacks and quality

Odd frames transmit the decoded left eye and reconstruct the right; even
frames do the reverse. The previous image for the reconstructed eye is the
previous frame's received decoded eye. This follows strict alternate-eye
dependency: a previous *reconstruction* is normally refreshed by transmission
before that eye is reconstructed again. Two per-eye states are maintained;
decoded packets update their eye even when too late for display, whereas a
late reconstructed result is discarded. The state assertion checks that the
motion-compensation source has identity `current_frame - 1`. Bootstrap uses
decoded frame `start - 1`, never GT. More general k-frame reuse is not claimed.

For the same reason, reusing a previous generated frame as the motion source
on every iteration would be wrong for this alternating-eye experiment. The
archived odd-only `.pir` exporter supplied a decoded previous eye, not GT.

The original even-eye source references an unavailable `7_depth_right`
directory and casts depth to uint8. This runner instead uses available
symmetric `gray_depth[_right]` uint16 maps and `8_left/8_right` decoded images
for both directions, identically for every strategy. Leftward reconstruction
uses reflected geometry with sign-inverted horizontal flow. The original
non-atomic disparity competition and uint8 z-buffer remain common limitations;
this is not a claim of bitwise equivalence to a complete published streamer.

At each fixed deadline, an on-time generated stereo pair is displayed; otherwise
repeat the last on-time pair. Logs record source frame identity for each
simulated display slot, including the initial decoded bootstrap. Late outputs
are never shown later. Measurements include the resulting queue backlog.

All new quality uses float64 subtraction/squaring, peak 255. Stereo error is
pooled over both **actual** eye images, not a fabricated halving of dB loss.
Generated quality includes late generated frames and is separate from on-time
quality and fallback-inclusive simulated-display quality. Current GT is used
for stale displayed frames, so freezing is penalized. Fixed-center and fixed
boundary-band MSE supplement whole-image quality. Reported PSNR is the arithmetic
mean of per-frame standard PSNR; pooled-MSE PSNR for profiling is named separately.
Historical overflow metrics/results are preserved but do not support new claims.

Every profiling trial and playback trial receives the same one-second sustained
GPU warmup across all six configurations. Playback logs the GPU frequency after
warmup. Profiling uses the 90Hz cadence and defers CPU metrics/readback until its
16-frame trial ends, as playback does. Evaluation still changes the release
cadence deliberately. Clocks are not locked, so content and DVFS can still change
execution time; those misses remain in the results. The first closed loop uses
one contiguous Driving sequence and three repetitions, not all Driving or
independent scenes. An earlier short-warmup run is retained as a cold-start
diagnostic, not combined with the warmed results.

## Output and validation

- `profile.csv`, `estimates.csv`, `config.json`, `release_plan.csv`: immutable
  inputs/parameters for the experiment. Clip JSON includes hashes and source paths.
- `replay/*.csv`: per-frame planned/actual release, selection, queue, start,
  finish, deadline, margin, source/history/display IDs and standard quality.
- `summary.csv`, `per_round_summary.csv`, `selections.csv`, `audit.json`:
  audited aggregates. `COMPLETE` is written only after expected run counts,
  fixed deadlines, temporal order and fallback identities pass.
- `figures/`: budget vs miss/quality/margin, fixed/dynamic trade-offs, timelines.
- `image_metric_audit.json`: independent NumPy recomputation from saved actual
  pixels, verifying standard errors, received-eye images and repeated frames.
- `transition_summary.csv`: configuration switch counts, longest miss streaks
  and absolute quality steps. Quality steps also contain scene motion and eye
  alternation; they are not an isolated measure of switching artifacts.
- Phase round 0 saves actual simulated stereo outputs: all frames for the
  primary controller and eight representative phase-boundary frames for Full,
  Half and the secondary controller. Readback and quality/image work are outside
  the live loop. They cannot cause a playback miss within a run.
- `paired_full.cu` and `paired_numba.py` implement a bounded matched Full
  comparison: identical four original frame-39 packets, resident inputs,
  20 warmups/50 repetitions, original kernels and matched scratch/debug writes.
  This control is separate from the coalesced-clear continuous experiment.
  `analyze_paired.py` checks saved output quality against source GT. It does not
  assume Numba and C++ outputs are bitwise identical.

  ```bash
  bash deadline_experiments/run_paired.sh NEW_CONTROL PACKET_DIRECTORY DATASET_ROOT /path/to/numba/python
  python deadline_experiments/analyze_paired.py NEW_CONTROL --data DATASET_ROOT
  ```

Do not run other GPU experiments concurrently with these trials. Do not reuse
old Full timing from another power mode, sample or timing boundary in a new plot.
