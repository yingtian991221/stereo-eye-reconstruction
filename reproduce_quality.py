"""Audit the saved Driving images using PIRATE's unmodified PSNR function.

The original code and data under the network share are read only. The image
selection follows the 0.1-bpp comparison suggested by preprocess.sh:
two 5-Mbps HEVC eyes versus one 8-Mbps eye and a reconstructed partner.
The additional 0.02-bpp map/flow budget comes from paper Section 4.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


DEFAULT_ROOT = Path(r"\\YZ\2023fall1\driving__frames_cleanpass\frames_cleanpass")
WORKLOADS = {
    "driving_15_300": "15mm_focallength/scene_forwards/aaa",
    "driving_15_800": "15mm_focallength/scene_forwards/bbb",
    "driving_35_300": "35mm_focallength/scene_forwards/aaa",
    "driving_35_800": "35mm_focallength/scene_forwards/bbb",
}


def original_psnr(source: Path):
    """Load the function AST directly, without importing heavy source dependencies."""
    body = ast.parse(source.read_text(encoding="utf-8")).body
    matches = [node for node in body if isinstance(node, ast.FunctionDef) and node.name == "calculate_psnr"]
    if len(matches) != 1:
        raise ValueError(f"Expected one calculate_psnr in {source}")
    code = compile(ast.fix_missing_locations(ast.Module(body=matches, type_ignores=[])), str(source), "exec")
    scope = {"np": np}
    exec(code, scope)
    return scope["calculate_psnr"]


def read_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"))


def measure(root: Path, workload: str, limit: int | None, pirate_right_dir: str):
    folder = root / WORKLOADS[workload]
    source = next(
        (path for path in (folder / "generate_left_and_right.py", folder / "test_numba.py") if path.is_file()),
        None,
    )
    if source is None:
        raise FileNotFoundError(f"No original PSNR function found in {folder}")
    metric = original_psnr(source)
    n = int(workload[-3:])
    frame_ids = list(range(7, n + 1, 2))
    if limit:
        frame_ids = frame_ids[:limit]
    rows = []
    missing = []
    for frame in frame_ids:
        name = f"{frame:04d}.png"
        paths = {
            "left_gt": folder / "left" / name,
            "right_gt": folder / "right" / name,
            "hevc_left": folder / "5_left" / name,
            "hevc_right": folder / "5_right" / name,
            "pirate_left": folder / "8_left" / name,
            "pirate_right": folder / pirate_right_dir / name,
        }
        absent = [key for key, path in paths.items() if not path.is_file()]
        if absent:
            missing.append({"frame": frame, "files": absent})
            continue
        images = {key: read_rgb(path) for key, path in paths.items()}
        shapes = {value.shape for value in images.values()}
        if len(shapes) != 1:
            missing.append({"frame": frame, "shape_mismatch": {key: list(value.shape) for key, value in images.items()}})
            continue
        psnr = {
            "hevc_left": float(metric(images["hevc_left"], images["left_gt"])),
            "hevc_right": float(metric(images["hevc_right"], images["right_gt"])),
            "pirate_left": float(metric(images["pirate_left"], images["left_gt"])),
            "pirate_right": float(metric(images["pirate_right"], images["right_gt"])),
        }
        rows.append({
            "workload": workload,
            "frame": frame,
            **psnr,
            "hevc_mean": (psnr["hevc_left"] + psnr["hevc_right"]) / 2,
            "pirate_mean": (psnr["pirate_left"] + psnr["pirate_right"]) / 2,
        })
    summary = {
        "workload": workload,
        "requested_frames": len(frame_ids),
        "measured_frames": len(rows),
        "missing": missing,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "directory": str(folder),
        "pirate_right_dir": pirate_right_dir,
    }
    if rows:
        for key in ("hevc_left", "hevc_right", "pirate_left", "pirate_right", "hevc_mean", "pirate_mean"):
            summary[key] = float(np.mean([row[key] for row in rows]))
        summary["pirate_minus_hevc_db"] = summary["pirate_mean"] - summary["hevc_mean"]
    return rows, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--workloads", nargs="+", choices=WORKLOADS, default=list(WORKLOADS))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pirate-right-dir", default="8+1_cuda")
    parser.add_argument("--out", type=Path, default=Path("results/quality_audit"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    all_rows, summaries = [], []
    for workload in args.workloads:
        rows, summary = measure(args.root, workload, args.limit, args.pirate_right_dir)
        all_rows.extend(rows)
        summaries.append(summary)
        print(json.dumps({key: value for key, value in summary.items() if key not in ("missing", "source", "source_sha256", "directory")}, ensure_ascii=False), flush=True)
    with (args.out / "frames.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["workload", "frame", "hevc_left", "hevc_right", "pirate_left", "pirate_right", "hevc_mean", "pirate_mean"])
        writer.writeheader()
        writer.writerows(all_rows)
    (args.out / "summary.json").write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
