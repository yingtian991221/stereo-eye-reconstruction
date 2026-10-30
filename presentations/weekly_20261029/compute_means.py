"""Compute slide arithmetic means from recorded timing samples, not medians."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'results/fov_levels_xavier_full_20261027/timings.csv'
groups = defaultdict(list)
with source.open(newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        groups[row['level'], row['timing'], row['mode']].append(float(row['wall_ms']))
assert len(groups) == 30
rows = []
for (level, timing, mode), samples in sorted(groups.items()):
    assert len(samples) == 5340
    width, height = map(int, level.split('x'))
    rows.append(dict(level=level, timing=timing, mode=mode, samples=len(samples),
                     region_percent=100 * width * height / (960 * 540),
                     wall_mean_ms=fmean(samples)))
numba = {}
for power in ['mode7_15w', 'mode5_30w']:
    record = json.loads((ROOT / 'results/numba_xavier_20261029' / power / 'result.json').read_text())
    numba[power] = {}
    for key, value in record['workloads'].items():
        fov = value['fov_pilot']
        measurements = {'full': fov['full'], **{k: v['half_base_plus_roi'] for k, v in fov['rois'].items()}}
        assert all(len(v['samples_ms']) == 100 for v in measurements.values())
        numba[power][key] = {k: fmean(v['samples_ms']) for k, v in measurements.items()}
result = dict(statistic='arithmetic mean of recorded wall_ms samples',
              timing_source=str(source.relative_to(ROOT)),
              timing_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
              cuda=rows, numba=numba)
Path(__file__).with_name('mean_timings.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
for r in rows:
    if r['timing'] == 'resident' and r['mode'] == 'fov':
        print(r['level'], r['region_percent'], r['wall_mean_ms'])
