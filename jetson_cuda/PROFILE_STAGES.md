# Reconstruction stage profiling

`profile_stages.cu` includes the unchanged `pirate_bench.cu` implementation and
uses exactly the same kernels, parameters, launch layouts and output buffers.
It adds timing boundaries, not a reconstruction optimization. No Graph or
cross-frame reuse is introduced.

```bash
nvcc -O3 -std=c++14 --fmad=false -arch=sm_72 profile_stages.cu -o profile_stages
./profile_stages --self-test
./profile_stages --manifest sample_manifest.txt --csv new_resident.csv \
  --roi-width 160 --roi-height 90 --warmup 10 --repeats 100 --fast-resample
./profile_stages --manifest sample_manifest.txt --csv new_stream.csv \
  --roi-width 160 --roi-height 90 --warmup 10 --repeats 100 --fast-resample --stream
```

Each CSV path must be new. Manifests accept absolute paths or paths relative to
the manifest. `--precomputed-base` and image dumps are rejected for this test.
The full, half-base and FOV modes rotate their execution order. Within each
mode/iteration, the reference and staged variants also alternate order. Warmup
counts apply separately to all six mode/variant combinations. There is no
inter-stage device synchronization. Event objects and output buffers are
allocated before warmup.

## Mapping to the paper

The supplied paper's Fig. 6 / Sec. 6.1 names Decoding, Intra-frame, Inter-frame,
and Composite and Filling. The following measured categories preserve those
reconstruction meanings:

| CSV stage | Meaning |
| --- | --- |
| `intra_frame` | Disparity-based pixel shifting |
| `inter_frame` | Optical-flow temporal reconstruction |
| `composite_fill` | Composition followed by remaining-hole filling |
| `clear` | Scratch initialization, separate from the paper's three reuse stages |
| `downsample` | Current full input to half-resolution input, FOV extension |
| `upsample` | Half-resolution reconstructed output to full output |
| `overlay` | Full-resolution ROI blending into the upsampled base |

The existing implementation runs inter-frame before intra-frame. The profiler
preserves that order. For FOV, reuse stages appear twice with `pass=base` and
`pass=roi`; sum corresponding stages when presenting a paper-style breakdown.
The half-base pass alone does not represent all of FOV reconstruction.

**Decoding is not measured.** The `.pir` packet already contains decoded arrays.
Do not add the paper's decoding time to these measurements or treat a missing
decode stage as zero. Disk reads, allocation, quality metrics, network transport,
video decoding and display are excluded from both variants.

## What the numbers mean

- `variant=reference` calls `Pipeline.run` with no events between its kernels.
  It still has the outer timeline/transfer events needed for this comparison.
- `variant=staged` inserts consecutive default-stream CUDA event boundaries.
  These can perturb scheduling. Compare the reference and staged **means** to
  report the observed profiling overhead. Do not silently equate stage totals
  with the previously measured uninstrumented executable.
- `stage=total` is the CUDA event span of the measured pipeline. The repeated
  `wall_total_ms` column is the CPU wall time from the first event submission to
  synchronization on the final event. Use only one `total` row per sample when
  aggregating wall time; the same value repeats on all stage rows for context.
- `stage=reconstruction` excludes the H2D/D2H event spans. In resident mode the
  input was uploaded before warmup, and there is no timed output download.
- Stream mode has `h2d` and `d2h` CUDA-event spans. They cover transfer commands
  and any event-timeline gaps in those segments, not network traffic. On Xavier
  the CPU and GPU share physical DRAM, but this implementation still uses
  explicit CUDA host/device memory copies.
- `h2d_api_wall_ms` and `d2h_api_wall_ms` are CPU time spent inside the copy APIs.
  In particular, the blocking D2H call can wait for preceding reconstruction.
  **Do not add these API wall values to GPU stages or call their sum isolated
  transfer cost.** `cpu_reconstruction_enqueue_ms` likewise measures CPU enqueue
  work, not completed GPU execution, and is not additive to GPU times.
- The staged reconstruction total equals the sum of detailed reconstruction
  stages plus `trace_boundary` (the small outer-to-inner boundary remainder),
  up to CUDA event floating-point precision. Stream GPU total equals H2D +
  reconstruction + D2H. These sums are accounting checks, not independent
  measurements of overhead. Tiny signed rounding residuals can occur.

The legacy PSNR function and non-atomic competing writes remain unchanged.
This profiler does not establish deterministic image equivalence. All printed
timing summaries use arithmetic means; the CSV retains individual samples.
