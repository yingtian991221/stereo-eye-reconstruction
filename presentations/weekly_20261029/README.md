# Weekly research update — 2026-10-29

[Editable PowerPoint](weekly_20261029_english_final.pptx), 9 slides, entirely in English.

The deck follows the requested order: network jitter and remaining budget, reconstruction mechanism, and measured results. Diagrams use native shapes/text, tables remain editable, and the latency chart contains an embedded data workbook.

The main results come from `results/fov_levels_xavier_full_20261027/README.md`, `overview.csv`, and `summary.csv`. The Numba compatibility slide uses `results/numba_xavier_20261029/mode7_15w/result.json`: four workloads, frame 39 only, 100 repetitions per path. No 30W result is claimed.

The jitter diagram is schematic. Dynamic scheduling and deadline-miss improvements remain proposed work. The 90 FPS frame period, display deadline, and local reconstruction timing are distinguished. The original overflow PSNR is preserved, and the stereo-mean difference is explicitly conditional and derived.

## Rebuild

`build.mjs` uses the installed Artifact Tool runtime. Run from the repository root. Choose a new output name because the finalizer does not overwrite existing outputs:

```powershell
$env:PPTX_NAME = 'weekly_20261029_revision.pptx'
& 'C:/Users/yingt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' presentations/weekly_20261029/build.mjs
```

Private build artifacts, validation receipts, and slide previews are under `tmp/weekly_ppt_build/`. The final deck passed package, page-count, font, native-table, and embedded-chart/workbook checks. All nine slides were reimported from the final PPTX and visually reviewed. This does not claim testing inside Microsoft PowerPoint itself.
