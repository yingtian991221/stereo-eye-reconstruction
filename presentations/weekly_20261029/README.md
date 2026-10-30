# Weekly research update — 2026-10-29

[Latest editable PowerPoint](weekly_20261029_english_30w.pptx), 7 slides, entirely in English. The [alternate historical filename](weekly_20261029_english_final.pptx) now contains the identical current deck. Both are CUDA C++ only; the Numba slide has been removed. Prior Numba decks remain available through Git history.

The requested order is network jitter and remaining budget, reconstruction mechanism, then results. The approved jitter slide is unchanged. The simplified mechanism uses two equal 16:9 picture frames with centered 16:9 ROIs, a larger region for more time and a smaller region for less time. Diagrams use native editable shapes and text, tables remain editable, and slide 5 is a native stacked column chart with an embedded data workbook.

## Current results

The slides use the saved partial results in `results/fov_only_clear_partial_20261030/presentation_results.json`, not a completed full-dataset run. The experiment was stopped at the user’s request. No new GPU testing was performed to build this deck.

Four linear region-width scales are shown: 0.1×, 0.25×, 0.5× and 0.7× (96×54, 240×135, 480×270, 672×378). Timing uses the first 500 saved common frames, five measurements each, for 2500 GPU timing samples per level. Quality uses 672 saved common frames. These scopes are disclosed in the slides and notes.

The chart stacks measured GPU reconstruction means with a fixed 2 ms/frame decode budget. This budget is assumed, not measured end-to-end latency. The Full baseline is from the 0.25× configuration: 10.658 ms including the budget. FOV totals are 4.460, 4.890, 6.461 and 7.429 ms; the 0.25× ratio is 2.18×.

The quality table reports only positive stereo PSNR loss: 0.0979, 0.0904, 0.0712 and 0.0481 dB. Values use the original evaluation protocol and are derived assuming an unchanged left eye and arithmetic mean of the two per-eye PSNR values in dB. Underlying experimental records and previous full-run results remain unchanged.

The slides present empirical Full/FOV results without internal implementation details. Jitter remains schematic, and adaptive scheduling remains proposed. The approved jitter/mechanism layouts are unchanged; standalone scope and Numba pages remain removed.

## Rebuild

`build.mjs` uses the installed Artifact Tool runtime. Run from the repository root and choose a new filename because the finalizer does not overwrite existing output:

```powershell
$env:PPTX_NAME = 'weekly_20261029_revision.pptx'
& 'C:/Users/yingt/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' presentations/weekly_20261029/build.mjs
```

No Numba-specific environment variable is used. The builder reads committed JSON evidence directly; no dataset extraction is needed. `compute_means.py` and `mean_timings.json` are retained for the historical mean-based 15W/Numba deck calculations, but are no longer inputs to the current deck. To recompute those historical CUDA means, `timings.csv` is inside `results/fov_levels_xavier_full_20261027/evidence.tar.gz`. Raw reports and their original p50/p95 values remain unchanged.

Private backups, build artifacts, validation receipts and slide previews are under ignored `tmp/` directories. The final deck passed package, page-count, font, native-table and embedded-chart/workbook checks. All seven slides were reimported from the final PPTX and rendered for review. This does not claim testing inside Microsoft PowerPoint itself.
