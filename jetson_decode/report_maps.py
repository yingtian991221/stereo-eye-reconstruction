"""Audit map video decoding and report arithmetic means with precision scope."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    a = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    records = read(a.root/'encoding.json')
    outcomes = read(a.root/'raw/outcomes.json')
    assert (a.root/'raw/COMPLETE').exists() and len(outcomes) == 56
    assert len(records) == 28
    rows = []
    for r in records:
        row = dict(name=r['name'], group=r['group'], channel=r['channel'], variant=r['variant'],
                   width=r['width'], height=r['height'], frames=r['frames'],
                   bitrate_mbps=r['bitrate_container_bps']/1e6,
                   uint16_mae=r.get('reconstructed_uint16_mae'), uint16_max_error=r.get('reconstructed_uint16_max_error'),
                   software_bit_exact=r.get('bit_exact'))
        if r['variant'] == 'pack16_lossless':
            assert r['bit_exact'] and r['changed_values'] == 0 and r['compared_values'] == 120*960*540
        for kind in ['serial', 'throughput']:
            folder = a.root/'raw'/(r['name']+'_'+kind)
            outcome = next(o for o in outcomes if o['name'] == r['name'] and o['kind'] == kind)
            row[kind+'_exit_code'] = outcome['exit_code']
            if outcome['exit_code']:
                continue
            assert (folder/'COMPLETE').exists()
            data = read(folder/'result.json')
            assert data['sha256'] == r['sha256']
            assert data['enable_max_performance'] and data['disable_dpb']
            assert len(data['runs']) == 3 and all(v['frames'] == 120 for v in data['runs'])
            if kind == 'serial':
                assert data['samples'] == 360 and 'memory:NVMM' in data['output_caps']
                with (folder/'latencies.csv').open(newline='') as f:
                    raw = list(csv.DictReader(f))
                assert len(raw) == len({(x['repeat'], x['frame_index']) for x in raw}) == 360
                assert abs(fmean(float(x['latency_ms']) for x in raw)-data['mean_all_ms']) < 1e-6
                row['serial_all_mean_ms'] = data['mean_all_ms']
                row['serial_after10_mean_ms'] = data['mean_after_initial10_ms']
            else:
                assert all('memory:NVMM' in x['output_caps'] for x in data['runs'])
                row['output_interval_mean_ms'] = fmean(x['mean_output_interval_ms'] for x in data['runs'])
        rows.append(row)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (a.root/'summary.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    groups=defaultdict(list)
    for row in rows: groups[row['channel'],row['variant']].append(row)
    failures = [o for o in outcomes if o['exit_code']]
    text='''# Depth / flow 单通道视频解码实测

2026-10-29，Jetson AGX Xavier，30W 4CORE，未锁频。四组Driving各取前120个连续帧；depth、flow-u、flow-v共12路数据，另加四路相同时间范围的RGB对照。每条视频分别做三轮逐帧延迟测试和三轮流水吞吐测试。全部数值为算术平均值。

## 编码与精度

当前数据是16-bit单通道PNG；原始depth/flow视频码流缺失，因此本次为新编码的受控实验。

- **q8_lossy**：将16-bit数值按round(value/257)量化为8-bit，放进HEVC Y平面，UV固定128。960×540，depth目标0.5Mbps，u/v各0.25Mbps。90FPS、无B帧、GOP90。属于YUV420灰度内容视频，未测试原生monochrome profile。精度与现有16-bit输入不等价。
- **pack16_lossless**：把原数值高8位、低8位并排放进Y平面，宽度变成1920×540，HEVC lossless，无B帧、90FPS。仍是8-bit HEVC Main码流的双字节打包，不能称为原生16-bit硬解码。它是精度控制实验，带宽远高于低码率方案。
- RGB对照为960×540、8Mbps目标码率、相同120帧/90FPS/GOP90/无B帧，沿用之前veryfast/zerolatency设置。灰度与RGB还同时改变码率及图像内容，不能把差异只归因于通道数。

所有pack16视频均经本机FFmpeg软件解码，再组合高低字节，与输入逐像素比较，全部误差为0。板上硬解码测量验证了帧数、PTS和NVMM输出；没有读回NVMM像素，所以不宣称已逐像素验证NVDEC输出。原PSNR函数没有修改。

## 平均解码耗时

使用nvv4l2decoder，disable-dpb=true、enable-max-performance=true。输出保持NVMM。逐帧测试从压缩AU提交到对应输出可用，含Python/GStreamer与队列开销，不含文件/MP4解析、输入复制、解码输出下载、高低字节重组、颜色转换或重建。
“去首10帧”在每轮单独处理；全样本均值包含启动。流水输出间隔只描述吞吐。

下表为四组各自均值的平均（每组同为120帧、3轮，等权与按样本加权一致）。详细逐组数值在summary.csv。

| 内容 / 方案 | 编码分辨率 | 实际平均码率(Mbps) | 全样本平均延迟(ms) | 每轮去首10帧平均(ms) | 流水平均输出间隔(ms) |
| --- | --- | ---: | ---: | ---: | ---: |
'''
    for key, values in groups.items():
        assert len(values) == 4
        def avg(k):
            return f'{fmean(v[k] for v in values):.3f}' if all(k in v for v in values) else '未通过完整校验'
        text+=f'| {key[0]} / {key[1]} | {values[0]["width"]}×540 | {avg("bitrate_mbps")} | {avg("serial_all_mean_ms")} | {avg("serial_after10_mean_ms")} | {avg("output_interval_mean_ms")} |\n'
    text+='\n## 数值精度（软件回解，对输入PNG）\n\n单位为原16-bit整数单位；包括8-bit量化和视频有损压缩带来的误差，不能解释为重建图像PSNR。\n\n| 内容 / 方案 | 平均绝对误差 | 最大绝对误差 |\n| --- | ---: | ---: |\n'
    for (channel,variant), values in groups.items():
        if channel != 'rgb':
            text+=f'| {channel} / {variant} | {fmean(v["uint16_mae"] for v in values):.3f} | {max(v["uint16_max_error"] for v in values)} |\n'
    text+='\n## 完整性与解释边界\n\n'
    text+=f'56个解码测试中，失败数为{len(failures)}。失败不计为速度结果，原始错误日志也保留。\n\n'
    text+='''这些单路结果不能直接代表RGB+depth+u+v并行解码的端到端耗时，也不能简单用RGB耗时除以3。解码后地图的拼接/数值恢复、跨CUDA输入的互操作和重建尚未接成同一条流水线。

编码参数、视频SHA和逐像素精度统计见encoding.json；本机视频在`C:/Users/yingt/Datasets/PIRATE/map_decode_20261029/`，板上在`/home/yingtian/stereo-map-decode-20261029/videos/`。原始逐帧时间、日志及源码快照见evidence.tar.gz。视频与原PNG不提交Git。旧RGB完整视频结果保留在[上轮报告](../hevc_decode_xavier_20261029/README.md)。
'''
    (a.root/'README.md').write_text(text,encoding='utf-8')
    (a.root/'audit.json').write_text(json.dumps(dict(videos=28,tests=56,failures=failures,
        frames_per_run=120,repeats=3,statistic='arithmetic mean',packed_software_exact=True,
        hardware_pixel_exactness_verified=False),indent=2),encoding='utf-8')
    print('Verified',len(rows),'clips;',len(failures),'failed tests')


if __name__=='__main__': main()
