"""Audit and summarize the paired clear-layout optimization pilot."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);a=p.parse_args()
    root=a.root;assert (root/'COMPLETE').exists()
    groups=defaultdict(list)
    for file in (root/'raw').glob('*.csv'):
        level,block,variant=file.stem.split('_')
        assert variant==['original','fast','fast','original'][int(block)]
        rows=list(csv.DictReader(file.open(newline='')))
        assert len(rows)==1200
        assert len({(r['frame'],r['mode'],r['iteration']) for r in rows})==1200
        for r in rows:
            assert r['fast_clear']==str(int(variant=='fast')) and r['fast_resample']=='1'
            groups[level,variant,r['mode']].append(r)
    assert len(groups)==18 and all(len(v)==800 for v in groups.values())
    summary=list(csv.DictReader((root/'summary.csv').open(newline='')))
    for r in summary:
        values=groups[r['level'],r['variant'],r['mode']]
        for field,col in [('gpu_mean_ms','gpu_timeline_ms'),('wall_mean_ms','wall_ms')]:
            assert abs(fmean(float(x[col]) for x in values)-float(r[field]))<1e-9
    get=lambda l,v,m:next(r for r in summary if (r['level'],r['variant'],r['mode'])==(l,v,m))
    text='''# 连续访存清零：Xavier FOV 加速试测

2026-10-29，CUDA C++，Xavier30W。只改变清零kernel的线程到字节映射；Full、half-base和FOV均应用相同开关。旧路径为默认，优化通过`--fast-clear`显式启用。fast-resample在两边均开启。每次仍完整清零全部五个工作缓冲区，没有跨帧复用RGB、特征或跳过清零；无Graph改动。

## 结果（算术平均）

四组Driving各第39帧，三档线性区域比例。按旧/新/新/旧（ABBA）顺序跑独立进程，每帧预热10次、计时100次；每档每模式每种实现合计800条样本。下面是GPU重建均值加每帧固定2ms解码预算；不含额外输入输出拷贝。

| 路径 | 旧清零，总时间(ms) | 连续访存清零，总时间(ms) | 总时间降低 | 相对同样优化的Full加速 |
| --- | ---: | ---: | ---: | ---: |
'''
    for label,level,mode in [('Full','240x135','full'),('FOV 0.1×','96x54','fov'),('FOV 0.25×','240x135','fov'),('FOV 0.5×','480x270','fov')]:
        old=float(get(level,'original',mode)['gpu_mean_ms'])+2
        new=float(get(level,'fast',mode)['gpu_mean_ms'])+2
        full=float(get(level,'fast','full')['gpu_mean_ms'])+2
        text+=f'| {label} | {old:.3f} | {new:.3f} | {(1-new/old)*100:.1f}% | {full/new:.2f}× |\n'
    text+='''
## 正确性与范围

- 板上实际自检通过：七种尺寸，含1×1、奇数ROI加halo、960×540；旧/新清零逐字节对照一致，五个缓冲区首尾17字节保护区未改变。常量图full/base/FOV在两开关下通过，原恒等/平移/填洞、上采样和溢出PSNR自检通过。
- 重建几何、视差/光流、补洞、PSNR公式未改。原有非原子竞争写入仍在，因此清零逐字节等价不等于完整重建逐像素确定。quality_observations.csv保留各次末次输出的原PSNR，仅为观察，尚无本优化的全1068帧质量复测。
- 这是四帧配对试测，与之前完整1068帧的采样数、预热和重复次数不同。只在本次同配置旧/新之间计算优化收益，不能拿旧全量均值直接相除。
- 2ms是固定预算，不是本次实测解码或端到端延迟。Full也获得优化，FOV收益必须与优化后的Full比较。
- CUDA event包含相关launch间隙；墙钟均值另存summary.csv。默认动态调频，未执行jetson_clocks。ABBA降低顺序偏差，但没有提供置信区间。

## 用法与证据

```bash
./pirate_bench --input frame.pir --roi-width 240 --roi-height 135 \\
  --fast-resample --fast-clear --warmup 10 --repeats 100 --csv new.csv
```

完整质量runner也支持`--fast-clear`并在metadata记录。移除该选项即使用旧清零。当前PPT仍引用[1068帧正式实验](../fov_scales_full_20261029/README.md)；本试测另存。

原始CSV/日志、清零自检、源码快照见evidence.tar.gz。逐次wall/GPU时间与flags均保留，汇总为summary.csv。输入为原四组相同frame39包，板上实验目录`/home/yingtian/stereo-fast-clear-20261029/`。
'''
    (root/'README.md').write_text(text,encoding='utf-8')
    print('Verified 14400 raw timing samples, 18 mean groups')


if __name__=='__main__':main()
