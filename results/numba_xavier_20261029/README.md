# Xavier Numba 小样本实测（2026-10-29）

**Numba 已在真实 Xavier GPU 上运行成功**，不是 CUDA simulator。独立 Python 3.8 虚拟环境：Numba 0.58.1 / llvmlite 0.41.1 / NumPy 1.24.4 / Pillow 10.4.0，CUDA 11.4，SM72。

范围：四组 Driving，各自第 39 帧（960×540），每条路径 100 次计时。不是完整 Driving 质量复测。原始 kernel 及 PSNR 未改，沿用 uint8 溢出公式。

## 各配置结果

以下是 wall latency p50，单位 ms；p95/p99 和全部逐次时间见各模式 result.json。
source 包含分配、参数 NPY 读取、上传/下载及中间 debug 下载，PNG 已缓存、保存被抑制。
其余列为复用缓冲区的 resident 原型，含 Python launch 与同步，不含传输、分配、I/O。
source 和每种 resident 变体各有一次不计时调用，排除首次 JIT；这不保证已达到稳态。

### mode7_15w

| Driving | source | full | half-base | FOV160×90 | FOV320×180 | FOV480×270 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| driving_15_300 | 48.609 | 14.653 | 8.302 | 8.923 | 10.299 | 12.487 |
| driving_15_800 | 49.078 | 14.421 | 8.312 | 8.900 | 10.280 | 12.465 |
| driving_35_300 | 46.652 | 14.536 | 8.299 | 8.910 | 10.322 | 12.518 |
| driving_35_800 | 47.525 | 14.534 | 8.356 | 8.936 | 10.331 | 12.538 |

CPU 温度范围 36.5–38.5°C。

GPU 温度范围 33.5–37.0°C。

[原始 JSON](mode7_15w/result.json) · [环境](mode7_15w/environment.txt) · [tegrastats](mode7_15w/tegrastats.log)

### mode5_30w

| Driving | source | full | half-base | FOV160×90 | FOV320×180 | FOV480×270 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| driving_15_300 | 44.719 | 11.003 | 6.324 | 6.775 | 7.808 | 9.448 |
| driving_15_800 | 42.795 | 10.847 | 6.327 | 6.772 | 7.810 | 9.428 |
| driving_35_300 | 44.155 | 10.889 | 6.345 | 6.793 | 7.853 | 9.471 |
| driving_35_800 | 44.154 | 10.974 | 6.387 | 6.811 | 7.860 | 9.508 |

CPU 温度范围 36.0–38.0°C。

GPU 温度范围 33.0–36.5°C。

[原始 JSON](mode5_30w/result.json) · [环境](mode5_30w/environment.txt) · [tegrastats](mode5_30w/tegrastats.log)

## 15W → 30W：同帧同实现

| Driving | full 加速 | FOV160 加速 | FOV320 加速 | FOV480 加速 |
| --- | ---: | ---: | ---: | ---: |
| driving_15_300 | 1.33× | 1.32× | 1.32× | 1.32× |
| driving_15_800 | 1.33× | 1.31× | 1.32× | 1.32× |
| driving_35_300 | 1.33× | 1.31× | 1.31× | 1.32× |
| driving_35_800 | 1.32× | 1.31× | 1.31× | 1.32× |

## 原始调用的启动趋势

| 模式 / 序列 | 前10次中位数 (ms) | 末10次中位数 (ms) |
| --- | ---: | ---: |
| mode7_15w / driving_15_300 | 75.415 | 47.155 |
| mode7_15w / driving_15_800 | 49.233 | 46.242 |
| mode7_15w / driving_35_300 | 48.266 | 46.591 |
| mode7_15w / driving_35_800 | 47.940 | 47.807 |
| mode5_30w / driving_15_300 | 61.073 | 43.721 |
| mode5_30w / driving_15_800 | 42.943 | 43.375 |
| mode5_30w / driving_35_300 | 48.985 | 44.365 |
| mode5_30w / driving_35_800 | 43.442 | 44.214 |

## 解释与复现

- 模式7：15W Desktop，4核 CPU 上限2.1888GHz，实读GPU上限675.75MHz。模式5：30W 4CORE，实读CPU上限1.8048GHz、GPU上限905.25MHz（配置目标1.78GHz/900MHz，EMC配置1600MHz）。这些是频率上限，不是计时期间恒定频率。30W并非所有频率都更高；模式切换在两轮测试之间完成。
- 未执行 jetson_clocks；使用动态调频。tegrastats 提供CPU频率、温度及GPU利用率，但这台板的日志没有GPU实际MHz，不能据此宣称GPU频率固定。
- 15W 第一组 source 前10次中位数约75.4ms、末10次约47.2ms；30W 第一组约61.1ms到43.7ms，均有明显启动趋势。source数字仅为这轮观测，不称稳态延迟。resident路径更稳定，仍是单帧小样本。
- resident也有轻微漂移：30W的35mm/800组，full前10/末10中位数为11.925/10.983ms，FOV160为7.119/6.786ms；一次预热不足以宣称所有路径完全稳态。功耗模式测试顺序为15W后30W，未做往返重复或置信区间。
- 原始部分初始化、uint8深度缓存和非原子竞争写入仍保留；resident原型另做完整scratch清零。两者不能视为逐像素等价实现。ROI检查确认有像素变化且ROI外0变化。
- Numba FOV使用旧bilinear上采样，未移植CUDA C++的fast-resample；不能把与优化C++的差异解释为语言开销。全1068帧C++结果仍见[原报告](../fov_levels_xavier_full_20261027/README.md)。
- 初次JIT报错来自提取工具链的libcudart悬空链接；接到板上已有11.4运行库后成功，无需修改Numba或驱动。首次失败日志与30次smoke记录独立保留。
- [重跑说明](../../jetson_numba/README.md)、[环境依赖](requirements.txt)、[输入及程序哈希](provenance.json)。板上实验目录 `/home/yingtian/stereo-numba-20261029/`。
