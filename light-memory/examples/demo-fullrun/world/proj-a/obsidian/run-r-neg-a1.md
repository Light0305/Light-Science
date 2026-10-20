---
light_memory_object: run:R-NEG-a1
object_type: run
status: active
tags:
  - stage/Experiment
  - status/active
---
<!-- light-memory:machine:start -->
# 运行 R-NEG-a1

- 对象：run:R-NEG-a1（类型 run，上游 ID R-NEG-a1，状态 active）
- 来源指针：experiment / failures.jsonl
- 来源指针：light-memory / verdict:demo-driver

## 观察
- [失败] 承接条目登记的数据版本 turkey-barn-vnext-v1 交付不完整（seg-05/06 缺失），登记的实验对象不存在完整形态；执行端无从补齐未交付数据——设计期数据可得性假设在该版本上被证伪
  - 事实 fact_b4282a9043ef，有效 2026-10-20 → …
- [失败] 教训：承接执行前必须核验登记数据版本的完整交付（逐段清单对账）——数据版本交付不完整时，登记对象不存在完整形态、执行端无从补齐，设计期的数据可得性假设会被直接证伪（F-0001，FM-2.3）
  - 事实 fact_d0e2be643aa3，有效 2026-10-20 → …
<!-- light-memory:machine:end -->

<!-- light-memory:annotations:start -->
（用户标注区：在这里写下的内容不会被投影覆盖；用 light-memory readback 回读为候选）
<!-- light-memory:annotations:end -->
