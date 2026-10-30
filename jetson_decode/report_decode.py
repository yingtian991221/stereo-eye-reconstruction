"""Summarize controlled HEVC decoding measurements using arithmetic means."""
import argparse
import csv
import json
from pathlib import Path
from statistics import fmean


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    a = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    software = read(a.root / 'ffmpeg_software/runs.json')
    rows = []
    for group in ['15_300', '15_800', '35_300', '35_800']:
        frames = int(group.split('_')[1])
        row = dict(workload=group, frames=frames, repeats=3)
        for setting, directory in [('default', 'gst_'), ('max', 'gst_max_')]:
            folder = a.root / (directory + group)
            data = read(folder / 'result.json')
            assert data['samples'] == frames*3 and 'memory:NVMM' in data['output_caps']
            assert data.get('enable_max_performance', False) == (setting == 'max')
            with (folder / 'latencies.csv').open(newline='') as f:
                raw = list(csv.DictReader(f))
            assert len(raw) == frames*3
            assert len({(r['repeat'], r['frame_index']) for r in raw}) == frames*3
            assert abs(fmean(float(r['latency_ms']) for r in raw)-data['mean_all_ms']) < 1e-6
            row[setting+'_serial_all_mean_ms'] = data['mean_all_ms']
            row[setting+'_serial_after10_mean_ms'] = data['mean_after_initial10_ms']
        for setting in ['default', 'max']:
            data = read(a.root / f'throughput_{setting}_{group}/result.json')
            assert len(data['runs']) == 3
            assert all(r['frames'] == frames and 'memory:NVMM' in r['output_caps'] for r in data['runs'])
            interval = fmean(r['mean_output_interval_ms'] for r in data['runs'])
            row[setting+'_mean_output_interval_ms'] = interval
            row[setting+'_output_throughput_fps'] = 1000/interval
        sw = [r for r in software if r['video'] == f'driving_{group}.mp4' and not r['warmup']]
        assert len(sw) == 3 and all(r['frames'] == frames for r in sw)
        row['software_amortized_wall_mean_ms'] = fmean(r['amortized_ms_per_frame'] for r in sw)
        row['actual_video_bitrate_bps'] = int(sw[0]['stream']['bit_rate'])
        rows.append(row)
    with (a.root / 'summary.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    text = '''# Driving 图片合成 HEVC MP4 后的 Jetson 解码测试

2026-10-29。Jetson AGX Xavier，30W 4CORE，未执行jetson_clocks。四组原始左眼PNG共2200帧，960×540，按90 FPS编码成HEVC MP4，8Mbps目标码率、yuv420p、无B帧、GOP90、x265 veryfast/zerolatency。实际码率约7.73–7.85Mbps。这里是新编码的受控实验，不是对原论文所有编码配置的复现。

## FFmpeg 与文件

本机使用独立目录中的FFmpeg7.1编码；Jetson从NVIDIA软件源提取FFmpeg4.2.7及缺少的libdc1394到用户目录，没有修改系统包。FFmpeg可用，支持软件hevc与hevc_nvv4l2dec硬件封装。

本机视频目录：`C:/Users/yingt/Datasets/PIRATE/hevc_decode_20261029/`。
板上视频目录：`/home/yingtian/stereo-decode-20261029/videos/`。视频没有提交到Git；编码命令、文件大小和SHA256见encoding.json。

## 硬解码：逐帧平均延迟与流水输出间隔

使用GStreamer的nvv4l2decoder，disable-dpb=true，enable-max-performance=true，输出为NVMM/NV12，无CPU下载或颜色转换。每个视频独立建立管线3次，帧数和PTS全部验证。

逐帧测试一次只提交一帧压缩AU，测push之前到对应NVMM输出可用的时间，包含Python/GStreamer、队列和解码。MP4解复用、解析、输入buffer分配/复制在计时外。全样本均值保留冷启动，另列每轮去掉前10帧的均值，二者不混用。
连续流水测试不逐帧等待。输出间隔用于描述吞吐，不能作为输入到输出延迟。

| Driving | 帧数/轮 | 逐帧全样本均值(ms) | 每轮去前10帧均值(ms) | 流水平均输出间隔(ms) | 流水吞吐(FPS) |
| --- | ---: | ---: | ---: | ---: | ---: |
'''
    for r in rows:
        text += f'| {r["workload"]} | {r["frames"]} | {r["max_serial_all_mean_ms"]:.3f} | {r["max_serial_after10_mean_ms"]:.3f} | {r["max_mean_output_interval_ms"]:.3f} | {r["max_output_throughput_fps"]:.1f} |\n'
    text += '''
性能选项关闭时的原始结果也完整保留：逐帧均值在不同轮次有较大波动，不能只选最快的一轮。见summary.csv与gst_*/result.json。性能选项的测试在其后进行，没有做往返随机化，因此改善幅度还受运行顺序等影响。

## FFmpeg 软件解码与失败的硬件封装尝试

软件hevc每视频先完整预热一轮，再测三轮，4线程，-f null，不按90FPS限速。下表是启动到进程结束的墙钟/帧数，含初始化、文件/解复用/解码/输出处理，不能称为纯解码器单帧延迟。

| Driving | 软件解码平均墙钟摊销(ms/frame) |
| --- | ---: |
'''
    for r in rows:
        text += f'| {r["workload"]} | {r["software_amortized_wall_mean_ms"]:.3f} |\n'
    text += '''
FFmpeg hevc_nvv4l2dec首轮在300帧视频只输出294帧，未通过帧数校验；日志保存在ffmpeg/。这次尝试不计入有效速度结论。原生GStreamer硬解码上述所有测试都完整输出，且确认NVMM caps。

## 与重建计时的边界

- 现有证据支持硬解码预热后约2.40–2.51ms的应用可见逐帧延迟，以及约1.95ms流水输出间隔。两者都不等于此前估计的1.5ms，不能从200FPS推导1.5ms。
- 输出为NV12/NVMM；接到当前重建所需的BGR/CUDA输入还需要验证格式转换及互操作成本。没有在此宣称已测完整解码加重建端到端流水线。
- 当前视频是单路左眼输入；未合成左右眼交替流，也未把视差/光流视频解码计入。地图输入、网络和显示时间尚未纳入。
- 全部数值使用算术平均。原始逐帧CSV、日志、环境和源码快照存于evidence.tar.gz；summary.csv可直接查看。重跑说明见[jetson_decode](../../jetson_decode/README.md)。
'''
    (a.root / 'README.md').write_text(text, encoding='utf-8')
    print('Verified four videos and all complete hardware/software runs')


if __name__ == '__main__':
    main()
