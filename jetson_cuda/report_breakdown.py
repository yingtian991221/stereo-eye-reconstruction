"""Audit event partitions and report arithmetic mean stage timings."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean

DETAIL = ['clear', 'intra_frame', 'inter_frame', 'composite_fill', 'downsample', 'upsample', 'overlay', 'trace_boundary']
LEVELS = ['80x46', '160x90', '320x180', '480x270', '640x360']
FRAMES = {f'driving_{w}_0039.pir' for w in ['15_300', '15_800', '35_300', '35_800']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--plot', action='store_true')
    a = p.parse_args()
    assert (a.root / 'COMPLETE').exists(), 'Incomplete run'
    summaries = []
    max_partition_error = 0
    for level in LEVELS:
        for timing in ['resident', 'stream']:
            groups = defaultdict(dict)
            with (a.root / 'raw' / f'{level}_{timing}.csv').open(newline='') as f:
                for r in csv.DictReader(f):
                    assert r['fast_resample'] == '1'
                    assert f"{r['roi_width']}x{r['roi_height']}" == level
                    assert r['timing'] == ('gpu_resident' if timing == 'resident' else 'host_transfer')
                    key = (r['frame'], r['mode'], int(r['iteration']), r['variant'])
                    stagekey = (r['stage'], r['pass'])
                    assert stagekey not in groups[key], 'Duplicate stage'
                    groups[key][stagekey] = r
            expected = {(f, m, i, v) for f in FRAMES for m in ['full', 'half_base', 'fov'] for i in range(100) for v in ['reference', 'staged']}
            assert set(groups) == expected
            aggregate = defaultdict(list)
            for (frame, mode, iteration, variant), stages in groups.items():
                total = stages['total', 'all']
                get = lambda name: sum(float(r['gpu_ms']) for (stage, _), r in stages.items() if stage == name)
                detail_keys = set()
                if variant == 'staged':
                    passes = ['full'] if mode == 'full' else (['base'] if mode == 'half_base' else ['base', 'roi'])
                    detail_keys = {(s, part) for part in passes for s in ['clear', 'inter_frame', 'intra_frame', 'composite_fill']}
                    if mode != 'full': detail_keys |= {('downsample', 'base'), ('upsample', 'base')}
                    if mode == 'fov': detail_keys.add(('overlay', 'roi'))
                    detail_keys.add(('trace_boundary', 'all'))
                expected_stages = {('total', 'all'), ('reconstruction', 'all')} | detail_keys
                if timing == 'stream': expected_stages |= {('h2d', 'all'), ('d2h', 'all')}
                assert set(stages) == expected_stages, set(stages) ^ expected_stages
                if variant == 'staged':
                    error = abs(sum(get(s) for s in DETAIL) - get('reconstruction'))
                    assert error < 0.002
                    max_partition_error = max(max_partition_error, error)
                if timing == 'stream':
                    error = abs(get('h2d') + get('reconstruction') + get('d2h') - get('total'))
                    assert error < 0.002
                    max_partition_error = max(max_partition_error, error)
                row = {s: get(s) for s in DETAIL + ['reconstruction', 'h2d', 'd2h', 'total']}
                row['wall'] = float(total['wall_total_ms'])
                assert row['wall'] > 0 and row['reconstruction'] > 0
                aggregate[mode, variant].append(row)
            for (mode, variant), rows in aggregate.items():
                assert len(rows) == 400
                summaries.append(dict(level=level, timing=timing, mode=mode, variant=variant, samples=400,
                                      **{k + '_mean_ms': fmean(r[k] for r in rows) for k in rows[0]}))
    with (a.root / 'summary.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0])); w.writeheader(); w.writerows(summaries)
    (a.root / 'audit.json').write_text(json.dumps(dict(frames=sorted(FRAMES), levels=LEVELS, samples_per_group=400,
        groups=len(summaries), max_partition_error_ms=max_partition_error, statistic='arithmetic mean'), indent=2), encoding='utf-8')
    def find(level, mode='fov', variant='staged', timing='resident'):
        return next(r for r in summaries if (r['level'], r['mode'], r['variant'], r['timing']) == (level, mode, variant, timing))
    text = '''# CUDA C++：按论文阶段拆分耗时

2026-10-29，Jetson AGX Xavier，30W 4CORE（mode 5），未锁频。四组 Driving 各第39帧，960×540，每路径预热10次、计时100次。下文全部是算术平均值，无裁剪。不是完整1068帧测试。

## 论文口径

原论文 Fig.6 / Sec.6.1：Decoding 3.2ms、Intra-frame 1.3ms、Inter-frame 2.5ms、Composite and Filling 2.4ms，总计9.4ms。论文采用15W；这些是论文图中的参考值，不是本次测量，也不与本次30W直接做加速比。

本次输入已经解码，**Decoding 未测**，不能写成0，也不能把论文3.2ms加到本次结果当实测总时间。
Intra-frame 对应视差重投影，Inter-frame 对应光流重投影，Composite and Filling 对应合成与补洞。代码保持光流先于视差的原执行顺序，表格仅按论文栏目排列。

## 重建阶段：GPU timeline 均值（ms）

同一轮的阶段采用CUDA event标记，阶段之间不插入同步。FOV的base和中心ROI两个pass按同类阶段相加。额外列出原论文未单列的清零，以及FOV新增的降采样、上采样和融合。
Full取2.8%配置那一轮的配对基线，并非五轮Full合并后的均值。

| 路径 | Intra-frame | Inter-frame | Composite + Filling | 清零 | 降采样 | 上采样 | ROI融合 | 边界标记 | 重建合计 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
'''
    table = [('Full', find('160x90', 'full'))] + [(f'FOV {int(l.split("x")[0])*int(l.split("x")[1])/518400*100:.1f}%', find(l)) for l in LEVELS]
    fields = ['intra_frame', 'inter_frame', 'composite_fill', 'clear', 'downsample', 'upsample', 'overlay', 'trace_boundary', 'reconstruction']
    for name, r in table:
        text += '| '+name+' | '+' | '.join(f'{r[k+"_mean_ms"]:.3f}' for k in fields)+' |\n'
    text += '\n清零是当前Full路径最大的单项开销（约46%）。Full到2.8% FOV的重建时间差中，约58%来自清零范围缩小。不能把全部收益归因于视差/光流计算减少。原clearKernel相邻lane沿行方向跨距写入，是值得检查的访存问题；具体硬件瓶颈仍需进一步验证，本次没有优化它。\n'
    text += '\n## 分段标记开销与整体延迟\n\nreference调用原Pipeline.run，仅保留外层计时标记；staged增加内部阶段标记。以下为resident墙钟均值，包含CPU发起及等待GPU完成，不含分配、磁盘、解码或显示。\n\n| 路径 | reference均值(ms) | staged均值(ms) | staged / reference |\n| --- | ---: | ---: | ---: |\n'
    for name, r in table:
        b = find(r['level'], r['mode'], 'reference')
        text += f'| {name} | {b["wall_mean_ms"]:.3f} | {r["wall_mean_ms"]:.3f} | {r["wall_mean_ms"]/b["wall_mean_ms"]:.3f}× |\n'
    text += '\n## CPU/GPU拷贝与解码的区别\n\n上传是CPU缓冲区到CUDA设备缓冲区的拷贝，回传是重建输出回到CPU缓冲区。它们不是网络上传/下载，也不是视频解码。Xavier共享物理DRAM，当前代码仍显式调用cudaMemcpy；本次没有实现零拷贝路径。输入拷贝6,220,800字节，输出1,555,200字节/次。\n\n下表为同一stream reference流水线的event区间均值，区间含对应API调度间隙，不是孤立DMA测量。前三段可相加为GPU timeline总跨度；墙钟另含外层主机开销。\n\n| 路径 | H2D区间(ms) | 重建区间(ms) | D2H区间(ms) | timeline总计(ms) | 墙钟总计(ms) |\n| --- | ---: | ---: | ---: | ---: | ---: |\n'
    for name, mode in [('Full', 'full'), ('FOV 2.8%', 'fov')]:
        r = find('160x90', mode, 'reference', 'stream')
        text += '| '+name+' | '+' | '.join(f'{r[k+"_mean_ms"]:.3f}' for k in ['h2d', 'reconstruction', 'd2h', 'total', 'wall'])+' |\n'
    text += '''
## 可比性与原始证据

- 原kernel、精度、执行顺序及PSNR代码未改，开启现有fast-resample。分段路径复用同一组kernel。reference仍有外层event开销，不能声称绝对无插桩。
- raw CSV中的wall_total_ms在各stage行重复，只能取stage=total计算均值。h2d_api_wall_ms/d2h_api_wall_ms为诊断字段，后者可能等待前序重建，不能与重建耗时直接相加。
- trace_boundary保留外层与内部event之间的差额，阶段总和已逐样本核对。GPU event跨度可能含CPU发起间隙，不是纯指令执行时间。
- 功耗为30W且样本只有4帧，不能直接与论文15W或此前1068帧均值归因比较。原竞争写入和部分实现差异仍存在；本实验没有验证视觉质量等价。
- 频率日志799个采样点中796个为GPU905.25MHz，其余3个为开始升频阶段；CPU范围1.1904–1.8048GHz。温度CPU36–40°C、GPU33–38°C。频率采样包含预热等时段，不代表每个kernel的逐时频率。
- 全部原始样本和源码快照见[evidence.tar.gz](evidence.tar.gz)中的raw/与source/，本地另保留未压缩raw/。均值见summary.csv，覆盖及加和校验见audit.json。频率/温度记录分别为frequencies.csv和tegrastats.log。源码和二进制哈希另存。没有将解码/网络/显示阶段补成估计值。
'''
    (a.root / 'README.md').write_text(text, encoding='utf-8')
    if a.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 5.8), constrained_layout=True)
        names = [name for name, _ in table]
        bottom = [0.0] * len(table)
        labels = [('clear', 'Buffer clear'), ('intra_frame', 'Intra-frame'),
                  ('inter_frame', 'Inter-frame'), ('composite_fill', 'Composite + filling'),
                  ('downsample', 'Downsample'), ('upsample', 'Upsample'),
                  ('overlay', 'ROI blend'), ('trace_boundary', 'Trace boundaries')]
        colors = ['#9aa4ad', '#086b93', '#148b83', '#d17b28', '#7555a2', '#bb86c1', '#a7bd45', '#dedede']
        for (key, label), color in zip(labels, colors):
            values = [r[key + '_mean_ms'] for _, r in table]
            ax.bar(names, values, bottom=bottom, label=label, color=color, width=0.65)
            bottom = [b + v for b, v in zip(bottom, values)]
        for i, value in enumerate(bottom):
            ax.text(i, value + 0.08, f'{value:.3f}', ha='center', fontsize=10)
        ax.set_ylim(0, max(bottom) * 1.25)
        ax.set_ylabel('Mean GPU timeline (ms)')
        ax.set_title('30W Xavier: reconstruction-stage breakdown\n4 Driving frames, 100 repeats per path; decoding not measured')
        ax.legend(ncol=4, loc='upper right', fontsize=9)
        ax.set_axisbelow(True)
        ax.grid(axis='y', alpha=0.2)
        fig.savefig(a.root / 'breakdown.png', dpi=180)
        fig.savefig(a.root / 'breakdown.svg')
        svg = a.root / 'breakdown.svg'
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
        plt.close(fig)
        text += '\n![Measured reconstruction-stage means](breakdown.svg)\n'
        (a.root / 'README.md').write_text(text, encoding='utf-8')
    print('Verified', len(summaries), 'groups; maximum partition error', max_partition_error, 'ms')


if __name__ == '__main__':
    main()
