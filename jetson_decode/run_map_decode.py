"""Run map/control clips sequentially on one Jetson hardware decoder."""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--videos', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    records = json.loads((a.videos / 'encoding.json').read_text())
    assert len(records) == 28
    script_dir = Path(__file__).resolve().parent
    outcomes = []
    for r in records:
        for kind, script in [('serial', 'gst_decode_latency.py'), ('throughput', 'gst_decode_throughput.py')]:
            cmd = [sys.executable, str(script_dir/script), '--input', str((a.videos/(r['name']+'.mp4')).resolve()),
                   '--outdir', str(a.out/(r['name']+'_'+kind)), '--expected-frames', str(r['frames']),
                   '--repeats', '3', '--max-performance']
            with (a.out/(r['name']+'_'+kind+'.log')).open('w') as f:
                proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
            outcomes.append(dict(name=r['name'], kind=kind, exit_code=proc.returncode))
            (a.out/'outcomes.json').write_text(json.dumps(outcomes, indent=2))
        print(r['name'], 'ATTEMPTED', flush=True)
    failures = sum(x['exit_code'] != 0 for x in outcomes)
    (a.out/'COMPLETE').write_text('28 clips attempted; %d failed tests (see outcomes.json)\n' % failures)


if __name__ == '__main__':
    main()
