"""Audit the complete four-scale Driving sweep and report arithmetic means."""
import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean

LEVELS = [('96x54', 0.1), ('240x135', 0.25), ('480x270', 0.5), ('720x405', 0.75)]
MODES = ['full', 'half_base', 'fov']
REGIONS = ['whole', 'fixed_center', 'fixed_periphery', 'level_roi', 'level_periphery']
WORKLOAD_LAST = {'driving_15_300': 299, 'driving_15_800': 779,
                 'driving_35_300': 299, 'driving_35_800': 779}
EXPECTED = {f'{work}_{frame:04d}.pir' for work, last in WORKLOAD_LAST.items()
            for frame in range(7, last+1, 2)}
DECODE_MS = 2.0


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def difference(value, baseline):
    return 0.0 if value == baseline else value-baseline


def metric_mean(values):
    values = list(values)
    if math.inf in values and -math.inf in values:
        return None  # The arithmetic mean is undefined; do not discard frames.
    if math.inf in values:
        return math.inf
    if -math.inf in values:
        return -math.inf
    return fmean(values)


def metric_text(value):
    if value is None:
        return '未定义（同时有正负无穷）'
    return f'{value:+.4f}'


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return 'inf' if value > 0 else '-inf'
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def audit(root):
    require((root/'COMPLETE').is_file(), 'Run is incomplete: COMPLETE is missing')
    meta = json.loads((root/'metadata.json').read_text(encoding='utf-8'))
    args = meta['arguments']
    require(args['levels'] == ','.join(level for level, _ in LEVELS), 'Unexpected ROI levels/order')
    for key, value in [('timing', 'resident'), ('warmup', 3), ('repeats', 5), ('quality_runs', 1),
                       ('fixed_region', '160x90'), ('fast_resample', True), ('batch_size', 32)]:
        require(args.get(key) == value, f'Unexpected argument {key}: {args.get(key)!r}')
    require('MODE_30W_4CORE' in meta.get('power', ''), 'Metadata does not confirm 30W 4CORE')
    packets = meta['packets']
    packet_names = [p['file'].replace('\\', '/').rsplit('/', 1)[-1] for p in packets]
    require(len(packets) == len(set(packet_names)) == 1068 and set(packet_names) == EXPECTED,
            'Metadata packets do not exactly cover the 1068 expected frames')
    require(all((p['width'], p['height']) == (960, 540) for p in packets), 'Unexpected image dimensions')
    source_checks = {}
    source_dir = root/'source'
    if source_dir.exists():
        for filename, field in [('evaluate_levels.py', 'runner_sha256'), ('pirate_bench.cu', 'cuda_source_sha256')]:
            file = source_dir/filename
            require(file.is_file(), f'Missing source snapshot: {file}')
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            require(digest == meta[field], f'Source hash mismatch: {filename}')
            source_checks[filename] = digest
    quality, times = read_csv(root/'quality.csv'), read_csv(root/'timings.csv')
    require(len(quality) == len(times) == 64080, 'Expected exactly 64080 quality and timing rows')
    q_by_group, t_by_group = defaultdict(dict), defaultdict(dict)
    for r in times:
        frame, level, mode = r['frame'], r['level'], r['mode']
        require(frame in EXPECTED and level in dict(LEVELS) and mode in MODES, 'Unknown timing key')
        require(r['workload'] == frame.rsplit('_', 1)[0], 'Timing workload/frame mismatch')
        require(r['timing'] == 'resident' and int(r['run']) == 0, 'Unexpected timing/run')
        width, height = map(int, level.split('x'))
        require(abs(float(r['roi_area_fraction'])-width*height/518400) < 1e-12, 'Timing ROI area mismatch')
        key = (frame, int(r['iteration']))
        group = t_by_group[level, mode]
        require(key not in group, 'Duplicate timing key')
        for field in ['wall_ms', 'gpu_timeline_ms']:
            value = float(r[field])
            require(math.isfinite(value) and value > 0, f'Invalid {field}')
        group[key] = r
    for r in quality:
        frame, level, mode, region = r['frame'], r['level'], r['mode'], r['region']
        require(frame in EXPECTED and level in dict(LEVELS) and mode in MODES and region in REGIONS,
                'Unknown quality key')
        require(r['workload'] == frame.rsplit('_', 1)[0], 'Quality workload/frame mismatch')
        require(r['timing'] == 'resident' and int(r['run']) == 0, 'Unexpected quality timing/run')
        width, height = map(int, level.split('x'))
        require(abs(float(r['roi_area_fraction'])-width*height/518400) < 1e-12, 'Quality ROI area mismatch')
        pixels = {'whole': 518400, 'fixed_center': 14400, 'fixed_periphery': 504000,
                  'level_roi': width*height, 'level_periphery': 518400-width*height}
        require(int(r['pixels']) == pixels[region], 'Region pixel count mismatch')
        mse, score = float(r['mse']), float(r['standard_psnr_db'])
        require(math.isfinite(mse) and mse >= 0, 'Invalid MSE')
        expected_score = math.inf if mse == 0 else 10*math.log10(255.0**2/mse)
        require(score == expected_score or abs(score-expected_score) < 1e-8, 'Standard PSNR/MSE mismatch')
        require(math.isfinite(float(r['legacy_whole_psnr_db'])), 'Invalid legacy whole PSNR')
        key = (frame, region)
        group = q_by_group[level, mode]
        require(key not in group, 'Duplicate quality key')
        group[key] = r
    expected_time = {(frame, iteration) for frame in EXPECTED for iteration in range(5)}
    expected_quality = {(frame, region) for frame in EXPECTED for region in REGIONS}
    require(len(t_by_group) == len(q_by_group) == 12, 'Unexpected group count')
    for level, _ in LEVELS:
        for mode in MODES:
            require(set(t_by_group[level, mode]) == expected_time, f'Incomplete timing coverage: {level}/{mode}')
            group = q_by_group[level, mode]
            require(set(group) == expected_quality, f'Incomplete quality coverage: {level}/{mode}')
            baseline = q_by_group[level, 'full']
            for (frame, region), r in group.items():
                paired = float(baseline[frame, region]['standard_psnr_db'])
                score, reported = float(r['standard_psnr_db']), float(r['delta_vs_full_db'])
                delta = difference(score, paired)
                require(reported == delta or abs(reported-delta) < 1e-8, 'Standard paired delta mismatch')
                require(float(r['legacy_whole_psnr_db']) == float(group[frame, 'whole']['legacy_whole_psnr_db']),
                        'Legacy whole score differs between regions')
    result = dict(frames=1068, workload_frames={w: sum(f.startswith(w+'_') for f in EXPECTED) for w in WORKLOAD_LAST},
                  quality_rows=len(quality), timing_rows=len(times),
                  exact_per_frame_per_config_coverage=True, quality_regions=REGIONS,
                  levels=[level for level, _ in LEVELS], iterations=list(range(5)),
                  source_hashes_verified=source_checks, statistic='arithmetic mean',
                  decode_budget_ms=DECODE_MS, power='30W 4CORE', timing='resident')
    return meta, q_by_group, t_by_group, result


def summarize(q_groups, t_groups):
    rows = []
    for level, scale in LEVELS:
        baseline_times = t_groups[level, 'full']
        full_gpu = fmean(float(r['gpu_timeline_ms']) for r in baseline_times.values())
        full_wall = fmean(float(r['wall_ms']) for r in baseline_times.values())
        baseline_quality = q_groups[level, 'full']
        for mode in MODES:
            quality, times = q_groups[level, mode], t_groups[level, mode]
            gpu = fmean(float(r['gpu_timeline_ms']) for r in times.values())
            wall = fmean(float(r['wall_ms']) for r in times.values())
            legacy = fmean(float(quality[frame, 'whole']['legacy_whole_psnr_db']) for frame in EXPECTED)
            legacy_full = fmean(float(baseline_quality[frame, 'whole']['legacy_whole_psnr_db']) for frame in EXPECTED)
            legacy_delta = fmean(difference(float(quality[frame, 'whole']['legacy_whole_psnr_db']),
                                            float(baseline_quality[frame, 'whole']['legacy_whole_psnr_db']))
                                  for frame in EXPECTED)
            row = dict(level=level, linear_scale=scale, region_percent=100*scale**2, mode=mode,
                       frames=1068, timing_samples=5340, quality_samples=1068,
                       gpu_mean_ms=gpu, wall_mean_ms=wall, decode_budget_ms=DECODE_MS,
                       total_gpu_mean_ms=gpu+DECODE_MS, total_wall_mean_ms=wall+DECODE_MS,
                       full_gpu_mean_ms=full_gpu, full_wall_mean_ms=full_wall,
                       full_total_gpu_mean_ms=full_gpu+DECODE_MS, full_total_wall_mean_ms=full_wall+DECODE_MS,
                       speedup_gpu=full_gpu/gpu, speedup_wall=full_wall/wall,
                       speedup_total=(full_gpu+DECODE_MS)/(gpu+DECODE_MS),
                       speedup_total_wall=(full_wall+DECODE_MS)/(wall+DECODE_MS),
                       legacy_psnr_db=legacy, full_legacy_psnr_db=legacy_full,
                       legacy_delta_db=legacy_delta, derived_stereo_delta_db=legacy_delta/2)
            for region in REGIONS:
                row[region+'_standard_psnr_db'] = metric_mean(float(quality[frame, region]['standard_psnr_db']) for frame in EXPECTED)
                row[region+'_standard_delta_db'] = metric_mean(float(quality[frame, region]['delta_vs_full_db']) for frame in EXPECTED)
            rows.append(row)
    return rows


def report(root, meta, rows, audit_result):
    fov = [r for r in rows if r['mode'] == 'fov']
    # A single displayed Full bar uses the second ROI's paired reference. Every
    # FOV row separately retains its own matched Full timing and PSNR baseline.
    full_reference = next(r for r in rows if r['level'] == '240x135' and r['mode'] == 'full')
    output = dict(date='2026-10-29', power_w=30, implementation='CUDA C++', frames=1068,
                  warmup_per_frame=3, repeats_per_frame=5, quality_outputs_per_config_per_frame=1,
                  timing='resident GPU timeline means; wall means separately retained',
                  fixed_decode_budget_ms=DECODE_MS,
                  decode_scope='One fixed per-frame budget, not joint RGB/depth/flow measurement',
                  full_reference_level='240x135', full_reference=full_reference,
                  levels=fov, overview=rows, audit=audit_result,
                  right_eye_quality='Legacy uint8-overflow PSNR is unmodified',
                  stereo_delta='Derived right-eye delta / 2, conditional on unchanged left eye and per-eye dB averaging')
    write_csv(root/'overview.csv', rows)
    (root/'scale_results.json').write_text(json.dumps(json_safe(output), indent=2, allow_nan=False), encoding='utf-8')
    (root/'audit.json').write_text(json.dumps(audit_result, indent=2), encoding='utf-8')
    text = '''# 新缩放档位：完整有效 Driving 质量与时间

2026-10-29，Jetson AGX Xavier，30W 4CORE，未锁频。CUDA C++、fast-resample开启。新档位为中心区域宽高相对全图的线性比例，不是面积比例，也不改变ROI内的全分辨率采样。

| 线性比例 | 中心区域尺寸 | 占全图面积 |
| --- | --- | ---: |
| 0.10× | 96×54 | 1.00% |
| 0.25× | 240×135 | 6.25% |
| 0.50× | 480×270 | 25.00% |
| 0.75× | 720×405 | 56.25% |

## 覆盖与计时口径

完整覆盖现有代码四组Driving forward的1068个有效右眼重建帧：15mm/300与35mm/300各147帧（7–299全部奇数帧），15mm/800与35mm/800各387帧（7–779全部奇数帧）。不包含backward、偶数帧交替重建及原脚本范围外的尾帧。

各帧各档full/half_base/fov均重新执行；预热3次、计时5次，质量取最后一次计时的实际输出，每帧每配置一个质量样本。每档每模式有1068个质量输出和5340个计时样本。32帧一批，档位及模式顺序轮换。质量和时间来自本轮同一数据覆盖与功耗模式。

时间只报告算术平均值。GPU timeline包含降采样、重建、上采样、融合及相关launch间隙，墙钟另列；均不含输入输出拷贝、分配、文件I/O、质量计算、网络、解码或显示。每帧统一增加一次固定2ms解码预算，属于推导预算，不是多路联合解码或端到端实测。

本轮图像保存改为批量写入相同RGB字节，发生在重建计时区间之外；重建kernel、精度和PSNR公式没有因此改变。使用独立输出目录，旧结果保留。

## 新档位主结果

PSNR差为FOV对GT的分数减去同档同帧Full对GT的分数。原uint8溢出PSNR保留。双眼差是推导值：仅当左眼不变、按左右眼PSNR的dB取平均时，等于右眼差的一半；时间不除以2。

| 区域比例 | GPU重建均值(ms) | 加固定解码预算(ms) | 对配对Full+decode加速 | 右眼ΔPSNR(dB) | 推导双眼平均ΔPSNR(dB) |
| --- | ---: | ---: | ---: | ---: | ---: |
'''
    for r in fov:
        text += f'| {r["linear_scale"]:.2f}× | {r["gpu_mean_ms"]:.3f} | {r["total_gpu_mean_ms"]:.3f} | {r["speedup_total"]:.2f}× | {r["legacy_delta_db"]:+.4f} | {r["derived_stereo_delta_db"]:+.4f} |\n'
    text += f'\n单一Full参考（0.25×测试轮）GPU重建均值为{full_reference["gpu_mean_ms"]:.3f}ms，加固定解码预算后为{full_reference["total_gpu_mean_ms"]:.3f}ms。各行加速比使用各自同档的配对Full，而不是全部统一使用这一参考。\n'
    text += '\n## 补充标准PSNR与墙钟均值\n\n标准PSNR单独采用float64差分、峰值255；固定中心始终160×90，外围为补集。没有修改原PSNR公式。\n\n| 比例 | 重建墙钟均值(ms) | 标准全图ΔPSNR(dB) | 标准固定中心ΔPSNR(dB) | 标准固定外围ΔPSNR(dB) |\n| --- | ---: | ---: | ---: | ---: |\n'
    for r in fov:
        text += f'| {r["linear_scale"]:.2f}× | {r["wall_mean_ms"]:.3f} | {metric_text(r["whole_standard_delta_db"])} | {metric_text(r["fixed_center_standard_delta_db"])} | {metric_text(r["fixed_periphery_standard_delta_db"])} |\n'
    text += '''
## 解释边界与证据

- 当前仍是固定中心FOV档位测试，动态deadline选择、眼动追踪和jitter下deadline-miss改善尚未验证。
- 原uint8深度缓存及非原子竞争写入仍保留；单次输出不能证明逐像素可复现或质量稳定。重复计时不是独立质量样本；均值不是置信区间。
- Full包含现有完整scratch清零；缩小区域也减少清零工作。加速不能全部归因于重投影计算，未与最优Full实现比较。
- 本轮是实际新档位数据，不是把旧档位标签替换。旧30W四帧和15W完整实验保留，不能混为本轮采样。
- overview.csv保留每档full/half_base/fov的全部均值与标准区域指标。scale_results.json是PPT/图表的数据接口；audit.json记录精确覆盖校验。逐帧quality.csv和逐次timings.csv为原始证据，若Git上使用压缩归档，见同目录evidence.tar.gz。
- 元数据保存输入/程序SHA；若source/快照目录存在，报告脚本会验证runner与CUDA源码SHA。没有source/时audit不会声称已验证源码。
- 标准局部PSNR若MSE为0，保留合法正无穷，不裁剪帧。JSON将无穷写为字符串inf/-inf；若差值平均同时包含正负无穷，记为null并在报告中注明未定义，不填替代数值。主PSNR原公式全图分数与时间要求有限。
'''
    (root/'README.md').write_text(text, encoding='utf-8')
    return output


def plot(root, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    levels = output['levels']
    measured = [output['full_reference']['gpu_mean_ms']] + [r['gpu_mean_ms'] for r in levels]
    labels = ['Full'] + [f'{r["linear_scale"]:.2f}×' for r in levels]
    axes[0].bar(labels, measured, color='#086b93', label='Measured GPU reconstruction')
    axes[0].bar(labels, [DECODE_MS]*5, bottom=measured, color='#d17b28', label='Fixed decode budget')
    for i, value in enumerate(measured):
        axes[0].text(i, value+DECODE_MS+0.08, f'{value+DECODE_MS:.3f}', ha='center', fontsize=9)
    axes[0].set_ylim(0, max(measured)*1.3+DECODE_MS)
    axes[0].set_ylabel('Reconstruction mean + fixed budget (ms)')
    axes[0].legend(fontsize=8)
    x = list(range(4))
    axes[1].bar([v-0.18 for v in x], [r['legacy_delta_db'] for r in levels], width=0.36, label='Right-eye difference')
    axes[1].bar([v+0.18 for v in x], [r['derived_stereo_delta_db'] for r in levels], width=0.36, label='Derived stereo mean difference')
    axes[1].set_xticks(x, labels[1:])
    axes[1].set_ylabel('Original overflow PSNR difference vs Full (dB)')
    axes[1].axhline(0, color='gray', linewidth=0.8)
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.set_xlabel('Full-resolution region width / image width')
        ax.grid(axis='y', alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle('Xavier 30W: 1068 valid Driving frames, new region scales')
    fig.savefig(root/'quality_timing.png', dpi=180)
    fig.savefig(root/'quality_timing.svg')
    plt.close(fig)
    svg = root/'quality_timing.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n', encoding='utf-8')
    with (root/'README.md').open('a', encoding='utf-8') as handle:
        handle.write('\n![New scale quality and timing](quality_timing.svg)\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--plot', action='store_true')
    args = parser.parse_args()
    meta, quality, times, audit_result = audit(args.run)
    rows = summarize(quality, times)
    output = report(args.run, meta, rows, audit_result)
    if args.plot:
        plot(args.run, output)
    print('VERIFIED: 1068 exact frames; 64080 quality rows; 64080 timing rows; arithmetic means only')
    for row in output['levels']:
        print(f'{row["linear_scale"]:.2f}x GPU mean {row["gpu_mean_ms"]:.3f} ms; +decode {row["total_gpu_mean_ms"]:.3f} ms; legacy delta {row["legacy_delta_db"]:+.4f} dB')


if __name__ == '__main__':
    main()
