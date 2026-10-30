# PIRATE → Jetson Xavier：CUDA C++ 重建与 FOV 测速

本项目将目前的 Numba 重建/FOV 速度原型移植为 **CUDA C++ `.cu` 程序**，用于在 Jetson AGX Xavier / Xavier NX 上比较全尺寸重建、半分辨率底图和底图加全分辨率注视区的速度。**编译后的测速程序不需要 Python、Numba、PyTorch 或 OpenCV。** Xavier 已有数据集时，在设备上用 NumPy/Pillow 做一次数据导出即可，不需要重新传数据集。

已在 RTX 和 Jetson AGX Xavier 15W 上执行多档 FOV 对照，并增加可选的上采样加速路径。质量与时间、原始记录和限制见下方实测报告。当前程序使用固定 ROI；动态眼动、网络到达和 deadline 调度尚未接入。

## Xavier 已有数据：从 GitHub 开始

仓库公开提供代码、文档和小型实验记录，不包含 Driving 数据集或二进制帧包。使用下面的 HTTPS 地址 clone 无需登录 GitHub。

```bash
git clone https://github.com/yingtian991221/stereo-eye-reconstruction.git
cd stereo-eye-reconstruction

# 一次性导出工具需要这些包；测速程序本身不使用 Python。
sudo apt-get update
sudo apt-get install -y python3-numpy python3-pil

# 改为 Xavier 已有数据的真实目录。
# 此目录下面应直接有 15mm_focallength/ 和 35mm_focallength/。
export DRIVING_ROOT=/path/to/driving__frames_cleanpass/frames_cleanpass
ls "$DRIVING_ROOT/15mm_focallength/scene_forwards/aaa/max_array.npy"
python3 jetson_cuda/export_frames.py --data-root "$DRIVING_ROOT" \
  --out data/xavier_sample --frames 7,39

export PATH=/usr/local/cuda/bin:$PATH
mkdir -p build results/xavier
nvcc -O3 -std=c++14 --fmad=false -arch=sm_72 \
  jetson_cuda/pirate_bench.cu -o build/pirate_bench
./build/pirate_bench --self-test
./build/pirate_bench --manifest data/xavier_sample/manifest.txt \
  --warmup 10 --repeats 100 --roi-width 160 --roi-height 90 \
  --csv results/xavier/first_run.csv

# 跑完整速度矩阵：三个 ROI 大小 × GPU驻留/含上传回传。
PIRATE_BIN=./build/pirate_bench bash jetson_cuda/run_matrix.sh \
  data/xavier_sample/manifest.txt results/xavier/matrix 100
```

`data/`、`build/` 和 `results/xavier/` 都被 Git 忽略。导出读取原数据，输出写在 `data/xavier_sample/`，不会修改已有 PNG/NPY。若四组不全，可给导出命令加 `--workload driving_15_300` 先运行一组。

后续更新代码：在仓库里执行 `git pull --ff-only`，然后重新运行 `nvcc` 编译命令。数据格式和输入不变时无需重新导出。若设备已配置 GitHub SSH 身份，可将 clone URL 替换为 `git@github.com:yingtian991221/stereo-eye-reconstruction.git`。

## FOV level 的质量与时间联合测试

Numba 也已在 Xavier 真实 GPU 上跑通：见 [Numba 环境与重跑说明](jetson_numba/README.md) 和 [四组 frame 39 小样本结果](results/numba_xavier_20261029/README.md)。它使用旧上采样实现，不能直接把与优化 CUDA C++ 的差异解释为语言开销。

[2026-10-27 Xavier 完整有效 Driving 1068 帧报告与原始证据](results/fov_levels_xavier_full_20261027/README.md)。此前的 [64 帧抽样报告](results/fov_levels_xavier_20261027/README.md) 保留供对照。

第一轮 level 定义为中心全分辨率矩形大小：`80x46 / 160x90 / 320x180 / 480x270 / 640x360`。
外围固定为半分辨率重建再上采样；这不是视角度数，也不是不同外围分辨率。
每档都在相同帧上重新测 `full / half_base / fov`，不与 HEVC 比较。

在 Xavier 的仓库根目录，用已有数据运行（NumPy/Pillow 与 nvcc 需可用）：

```bash
git pull --ff-only
bash jetson_cuda/run_levels.sh /path/to/frames_cleanpass results/xavier/levels_01 16 100
```

这会为四组序列各均匀取 16 帧，编译 `sm_72`、自检，跑五档 ROI 和 resident/stream 两种计时。
每配置独立跑三次，每次预热 10 次、计时 100 次；每次只取最后一次计时的实际输出评估质量。
脚本使用 `--batch-frames`，在一个 CUDA 进程中依次评估清单内所有帧，省去重复创建 CUDA 上下文；
每帧仍单独分配、预热、计时，不复用前一帧的重建结果。进程启动与分配均不计入重建时间。
先跑通可将 `16 100` 换成 `2 20`。输出目录必须不存在，避免覆盖旧实验。
64 帧导出约 475 MiB；默认不保留中间图像，保留原始时间 CSV 与日志。

如果已经有导出的 `.pir` 包，可直接运行：

```bash
python3 jetson_cuda/evaluate_levels.py --binary ./build/pirate_bench \
  --manifest data/xavier_sample/manifest.txt --out results/xavier/levels_eval_01 \
  --repeats 100 --quality-runs 3 --timing both
```

`evaluation/summary.csv` 给出每组序列、每档 ROI 的质量与 p50/p95/p99 时间，以及对 full 的 p50 加速比。
`quality.csv` 是逐帧逐次质量，`timings.csv` 是逐次时间，`raw/` 保存原程序 CSV/日志；
`metadata.json` 保存输入/程序哈希、设备环境和参数，板上可用时自动记录 `tegrastats.log`。
只有出现 `COMPLETE` 才表示整轮执行完成。

质量均为**重建右眼对 ground truth**：原溢出公式 `legacy_whole_psnr_db` 保留不变；
另列 `standard_psnr_db`（float64 差分，255 峰值）和 `delta_vs_full_db`（两者对 GT 的分数差）。
全图、固定中心 `160x90`、固定外围、各档自己的 ROI/外围分别计算；跨 level 优先比较固定区域，
避免比较面积变化造成误导。summary 是逐帧/逐次 dB 的算术均值。原 kernel 写入竞争仍存在，
三次独立输出用于观察变化；这些样本不是三条独立视频，也不等于感知质量或完整双眼结果。

GPU resident 包含降采样、重建、上采样和 ROI 合成；stream 的 wall time 另含输入上传和输出回传。
两者都排除文件读取、分配、质量计算和图像保存；`gpu_timeline_ms` 不含传输。
记录原功耗/时钟配置，不自动更改功耗模式；正式比较应保持相同配置并检查温度/频率记录。

### 完整有效 Driving 帧范围

`--frames all` 导出四组 forward 序列的所有有效奇数帧，共 1068 帧（147/387/147/387）；
300 帧组为 7–299，800 帧组为 7–779。这不包含偶数帧交替重建或 backward 场景。
帧包约 7.73 GiB，完整运行使用 `--batch-size 32`，将临时 PPM 限制在约 150 MiB，评估后清理临时图像。

```bash
python3 jetson_cuda/export_frames.py --data-root "$DRIVING_ROOT" --out data/full1068 --frames all
python3 jetson_cuda/evaluate_levels.py --binary ./build/pirate_bench \
  --manifest data/full1068/manifest.txt --out results/xavier/full1068_01 \
  --batch-size 32 --warmup 3 --repeats 5 --quality-runs 1 --timing both --fast-resample
```

这组参数每档每种模式产生 5340 个计时样本，质量逐帧计算一次。它与 64 帧实验的预热/重复次数不同；
比较时应保留参数记录。`quality.csv`、`timings.csv` 逐批追加保存，只有 `COMPLETE` 表示全部完成。

### 可选的上采样加速

编译新版后，给 `pirate_bench` 或 `evaluate_levels.py` 加 `--fast-resample` 可启用
FP32 的 2×双线性上采样，并让线程沿连续像素排列（32×8 block）。默认仍为原 FP64 路径，
便于做同档 ROI 的优化前后对照。当前 2×比例的坐标/权重为二进制可精确表示的分数；
`--self-test` 会验证随机字节图像的 FP32/FP64 上采样逐字节一致。
这不是降低重建几何精度，未更改视差/光流计算；完整输出仍受旧视差 kernel 的竞争写入影响。
开启前后应使用独立输出目录，不能将缩小 ROI 与此优化合并归因。

主机可运行 `python3 jetson_cuda/report_levels.py RUN_DIRECTORY --plot` 汇总并画图（额外需要 matplotlib）。
汇总按实际计时样本计算 p50/p95/p99，质量按帧/独立运行计算，不把一个输出当作多次质量样本。

## 1. 先看这几个文件

| 文件 | 用途 |
| --- | --- |
| `jetson_cuda/pirate_bench.cu` | 全部 CUDA kernel、数据读取、测速、原公式 PSNR、自检；可直接用 nvcc 编译 |
| `jetson_cuda/CMakeLists.txt` | CMake 编译入口，默认 Xavier `sm_72` |
| `jetson_cuda/export_frames.py` | 把现有 PNG/NPY 数据导出成可移动的帧包；仅需 NumPy/Pillow |
| `jetson_cuda/run_matrix.sh` | 一次执行三个 ROI 大小、两种计时范围，并保存 CSV/日志 |
| `jetson_cuda/verify_port.py` | 导出端核对帧包哈希，以及 C++ 图像的分数与原始 PSNR 函数一致 |
| `results/speed_baseline/README.md` | 移植前的 Numba 速度试验与限制 |
| `docs/deadline_aware_foveated_reconstruction.md` | 期刊扩展方案 |

旧 Python 实验脚本仍保留。新的 `.cu` 程序可以独立编译和运行。

## 2. Xavier 环境与编译

建议使用设备已有的 JetPack CUDA 工具链。参考环境为 JetPack 5.x 的 CUDA 11.4；代码使用 C++14 和基础 CUDA Runtime API。Xavier 的架构参数是 **`sm_72`**。不要在 Xavier 上使用 RTX 3080 的 `sm_86` 可执行文件，也不要直接复制 Windows `.exe`。

先在 Xavier 检查：

```bash
uname -m                           # 应为 aarch64
cat /etc/nv_tegra_release
export PATH=/usr/local/cuda/bin:$PATH
nvcc --version
g++ --version
```

若没有 `nvcc`，需要安装/补齐当前 JetPack 对应的 CUDA 开发工具链；只有 CUDA runtime 不足以编译。无需处理 Numba 安装。

如果是已配置 NVIDIA apt 源、已有 GCC 与 CUDA 11.4 runtime 的 Xavier，也可将开发组件解压到项目目录，
无需改动系统 CUDA 安装（本次 R35.6.4 板子已验证）：

```bash
mkdir -p toolchains/cuda114/debs toolchains/cuda114/root
(cd toolchains/cuda114/debs && apt-get download cuda-nvcc-11-4 cuda-cudart-dev-11-4 cuda-cccl-11-4)
for package in toolchains/cuda114/debs/*.deb; do
  dpkg-deb -x "$package" toolchains/cuda114/root
done
export PATH="$PWD/toolchains/cuda114/root/usr/local/cuda-11.4/bin:$PATH"
nvcc --version
```

**最简单的编译方式**，在项目根目录运行：

```bash
mkdir -p build
nvcc -O3 -std=c++14 --fmad=false -arch=sm_72 \
  jetson_cuda/pirate_bench.cu -o build/pirate_bench
./build/pirate_bench --self-test
```

正常会先显示 GPU 名称，再打印 `SELF_TEST_OK`。`--fmad=false` 用于减少与原 Python 浮点计算的差异；测速比较双方使用相同编译参数，不开启 `--use_fast_math`。

也可以使用 CMake（3.10 或以上）：

```bash
mkdir -p build
cd build
cmake ../jetson_cuda -DCMAKE_BUILD_TYPE=Release -DPIRATE_CUDA_ARCH=72 \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc
cmake --build . -- -j2
ctest --output-on-failure
cd ..
```

官方参考：[Xavier compute capability 7.2](https://developer.nvidia.com/cuda/gpus/legacy)、[JetPack 5.1 的 CUDA 11.4](https://developer.nvidia.com/embedded/jetpack-sdk-51)。CUDA 13 已移除 `sm_72` 离线编译支持，优先使用 Xavier 已配置的兼容工具链。[NVIDIA 架构支持说明](https://developer.nvidia.com/blog/navigating-gpu-architecture-support-a-guide-for-nvidia-cuda-developers/)

## 3. 准备数据：先搬小样本，跑通后再扩展

原共享 Driving 树约 134.9 GiB。本机已经为四组 forward workload 复制了约 10.646 GiB 的输入/真值/对照数据，位于：

```text
C:\Users\yingt\Datasets\PIRATE\driving_forward_speed
```

导出器仅把运行需要的当前编码眼、前一帧另一眼、视差、光流、缩放参数和右眼真值打包。960×540 每帧包约 7.42 MiB；四组各取第 7、39 帧约 59.3 MiB，足以做第一次检查。运行端按帧加载，不会把整个数据集一次塞进 Xavier 内存。

在已有 NumPy/Pillow 的电脑上导出，**无需导入任何 Numba 脚本**。本机 PowerShell 示例：

```powershell
& 'C:\Users\yingt\anaconda3\python.exe' .\jetson_cuda\export_frames.py `
  --data-root 'C:\Users\yingt\Datasets\PIRATE\driving_forward_speed' `
  --out 'C:\Users\yingt\Datasets\PIRATE\xavier_sample' --frames 7,39
```

普通 Linux/Python 环境：

```bash
python3 -m pip install numpy pillow    # 只在导出端需要
python3 jetson_cuda/export_frames.py --data-root /path/to/frames_cleanpass \
  --out xavier_sample --frames 7,39
```

输出目录含 `manifest.txt`、`metadata.json` 和 `.pir` 帧包。manifest 使用相对路径，整个目录移动后仍有效。metadata 保存源路径、帧号、参数和每个帧包的 SHA-256。

将项目源代码目录和 `xavier_sample` 一起复制到 Xavier，例如放在：

```text
~/pirate-xavier/
  README.md
  jetson_cuda/
  xavier_sample/
    manifest.txt
    metadata.json
    driving_15_300_0007.pir
    ...
```

可以使用 U 盘、SCP 或 rsync；如果使用提供的移植 ZIP，解压后就是上述结构。请在 Xavier 本地 SSD/eMMC 上运行，不要从共享网络盘计时。

扩大帧集合：

```bash
python3 jetson_cuda/export_frames.py --data-root /path/to/frames_cleanpass \
  --out driving_samples --frames 7,19,31,39,51,63,75,87,99,111,123,135
# 单 workload 的全部原循环帧：
python3 jetson_cuda/export_frames.py --data-root /path/to/frames_cleanpass \
  --out driving_15_300_all --workload driving_15_300 --frames all
```

四组全部导出有 1,068 个帧包，约 7.73 GiB。不要把不同帧集合重复导出进同一输出目录后手动用通配符运行；始终用本次生成的 manifest。

## 4. 在 Xavier 上第一次运行

从项目根目录执行：

```bash
mkdir -p results/xavier
./build/pirate_bench --manifest xavier_sample/manifest.txt \
  --warmup 10 --repeats 100 --roi-width 160 --roi-height 90 \
  --csv results/xavier/resident_160x90.csv
```

每个输入帧都会运行三个模式，轮换执行顺序：

| 模式 | 实际做什么 |
| --- | --- |
| `full` | 原尺寸时间重建 → 视差重建 → 合成 → 7×7 填洞 |
| `half_base` | GPU 降采样到半宽半高 → 同样重建 → 双线性上采样 |
| `fov` | 完成底图，再对原尺寸 ROI 重建，使用 3px halo 填洞和 8px 边缘羽化覆盖底图 |

**默认包含 GPU 降采样成本。** 全尺寸/FOV 都提前分配缓冲区，每次运行都清空 scratch。这里比较的是 CUDA C++ 全尺寸基线与 FOV 的增量工作；不是拿优化后的 FOV 与旧 Python 的逐帧分配开销比较。

改 ROI 大小或位置：

```bash
./build/pirate_bench --manifest xavier_sample/manifest.txt --roi-width 320 --roi-height 180 --csv results/xavier/roi320.csv
./build/pirate_bench --manifest xavier_sample/manifest.txt --roi-width 480 --roi-height 270 --csv results/xavier/roi480.csv
# 注视中心默认在画面中心。以下是 960x540 的合法示例：
./build/pirate_bench --input xavier_sample/driving_15_300_0039.pir \
  --center-x 400 --center-y 240 --roi-width 160 --roi-height 90 --csv results/xavier/offcenter.csv
```

ROI 加 3px halo 必须完全在图像内。越界时程序报错，不会静默裁剪；当前版本没有眼动跟踪器。

## 5. 两种计时范围必须分开看

**默认 `gpu_resident`：** 图片读取、二进制读取、GPU 分配、输入上传在计时外；计时内包括 scratch 清零、kernel 启动、重建、FOV 降采样/上采样/覆盖以及等待 GPU 完成。适合先检查 FOV 的重建计算收益。

**`--stream` 的 `host_transfer`：** 每次从已解码的主机数组上传输入，运行同一重建链，再回传最终图像；复用设备缓冲区。包含上传和回传的主机墙钟耗时，但仍不包含图片/视频解码、网络传输、显示提交。这里使用普通主机内存，没有假设 Jetson 的统一内存等于零拷贝。

```bash
./build/pirate_bench --manifest xavier_sample/manifest.txt --stream \
  --roi-width 160 --roi-height 90 --repeats 100 --csv results/xavier/stream_160x90.csv
```

**`--precomputed-base`** 仅用于对应旧 Numba 的预先缩放输入实验：在计时前做一次降采样，计时内不再包含它。此选项不能与 `--stream` 同用；这种结果必须单独标注，不能与默认结果混合。

一次跑完整速度矩阵：

```bash
PIRATE_BIN=./build/pirate_bench bash jetson_cuda/run_matrix.sh \
  xavier_sample/manifest.txt results/xavier/matrix 100
```

结果包含三种 ROI 大小 × 两种范围共六份 CSV，以及环境信息、标准输出和自检日志。每份 CSV 已包含 full/half_base/fov 三种模式。

## 6. 输出字段与判读

标准输出按帧、按模式显示 wall p50/p95/p99。CSV 每行对应一次实际重复测量：

| 字段 | 含义 |
| --- | --- |
| `wall_ms` | 主机墙钟时间，是否包含传输由 `timing` 决定 |
| `gpu_timeline_ms` | CUDA event 覆盖重建链的时间；即使在 stream 模式也不包含上传/最终下载，包含 GPU 空闲等待主机提交的间隙 |
| `legacy_right_psnr_db` | 此帧此模式最后一次输出的右眼 PSNR，重复填写在各行；不是每次输出都做质量评估 |
| `downsample_included` | 当前模式是否把 GPU 降采样放在计时内 |
| `roi_width/roi_height` | 本次运行的 ROI 配置；full/half_base 不使用 ROI |

先在相同设备、供电/功耗模式、输入帧、ROI 和计时范围下比较 `fov/full`。优先关注 p50、p95、p99 与逐帧变化，不把 FPS 的倒数或单个平均数当作 deadline 保证。全流程显示失约率需要后续接入网络/解码/显示时间线。

Xavier 复现实验前记录 `nvpmodel -q`、`jetson_clocks --show` 和散热/供电情况。`sudo jetson_clocks` 可以锁定时钟以减少变量，但会改变设备的功耗/热状态；若采用，所有方案保持同一设置并记录。AGX Xavier 与 Xavier NX 的功耗模式编号可能不同，不在脚本中硬编码 `nvpmodel -m 0`。可另开终端用 `tegrastats --interval 1000` 记录温度、频率和负载。

## 7. 算法对应关系与保持的行为

| Numba 原型 | `.cu` |
| --- | --- |
| `now_to_prev` / `temporal_roi` | `temporalKernel`，传入输出区域偏移 |
| `left_to_right` / `disparity_roi` | `disparityKernel`，ROI 源区向右扩展最大视差 |
| `composite` | `compositeKernel` |
| `interpolate` | `fillKernel` |
| `clear_scratch` | `clearKernel` |
| `bilinear_upsample` / `overlay_roi` | `upsampleKernel` / `overlayKernel` |

沿用 BGR、uint16 视差/光流编码、`max/min` 解码公式和最近偶数舍入；半尺寸使用 2×2 网格中心最近邻采样，位移参数减半。CUDA block 保持 32×32，行对应 CUDA x，方便与当前原型对照。默认没有进行访存重排、kernel 融合或 block 调参。

**PSNR 公式保持原行为。** `.cu` 明确按 uint8 模 256 做减法及平方，再求平均和 dB；MSE 为零返回 `inf`。没有把差值改成浮点来修正溢出。当前列只评估重建右眼，不是原论文的双眼平均质量结果。

这次移植的参照是已经完整清空 scratch 的速度原型：没有移植旧脚本只清理少数像素的 `init`；移除了未用于输出的 `mask1` 存储和调试回传，并对 full/FOV 同样处理。**仍保留原代码 uint8 深度缓冲和无原子保护的视差竞争写入**，所以真实图像不能要求与 Numba 逐像素完全一致，也还不能称为确定性重建。后续若修正，需要为全尺寸和 FOV 同时修正，再单独报告影响。

## 8. 四组 Driving 输入映射

导出器忠实采用各自 `generate_right` 的输入路径，不能假设四份脚本都读 `8_left`。

| Workload | 当前眼 / 前一眼目录 | 视差目录 | 光流目录 | 输出帧 f 使用的光流帧 |
| --- | --- | --- | --- | --- |
| driving_15_300 | 8_left / 8_right | gray_depth | gray_u_past / gray_v_past | f |
| driving_15_800 | 14_left / 14_right | 05_depth | 025_u_past / 025_v_past | f−1 |
| driving_35_300 | 14_left / 14_right | 05_depth | 025_u_past / 025_v_past | f |
| driving_35_800 | 8_left / 8_right | 05_depth | 025_u_past / 025_v_past | f−1 |

前一眼图像使用 f−1，`max_array.npy`、`max_uv_past.npy`、`min_uv_past.npy` 使用索引 f−1。300 帧组运行奇数帧 7–299；800 帧组按原代码截止到 779。这里固定已有输入比较速度，不宣称已核实端到端 0.1 bpp。

帧包格式：8 字节 `PIRFRM1\0`；little-endian uint32 宽高；5 个 float64 `[max_d,max_u,max_v,min_u,min_v]`；随后是连续 BGR uint8 当前眼、前一眼、uint16 视差、交错 uint16 `[u,v]` 光流、BGR uint8 右眼真值。总字节数为 `56 + 15*W*H`。

## 9. 检查图像和常见问题

```bash
./build/pirate_bench --input xavier_sample/driving_15_300_0039.pir \
  --repeats 5 --warmup 2 --dump-prefix results/xavier/check --csv results/xavier/check.csv
```

会输出 `check_0_full.ppm`、`check_0_half_base.ppm`、`check_0_fov.ppm`。PPM 可直接查看或拷回电脑用 Pillow 转 PNG；文件保存不在计时内。`--dump-prefix` 的父目录需先创建。

| 问题 | 检查 |
| --- | --- |
| `nvcc: command not found` | `/usr/local/cuda/bin` 是否在 PATH；设备是否有 JetPack CUDA 开发工具链 |
| `no kernel image is available` | 是否在 Xavier 本机以 `-arch=sm_72` 编译 |
| `Unsupported gpu architecture compute_72` | 是否误用了移除 Volta 支持的工具链；使用当前 JetPack 兼容版本 |
| `cannot open manifest/frame` | manifest 必须和导出的 `.pir` 保持相对目录关系 |
| `invalid header / truncated frame` | 帧包是否完整，是否使用当前 export_frames.py 导出；核对 metadata SHA-256 |
| ROI 越界 | 检查中心和大小，包括周围 3px halo |
| 速度波动 / FOV 没更快 | 检查功耗、频率、温度、后台 GPU 任务和 ROI 大小；不要混用不同计时范围 |

## 10. 验证状态

已在本机 RTX 3080 Laptop、Windows、CUDA 12.8 编译执行；通过合成图像的 full/base/FOV、自检中的恒等/平移重建与填洞、原 PSNR 溢出规则检查。已读取四组 Driving 的第 7、39 帧并执行三种模式；Xavier `sm_72` kernel 编译检查与 CMake 构建检查记录见 `jetson_cuda/VALIDATION.md`。

**2026-10-27 已完成实际 Xavier 编译、自检和四组 forward 全部有效 1068 奇数帧的五档 FOV resident/stream 测试。** 设备为 Jetson AGX Xavier，L4T R35.6.4，CUDA 11.4，15W。请使用 [Xavier 完整有效范围实测报告](results/fov_levels_xavier_full_20261027/README.md) 的板上数据；前面的 RTX 记录仍只是本机验证。
