"""Small real-GPU Numba check: four Driving workloads, frame 39 only."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numba
import numpy as np
from numba import cuda
import benchmark_reconstruction_speed as speed
import benchmark_foveated_roi_speed as fov
from benchmark_reconstruction_speed import (
    CachedPNGIO, original_functions, source_wall_benchmark,
)
from benchmark_foveated_roi_speed import benchmark_one
from reproduce_quality import WORKLOADS, original_psnr, read_rgb


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--repeats', type=int, default=30)
    a = p.parse_args()
    if a.out.exists():
        p.error('Output already exists; choose a new file')
    if a.repeats < 5:
        p.error('At least five repeats required')
    if numba.config.ENABLE_CUDASIM or not cuda.is_available():
        raise RuntimeError('A real CUDA device is required')
    # Keep the existing timing routines, and retain their individual samples.
    original_stats = speed.stats
    def recorded_stats(values):
        return dict(original_stats(values), samples_ms=list(values))
    speed.stats = recorded_stats
    fov.stats = recorded_stats
    result = dict(platform=platform.platform(), numba=numba.__version__,
                  numpy=np.__version__, device=str(cuda.get_current_device().name),
                  compute_capability=cuda.get_current_device().compute_capability,
                  frame=39, repeats=a.repeats, workloads={})
    for key, relative in WORKLOADS.items():
        folder = (a.data_root / relative).resolve()
        source = folder / 'test_numba.py'
        io = CachedPNGIO(folder)
        scope = original_functions(source, io)
        row = dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        row['source_function'] = source_wall_benchmark(folder, scope, io, [39], a.repeats)
        gt = read_rgb(folder / 'right/0039.png')[:, :, ::-1].copy()
        row['last_source_output_legacy_psnr_db'] = float(original_psnr(source)(io.last_written, gt))
        row['fov_pilot'] = benchmark_one(folder, key, a.repeats)
        result['workloads'][key] = row
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(key, json.dumps(row), flush=True)
    print('COMPLETE: four workloads, one frame each', flush=True)


if __name__ == '__main__':
    main()
