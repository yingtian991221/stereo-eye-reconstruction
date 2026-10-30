# Weekly research update — 2026-10-29

[Latest editable PowerPoint](weekly_20261029_english_30w.pptx), 8 slides, entirely in English. The [alternate historical filename](weekly_20261029_english_final.pptx) now contains the identical current deck. Both are CUDA C++ only; the Numba slide has been removed. Prior Numba decks remain available through Git history.

The requested order is network jitter and remaining budget, reconstruction mechanism, then results. The approved jitter and simplified mechanism slides are unchanged. Diagrams use native editable shapes and text, tables remain editable, and slide 6 is a native stacked column chart with an embedded data workbook.

## Current timing and quality sources

Timing is the latest CUDA C++ staged reconstruction experiment at Xavier 30W 4CORE (mode 5), with unlocked clocks: four Driving workloads, frame 39 in each, 10 warmups and 100 repetitions per path. Slide 6 reads `results/fov_decode_budget_2ms_20261029/summary.csv`, selecting 30W, resident, staged GPU-timeline means. The raw experiment is documented in `results/cu_breakdown_xavier_20261029/README.md`. These values are GPU event timeline means, not wall time. Input/output copies, allocation, disk I/O, network, decoding and display are excluded.

The chart stacks measured reconstruction with one fixed 2 ms decoding budget per frame. This constant is defined once as `DECODE_BUDGET_MS=2` in `build.mjs`; it is a budget assumption, not measured end-to-end latency or measured joint RGB/depth/flow decoding. Full uses the baseline paired with the 2.8% configuration. Full plus decode is 9.996 ms; the 2.8% FOV total is 5.462 ms, or 1.83× faster by the ratio of derived totals. Savings include reduced clearing work; this is not an optimal-Full baseline claim.

Quality remains the earlier 15W CUDA C++ experiment over 1068 supported forward odd frames, using `results/fov_levels_xavier_full_20261027/overview.csv`. Original overflow PSNR and the conditional derived stereo-mean difference are unchanged. Slides 5 and 7 visibly distinguish the two experimental cohorts. The displayed quality and timing columns are not jointly measured pairs, and quality equivalence was not revalidated in the 30W experiment.

The jitter diagram is schematic. Dynamic scheduling and deadline-miss improvement remain proposed work; the 90 FPS frame period is not an established end-to-end deadline.

## Rebuild

`build.mjs` uses the installed Artifact Tool runtime. Run from the repository root and choose a new filename because the finalizer does not overwrite existing output:

```powershell
$env:PPTX_NAME = 'weekly_20261029_revision.pptx'
& 'C:/Users/yingt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' presentations/weekly_20261029/build.mjs
```

No Numba-specific environment variable is used. The builder reads committed CSV evidence directly; no dataset extraction is needed. `compute_means.py` and `mean_timings.json` are retained for the historical mean-based 15W/Numba deck calculations, but are no longer inputs to the current deck. To recompute those historical CUDA means, `timings.csv` is inside `results/fov_levels_xavier_full_20261027/evidence.tar.gz`. Raw reports and their original p50/p95 values remain unchanged.

Private backups, build artifacts, validation receipts and slide previews are under ignored `tmp/` directories. The final deck passed package, page-count, font, native-table and embedded-chart/workbook checks. All eight slides were reimported from the final PPTX and rendered for review. This does not claim testing inside Microsoft PowerPoint itself.
