# Retained cold-start diagnostic — not the main comparison

This directory contains the first complete, measured 264-trial run. It is
preserved without replacing its raw logs, plans, profile or source archive.
Use `../deadline_readiness_xavier_20261104_warm/` for the uniformly warmed repeat.

The initial replay warmup ran only six reconstructions. CPU quality processing
between trials allowed the GPU to downclock; the following trial could start
before clocks recovered. In `clock_diagnostic.csv`, the first Full frame took
19.50 ms wall / 18.51 ms GPU, starting at 114.75 MHz; GPU time settled near
5.30 ms after the clock rose to 828.75 MHz. This strongly affected initial
misses and policy order, so these results do not establish controller benefits.

The repeat uses the same one-second sustained warmup for every strategy and
records the pretrial GPU frequency. Its profiling uses the same 90Hz cadence
and defers metrics until after each clip. The mean + 2 SD + 0.2ms estimator,
quality objectives, release-plan construction rules, evaluation frames and
late-output handling are unchanged. New profiles/plans are frozen before the
repeat. No power mode or clock limit is changed.

The matched original Numba/C++ control in `paired_cpp`, `paired_numba` and
`paired_summary.csv` is a separate resident, back-to-back benchmark with its
own 20 warmups and 50 repetitions. It remains useful as a bounded compatibility
check; it is not combined with the continuous playback timing.

`source_snapshot.tar.gz` preserves the source used for this original run.
`COMPLETE` confirms log/protocol completeness, not suitability as the warmed
headline result. Its figures and video show actual measured cold-start output.
