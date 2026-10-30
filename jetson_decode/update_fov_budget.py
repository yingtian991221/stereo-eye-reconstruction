"""Add a fixed per-frame decode budget to measured FOV means without replacing measurements."""
import csv
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/fov_decode_budget_2ms_20261029'
LEVELS = ['80x46', '160x90', '320x180', '480x270', '640x360']
DECODE = 2.0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plot',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    means = json.loads((ROOT/'presentations/weekly_20261029/mean_timings.json').read_text())
    with (ROOT/'results/cu_breakdown_xavier_20261029/summary.csv').open(newline='') as f:
        stages = list(csv.DictReader(f))
    rows = []
    for r in means['cuda']:
        rows.append(dict(power_w=15, dataset='1068 valid forward odd frames', level=r['level'],
                         region_percent=r['region_percent'], mode=r['mode'], timing=r['timing'],
                         basis='wall', variant='original mean', reconstruction_mean_ms=r['wall_mean_ms']))
    for r in stages:
        if r['timing'] != 'resident': continue
        if r['variant'] == 'staged':
            basis, value = 'GPU timeline', float(r['reconstruction_mean_ms'])
        else:
            basis, value = 'wall', float(r['wall_mean_ms'])
        w,h=map(int,r['level'].split('x'))
        rows.append(dict(power_w=30,dataset='4 workloads, frame39 each',level=r['level'],region_percent=w*h/5184,
                         mode=r['mode'],timing='resident',basis=basis,variant=r['variant'], reconstruction_mean_ms=value))
    for r in rows:
        r['fixed_decode_budget_ms'] = DECODE
        r['decode_plus_reconstruction_ms'] = DECODE + r['reconstruction_mean_ms']
        baseline = next(b for b in rows if all(b[k]==r[k] for k in ['power_w','dataset','level','timing','basis','variant']) and b['mode']=='full')
        r['speedup_with_fixed_decode'] = (DECODE+baseline['reconstruction_mean_ms'])/r['decode_plus_reconstruction_ms']
    with (OUT/'summary.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    text='''# FOV timing：统一固定2ms解码预算

根据用户指定，所有档位按每帧一次 **2ms** 解码预算计算：`总时间 = 重建实测均值 + 2ms`。
2ms是统一预算假设，不是本次端到端实测，也不是RGB、depth、u、v各加2ms。多路联合解码及格式转换/互操作尚未联调。所有原始时间、质量数据与历史报告保留。

## CUDA C++ 30W：最近分段测试

四组各第39帧，每路径100次，表中重建值为staged GPU timeline均值，与上一轮breakdown一致。未包含额外CPU/GPU拷贝、网络与显示。Full取2.8%配置的配对基线。

| 区域 | 重建均值(ms) | 固定解码预算(ms) | 解码+重建(ms) |
| --- | ---: | ---: | ---: |
'''
    def select(power,level,mode='fov',basis='GPU timeline',timing='resident'):
        return next(r for r in rows if (r['power_w'],r['level'],r['mode'],r['basis'],r['timing'])==(power,level,mode,basis,timing))
    choices=[('Full',select(30,'160x90','full'))]+[(f'{select(30,l)["region_percent"]:.1f}%',select(30,l)) for l in LEVELS]
    for label,r in choices:
        text+=f'| {label} | {r["reconstruction_mean_ms"]:.3f} | 2.000 | {r["decode_plus_reconstruction_ms"]:.3f} |\n'
    text+='\n## CUDA C++ 15W：完整有效1068帧\n\n表中重建为resident墙钟均值，保留作完整覆盖的历史对照。当前PPT时间已改用上表30W小样本；质量仍来自15W完整1068帧，两组不能视为同一轮联合质量/时间测量。\n\n| 区域 | 重建均值(ms) | 解码+重建(ms) | 含输入输出拷贝再加解码预算(ms) |\n| --- | ---: | ---: | ---: |\n'
    for label,level,mode in [('Full','160x90','full')]+[(f'{select(15,l,basis="wall")["region_percent"]:.1f}%',l,'fov') for l in LEVELS]:
        r=select(15,level,mode,basis='wall');s=select(15,level,mode,basis='wall',timing='stream')
        text+=f'| {label} | {r["reconstruction_mean_ms"]:.3f} | {r["decode_plus_reconstruction_ms"]:.3f} | {s["decode_plus_reconstruction_ms"]:.3f} |\n'
    text+='''
固定解码预算加入Full与FOV两边，加速比也必须重新计算，不能沿用纯重建的比值。15W的2.8%档为6.770ms，相对同轮Full+decode约1.92×。

[30W原始分段报告](../cu_breakdown_xavier_20261029/README.md)、[15W完整范围报告](../fov_levels_xavier_full_20261027/README.md)、[实测解码实验](../hevc_decode_xavier_20261029/README.md)、[地图解码与精度实验](../map_decode_xavier_20261029/README.md)。
summary.csv同时保留重建原值、预算值、推导总时间及更新后的比值。各档位PSNR没有改变。
'''
    (OUT/'README.md').write_text(text,encoding='utf-8')
    if args.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(1,2,figsize=(12,5),constrained_layout=True)
        for ax,power,basis,title in zip(axes,[30,15],['GPU timeline','wall'],
                ['30W: GPU reconstruction timeline\n4 workloads, frame 39 each',
                 '15W: reconstruction wall time\n1068 valid forward odd frames']):
            selected=[select(power,'160x90','full',basis)]+[select(power,l,basis=basis) for l in LEVELS]
            labels=['Full']+[f'{r["region_percent"]:.1f}%' for r in selected[1:]]
            reconstruction=[r['reconstruction_mean_ms'] for r in selected]
            ax.bar(labels,reconstruction,label='Measured reconstruction',color='#086b93')
            ax.bar(labels,[DECODE]*6,bottom=reconstruction,label='Fixed decode budget',color='#d17b28')
            for i,r in enumerate(selected):
                ax.text(i,r['decode_plus_reconstruction_ms']+0.12,f'{r["decode_plus_reconstruction_ms"]:.3f}',ha='center',fontsize=9)
            ax.set_ylim(0,15);ax.set_title(title,fontsize=11)
            ax.set_ylabel('Reconstruction mean + fixed budget (ms)')
            ax.set_xlabel('Full-resolution region (% of image)')
            ax.grid(axis='y',alpha=0.2);ax.set_axisbelow(True)
        axes[0].legend(fontsize=8,loc='upper right')
        fig.suptitle('Fixed 2 ms decoding budget, added once per frame')
        fig.savefig(OUT/'budget_timing.png',dpi=180)
        fig.savefig(OUT/'budget_timing.svg')
        path=OUT/'budget_timing.svg'
        path.write_text('\n'.join(s.rstrip() for s in path.read_text().splitlines())+'\n')
        plt.close(fig)
        (OUT/'README.md').write_text(text+'\n![Timing with fixed decoding budget](budget_timing.svg)\n',encoding='utf-8')
    print('Updated',len(rows),'derived timing rows; original measurements preserved')


if __name__=='__main__': main()
