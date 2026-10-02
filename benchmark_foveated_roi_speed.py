"""Speed-only prototype: half-resolution base plus one full-resolution ROI.

The source kernels are loaded from the local copy of test_numba.py without
editing that file. ROI kernels keep output ownership within the selected ROI.
This pilot does not establish visual correctness or deadline performance.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
from numba import cuda

from benchmark_reconstruction_speed import (
    BLOCK,
    DEFAULT_LOCAL_ROOT,
    FRAME,
    device_buffers,
    launch_pipeline,
    load_frame,
    original_functions,
    stats,
)
from reproduce_quality import WORKLOADS


@cuda.jit
def temporal_roi(right, max_uv, min_uv, previous, flow, y0, x0):
    row, col = cuda.grid(2)
    roi_h, roi_w, _ = right.shape
    if row >= roi_h or col >= roi_w:
        return
    y = y0 + row
    x = x0 + col
    full_h, full_w, _ = previous.shape
    u, v = flow[y, x]
    u = round(float(u) / 65535 * (max_uv[0] - min_uv[0]) + min_uv[0])
    v = round(float(v) / 65535 * (max_uv[1] - min_uv[1]) + min_uv[1])
    sample_x = x + u
    sample_y = y + v
    if sample_y < 0 or sample_y >= full_h or sample_x < 0 or sample_x >= full_w:
        return
    for channel in range(3):
        right[row, col, channel] = previous[sample_y, sample_x, channel]


@cuda.jit
def disparity_roi(right1, max_d, left, depth, depth1, y0, x0, source_width):
    row, source_col = cuda.grid(2)
    roi_h, roi_w, _ = right1.shape
    if row >= roi_h or source_col >= source_width:
        return
    y = y0 + row
    x = x0 + source_col
    full_h, full_w, _ = left.shape
    if y >= full_h or x >= full_w:
        return
    disparity = round(depth[y, x] * max_d[0] / 65535)
    out_col = source_col - disparity
    if out_col < 0 or out_col >= roi_w:
        return
    # Same depth competition rule as the source kernel; its concurrent writes
    # remain a correctness limitation until the deterministic kernel is built.
    if depth1[row, out_col] == 0 or depth1[row, out_col] < depth[y, x]:
        for channel in range(3):
            right1[row, out_col, channel] = left[y, x, channel]
        depth1[row, out_col] = depth[y, x]


@cuda.jit
def overlay_roi(full, roi, y0, x0, pad, core_h, core_w, feather):
    row, col = cuda.grid(2)
    if row >= core_h or col >= core_w:
        return
    y = y0 + pad + row
    x = x0 + pad + col
    edge = min(row, col, core_h - 1 - row, core_w - 1 - col)
    weight = min(1.0, float(edge + 1) / feather)
    for channel in range(3):
        base = full[y, x, channel]
        detail = roi[row + pad, col + pad, channel]
        full[y, x, channel] = base * (1.0 - weight) + detail * weight + 0.5


def allocate_roi_buffers(core_h: int, core_w: int, pad: int) -> dict:
    h, w = core_h + 2 * pad, core_w + 2 * pad
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    mono = np.zeros((h, w), dtype=np.uint8)
    return {
        "right": cuda.to_device(rgb),
        "right1": cuda.to_device(rgb),
        "right2": cuda.to_device(rgb),
        "depth1": cuda.to_device(mono),
        "mask": cuda.to_device(mono),
        "mask1": cuda.to_device(rgb),
    }


def launch_roi(scope: dict, full: dict, destination, roi: dict, y0: int, x0: int, core_h: int, core_w: int, pad: int, feather: int, max_disparity: int):
    from benchmark_reconstruction_speed import clear_scratch

    roi_h, roi_w = roi["right"].shape[:2]
    grid = ((roi_h + 31) // 32, (roi_w + 31) // 32)
    source_width = min(full["left"].shape[1] - x0, roi_w + max_disparity)
    source_grid = ((roi_h + 31) // 32, (source_width + 31) // 32)
    core_grid = ((core_h + 31) // 32, (core_w + 31) // 32)
    clear_scratch[grid, BLOCK](roi["right"], roi["right1"], roi["right2"], roi["depth1"], roi["mask"], roi["mask1"])
    temporal_roi[grid, BLOCK](roi["right"], full["max_uv"], full["min_uv"], full["previous"], full["flow"], y0, x0)
    disparity_roi[source_grid, BLOCK](roi["right1"], full["max_d"], full["left"], full["depth"], roi["depth1"], y0, x0, source_width)
    scope["composite"][grid, BLOCK](roi["right"], roi["right1"], roi["mask"], roi["mask1"])
    scope["interpolate"][grid, BLOCK](roi["right1"], roi["right2"], roi["mask"])
    overlay_roi[core_grid, BLOCK](destination, roi["right2"], y0, x0, pad, core_h, core_w, feather)


def benchmark_one(folder: Path, workload: str, repeats: int) -> dict:
    scope = original_functions(folder / "test_numba.py")
    full_data = load_frame(folder, workload, FRAME, 1.0)
    half_data = load_frame(folder, workload, FRAME, 0.5)
    full_shape = full_data["left"].shape
    half = device_buffers(half_data, full_shape)
    full = device_buffers(full_data, full_shape)
    half_grid = ((half_data["left"].shape[0] + 31) // 32, (half_data["left"].shape[1] + 31) // 32)
    full_grid = ((full_shape[0] + 31) // 32, (full_shape[1] + 31) // 32)
    pad, feather = 3, 8
    disparity_bound = math.ceil(float(full_data["max_d"][0]))
    result = {"full_shape": list(full_shape), "max_disparity_pixels": disparity_bound, "rois": {}}

    def full_launch():
        launch_pipeline(scope, full, full_grid, full_grid, 1.0)

    def half_launch():
        launch_pipeline(scope, half, half_grid, full_grid, 0.5)

    variants = {"full": full_launch, "half_base": half_launch}
    roi_cases = {}
    for core_w, core_h in ((160, 90), (320, 180), (480, 270)):
        x0 = (full_shape[1] - core_w) // 2 - pad
        y0 = (full_shape[0] - core_h) // 2 - pad
        roi = allocate_roi_buffers(core_h, core_w, pad)

        def combined_launch(roi=roi, y0=y0, x0=x0, core_h=core_h, core_w=core_w):
            half_launch()
            launch_roi(scope, full, half["full"], roi, y0, x0, core_h, core_w, pad, feather, disparity_bound)

        label = f"{core_w}x{core_h}"
        variants[label] = combined_launch
        roi_cases[label] = (roi, y0, x0, core_h, core_w)
        result["rois"][label] = {"area_fraction": round(core_w * core_h / (full_shape[0] * full_shape[1]), 4)}

    for launch in variants.values():
        launch()
        cuda.synchronize()
    half_launch()
    cuda.synchronize()
    base_image = half["full"].copy_to_host()
    roi, y0, x0, core_h, core_w = roi_cases["320x180"]
    launch_roi(scope, full, half["full"], roi, y0, x0, core_h, core_w, pad, feather, disparity_bound)
    cuda.synchronize()
    with_roi = half["full"].copy_to_host()
    changed = np.any(base_image != with_roi, axis=2)
    inside = np.zeros(changed.shape, dtype=bool)
    inside[y0 + pad:y0 + pad + core_h, x0 + pad:x0 + pad + core_w] = True
    result["overlay_changed_inside_pixels"] = int(np.count_nonzero(changed & inside))
    result["overlay_changed_outside_pixels"] = int(np.count_nonzero(changed & ~inside))
    if result["overlay_changed_inside_pixels"] == 0 or result["overlay_changed_outside_pixels"] != 0:
        raise AssertionError("ROI overlay did not stay within its output region")
    samples = {label: [] for label in variants}
    labels = list(variants)
    for repeat in range(repeats):
        # Rotate method order so changing clocks/background work do not always
        # favor the same candidate.
        order = labels[repeat % len(labels):] + labels[:repeat % len(labels)]
        for label in order:
            start = time.perf_counter()
            variants[label]()
            cuda.synchronize()
            samples[label].append((time.perf_counter() - start) * 1000)
    result["full"] = stats(samples["full"])
    result["half_base"] = stats(samples["half_base"])
    for label in result["rois"]:
        result["rois"][label]["half_base_plus_roi"] = stats(samples[label])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DEFAULT_LOCAL_ROOT)
    parser.add_argument("--workload", choices=["all", *WORKLOADS], default="all")
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path("results/speed_baseline/foveated_roi_pilot.json"))
    args = parser.parse_args()
    if args.repeats < 5:
        raise ValueError("Use at least five repeats")
    keys = list(WORKLOADS) if args.workload == "all" else [args.workload]
    result = {"repeats": args.repeats, "data_root": str(args.data_root.resolve()), "frame": FRAME, "workloads": {}}
    for key in keys:
        print(f"Benchmarking ROI: {key}", flush=True)
        result["workloads"][key] = benchmark_one(args.data_root / WORKLOADS[key], key, args.repeats)
        row = result["workloads"][key]
        print(json.dumps({"full_ms": row["full"]["p50_ms"], "half_ms": row["half_base"]["p50_ms"], "base_plus_roi_ms": {name: value["half_base_plus_roi"]["p50_ms"] for name, value in row["rois"].items()}}), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved {args.out}", flush=True)


if __name__ == "__main__":
    main()
