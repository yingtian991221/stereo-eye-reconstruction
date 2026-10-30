# Numba on Xavier: small real-GPU test

This runner tests the existing Numba implementation on four Driving workloads,
frame 39 only. It does not replace the complete 1068-frame CUDA C++ evaluation.
Original `test_numba.py` kernels and the overflow-preserving PSNR function are
loaded directly from their AST; unrelated Torch/torchmetrics imports are skipped.

## Environment

Use an isolated environment on the tested Python 3.8 / aarch64 platform:

```bash
python3 -m venv ~/venvs/stereo-numba
~/venvs/stereo-numba/bin/python -m pip install --only-binary=:all: --no-cache-dir \
  numba==0.58.1 llvmlite==0.41.1 numpy==1.24.4 Pillow==10.4.0
```

The CUDA runtime alone is insufficient for Numba JIT. Set `CUDA_HOME` to a
complete CUDA 11.4 toolkit with NVVM, libdevice, and ptxas. On our board the
existing extracted toolkit is used by `run_smoke.sh`; no system CUDA or system
Python packages are changed.

The extracted toolkit initially had a dangling `lib64/libcudart.so` link.
Numba detected the GPU but JIT failed with `No supported GPU compute
capabilities found`. The missing `libcudart.so.11.0` target was linked to the
board's existing `/usr/local/cuda-11.4/targets/aarch64-linux/lib/libcudart.so.11.4.298`.
This repaired runtime discovery without replacing the driver or patching Numba.

```bash
bash jetson_numba/run_smoke.sh \
  --data-root /home/yingtian/stereo-numba-20261029/data \
  --out /home/yingtian/stereo-numba-20261029/results/new_run.json \
  --repeats 30
```

For a 100-repeat run with power-mode metadata and 200 ms tegrastats logging:

```bash
bash jetson_numba/capture_smoke.sh /absolute/path/new_output /absolute/path/data
```

The capture script does not change power mode. On this AGX Xavier, mode 7 is
15W Desktop and mode 5 is 30W 4CORE; switch only between completed tests using
`sudo nvpmodel -m 5`. Verify the configuration on other boards before reusing IDs.

`--data-root` uses the original `15mm_focallength/scene_forwards/aaa` etc.
directory layout. Each workload needs its original `test_numba.py`, parameter
NPY files, and input PNG files for frames 38/39. Real CUDA is required; simulator
mode is rejected. The output file must not exist. JSON is checkpointed after
each workload; only the final `COMPLETE` log line confirms all four finished.

## Timing interpretation

- `source_function`: original `generate_right`, with PNG reads cached and image
  saves suppressed. Includes allocation, parameter-file reads, transfers,
  intermediate debug downloads, kernel launches and synchronization. A first
  untimed call fills the cache and compiles the kernels.
- `fov_pilot`: existing `benchmark_foveated_roi_speed.py`, GPU-resident buffers,
  full scratch clearing, full / half-base / three ROI sizes. Includes Python
  launch overhead and synchronization; excludes allocation, transfers, disk and
  JIT. Each variant has an untimed warmup and timing order rotates.
- This Numba prototype uses the original bilinear upsampler, not the CUDA C++
  `--fast-resample` optimization. A timing difference against that optimized C++
  result cannot be attributed to the language alone.
- Original initialization limitations and non-atomic competing writes remain.
  The last source output's legacy PSNR is a smoke-test observation, not a
  full-dataset quality measurement. No original PSNR formula is changed.
