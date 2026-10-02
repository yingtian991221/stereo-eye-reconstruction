"""Speed pilot for the original PIRATE Numba kernels on local Driving inputs.

This is an engineering timing experiment, not a quality evaluation. The
original test_numba.py files and their PSNR function are not modified.
"""

from __future__ import annotations

import argparse
import ast
import copy
import functools
import hashlib
import json
import os
import time
from pathlib import Path

import numba
import numpy as np
from numba import cuda
from PIL import Image

from reproduce_quality import WORKLOADS
from replay_cuda_frame import KERNELS, PNGIO


DEFAULT_LOCAL_ROOT = Path(r"C:\Users\yingt\Datasets\PIRATE\driving_forward_speed")
BLOCK = (32, 32)
FRAME = 39
INPUTS = {
    "driving_15_300": ("8_left", "8_right", "gray_depth", "gray_u_past", "gray_v_past", 0),
    "driving_15_800": ("14_left", "14_right", "05_depth", "025_u_past", "025_v_past", -1),
    "driving_35_300": ("14_left", "14_right", "05_depth", "025_u_past", "025_v_past", 0),
    "driving_35_800": ("8_left", "8_right", "05_depth", "025_u_past", "025_v_past", -1),
}


class CachedPNGIO(PNGIO):
    """Exclude PNG decode and file writes from the source-function timing."""

    def __init__(self, source_dir: Path):
        super().__init__(source_dir, Path("."), save_images=False)
        self.cache: dict[tuple[str, int | None], np.ndarray] = {}

    def imread(self, filename: str, mode=None):
        key = (filename, mode)
        if key not in self.cache:
            self.cache[key] = super().imread(filename, mode)
        return self.cache[key]

    def imwrite(self, filename: str, array: np.ndarray):
        self.last_written = array
        return True


class TimingOnlyRewriter(ast.NodeTransformer):
    """Ablate unused copies/repeated scalar loads without editing source files."""

    def __init__(self, skip_debug_copies: bool, cache_parameters: bool):
        self.skip_debug_copies = skip_debug_copies
        self.cache_parameters = cache_parameters

    def visit_Assign(self, node: ast.Assign):
        if self.skip_debug_copies and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in {"holes", "mask1"}:
                return None
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        node = self.generic_visit(node)
        if self.cache_parameters and isinstance(node.func, ast.Attribute) and node.func.attr == "load":
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "np":
                node.func = ast.copy_location(ast.Name(id="cached_load", ctx=ast.Load()), node.func)
        return node


def original_functions(source: Path, io: PNGIO | None = None, *, skip_debug_copies: bool = False, cache_parameters: bool = False):
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [copy.deepcopy(node) for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in KERNELS]
    if {node.name for node in nodes} != KERNELS:
        raise ValueError(f"Missing original functions in {source}")
    if skip_debug_copies or cache_parameters:
        for index, node in enumerate(nodes):
            if node.name == "generate_right":
                nodes[index] = TimingOnlyRewriter(skip_debug_copies, cache_parameters).visit(node)
                break
    scope = {"np": np, "numba": numba, "cuda": cuda, "cv2": io, "cached_load": functools.lru_cache(maxsize=None)(np.load)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(source), "exec"), scope)
    return scope


def stats(values: list[float]) -> dict[str, float]:
    v = np.asarray(values, dtype=np.float64)
    return {
        "n": int(v.size),
        "p50_ms": round(float(np.percentile(v, 50)), 4),
        "p95_ms": round(float(np.percentile(v, 95)), 4),
        "p99_ms": round(float(np.percentile(v, 99)), 4),
        "min_ms": round(float(v.min()), 4),
        "max_ms": round(float(v.max()), 4),
    }


def source_wall_benchmark(folder: Path, scope: dict, io: CachedPNGIO, frames: list[int], rounds: int) -> dict:
    previous = Path.cwd()
    try:
        os.chdir(folder)
        # First pass compiles the kernels and fills the PNG cache.
        for frame in frames:
            scope["generate_right"](frame - 1, 0)
        cuda.synchronize()
        durations = []
        for _ in range(rounds):
            for frame in frames:
                start = time.perf_counter()
                scope["generate_right"](frame - 1, 0)
                cuda.synchronize()
                durations.append((time.perf_counter() - start) * 1000)
        return {"cached_source_wall": stats(durations), "cached_png_arrays": len(io.cache)}
    finally:
        os.chdir(previous)


def read_image(folder: Path, image_dir: str, number: int, unchanged: bool = False) -> np.ndarray:
    with Image.open(folder / image_dir / f"{number:04d}.png") as image:
        if unchanged:
            return np.asarray(image).copy()
        return np.asarray(image.convert("RGB"))[:, :, ::-1].copy()


def resize_nearest(array: np.ndarray, scale: float) -> np.ndarray:
    if scale == 1:
        return array
    height, width = array.shape[:2]
    shape = (round(width * scale), round(height * scale))
    return np.asarray(Image.fromarray(array).resize(shape, Image.Resampling.NEAREST)).copy()


def load_frame(folder: Path, workload: str, frame: int, scale: float) -> dict:
    left_dir, prev_dir, depth_dir, u_dir, v_dir, flow_offset = INPUTS[workload]
    left = resize_nearest(read_image(folder, left_dir, frame), scale)
    previous = resize_nearest(read_image(folder, prev_dir, frame - 1), scale)
    depth = resize_nearest(read_image(folder, depth_dir, frame, unchanged=True), scale)
    u = resize_nearest(read_image(folder, u_dir, frame + flow_offset, unchanged=True), scale)
    v = resize_nearest(read_image(folder, v_dir, frame + flow_offset, unchanged=True), scale)
    index = frame - 1
    return {
        "left": left,
        "previous": previous,
        "depth": depth,
        "flow": np.stack((u, v), axis=2),
        "max_d": np.array([np.load(folder / "max_array.npy")[index] * scale], dtype=np.float64),
        "max_uv": np.asarray(np.load(folder / "max_uv_past.npy")[index] * scale),
        "min_uv": np.asarray(np.load(folder / "min_uv_past.npy")[index] * scale),
    }


@cuda.jit
def bilinear_upsample(src, dst):
    row, col = cuda.grid(2)
    out_h, out_w, _ = dst.shape
    if row >= out_h or col >= out_w:
        return
    in_h, in_w, _ = src.shape
    y = (row + 0.5) * in_h / out_h - 0.5
    x = (col + 0.5) * in_w / out_w - 0.5
    y = max(0.0, min(float(in_h - 1), y))
    x = max(0.0, min(float(in_w - 1), x))
    y0 = int(y)
    x0 = int(x)
    y1 = min(y0 + 1, in_h - 1)
    x1 = min(x0 + 1, in_w - 1)
    dy = y - y0
    dx = x - x0
    for channel in range(3):
        top = src[y0, x0, channel] * (1 - dx) + src[y0, x1, channel] * dx
        bottom = src[y1, x0, channel] * (1 - dx) + src[y1, x1, channel] * dx
        dst[row, col, channel] = top * (1 - dy) + bottom * dy + 0.5


@cuda.jit
def clear_scratch(right, right1, right2, depth1, mask, mask1):
    row, col = cuda.grid(2)
    h, w, _ = right.shape
    if row >= h or col >= w:
        return
    depth1[row, col] = 0
    mask[row, col] = 0
    for channel in range(3):
        right[row, col, channel] = 0
        right1[row, col, channel] = 0
        right2[row, col, channel] = 0
        mask1[row, col, channel] = 0


def device_buffers(data: dict, full_shape: tuple[int, int, int]) -> dict:
    height, width, _ = data["left"].shape
    return {
        "right": cuda.to_device(np.zeros_like(data["left"])),
        "right1": cuda.to_device(np.zeros_like(data["left"])),
        "right2": cuda.to_device(np.zeros_like(data["left"])),
        "depth1": cuda.to_device(np.zeros((height, width), dtype=np.uint8)),
        "mask": cuda.to_device(np.zeros((height, width), dtype=np.uint8)),
        "mask1": cuda.to_device(np.zeros_like(data["left"])),
        "left": cuda.to_device(data["left"]),
        "previous": cuda.to_device(data["previous"]),
        "depth": cuda.to_device(data["depth"]),
        "flow": cuda.to_device(data["flow"]),
        "max_d": cuda.to_device(data["max_d"]),
        "max_uv": cuda.to_device(data["max_uv"]),
        "min_uv": cuda.to_device(data["min_uv"]),
        "full": cuda.device_array(full_shape, dtype=np.uint8),
    }


def launch_pipeline(scope: dict, b: dict, grid: tuple[int, int], up_grid: tuple[int, int], scale: float):
    # The source init kernel only clears a few pixels. This timing path uses a
    # full clear so repeated launches begin from the same scratch state.
    clear_scratch[grid, BLOCK](b["right"], b["right1"], b["right2"], b["depth1"], b["mask"], b["mask1"])
    scope["now_to_prev"][grid, BLOCK](b["right"], b["max_uv"], b["min_uv"], b["previous"], b["flow"])
    scope["left_to_right"][grid, BLOCK](b["right1"], b["max_d"], b["left"], b["depth"], b["depth1"])
    scope["composite"][grid, BLOCK](b["right"], b["right1"], b["mask"], b["mask1"])
    scope["interpolate"][grid, BLOCK](b["right1"], b["right2"], b["mask"])
    if scale < 1:
        bilinear_upsample[up_grid, BLOCK](b["right2"], b["full"])


def preloaded_benchmark(scope: dict, data: dict, full_shape: tuple[int, int, int], scale: float, repeats: int) -> dict:
    b = device_buffers(data, full_shape)
    h, w = data["left"].shape[:2]
    grid = ((h + 31) // 32, (w + 31) // 32)
    up_grid = ((full_shape[0] + 31) // 32, (full_shape[1] + 31) // 32)
    launch_pipeline(scope, b, grid, up_grid, scale)
    cuda.synchronize()
    wall, device = [], []
    for _ in range(repeats):
        cuda.synchronize()
        start_event = cuda.event(timing=True)
        end_event = cuda.event(timing=True)
        start_wall = time.perf_counter()
        start_event.record()
        launch_pipeline(scope, b, grid, up_grid, scale)
        end_event.record()
        end_event.synchronize()
        wall.append((time.perf_counter() - start_wall) * 1000)
        device.append(float(cuda.event_elapsed_time(start_event, end_event)))
    stages = [
        ("clear", lambda: clear_scratch[grid, BLOCK](b["right"], b["right1"], b["right2"], b["depth1"], b["mask"], b["mask1"])),
        ("temporal", lambda: scope["now_to_prev"][grid, BLOCK](b["right"], b["max_uv"], b["min_uv"], b["previous"], b["flow"])),
        ("disparity", lambda: scope["left_to_right"][grid, BLOCK](b["right1"], b["max_d"], b["left"], b["depth"], b["depth1"])),
        ("composite", lambda: scope["composite"][grid, BLOCK](b["right"], b["right1"], b["mask"], b["mask1"])),
        ("inpaint", lambda: scope["interpolate"][grid, BLOCK](b["right1"], b["right2"], b["mask"])),
    ]
    if scale < 1:
        stages.append(("upsample", lambda: bilinear_upsample[up_grid, BLOCK](b["right2"], b["full"])))
    stage_samples: dict[str, list[float]] = {name: [] for name, _ in stages}
    for _ in range(min(repeats, 20)):
        for name, launch in stages:
            start_event = cuda.event(timing=True)
            end_event = cuda.event(timing=True)
            start_event.record()
            launch()
            end_event.record()
            end_event.synchronize()
            stage_samples[name].append(float(cuda.event_elapsed_time(start_event, end_event)))
    return {
        "shape": [h, w],
        "host_launch_and_gpu": stats(wall),
        "gpu_timeline": stats(device),
        "stage_gpu": {name: stats(samples) for name, samples in stage_samples.items()},
        "note": "Inputs and output buffers are already on GPU. Full scratch clear and bilinear upsample are included. PNG decode, transfers, and display submission are excluded. Original warp kernels are unchanged and still have competing writes.",
    }


def preallocated_stream_benchmark(scope: dict, folder: Path, workload: str, frames: list[int], rounds: int) -> dict:
    """Time CPU-to-GPU uploads, kernels, and final download with reused buffers."""
    decoded = [load_frame(folder, workload, frame, 1.0) for frame in frames]
    first = decoded[0]
    shape = first["left"].shape
    b = device_buffers(first, shape)
    host_output = np.empty(shape, dtype=np.uint8)
    grid = ((shape[0] + 31) // 32, (shape[1] + 31) // 32)

    def run_one(data: dict):
        for name in ("left", "previous", "depth", "flow", "max_d", "max_uv", "min_uv"):
            b[name].copy_to_device(data[name])
        launch_pipeline(scope, b, grid, grid, 1.0)
        b["right2"].copy_to_host(host_output)
        cuda.synchronize()

    for data in decoded:
        run_one(data)
    durations = []
    for _ in range(rounds):
        for data in decoded:
            start = time.perf_counter()
            run_one(data)
            durations.append((time.perf_counter() - start) * 1000)
    return {
        "wall": stats(durations),
        "note": "Decoded input arrays and output buffer are in host memory; device buffers are reused. Includes uploads, full scratch clear, kernel launches, and final download. Excludes PNG decode and display submission.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DEFAULT_LOCAL_ROOT)
    parser.add_argument("--out", type=Path, default=Path("results/speed_baseline/summary.json"))
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--rounds", type=int, default=5, help="Repeated passes over 12 frames for wall-time percentiles")
    args = parser.parse_args()
    if not cuda.is_available():
        raise RuntimeError("Numba CUDA device unavailable")
    if args.repeats < 5:
        raise ValueError("Use at least five repeats")
    if args.rounds < 1:
        raise ValueError("Use at least one round")
    result = {
        "device": cuda.get_current_device().name.decode(errors="replace"),
        "numba": numba.__version__,
        "data_root": str(args.data_root.resolve()),
        "frame_for_scaled_pilot": FRAME,
        "repeats": args.repeats,
        "rounds": args.rounds,
        "workloads": {},
    }
    frames = [7, 19, 31, 39, 51, 63, 75, 87, 99, 111, 123, 135]
    for workload, relative in WORKLOADS.items():
        folder = args.data_root / relative
        source = folder / "test_numba.py"
        io = CachedPNGIO(folder)
        scope = original_functions(source, io)
        print(f"Benchmarking {workload}", flush=True)
        row = {
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "source_function": source_wall_benchmark(folder, scope, io, frames, args.rounds),
            "scaled_preloaded": {},
        }
        for label, flags in (
            ("no_debug_copies", {"skip_debug_copies": True}),
            ("no_debug_copies_cached_parameters", {"skip_debug_copies": True, "cache_parameters": True}),
        ):
            variant_io = CachedPNGIO(folder)
            variant_scope = original_functions(source, variant_io, **flags)
            row[label] = source_wall_benchmark(folder, variant_scope, variant_io, frames, args.rounds)
        row["preallocated_stream"] = preallocated_stream_benchmark(scope, folder, workload, frames, args.rounds)
        full_shape = read_image(folder, INPUTS[workload][0], FRAME).shape
        for scale in (1.0, 0.5, 0.25):
            data = load_frame(folder, workload, FRAME, scale)
            row["scaled_preloaded"][str(scale)] = preloaded_benchmark(scope, data, full_shape, scale, args.repeats)
        result["workloads"][workload] = row
        print(json.dumps({"workload": workload, "source_p50_ms": row["source_function"]["cached_source_wall"]["p50_ms"], "scales": {k: v["host_launch_and_gpu"]["p50_ms"] for k, v in row["scaled_preloaded"].items()}}), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved {args.out}", flush=True)


if __name__ == "__main__":
    main()
