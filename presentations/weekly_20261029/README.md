# Weekly research update — 2026-10-29

[Latest editable PowerPoint](weekly_20261029_english_30w.pptx), 7 slides, entirely in English. The [alternate historical filename](weekly_20261029_english_final.pptx) now contains the identical current deck. Both are CUDA C++ only; the Numba slide has been removed. Prior Numba decks remain available through Git history.

The requested order is network jitter and remaining budget, reconstruction mechanism, then results. The approved jitter slide is unchanged. The simplified mechanism uses two equal 16:9 picture frames with centered 16:9 ROIs, a larger region for more time and a smaller region for less time. Diagrams use native editable shapes and text, tables remain editable, and slide 5 is a native stacked column chart with an embedded data workbook.

## Current timing and quality sources

Both timing and quality now use the same complete 30W CUDA C++ run over 1068 supported forward odd frames, with four region-width scales: 0.1×, 0.25×, 0.5× and 0.75×. These correspond to 96×54, 240×135, 480×270 and 720×405 pixels within the 960×540 output. Base sampling remains 0.5× in each dimension; ROI pixels remain full-resolution. All scale labels on pages 4–6 use linear width scale, not area fraction.

The builder reads `results/fov_scales_full_20261029/scale_results.json`. Each configuration has 3 warmups and 5 timing samples per frame, plus one quality output per frame (5340 timing samples and 1068 quality outputs). The chart uses resident whole-pipeline GPU event means without internal stage markers, not wall time. This timing protocol differs from the prior small-sample staged experiment. Clocks remain dynamic and fast resampling is enabled. Copies, allocation, disk I/O, network, decoding and display are excluded.

The chart stacks measured reconstruction with one fixed 2 ms decoding budget per frame. This is a budget assumption, not measured end-to-end latency or measured joint RGB/depth/flow decoding. Full uses the baseline paired with the 0.25× configuration: 10.882 ms including decode. FOV totals are 5.631, 6.257, 8.158 and 11.039 ms. The 0.25× ratio is 1.74×; 0.75× is slightly slower than Full. No optimal-Full baseline claim is made.

Original overflow PSNR and conditional derived stereo-mean differences are preserved. The four legacy right-eye differences are −0.1718, −0.1569, −0.1198 and −0.0669 dB. Their conditional stereo-mean differences are −0.0859, −0.0785, −0.0599 and −0.0335 dB. This complete run supersedes the mixed 30W four-frame timing / 15W quality presentation; older experimental records remain intact.

The jitter diagram is schematic. Dynamic scheduling and deadline-miss improvement remain proposed work; the 90 FPS frame period is not an established end-to-end deadline. The standalone measurement-scope slide and Numba slide remain removed.

## Rebuild

`build.mjs` uses the installed Artifact Tool runtime. Run from the repository root and choose a new filename because the finalizer does not overwrite existing output:

```powershell
$env:PPTX_NAME = 'weekly_20261029_revision.pptx'
& 'C:/Users/yingt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' presentations/weekly_20261029/build.mjs
```

No Numba-specific environment variable is used. The builder reads committed JSON evidence directly; no dataset extraction is needed. `compute_means.py` and `mean_timings.json` are retained for the historical mean-based 15W/Numba deck calculations, but are no longer inputs to the current deck. To recompute those historical CUDA means, `timings.csv` is inside `results/fov_levels_xavier_full_20261027/evidence.tar.gz`. Raw reports and their original p50/p95 values remain unchanged.

Private backups, build artifacts, validation receipts and slide previews are under ignored `tmp/` directories. The final deck passed package, page-count, font, native-table and embedded-chart/workbook checks. All seven slides were reimported from the final PPTX and rendered for review. This does not claim testing inside Microsoft PowerPoint itself.
