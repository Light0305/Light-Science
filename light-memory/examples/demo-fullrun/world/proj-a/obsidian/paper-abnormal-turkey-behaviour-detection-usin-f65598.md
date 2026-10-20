---
light_memory_object: paper:abnormal-turkey-behaviour-detection-usin_f65598
object_type: paper
status: active
tags:
  - stage/Literature
  - status/active
---
<!-- light-memory:machine:start -->
# Abnormal turkey behaviour detection using self-supervised video anomaly detection and multiple object tracking

- 对象：paper:abnormal-turkey-behaviour-detection-usin_f65598（类型 paper，上游 ID abnormal-turkey-behaviour-detection-usin_f65598，状态 active）
- 来源指针：literature / 证据表.jsonl

## 观察
- [证据] 与原版 ByteTrack 相比（2.5 分钟视频平均）：MOTA +8.2、MOTP +0.3、IDF1 +2.7、HOTA +2.2 个百分点，身份切换数 N_ID 减少 166
  - 事实 fact_05f9a32d58ec，有效 2026-10-20 → …
- [证据] 作者自述局限：系统只检测异常行为、不将其分类到具体行为类别，分类留作未来工作
  - 事实 fact_07030cae6e2f，有效 2026-10-20 → …
- [证据] 跟踪阈值经附录 A 逐参数扫描选定且两套时长取值不同：2.5 分钟视频 θ_modIoU=0.99、θ_high=0.7、θ_low=0.68；5 分钟视频 θ_modIoU=0.95、θ_high=0.4、θ_low=0.3
  - 事实 fact_0c5017d20256，有效 2026-10-20 → …
- [证据] 检测数据集规模：人工标注 1,808 帧、共 35,489 只火鸡；头部区域标注由颜色范围与闭运算自动生成
  - 事实 fact_149263c2d134，有效 2026-10-20 → …
- [证据] 异常检测数据：训练集 8 段视频（每段 300 帧、30 fps、仅正常行为、无标注）；测试集 7 段、共 2,167 帧、带帧级标注
  - 事实 fact_3f8620933ca6，有效 2026-10-20 → …
- [证据] Byte³Track 跟踪性能：2.5 分钟视频平均 MOTA 87.7%、MOTP 80.4%、IDF1 90.8%、HOTA 72.0%；5 分钟视频 MOTA 85.4%、MOTP 82.6%、IDF1 89.1%、HOTA 72.5%
  - 事实 fact_48ead41270f3，有效 2026-10-20 → …
- [证据] 训练配置：HF²-VAD 沿用 Ped2 参数（batch size 128、80 epochs、w_r=1.0、w_p=0.1、k=4）；YOLOX 训练 400 epochs、batch 16；硬件为 RTX5000（16 GB）服务器
  - 事实 fact_89ff0bca0377，有效 2026-10-20 → …
- [证据] 数据可用性：作者声明没有共享数据的许可，三套自建数据集未公开
  - 事实 fact_9a86260a9686，有效 2026-10-20 → …
- [证据] modIoU 版并非全指标占优：2.5 分钟消融中其 N_ID=169，高于 IoU 版的 140（表 3）——modIoU 以更多身份切换换取整体跟踪性能
  - 事实 fact_a116a64934f8，有效 2026-10-20 → …
- [证据] 作者自述局限：头部区域采用自动标注，其边界框可能不如人工标注准确；作者预期人工标注训练可带来更好性能
  - 事实 fact_a86e30097d19，有效 2026-10-20 → …
- [证据] 异常检测（YOLOX 检测 + HF²-VAD）在 7 段含异常事件的测试视频上取得 AUROC 92.1%
  - 事实 fact_cc25b1bc3d18，有效 2026-10-20 → …
- [证据] 消融（2.5 分钟平均，表 3）：modIoU 版 MOTA 87.682 / IDF1 90.849 / HOTA 71.95，优于 IoU 版（80.615 / 88.563 / 70.098）与原版 ByteTrack（79.493 / 88.173 / 69.782）
  - 事实 fact_cfb6611dc088，有效 2026-10-20 → …
- [证据] 遮挡个例（图 5）：火鸡身体大部被遮挡时，靠仍可见的头部在第 846 帧被重识别，ByteTrack 则赋予新 ID
  - 事实 fact_de79fe9b29a3，有效 2026-10-20 → …
- [证据] 5 分钟视频基准（表 6）：Byte³Track 五项指标全部最佳（MOTA 85.431、MOTP 82.563、IDF1 89.128、HOTA 72.523、N_ID 78）
  - 事实 fact_fe8f5b873066，有效 2026-10-20 → …
<!-- light-memory:machine:end -->

<!-- light-memory:annotations:start -->
（用户标注区：在这里写下的内容不会被投影覆盖；用 light-memory readback 回读为候选）
<!-- light-memory:annotations:end -->
