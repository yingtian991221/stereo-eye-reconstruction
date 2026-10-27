# CUDA 移植验证记录

## 2026-10-27：Xavier 实机补充

已在 Jetson AGX Xavier（L4T R35.6.4、CUDA 11.4.315、15W Desktop mode 7）完成编译、自检及五档 ROI 的 resident/stream 对照。
可选 `--fast-resample` 的 FP32/连续像素线程上采样通过随机字节图像与 FP64 逐字节一致性检查。
原始计时、逐帧质量、温度和源码快照见 [板上实测报告](../results/fov_levels_xavier_20261027/README.md)。
真实重建仍保留旧版竞争写入，完整图像不保证逐像素一致；不要将上采样模块的一致性检查扩大为整条路径的确定性保证。

## 2026-10-02：历史工作站验证

日期：2026-10-02。执行设备：Windows 本机 RTX 3080 Laptop（SM 8.6），CUDA Toolkit 12.8.61，MSVC 19.44；不是 Xavier 实测。

已完成：

- 直接 nvcc 编译原生 SM 8.6 可执行程序，并实际运行。
- CMake Release 构建通过，CTest 的 GPU self-test 1/1 通过。
- 同一 `.cu` 源码以 `-arch=sm_72` 编译 PTX 和 cubin 均通过。只确认 kernel 可以为 Xavier 架构生成代码，未确认 Xavier 的 Linux/JetPack 运行环境。
- GPU 自检验证常量图像的 full/half_base/fov 输出；非恒定图像零视差恒等变换；无竞争的平移视差、光流补偿与 7×7 填洞结果逐字节匹配 CPU reference。
- 非恒定输入的 ROI 覆盖与羽化逐字节匹配参考结果，ROI 外保持底图像素。
- PSNR 自检保留 uint8 减法/平方溢出和零 MSE 时 `inf`。
- 导出四组 Driving 各第 7、39 帧，共 8 个包、62,208,448 字节。包 SHA-256 校验通过。
- 8 帧 × 3 模式在默认 GPU 降采样计时模式运行，生成 480 行 CSV（20 次重复）；`--stream` 配置运行 240 行 CSV（10 次重复）。数据见 `../results/cuda_port_validation/`。
- 24 张导出 PPM 的 C++ PSNR 数值与从对应原 `test_numba.py` AST 提取的 `calculate_psnr` 完全一致到 1e-7 dB 容差。
- 单帧 `--precomputed-base` 和偏移 ROI 运行通过。
- `run_matrix.sh` 通过 Bash 语法检查；Linux/Xavier 上的完整脚本执行待设备验收。

验证命令（工作站，需要 NumPy/Pillow，不需要 Numba）：

```bash
python3 jetson_cuda/verify_port.py --data-root /path/to/frames_cleanpass \
  --package xavier_sample --csv /path/to/resident.csv \
  --dump-prefix /path/to/sample
```

`resident.csv` 与 `sample_0_full.ppm` 等文件必须来自同一次 `--dump-prefix sample` 运行。真实 Driving 上的 C++ 输出不保证与 Numba 逐像素一致，因为两者仍有旧版无原子保护的视差写入；上述验证不代表已经消除了这个问题。

尚待 Xavier 验收：本机编译、`--self-test`、三种 ROI 的 resident/stream 矩阵、功耗/时钟/温度记录。请保留真实设备输出，不能用本报告的 RTX 日志代替。
