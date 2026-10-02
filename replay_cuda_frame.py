"""Replay one original PIRATE CUDA reconstruction frame, reading source data only.

The original CUDA functions are compiled directly from their source AST.
Pillow supplies only the cv2 PNG read/write interface, so the large Torch and
torchmetrics imports used by unrelated quality code are unnecessary here.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
from pathlib import Path

import numba
import numpy as np
from numba import cuda
from PIL import Image

from reproduce_quality import DEFAULT_ROOT, WORKLOADS, original_psnr, read_rgb


KERNELS = {"init", "now_to_prev", "left_to_right", "composite", "interpolate", "generate_right"}


class PNGIO:
    IMREAD_UNCHANGED = -1

    def __init__(self, source_dir: Path, output_dir: Path, save_images: bool = True):
        self.source_dir = source_dir
        self.output_dir = output_dir
        self.save_images = save_images
        self.last_written = None

    def imread(self, filename: str, mode=None):
        path = self.source_dir / filename
        with Image.open(path) as image:
            if mode == self.IMREAD_UNCHANGED:
                return np.array(image)
            return np.array(image.convert("RGB"))[:, :, ::-1].copy()

    def imwrite(self, filename: str, array: np.ndarray):
        self.last_written = array.copy()
        if not self.save_images:
            return True
        path = self.output_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(array[:, :, ::-1]).save(path)
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", choices=WORKLOADS, default="driving_15_300")
    parser.add_argument("--frame", type=int, default=7, help="Odd output frame number")
    parser.add_argument("--all-frames", action="store_true", help="Run the original top-level frame range")
    parser.add_argument("--count", type=int, default=None, help="Optional pilot size for --all-frames")
    parser.add_argument("--out", type=Path, default=Path("results/quality_audit/replay"))
    args = parser.parse_args()
    if args.frame % 2 != 1 or args.frame < 7:
        raise ValueError("Use an odd frame >= 7")
    if not cuda.is_available():
        raise RuntimeError("Numba CUDA device unavailable")
    folder = DEFAULT_ROOT / WORKLOADS[args.workload]
    source = folder / "test_numba.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in KERNELS]
    if {node.name for node in nodes} != KERNELS:
        raise ValueError("Could not find all original CUDA functions")
    output_dir = args.out.resolve()
    io = PNGIO(folder, output_dir, save_images=not args.all_frames)
    namespace = {"np": np, "numba": numba, "cuda": cuda, "cv2": io}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(source), "exec"), namespace)
    original_dir = Path.cwd()
    try:
        os.chdir(folder)
        if args.all_frames:
            loops = [node for node in tree.body if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "i" and isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range"]
            if len(loops) != 1:
                raise ValueError("Could not identify original top-level frame range")
            stop = ast.literal_eval(loops[0].iter.args[1])
            frames = list(range(7, stop + 1, 2))
            if args.count:
                frames = frames[:args.count]
            metric = original_psnr(source)
            rows = []
            for frame in frames:
                namespace["generate_right"](frame - 1, 0)
                name = f"{frame:04d}.png"
                right_gt = io.imread(f"right/{name}")
                left_gt = io.imread(f"left/{name}")
                values = {
                    "frame": frame,
                    "hevc_left": float(metric(io.imread(f"5_left/{name}"), left_gt)),
                    "hevc_right": float(metric(io.imread(f"5_right/{name}"), right_gt)),
                    "pirate_left": float(metric(io.imread(f"8_left/{name}"), left_gt)),
                    "pirate_right": float(metric(io.last_written, right_gt)),
                }
                values["hevc_mean"] = (values["hevc_left"] + values["hevc_right"]) / 2
                values["pirate_mean"] = (values["pirate_left"] + values["pirate_right"]) / 2
                rows.append(values)
                if len(rows) % 50 == 0:
                    print(f"{args.workload}: {len(rows)}/{len(frames)}", flush=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            with (output_dir / "frames.csv").open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            summary = {"workload": args.workload, "frames": len(rows), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
            for key in ("hevc_left", "hevc_right", "pirate_left", "pirate_right", "hevc_mean", "pirate_mean"):
                summary[key] = float(np.mean([row[key] for row in rows]))
            summary["pirate_minus_hevc_db"] = summary["pirate_mean"] - summary["hevc_mean"]
            (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps(summary), flush=True)
            return
        namespace["generate_right"](args.frame - 1, 0)
    finally:
        os.chdir(original_dir)
    filename = f"{args.frame:04d}.png"
    replay_path = output_dir / "cuda_right" / filename
    saved_path = folder / "cuda_right" / filename
    replayed = read_rgb(replay_path)
    metric = original_psnr(source)
    print("source_sha256", hashlib.sha256(source.read_bytes()).hexdigest())
    print("replay_path", replay_path.resolve())
    print("replay_psnr", float(metric(replayed, read_rgb(folder / "right" / filename))))
    if saved_path.is_file():
        saved = read_rgb(saved_path)
        print("saved_psnr", float(metric(saved, read_rgb(folder / "right" / filename))))
        print("pixel_equal_to_saved", bool(np.array_equal(replayed, saved)))
        print("mismatched_channel_values", int(np.count_nonzero(replayed != saved)))


if __name__ == "__main__":
    main()
