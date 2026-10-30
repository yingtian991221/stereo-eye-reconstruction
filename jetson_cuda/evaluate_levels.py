"""Paired right-eye quality/timing sweep. Requires only NumPy and Pillow.

Each invocation retains its raw timing CSV and log. Quality uses the actual
last timed output (not a second reconstruction). Metric work and PNG/PPM I/O
are outside the CUDA program's timing interval. Never overwrites a run folder.
"""
import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path, rows):
    if not rows:
        return
    exists = path.exists()
    with path.open('a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def rectangle(w, h, rw, rh):
    mask = np.zeros((h, w), dtype=bool)
    x, y = w // 2 - rw // 2, h // 2 - rh // 2
    mask[y:y + rh, x:x + rw] = True
    return mask


def metrics(out, gt, mask):
    # Supplemental metric only: original CUDA legacyPSNR is unchanged.
    delta = out[mask].astype(np.float64) - gt[mask].astype(np.float64)
    mse = float(np.mean(delta * delta))
    psnr = float('inf') if mse == 0 else float(10 * np.log10(255.0 ** 2 / mse))
    return mse, psnr


def region_metrics(images, gt, regions):
    # Compute each pixel's error once; avoid repeatedly converting whole images
    # on the board's CPU. This work remains outside all reconstruction timers.
    result = {}
    reference = gt.astype(np.float64)
    for mode, image in images.items():
        delta = image.astype(np.float64) - reference
        error = np.mean(delta * delta, axis=2)
        for region, mask in regions.items():
            mse = float(np.mean(error[mask]))
            score = float('inf') if mse == 0 else float(10 * np.log10(255.0 ** 2 / mse))
            result[mode, region] = (mse, score)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--levels', default='96x54,240x135,480x270,720x405')
    parser.add_argument('--timing', choices=['resident', 'stream', 'both'], default='both')
    parser.add_argument('--repeats', type=int, default=100)
    parser.add_argument('--warmup', type=int, default=10)
    parser.add_argument('--quality-runs', type=int, default=3,
                        help='Independent runs to expose nondeterministic output variation')
    parser.add_argument('--fixed-region', default='160x90')
    parser.add_argument('--keep-images', action='store_true')
    parser.add_argument('--batch-frames', action='store_true', help='One CUDA process per level/run; retain per-frame warmups and timing')
    parser.add_argument('--batch-size', type=int, help='Bound frames per CUDA process and temporary image disk usage')
    parser.add_argument('--fast-resample', action='store_true', help='Use byte-exact FP32 2x resampling')
    parser.add_argument('--fast-clear', action='store_true', help='Clear the same scratch bytes with contiguous stores')
    args = parser.parse_args()
    if args.batch_size is not None and args.batch_size < 1:
        parser.error('--batch-size must be positive')
    levels = [tuple(map(int, s.split('x'))) for s in args.levels.split(',')]
    fixed = tuple(map(int, args.fixed_region.split('x')))
    if any(len(v) != 2 or min(v) < 1 for v in levels + [fixed]):
        parser.error('regions must be positive WIDTHxHEIGHT')
    if len(set(levels)) != len(levels) or min(args.repeats, args.warmup, args.quality_runs) < 1:
        parser.error('levels must be unique; counts must be positive')
    binary = args.binary.resolve(strict=True)
    manifest = args.manifest.resolve(strict=True)
    packets = [(manifest.parent / s.strip()).resolve(strict=True)
               for s in manifest.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
    if not packets or len(set(packets)) != len(packets):
        parser.error('manifest must contain unique frames')
    # Validate all inputs before starting any benchmark.
    packet_info = []
    for packet in packets:
        raw = packet.read_bytes()
        magic, w, h = struct.unpack_from('<8sII', raw)
        if magic != b'PIRFRM1\0' or len(raw) != 56 + 15 * w * h:
            raise ValueError('Invalid packet: ' + str(packet))
        if any(rw + 6 > w or rh + 6 > h for rw, rh in levels) or fixed[0] >= w or fixed[1] >= h:
            raise ValueError('Regions do not fit ' + str(packet))
        packet_info.append(dict(file=str(packet), sha256=hashlib.sha256(raw).hexdigest(), width=w, height=h))
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'raw').mkdir()
    meta = dict(created_utc=datetime.now(timezone.utc).isoformat(), platform=platform.platform(),
                binary=str(binary), binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                packets=packet_info, quality_scope='right eye vs GT; last timed output per independent run')
    source = Path(__file__).with_name('pirate_bench.cu')
    if source.exists():
        meta['cuda_source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    for label, command in [('git', ['git', 'rev-parse', 'HEAD']),
                           ('power', ['nvpmodel', '-q']), ('clocks', ['jetson_clocks', '--show']),
                           ('cuda', ['nvcc', '--version']), ('gpu', ['nvidia-smi'])]:
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    universal_newlines=True, timeout=15)
            meta[label] = result.stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            meta[label] = str(exc)
    release = Path('/etc/nv_tegra_release')
    if release.exists():
        meta['l4t'] = release.read_text()
    gpu_clock = Path('/sys/devices/17000000.gv11b/devfreq/17000000.gv11b')
    meta['gpu_clock_at_start'] = {}
    for name in ['cur_freq', 'min_freq', 'max_freq', 'governor']:
        try:
            meta['gpu_clock_at_start'][name] = (gpu_clock / name).read_text().strip()
        except OSError:
            pass
    (args.out / 'metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    telemetry = None
    telemetry_file = None
    quality, times = [], []
    try:
        if shutil.which('tegrastats'):
            telemetry_file = (args.out / 'tegrastats.log').open('w')
            telemetry = subprocess.Popen(['tegrastats', '--interval', '1000'],
                                         stdout=telemetry_file, stderr=subprocess.STDOUT)
        with (args.out / 'self_test.log').open('w') as log:
            subprocess.run([str(binary), '--self-test'], stdout=log, stderr=subprocess.STDOUT, check=True)
        timings = ['resident', 'stream'] if args.timing == 'both' else [args.timing]
        jobs = [list(zip(packets, packet_info))] if args.batch_frames else [[v] for v in zip(packets, packet_info)]
        if args.batch_size is not None:
            pairs = list(zip(packets, packet_info))
            jobs = [pairs[i:i + args.batch_size] for i in range(0, len(pairs), args.batch_size)]
        for ji, job in enumerate(jobs):
            input_args = ['--manifest', str(manifest)] if args.batch_frames else ['--input', str(job[0][0])]
            if args.batch_size is not None:
                batch_manifest = args.out / 'raw' / ('input_%04d.txt' % ji)
                batch_manifest.write_text(''.join(os.path.relpath(str(packet), str(batch_manifest.parent.resolve())) + '\n'
                                                  for packet, _ in job), encoding='utf-8')
                input_args = ['--manifest', str(batch_manifest.resolve())]
            for run in range(args.quality_runs):
                order = (ji + run) % len(levels)
                for rw, rh in levels[order:] + levels[:order]:
                    level = '%dx%d' % (rw, rh)
                    for timing in timings:
                        quality_start, times_start = len(quality), len(times)
                        tag = '%04d_%s_%s_r%d' % (ji, level, timing, run)
                        prefix = args.out / 'raw' / tag
                        timing_csv = Path(str(prefix) + '.csv')
                        cmd = [str(binary)] + input_args + ['--roi-width', str(rw), '--roi-height', str(rh),
                               '--warmup', str(args.warmup), '--repeats', str(args.repeats),
                               '--csv', str(timing_csv), '--dump-prefix', str(prefix)]
                        if timing == 'stream':
                            cmd.append('--stream')
                        if args.fast_resample:
                            cmd.append('--fast-resample')
                        if args.fast_clear:
                            cmd.append('--fast-clear')
                        with Path(str(prefix) + '.log').open('w') as log:
                            log.write(json.dumps(cmd) + '\n')
                            log.flush()
                            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
                        with timing_csv.open(newline='') as f:
                            rows = list(csv.DictReader(f))
                        for fi, (packet, info) in enumerate(job):
                            w, h = info['width'], info['height']
                            gt = np.frombuffer(packet.read_bytes(), dtype=np.uint8, offset=56 + 12 * w * h).reshape(h, w, 3)[:, :, ::-1]
                            workload = packet.stem.rsplit('_', 1)[0]
                            roi = rectangle(w, h, rw, rh)
                            fixed_roi = rectangle(w, h, *fixed)
                            regions = dict(whole=np.ones((h, w), dtype=bool), fixed_center=fixed_roi,
                                           fixed_periphery=~fixed_roi, level_roi=roi, level_periphery=~roi)
                            images = {}
                            for mode in ('full', 'half_base', 'fov'):
                                image_path = Path(str(prefix) + '_%d_%s.ppm' % (fi, mode))
                                with Image.open(image_path) as im:
                                    images[mode] = np.array(im)
                            scores = region_metrics(images, gt, regions)
                            for mode in images:
                                selected = [r for r in rows if r['mode'] == mode and r['frame'] == packet.name]
                                if len(selected) != args.repeats:
                                    raise ValueError('Timing rows do not match requested frame/repeats')
                                base = dict(workload=workload, frame=packet.name, level=level,
                                            roi_area_fraction=rw * rh / float(w * h), timing=timing, run=run, mode=mode)
                                for r in selected:
                                    times.append(dict(base, iteration=int(r['iteration']), wall_ms=float(r['wall_ms']),
                                                      gpu_timeline_ms=float(r['gpu_timeline_ms'])))
                                legacy = float(selected[0]['legacy_right_psnr_db'])
                                for region, mask in regions.items():
                                    mse, psnr = scores[mode, region]
                                    _, full_psnr = scores['full', region]
                                    quality.append(dict(base, region=region, pixels=int(mask.sum()), mse=mse,
                                                        standard_psnr_db=psnr,
                                                        delta_vs_full_db=0.0 if psnr == full_psnr else psnr-full_psnr,
                                                        legacy_whole_psnr_db=legacy))
                            if not args.keep_images:
                                for mode in images:
                                    Path(str(prefix) + '_%d_%s.ppm' % (fi, mode)).unlink()
                        print(tag, 'OK (%d frames)' % len(job), flush=True)
                        append_csv(args.out / 'quality.csv', quality[quality_start:])
                        append_csv(args.out / 'timings.csv', times[times_start:])
        groups = defaultdict(list)
        time_groups = defaultdict(list)
        for t in times:
            time_groups[(t['workload'], t['level'], t['timing'], t['mode'])].append(t)
        for q in quality:
            groups[(q['workload'], q['level'], q['timing'], q['mode'], q['region'])].append(q)
        summary = []
        for (workload, level, timing, mode, region), qs in sorted(groups.items()):
            ts = time_groups[workload, level, timing, mode]
            bs = time_groups[workload, level, timing, 'full']
            wall = [t['wall_ms'] for t in ts]
            summary.append(dict(workload=workload, level=level, timing=timing, mode=mode, region=region,
                                frames=len(set(q['frame'] for q in qs)), quality_samples=len(qs),
                                mean_standard_psnr_db=float(np.mean([q['standard_psnr_db'] for q in qs])),
                                mean_delta_vs_full_db=float(np.mean([q['delta_vs_full_db'] for q in qs])),
                                mean_legacy_whole_psnr_db=float(np.mean([q['legacy_whole_psnr_db'] for q in qs])),
                                wall_mean_ms=float(np.mean(wall)),
                                gpu_mean_ms=float(np.mean([t['gpu_timeline_ms'] for t in ts])),
                                speedup_vs_full_mean=float(np.mean([t['wall_ms'] for t in bs]) / np.mean(wall))))
        write_csv(args.out / 'summary.csv', summary)
        (args.out / 'COMPLETE').write_text('All requested frames, levels and timings completed.\n')
    finally:
        if telemetry is not None:
            telemetry.terminate()
            telemetry.wait(timeout=10)
        if telemetry_file is not None:
            telemetry_file.close()


if __name__ == '__main__':
    main()
