---
light_memory_object: design:zero-tuning-tracker-thresholds_979ee7
object_type: design
status: active
tags:
  - stage/Design
  - status/active
---
<!-- light-memory:machine:start -->
# Zero-tuning tracker thresholds：留一视频交叉验证对照实验设计

- 对象：design:zero-tuning-tracker-thresholds_979ee7（类型 design，上游 ID zero-tuning-tracker-thresholds_979ee7，状态 active）
- 来源指针：design / design.yaml

## 观察
- [方法] 视频级统计量（轨迹长度分布、检测置信分布、目标密度）与最优关联阈值之间存在稳定映射：由视频前 30 秒统计量联合回归出的三阈值，在留出视频上的 MOTA 达到逐段神谕扫描的 98% 以内（差 ≤2 点），且全面优于固定阈值。
  - 事实 fact_56e2ee3f2c33，有效 2026-10-20 → …
- [方法] 只用视频前 30 秒统计量预测的阈值不差于用全程统计量（段级差 <1 点）：部署可在视频开头即完成标定（承卡 unexpected_prediction）。
  - 事实 fact_7b4439d05507，有效 2026-10-20 → …
<!-- light-memory:machine:end -->

<!-- light-memory:annotations:start -->
（用户标注区：在这里写下的内容不会被投影覆盖；用 light-memory readback 回读为候选）
<!-- light-memory:annotations:end -->
