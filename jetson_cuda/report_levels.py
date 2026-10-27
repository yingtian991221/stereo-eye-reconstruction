"""Aggregate a completed level sweep. Optional plot needs matplotlib on the host."""
import argparse
import csv
from pathlib import Path

import numpy as np

from evaluate_levels import write_csv


def read(path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--plot', action='store_true')
    a = p.parse_args()
    if not (a.run / 'COMPLETE').exists():
        p.error('run is incomplete')
    quality = read(a.run / 'quality.csv')
    times = read(a.run / 'timings.csv')
    levels = sorted({r['level'] for r in times}, key=lambda s: int(s.split('x')[0]))
    result = []
    for timing in sorted({r['timing'] for r in times}):
        for level in levels:
            baseline = [float(t['wall_ms']) for t in times
                        if (t['timing'], t['level'], t['mode']) == (timing, level, 'full')]
            for mode in ['full', 'half_base', 'fov']:
                ts = [t for t in times if (t['timing'], t['level'], t['mode']) == (timing, level, mode)]
                qs = [q for q in quality if (q['timing'], q['level'], q['mode']) == (timing, level, mode)]
                wall = [float(t['wall_ms']) for t in ts]
                row = dict(timing=timing, level=level, mode=mode, frames=len({t['frame'] for t in ts}),
                           wall_p50_ms=float(np.median(wall)), wall_p95_ms=float(np.percentile(wall, 95)),
                           wall_p99_ms=float(np.percentile(wall, 99)),
                           gpu_p50_ms=float(np.median([float(t['gpu_timeline_ms']) for t in ts])),
                           speedup_vs_full=float(np.median(baseline) / np.median(wall)))
                legacy = [float(q['legacy_whole_psnr_db']) for q in qs if q['region'] == 'whole']
                legacy_full = [float(q['legacy_whole_psnr_db']) for q in quality
                               if (q['timing'], q['level'], q['mode'], q['region']) ==
                               (timing, level, 'full', 'whole')]
                row['legacy_whole_psnr_db'] = float(np.mean(legacy))
                row['legacy_delta_vs_full_db'] = float(np.mean(legacy) - np.mean(legacy_full))
                for region in ['whole', 'fixed_center', 'fixed_periphery', 'level_roi', 'level_periphery']:
                    subset = [q for q in qs if q['region'] == region]
                    row[region + '_psnr_db'] = float(np.mean([float(q['standard_psnr_db']) for q in subset]))
                    row[region + '_delta_db'] = float(np.mean([float(q['delta_vs_full_db']) for q in subset]))
                result.append(row)
    write_csv(a.run / 'overview.csv', result)
    for row in result:
        if row['mode'] == 'fov':
            print('%s %-7s %.3f ms %.2fx delta whole/center %.3f/%.3f dB' %
                  (row['timing'], row['level'], row['wall_p50_ms'], row['speedup_vs_full'],
                   row['whole_delta_db'], row['fixed_center_delta_db']))
    if a.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
        for timing, marker in [('resident', 'o'), ('stream', 's')]:
            rows = [r for r in result if r['mode'] == 'fov' and r['timing'] == timing]
            if not rows:
                continue
            axes[0].plot([r['level'] for r in rows], [r['wall_p50_ms'] for r in rows], marker=marker, label=timing)
        rows = [r for r in result if r['mode'] == 'fov' and r['timing'] == 'resident']
        for region, label in [('whole', 'Whole image'), ('fixed_center', 'Fixed center 160x90'),
                              ('fixed_periphery', 'Fixed periphery')]:
            axes[1].plot([r['level'] for r in rows], [r[region + '_delta_db'] for r in rows], marker='o', label=label)
        axes[0].set_ylabel('Reconstruction wall p50 (ms)')
        axes[1].set_ylabel('Standard PSNR difference vs full (dB)')
        axes[1].axhline(0, color='gray', lw=0.8)
        for ax in axes:
            ax.set_xlabel('Full-resolution ROI (pixels)')
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
        fig.suptitle('FOV sweep: %d frames (right eye)' % len({t['frame'] for t in times}))
        fig.savefig(a.run / 'quality_speed.png', dpi=180)
        fig.savefig(a.run / 'quality_speed.svg')
        svg = a.run / 'quality_speed.svg'
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines()) + '\n', encoding='utf-8')
        plt.close(fig)


if __name__ == '__main__':
    main()
