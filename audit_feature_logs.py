"""Summarize saved, right-eye feature logs after checking their PSNR provenance."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from reproduce_quality import DEFAULT_ROOT, WORKLOADS, original_psnr, read_rgb


PATTERN = re.compile(
    r"^(?P<frame>\d+)\s+CLIP: (?P<clip>[\d.]+) .*? "
    r"MSSSIM: tensor\((?P<ms_ssim>[\d.]+)\) "
    r"PSNR: (?P<psnr>[\d.]+) LPIPS: (?P<lpips>[\d.]+)"
)


def load_log(path: Path):
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PATTERN.search(line)
        if match:
            item = match.groupdict()
            frame = int(item.pop("frame"))
            rows[frame] = {key: float(value) for key, value in item.items()}
    return rows


def main():
    output = []
    for workload, subdir in WORKLOADS.items():
        folder = DEFAULT_ROOT / subdir
        source = next(path for path in (folder / "generate_left_and_right.py", folder / "test_numba.py") if path.is_file())
        metric = original_psnr(source)
        baseline = load_log(folder / "featrures5.log")
        pirate = load_log(folder / "featrures8+1cuda.log")
        common = sorted(baseline.keys() & pirate.keys())
        probes = {}
        for label, log, dirname, ground_truth in (
            ("hevc_left", baseline, "5_left", "left"),
            ("hevc_right", baseline, "5_right", "right"),
            ("pirate_right", pirate, "8+1_cuda", "right"),
        ):
            errors = []
            for frame in (common[:2] + common[-2:]):
                number = f"{frame:04d}.png"
                actual = float(metric(read_rgb(folder / dirname / number), read_rgb(folder / ground_truth / number)))
                errors.append(abs(actual - log[frame]["psnr"]))
            probes[label] = max(errors)
        baseline_eye = "right" if probes["hevc_right"] < 1e-10 else "left" if probes["hevc_left"] < 1e-10 else "unverified"
        item = {
            "workload": workload,
            "baseline_log_count": len(baseline),
            "pirate_log_count": len(pirate),
            "matched_frames": len(common),
            "psnr_probe_max_abs_error": probes,
            "baseline_log_eye": baseline_eye,
            "same_eye_comparison": baseline_eye == "right" and probes["pirate_right"] < 1e-10,
        }
        baseline_name = f"hevc_{baseline_eye}"
        for name, rows in ((baseline_name, baseline), ("pirate_right", pirate)):
            item[name] = {key: float(np.mean([rows[frame][key] for frame in common])) for key in ("psnr", "ms_ssim", "clip", "lpips")}
        if item["same_eye_comparison"]:
            item["pirate_minus_hevc"] = {key: item["pirate_right"][key] - item[baseline_name][key] for key in ("psnr", "ms_ssim", "clip", "lpips")}
        output.append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)
    out = Path("results/quality_audit/saved_feature_logs.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
