"""Paired old/fast-clear timing pilot; both Full and FOV receive the same option."""
import argparse
import csv
import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from statistics import fmean


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    binary=a.binary.resolve();manifest=a.manifest.resolve()
    a.out.mkdir(parents=True,exist_ok=False);raw=a.out/'raw';raw.mkdir()
    metadata=dict(binary=str(binary),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  manifest=str(manifest),manifest_contents=manifest.read_text(),warmup=10,repeats=100,
                  variant_order=['original','fast','fast','original'],fast_resample=True,
                  timing='resident',frames='four Driving workloads, frame39 each',decode_budget_ms=2)
    (a.out/'metadata.json').write_text(json.dumps(metadata,indent=2))
    with (a.out/'self_test.log').open('w') as f:
        subprocess.run([str(binary),'--self-test'],stdout=f,stderr=subprocess.STDOUT,check=True)
    groups=defaultdict(list); quality=[]
    for level in ['96x54','240x135','480x270']:
        w,h=level.split('x')
        for block,variant in enumerate(metadata['variant_order']):
            tag=f'{level}_{block}_{variant}'
            cmd=[str(binary),'--manifest',str(manifest),'--roi-width',w,'--roi-height',h,
                 '--warmup','10','--repeats','100','--fast-resample','--csv',str(raw/(tag+'.csv'))]
            if variant=='fast': cmd.append('--fast-clear')
            with (raw/(tag+'.log')).open('w') as f:
                f.write(json.dumps(cmd)+'\n');f.flush()
                subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
            with (raw/(tag+'.csv')).open(newline='') as f: rows=list(csv.DictReader(f))
            assert len(rows)==1200
            keys={(r['frame'],r['mode'],int(r['iteration'])) for r in rows}
            assert len(keys)==1200
            frames={r['frame'] for r in rows}
            assert frames=={f'driving_{g}_0039.pir' for g in ['15_300','15_800','35_300','35_800']}
            for r in rows:
                assert r['fast_clear']==str(int(variant=='fast'))
                assert r['fast_resample']=='1'
                groups[level,variant,r['mode']].append(r)
                if r['iteration']=='0':
                    quality.append(dict(level=level,block=block,variant=variant,frame=r['frame'],mode=r['mode'],
                                        last_output_legacy_psnr_db=r['legacy_right_psnr_db']))
            print(tag,'COMPLETE',flush=True)
    summary=[]
    for (level,variant,mode),rows in groups.items():
        assert len(rows)==800
        gpu=fmean(float(r['gpu_timeline_ms']) for r in rows)
        wall=fmean(float(r['wall_ms']) for r in rows)
        summary.append(dict(level=level,variant=variant,mode=mode,samples=800,gpu_mean_ms=gpu,
                            wall_mean_ms=wall,total_gpu_with_decode_ms=gpu+2))
    for name,rows in [('summary.csv',summary),('quality_observations.csv',quality)]:
        with (a.out/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (a.out/'COMPLETE').write_text('Paired ABBA fast-clear pilot completed\n')


if __name__=='__main__':main()
