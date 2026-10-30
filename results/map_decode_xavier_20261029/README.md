# Depth / flow 单通道视频解码实测

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
| rgb / rgb | 960×540 | 8.422 | 3.466 | 2.419 | 2.092 |
| depth / q8_lossy | 960×540 | 0.582 | 3.410 | 2.363 | 1.921 |
| depth / pack16_lossless | 1920×540 | 259.723 | 5.943 | 4.704 | 3.780 |
| u / q8_lossy | 960×540 | 0.284 | 3.407 | 2.359 | 1.903 |
| u / pack16_lossless | 1920×540 | 275.912 | 6.021 | 4.824 | 3.959 |
| v / q8_lossy | 960×540 | 0.289 | 3.408 | 2.363 | 1.907 |
| v / pack16_lossless | 1920×540 | 273.573 | 6.172 | 4.878 | 3.947 |

## 数值精度（软件回解，对输入PNG）

单位为原16-bit整数单位；包括8-bit量化和视频有损压缩带来的误差，不能解释为重建图像PSNR。

| 内容 / 方案 | 平均绝对误差 | 最大绝对误差 |
| --- | ---: | ---: |
| depth / q8_lossy | 419.424 | 44895 |
| depth / pack16_lossless | 0.000 | 0 |
| u / q8_lossy | 318.161 | 37440 |
| u / pack16_lossless | 0.000 | 0 |
| v / q8_lossy | 372.805 | 23775 |
| v / pack16_lossless | 0.000 | 0 |

## 完整性与解释边界

56个解码测试中，失败数为0。失败不计为速度结果，原始错误日志也保留。

这些单路结果不能直接代表RGB+depth+u+v并行解码的端到端耗时，也不能简单用RGB耗时除以3。解码后地图的拼接/数值恢复、跨CUDA输入的互操作和重建尚未接成同一条流水线。

编码参数、视频SHA和逐像素精度统计见encoding.json；本机视频在`C:/Users/yingt/Datasets/PIRATE/map_decode_20261029/`，板上在`/home/yingtian/stereo-map-decode-20261029/videos/`。原始逐帧时间、日志及源码快照见evidence.tar.gz。视频与原PNG不提交Git。旧RGB完整视频结果保留在[上轮报告](../hevc_decode_xavier_20261029/README.md)。
