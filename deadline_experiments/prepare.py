"""Freeze profiles and release schedules before seeing evaluation results."""
import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from pathlib import Path

NAMES = ['Full', 'Half', 'FOV_0.1', 'FOV_0.25', 'FOV_0.5', 'FOV_0.7']


def write_csv(p, rows):
    with p.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def select(estimates, budget, quality='whole_score'):
    feasible = [r for r in estimates if r['cost_ms'] <= budget]
    return (max(feasible, key=lambda r: (r[quality], -r['cost_ms'])) if feasible
            else min(estimates, key=lambda r: r['cost_ms']))['config']


def prepare(profile, out, count=96, start=39):
    out.mkdir(parents=True, exist_ok=False)
    rows = list(csv.DictReader(profile.open()))
    estimates, details = [], []
    for name in NAMES:
        group = [r for r in rows if r['config'] == name]
        t = [float(r['wall_ms']) for r in group]
        whole = [float(r['stereo_mse']) for r in group]
        center = [float(r['center_mse']) for r in group]
        # This formula is fixed before testing, not fitted per condition.
        cost = statistics.mean(t) + 2*statistics.stdev(t) + .2
        score = lambda x: 10*math.log10(65025/statistics.mean(x))
        estimates.append(dict(config=name, cost_ms=cost, whole_score=score(whole), center_score=score(center)))
        details.append(dict(config=name, samples=len(t), mean_ms=statistics.mean(t), std_ms=statistics.stdev(t),
                            whole_psnr_from_mean_mse=score(whole), center_psnr_from_mean_mse=score(center)))
    write_csv(out/'estimates.csv', estimates)
    write_csv(out/'profile_summary.csv', details)
    fast = min(r['cost_ms'] for r in estimates)
    full = estimates[0]['cost_ms']
    normal, mild, severe = 1.2*full, (fast+full)/2, .5*fast
    budgets = [-.5, .5*fast, .9*fast, 1.1*fast, mild, .95*full, normal]
    plans = []
    def add(name, values):
        last = -math.inf
        for i, b in enumerate(values):
            # 90 Hz playback; 20 ms model latency offset, 1 ms reserved for
            # submission. Neither is claimed to be a measured display delay.
            deadline = i*(1000/90)+19
            release = deadline-b
            if release < last:
                raise ValueError('Profile too slow for this release family; use a larger-period configuration')
            plans.append(dict(scenario=name, frame=start+i, release_ms=release, deadline_ms=deadline))
            last = release
    for i,b in enumerate(budgets): add('budget_%02d'%i, [b]*count)
    add('phase', [normal if i<count//4 or i>=3*count//4 else mild if i<count//2 else severe for i in range(count)])
    add('burst', [severe if i%32 in range(12,18) else normal for i in range(count)])
    rng = random.Random(20261104)
    add('seeded', [rng.uniform(.25*fast, normal) for _ in range(count)])
    write_csv(out/'release_plan.csv', plans)
    write_csv(out/'release_plan_generous.csv', [dict(scenario='budget_07', frame=start+i,
              release_ms=i*(1000/90),deadline_ms=i*(1000/90)+19) for i in range(count)])
    config = dict(fps=90, period_ms=1000/90, display_model_offset_ms=20, submission_reserve_ms=1,
                  reconstruction_deadline_offset_ms=19, decode_measured=False, network_measured=False,
                  boundary='decoded arrays resident on GPU; host producer release before reconstruction input binding',
                  count=count, first_frame=start, profiles_frames=sorted({int(r['frame']) for r in rows}),
                  timing_estimator='independent mean + 2 sample standard deviations + 0.2 ms',
                  policies=NAMES+['Dynamic_whole','Dynamic_center'], rounds=3,
                  quality='float64 MSE, 255 peak, pooled across both actual eyes; fixed 0.25x center and 8px boundary band',
                  quality_order='independent profile pooled-MSE score, never ROI-size order',
                  primary_policy='Dynamic_whole', secondary_policy='Dynamic_center (predeclared fixed central-region objective)',
                  fixed_budgets_ms=budgets, phase_budgets_ms=[normal,mild,severe,normal], random_seed=20261104,
                  queue='FIFO; skip reconstruction if already expired; update received-eye state even if skipped',
                  late_output='discard for display and reconstructed-history state; hold last accepted stereo pair',
                  history='strict alternation; prior target-eye image is previous received decoded eye, never GT',
                  fallback='attempt least-cost config when time positive but none predicted feasible; otherwise reuse',
                  profile_sha256=hashlib.sha256(profile.read_bytes()).hexdigest(),
                  release_sha256=hashlib.sha256((out/'release_plan.csv').read_bytes()).hexdigest())
    config['supplemental_control'] = '19 ms budget; full modeled readiness-to-completion allowance, separate plan'
    (out/'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    return config


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('profile',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--count',type=int,default=96);p.add_argument('--start',type=int,default=39)
    a=p.parse_args();print(json.dumps(prepare(a.profile,a.out,a.count,a.start),indent=2))
