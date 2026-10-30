"""Audit and summarize the small Numba power-mode experiment."""
import argparse
import json
import re
from pathlib import Path
import numpy as np


def measurements(work):
    fov = work['fov_pilot']
    return [work['source_function']['cached_source_wall'], fov['full'],
            fov['half_base']] + [fov['rois'][k]['half_base_plus_roi']
                                for k in ['160x90', '320x180', '480x270']]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    a = p.parse_args()
    records = {}
    for name in ['mode7_15w', 'mode5_30w']:
        folder = a.root / name
        if not folder.exists():
            continue
        assert (folder / 'exit_code').read_text().strip() == '0'
        assert 'COMPLETE: four workloads' in (folder / 'run.log').read_text()
        record = json.loads((folder / 'result.json').read_text())
        assert record['frame'] == 39 and record['repeats'] == 100
        assert set(record['workloads']) == {'driving_15_300', 'driving_15_800', 'driving_35_300', 'driving_35_800'}
        for work in record['workloads'].values():
            assert work['fov_pilot']['overlay_changed_outside_pixels'] == 0
            assert work['fov_pilot']['overlay_changed_inside_pixels'] > 0
            for m in measurements(work):
                v = np.array(m['samples_ms'])
                assert len(v) == m['n'] == 100 and np.isfinite(v).all() and (v > 0).all()
                for q in [50, 95, 99]:
                    assert abs(np.percentile(v, q) - m['p%d_ms' % q]) < 0.000051
        records[name] = record
    text = '''# Xavier Numba 小样本实测（2026-10-29）

**Numba 已在真实 Xavier GPU 上运行成功**，不是 CUDA simulator。独立 Python 3.8 虚拟环境：Numba 0.58.1 / llvmlite 0.41.1 / NumPy 1.24.4 / Pillow 10.4.0，CUDA 11.4，SM72。

范围：四组 Driving，各自第 39 帧（960×540），每条路径 100 次计时。不是完整 Driving 质量复测。原始 kernel 及 PSNR 未改，沿用 uint8 溢出公式。

## 各配置结果

以下是 wall latency p50，单位 ms；p95/p99 和全部逐次时间见各模式 result.json。
source 包含分配、参数 NPY 读取、上传/下载及中间 debug 下载，PNG 已缓存、保存被抑制。
其余列为复用缓冲区的 resident 原型，含 Python launch 与同步，不含传输、分配、I/O。
source 和每种 resident 变体各有一次不计时调用，排除首次 JIT；这不保证已达到稳态。

'''
    for name, record in records.items():
        text += '### %s\n\n' % name
        text += '| Driving | source | full | half-base | FOV160×90 | FOV320×180 | FOV480×270 |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n'
        for key, work in record['workloads'].items():
            text += '| ' + key + ' | ' + ' | '.join('%.3f' % m['p50_ms'] for m in measurements(work)) + ' |\n'
        log = (a.root / name / 'tegrastats.log').read_text()
        for sensor in ['CPU', 'GPU']:
            vals = [float(x) for x in re.findall(r'\b' + sensor + r'@([0-9.]+)C', log)]
            if vals:
                text += '\n%s 温度范围 %.1f–%.1f°C。\n' % (sensor, min(vals), max(vals))
        text += '\n[原始 JSON](%s/result.json) · [环境](%s/environment.txt) · [tegrastats](%s/tegrastats.log)\n\n' % (name, name, name)
    if len(records) == 2:
        text += '## 15W → 30W：同帧同实现\n\n| Driving | full 加速 | FOV160 加速 | FOV320 加速 | FOV480 加速 |\n| --- | ---: | ---: | ---: | ---: |\n'
        for key in records['mode7_15w']['workloads']:
            old = measurements(records['mode7_15w']['workloads'][key])
            new = measurements(records['mode5_30w']['workloads'][key])
            text += '| ' + key + ' | ' + ' | '.join('%.2f×' % (old[i]['p50_ms'] / new[i]['p50_ms']) for i in [1, 3, 4, 5]) + ' |\n'
    else:
        text += '## 30W 状态\n\n尚无通过完整校验的 30W 结果，不据此推断加速。\n'
    text += '''
## 解释与复现

- 模式7：15W Desktop，4核 CPU 上限2.1888GHz，实读GPU上限675.75MHz。模式5：30W 4CORE，CPU配置上限1.78GHz、GPU900MHz、EMC1600MHz。30W并非所有频率都更高；模式切换只能在两轮测试之间进行。
- 未执行 jetson_clocks；使用动态调频。tegrastats 提供CPU频率、温度及GPU利用率，但这台板的日志没有GPU实际MHz，不能据此宣称GPU频率固定。
- 15W 第一组 source 前10次中位数约75.4ms、末10次约47.2ms，存在明显启动趋势；source数字仅为这轮观测，不称稳态延迟。resident路径更稳定，仍是单帧小样本。
- 原始部分初始化、uint8深度缓存和非原子竞争写入仍保留；resident原型另做完整scratch清零。两者不能视为逐像素等价实现。ROI检查确认有像素变化且ROI外0变化。
- Numba FOV使用旧bilinear上采样，未移植CUDA C++的fast-resample；不能把与优化C++的差异解释为语言开销。全1068帧C++结果仍见[原报告](../fov_levels_xavier_full_20261027/README.md)。
- 初次JIT报错来自提取工具链的libcudart悬空链接；接到板上已有11.4运行库后成功，无需修改Numba或驱动。首次失败日志与30次smoke记录独立保留。
- [重跑说明](../../jetson_numba/README.md)、[环境依赖](requirements.txt)、[输入及程序哈希](provenance.json)。板上实验目录 `/home/yingtian/stereo-numba-20261029/`。
'''
    (a.root / 'README.md').write_text(text, encoding='utf-8')
    print('Verified %d completed power modes' % len(records))


if __name__ == '__main__':
    main()
