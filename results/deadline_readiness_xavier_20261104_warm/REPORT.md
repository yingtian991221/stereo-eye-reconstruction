# Xavier deadline-aware reconstruction：首轮闭环结果

**降低 Full 的超时率得到支持；相对固定 Half 的全图画质优势没有得到稳定支持。中心区域有小幅收益，但独立 profiling 的质量排序尚不可靠。**

这是在真实 Xavier 上执行重建的 **synthetic input-readiness experiment**。输入释放计划与显示序列是模拟的，释放、开始、完成时间和输出像素是实测的。没有测量 Wi-Fi、解码或物理显示，也没有加上历史的 2ms 解码假设。

## 关键结果

下表是三次重复的平均结果。画质针对包含超时停帧的模拟显示序列，使用浮点标准 stereo PSNR；中心固定为图像宽、高各 0.25 的区域。Dynamic 指预先声明的主策略 `Dynamic_whole`。

| 输入就绪变化 | 策略 | Miss rate | 全图 PSNR (dB) | 中心 PSNR (dB) |
|---|---|---:|---:|---:|
| 正常→轻度晚到→严重晚到→恢复 | Full | 48.26% | 16.407 | 16.968 |
| 同上 | Half | 25.00% | 19.607 | 19.503 |
| 同上 | Dynamic | **25.00%** | 19.611 | **19.667** |
| 短时突发 | Full | 18.75% | 20.281 | 20.785 |
| 同上 | Half | 18.75% | **20.334** | 20.683 |
| 同上 | Dynamic | 18.75% | 20.280 | 20.780 |
| 固定种子波动 | Full | 57.29% | 16.845 | 17.658 |
| 同上 | Half | 23.96% | **20.130** | 20.609 |
| 同上 | Dynamic | **23.96%** | 20.111 | **20.641** |

- **预算适应有效。** 分阶段与随机波动下，Dynamic 相对 Full 的 miss rate 分别降低 23.26 和 33.33 个百分点。极紧预算下所有策略都失败；突发条件下所有策略均为 18.75%，没有动态收益。
- **不能声称动态方案全面优于 Half。** Dynamic 与 Half 在三种变化条件下 miss rate 相同；全图 PSNR 差值分别为 +0.004、−0.053、−0.019 dB。分阶段的微小正差与重复间波动同量级，不能据此建立稳定画质优势。按全图 miss–quality 两项指标，Half 在突发与随机条件下支配主动态策略。
- **中心区域有局部收益。** 主动态策略相对 Half 的中心 PSNR 分别增加 0.164、0.097、0.032 dB。这是预先定义的中心指标，不能替代全图结果，也尚不足以证明感知质量改善。

所有固定 FoV 和两个动态目标均保留在 [完整汇总](summary.csv)、[全图 miss–quality 图](figures/miss_quality.pdf) 和 [中心 miss–quality 图](figures/miss_center_quality.pdf) 中。

## 固定配置：速度与画质不是单调对应

19ms 宽预算对照下，全部策略均无超时，生成画质与显示画质相同。以下为同一段 96 帧、三次重复的算术平均。时间包含重建输入绑定、方向转换、设备内复制、重建、融合及同步，不含上传、解码和输出下载。

| 配置 | 平均重建执行时间 (ms) | 全图 stereo PSNR (dB) | 中心 stereo PSNR (dB) |
|---|---:|---:|---:|
| Full | 4.997 | 22.113 | 22.688 |
| Half | 2.646 | 22.145 | 22.510 |
| FoV 0.1 | 2.774 | 22.145 | 22.490 |
| FoV 0.25 | 3.145 | 22.141 | 22.561 |
| FoV 0.5 | 4.277 | 22.147 | 22.635 |
| FoV 0.7 | 5.676 | 22.156 | 22.665 |

尺度指 ROI 宽、高相对于全图的比例。Full 比 Half 的中心 PSNR 高约 0.178 dB，全图 PSNR 却低约 0.032 dB。0.7 比 Full 还慢。因此不能把 ROI 大小同时当作可靠的质量排序和速度排序。

独立 profiling 使用帧 7–22，评估使用帧 39–134。Profiling 的全图质量排序使主策略选择 Full、Half 和部分预算下的 0.7；它没有读当前帧尚未生成的画质或耗时。中心目标的辅助策略 `Dynamic_center` 在可行时偏好 0.1，但这项排序未能迁移到评估段，不能靠测试结果重新排序后再声称策略有效。[冻结的 profile](profile_summary.csv) 和 [策略估计](estimates.csv) 已保留。

## 连续播放与失败边界

- 分阶段预算为 **8.159 → 5.019 → 1.619 → 8.159 ms**，每阶段 24 帧。主策略为 **Full → Half → Half → Full**，每轮只有两次配置切换，没有观察到需要引入滞回的频繁抖动。
- Round 0 中，Full 从帧 63 开始停留在帧 62，最多连续超时 48 帧；Dynamic 在轻度晚到时继续更新，严重晚到时停留在帧 86，连续超时 24 帧。帧 111 恢复后正常更新。其他重复保留在逐帧日志中。
- 固定预算覆盖 −0.5、1.619、2.915、3.563、5.019、6.459、8.159、19ms。−0.5 和 1.619ms 下所有方案均失约；2.915ms 附近仍有调度与执行波动导致的失约，独立均值加安全余量不是硬实时保证。
- 已检查实际输出的目标眼画面与阶段边界原尺寸中心裁剪。可见原重建中的拉伸、细节损失，以及 Half 的模糊；严重晚到产生明显停帧，恢复时场景内容跳变。当前对照不能把这些现象单独归因于 ROI 切换，也不能宣称已经消除边界伪影。没有添加滞回或额外优化。

[动态时序图](figures/timeline_dynamic_whole.pdf) 同时显示实际剩余预算、所选配置、完成余量、生成与显示画质。两种画质在严重晚到阶段明显分离。

## 条件、基线与核验

本轮使用 **Jetson AGX Xavier 32GB，nvpmodel 5 / 30W 4CORE**。一个连续 Driving 15mm forward/aaa 场景，960×540，96 个不同帧；8 个策略 × 11 个条件 × 3 次重复，共 **264 组、25,344 条逐帧记录**，不是 25,344 个独立场景或整个 Driving。

所有策略使用同一组解码后的 GPU resident 输入、双眼交替、精度、完整缓冲清理和已有 fast-clear/fast-resample 优化。没有使用历史 FOV-only-clear 的不对称优化，没有增加 Graph 或跨 refresh 特征缓存。双眼历史由实际接收/重建状态维护；严格交替下，目标眼上一帧来自前一次接收的解码图像，不用 GT 重置。GT 只用于计时后的评价。

固定播放周期为 11.111ms；模拟显示时刻为 `epoch+i×period+20ms`，预留 1ms，因此重建完成截止时间为 `epoch+i×period+19ms`。20ms 和 1ms 是显式模型假设。延后输入不会延后截止时间。独立线程实际释放输入，FIFO 工作线程记录排队、开始和完成；过期帧跳过重建，迟到输出不显示，接收眼状态仍更新，显示复用最近成功双眼帧。

每次 trial 统一预热至少 1s；profiling 按 90Hz 执行，质量统计全部在计时后进行。未锁定频率：262 组开始时为 905.25MHz，2 组为 828.75MHz，全部保留。原始短预热结果及升频诊断单独保存在 [冷启动目录](../deadline_readiness_xavier_20261104/COLD_START_DIAGNOSTIC.md)，没有混入本报告。

全部日志通过固定 deadline、因果选择、帧历史及显示身份核验。另从保存的 **120 对实际图像**独立重算浮点误差，验证了 24 次实际停帧和 88 对成功帧中的接收眼图像；日志与像素重算 MSE 的最大差小于 5×10⁻⁹。[日志核验](audit.json) · [像素核验](image_metric_audit.json)。

原版 Numba/CUDA 的有界同输入对照也已完成：四组 frame 39，各 20 次预热、50 次重复，保留原始清理和 debug 写入。CUDA 平均 GPU 时间 **9.904–9.952ms**，Numba **10.705–11.258ms**。保存输出的标准右眼 PSNR 相差 **0.005–0.038dB**，约 2.0%–3.2% 像素不同，不能声称逐位等价。原实现存在非原子视差写入竞争与 uint8 z-buffer，这是已识别但本轮未修改的共同限制，尚未单独证明其对质量差异的贡献。[对照原始记录与汇总](../deadline_readiness_xavier_20261104/paired_summary.csv) · [基线审计](../deadline_readiness_xavier_20261104/BASELINE_AUDIT.md)。此控制与新闭环的优化及计时边界不同，不能混为同一个 Full 时间。

原 Figure 14 的 **9.4ms = decoding 3.2ms + reconstruction 6.2ms**；本轮没有用 9.4ms 或其中的 6.2ms 作为异环境加速比基线。历史溢出 PSNR 和展示过的微小 loss 不支持新结论。

## 交付与下一步

- [复现程序与命令](../../deadline_experiments/README.md)、[实际命令](commands.txt)、[运行条件与源代码哈希](execution.json)、[源码快照](source_snapshot.tar.gz)。
- [配置](config.json)、[主释放计划](release_plan.csv)、[宽预算计划](release_plan_generous.csv)、`replay/*.csv` 原始逐帧日志、[汇总](summary.csv)、[逐轮结果](per_round_summary.csv)、[切换记录](transition_summary.csv)。
- [预算扫描图](figures/budget_sweep.pdf)、[全图质量对比](figures/miss_quality.pdf)、[中心质量对比](figures/miss_center_quality.pdf)、[配置质量与耗时](figures/generated_quality_latency.pdf)、[主策略时序图](figures/timeline_dynamic_whole.pdf)。PNG 和 PDF 均使用 Pirate 的蓝灰、绿、金色系及论文式字体。
- [90FPS 模拟双眼显示视频](visuals/simulated_display_90fps.mp4)、[6倍慢放检查版](visuals/simulated_display_6x_slow.mp4)、[代表帧](visuals/phase_contact_sheet.png)、[切换前后中心裁剪](visuals/transition_center_crops.png)，以及保存的无损双眼输出。慢放仅用于观察，不代表另一组时间测量。

**下一步最值得做的是验证质量排序，而不是继续扩大 jitter 测试。** 先在另一个独立连续场景检查 Full/Half 的全图与中心差异，定位原重建误差对排序的影响，再用多个独立片段建立稳定的中心质量估计。本轮已经验证了预算控制闭环；TMC 的画质贡献应围绕经验证的中心质量收益展开，不能写成动态 FoV 在所有质量指标上优于固定 Half。
