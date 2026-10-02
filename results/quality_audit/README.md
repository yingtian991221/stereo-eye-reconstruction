# PIRATE driving visual-quality audit (2026-09-28)

## Scope and sources

- Paper: `C:/Users/yingt/Downloads/PIRATE_Camera_ready (3).pdf`, Sections 4, 5.2–5.3, 6.3, Figure 9 and Table 1.
- Data and original scripts: `//YZ/2023fall1/driving__frames_cleanpass/frames_cleanpass`.
- Evaluation: driving forward scene at 15 mm and 35 mm focal lengths, 300 and 800 frame sequences. The folders `aaa` and `bbb` contain 300 and 800 source frames, respectively.
- The source folders were read only. No original code, including `calculate_psnr`, was changed.

## Comparison rule

The paper's Figure 9 compares quality at nominal 0.1 bpp. `preprocess.sh` produces HEVC frames at 5 Mbps per eye. The saved PIRATE variant uses the 8 Mbps input eye (`8_left`) and a reconstructed right eye (`8+1_cuda`). The paper assigns 0.02 bpp to disparity and optical flow. At 960 × 540 stereo and 90 FPS, the nominal budgets are approximately 0.107 bpp for 5+5 Mbps and 0.106 bpp for 8 Mbps plus 0.02 bpp side information. The 35 mm folders retain eye-view MP4 bitstreams: their file sizes imply 0.111/0.108 bpp for the two 5 Mbps HEVC streams (300/800 frames) and 0.088/0.086 bpp for the full 8 Mbps left-eye stream. Adding the paper's nominal 0.02 bpp side budget gives roughly 0.108/0.106 bpp, but the actual disparity/flow bitstreams and the final alternating-eye stream are unavailable. The 15 mm folders retain only lossless MP4s. Thus realized end-to-end bpp could not be verified.

For each available odd frame starting at 7, the audit pairs `5_left` and `5_right` with `left` and `right` ground truth, and `8_left` and `8+1_cuda` with the same ground truth. It loads the **original** `calculate_psnr` function from the original Python source AST and averages the two per-eye dB values, matching the source's arithmetic. The function computes `np.mean((image1 - image2) ** 2)` on `uint8` arrays. This reproduces the original overflow behavior; it is not a corrected PSNR calculation. RGB rather than BGR loading does not change the mean squared difference across the three channels.

## Recomputed PSNR from archived outputs

| Driving workload | Pairs measured | HEVC mean (dB) | PIRATE mean (dB) | PIRATE − HEVC (dB) |
| --- | ---: | ---: | ---: | ---: |
| 15 mm, 300 frames | 147 / 147 | 31.709 | 31.654 | −0.055 |
| 15 mm, 800 frames | 387 / 397 | 31.927 | 31.920 | −0.007 |
| 35 mm, 300 frames | 147 / 147 | 31.582 | 31.539 | −0.042 |
| 35 mm, 800 frames | 387 / 397 | 31.902 | 31.914 | +0.012 |

The 800-frame `8+1_cuda` outputs stop at frame 779. Frames 781–799 (odd IDs) are missing, so all methods were averaged on the same 387 matched frames. The exact per-frame scores and missing frame IDs are in `frames.csv` and `summary.json`.

The 15 mm, 300 frame folder also has a later `cuda_right` output, dated 2024-04-08, alongside `test_numba.py` from the same date. Its 147-frame PIRATE mean is **31.737 dB**, versus **31.709 dB** for HEVC, a **+0.028 dB** difference. The older `8+1_cuda` output is dated 2024-03-14, differs at the pixel level, and has no matching generator reference in the available source beyond the metric script. Its numbers should not be conflated with the later CUDA output. Details are in `cuda_right/summary.json`.

## Full replay of the available CUDA reconstruction path

The `test_numba.py` kernels and `generate_right` function were loaded directly from the original source AST and run over each script's **actual top-level loop range**, with a PNG I/O shim that preserves OpenCV's BGR channel order. The original code and data were read only. Generated images were scored in memory to avoid writing hundreds of megabytes of duplicate PNGs. This replay covers the right-eye reconstruction on odd frames and the corresponding directly encoded left eye; the source's `generate_left` function is not called by its top-level loop, so it does not reconstruct the full alternating sequence depicted in paper Figure 5.

| Driving workload | Frames | HEVC mean (dB) | Current CUDA PIRATE mean (dB) | PIRATE − HEVC (dB) |
| --- | ---: | ---: | ---: | ---: |
| 15 mm, 300 frames | 147 | 31.709 | 31.735 | +0.026 |
| 15 mm, 800 frames | 387 | 31.927 | 32.104 | +0.177 |
| 35 mm, 300 frames | 147 | 31.582 | 31.726 | +0.144 |
| 35 mm, 800 frames | 387 | 31.902 | 31.913 | +0.011 |

Per-frame values and source hashes are in `full_replay/<workload>/frames.csv` and `summary.json`. The 800-frame scripts explicitly stop at `range(5,780)`, explaining why their right-eye outputs end at frame 779. These modest PSNR gains support that the current kernels execute and produce reasonable images, but they do not establish the larger and broader visual-quality benefit claimed in the paper. In particular, no current-kernel MS-SSIM, CLIP, or LPIPS evaluation was run.

## Saved feature logs

The existing `featrures5.log` and `featrures8+1cuda.log` include CLIP, MS-SSIM, and LPIPS. Their PSNR entries were checked against decoded PNGs at the first and last two common frame IDs. The `5` log evaluates the right eye in three workloads, but the left eye in `driving_35_300`; that fourth log cannot be used for a same-eye feature comparison.

| Workload | Right-eye samples | HEVC MS-SSIM | PIRATE MS-SSIM | HEVC CLIP | PIRATE CLIP | HEVC LPIPS | PIRATE LPIPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 15 mm, 300 | 146 | 0.876 | 0.774 | 0.949 | 0.954 | 0.272 | 0.258 |
| 15 mm, 800 | 186 | 0.868 | 0.796 | 0.947 | 0.957 | 0.259 | 0.244 |
| 35 mm, 800 | 186 | 0.884 | 0.806 | 0.953 | 0.961 | 0.225 | 0.227 |

These are **existing log values**, not newly executed model evaluations, and cover one eye only. The log's MS-SSIM values are rounded to four decimal places. Their CLIP trend improves slightly, while MS-SSIM drops substantially; this does not establish the paper's full stereo result. Provenance details and all four workloads are in `saved_feature_logs.json`.

## CUDA replay check

`replay_cuda_frame.py` extracted the five CUDA kernels and `generate_right` directly from the original `test_numba.py` AST. It ran frame 7 twice on the local RTX 3080 Laptop GPU. Pillow supplied lossless PNG input/output in the same BGR channel order as OpenCV; unrelated Torch metric imports were omitted. The source and data stayed untouched, and output went to the local `replay/` and `replay2/` folders.

- Saved `cuda_right/0007.png`: 33.0272 dB under the original PSNR function.
- First replay: 33.0300 dB; second replay: 33.0283 dB.
- The two replays differ at 13,739 channel values out of 1,555,200, so the kernel result is not pixel deterministic.

The original source allocates CUDA arrays with `device_array` (lines 300–307), initializes only a few fixed positions in `init` (lines 175–192), and allows colliding writes in `left_to_right` without an atomic rule (lines 137–153). These are plausible causes of run-to-run variation; the replay alone does not isolate a single cause. No source fix was made.

`comparison_driving_15_300_frame0039.png` shows a ground-truth right eye, HEVC right eye, archived PIRATE right eye, and later CUDA right eye. Frame 39 is the median per-frame **stereo** PSNR difference in the 15 mm / 300 set, chosen before visual inspection. The labels show original-code right-eye PSNR.

## Conclusion and reproducibility limit

The saved driving output is sufficient to reproduce its own PSNR values with the original formula. The current CUDA path also executes across all four available driving workloads and shows **+0.011 to +0.177 dB** against HEVC under this approximate bitrate mapping. The result does not yet reproduce the full Figure 9 claim: there is no measured end-to-end bitrate, no complete alternating-eye output, and no fresh MS-SSIM, CLIP, or LPIPS evaluation. The side-information bitstreams, 15 mm lossy bitstreams, and a complete documented generator for the archived `8+1_cuda` outputs are missing; two 800-frame sets stop before frame 800. The CUDA output is not pixel deterministic. These gaps prevent a claim that the available codebase reproduces the published visual-quality result.

## Commands

Use the bundled Python with NumPy and Pillow for the image audit:

```powershell
& 'C:\Users\yingt\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\reproduce_quality.py
& 'C:\Users\yingt\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\audit_feature_logs.py
& 'C:\Users\yingt\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\make_comparison.py
```

The CUDA replay uses the locally installed Anaconda Python with Numba CUDA:

```powershell
$env:PYTHONIOENCODING='utf-8'
& 'C:\Users\yingt\anaconda3\python.exe' .\replay_cuda_frame.py --frame 7
& 'C:\Users\yingt\anaconda3\python.exe' .\replay_cuda_frame.py --workload driving_15_300 --all-frames --out results/quality_audit/full_replay/driving_15_300
```
