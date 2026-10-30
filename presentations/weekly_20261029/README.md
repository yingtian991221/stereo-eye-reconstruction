# Weekly research update — 2026-10-29

[Latest editable PowerPoint, including 30W](weekly_20261029_english_30w.pptx), 9 slides, entirely in English. The [earlier 15W-only version](weekly_20261029_english_final.pptx) is preserved.

The deck follows the requested order: network jitter and remaining budget, reconstruction mechanism, and measured results. Diagrams use native shapes/text, tables remain editable, and the latency chart contains an embedded data workbook.

The main results come from `results/fov_levels_xavier_full_20261027/README.md`, `overview.csv`, and `summary.csv`, and remain the full supported 1068-frame CUDA C++ evaluation at 15W. Slide 8 compares Numba at 15W Desktop (mode 7) and 30W 4CORE (mode 5), using `results/numba_xavier_20261029/mode7_15w/result.json` and `mode5_30w/result.json`. This is a small-sample comparison: four workloads, frame 39 only, 100 repetitions per path, with dynamic clocks. The 30W mode raises the GPU cap but lowers the CPU cap relative to 15W Desktop. The Numba and optimized CUDA C++ upsamplers differ.

The jitter diagram is schematic. Dynamic scheduling and deadline-miss improvements remain proposed work. The 90 FPS frame period, display deadline, and local reconstruction timing are distinguished. The original overflow PSNR is preserved, and the stereo-mean difference is explicitly conditional and derived.

## Rebuild

`build.mjs` uses the installed Artifact Tool runtime. Run from the repository root. Choose a new output name because the finalizer does not overwrite existing outputs:

```powershell
$env:PPTX_NAME = 'weekly_20261029_revision.pptx'
$env:NUMBA30_RESULT = 'results/numba_xavier_20261029/mode5_30w/result.json'
& 'C:/Users/yingt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' presentations/weekly_20261029/build.mjs
```

Omit `NUMBA30_RESULT` to rebuild the 15W-only version.

Private build artifacts, validation receipts, and slide previews are under `tmp/weekly_ppt_build/`. The final deck passed package, page-count, font, native-table, and embedded-chart/workbook checks. All nine slides were reimported from the final PPTX and visually reviewed. This does not claim testing inside Microsoft PowerPoint itself.
