# 演示：对 light-experiment 合成执行包的端到端判定（v1.0）

**身份明示**：输入是 light-experiment v1 演示用的**合成自签执行包**
（`light-experiment/examples/demo-synthetic/`，design 自签、非真实
冻结设计，数据为合成集）。本演示只验证 Analysis 的承接 → 判定 →
结论包链路，不传播任何数字为真实结论。完整逐行判定表、逐门数据与
一致性核对见 [demo-report.md](demo-report.md)。

## 终点（如实）

```
intake（Phase 1）→ 账本冻结 → checked → judge → judged → grade
→ graded → review（REVIEW_UNAVAILABLE）→ export → advance 被拦
→ 包停 blocked（delivered 之前）
```

本环境单一模型家族，跨模型复核不可用：按纪律落 REVIEW_UNAVAILABLE
停 blocked，不伪造收据、不由执行者代判。复核恢复后的续推路径写在
demo-report.md §1。

## 结果摘要

| 登记行 | 判定 | 一句话 |
|---|---|---|
| R-FIX | undetermined | 基线重跑与执行期逐段同值、效应 0，但独立口径 90% CI 半宽 6.55 > TOST 界 2，等价挣不到 |
| R-ORA | undetermined | 效应 +5.249、规格全同向，但主规格校正后 p=0.1378 未达 α，Type M=3.34 亦超阈 |
| R-PRED | undetermined | 同 R-ORA（效应 +5.198） |
| R-NEG | **untested** | fundamental 失败 + 事实层 incomparable：未检验 ≠ 不成立（承接预登记） |
| R-LONG | undetermined | 同 R-PRED（长跑分布与 R-PRED 相同） |

主张 C1：support = untested、强度 insufficient（冻结汇总规则：含
untested 行的主张落 untested，不许把其余行平均成 partial）。

## 演示目录

- `analysis-pkg/`：分析包全量产物（analysis.yaml / verdicts.jsonl /
  spec_ledger.yaml / spec_results.jsonl / conclusions.yaml /
  conclusion_card.json / review_packet.md / reflux/RX-A001.json /
  audit 双份 / ANALYSIS_REPORT.md）。
- `judge-data.json`：判定材料（逐可判行两臂段级原始值，来源与口径
  在文件内 note 与 demo-report §5）。
- `inputs/design-sesoi-source.json`：SESOI 演示转写件（合成 design
  的 SESOI 只有文本形态，此为失败模式 F1 的如实处置——登记细节见
  demo-report §2.2，并已生成 standard_gap 回流 RX-A001）。
- `grade-notes.json`：grade 的 boundaries/limitations 输入（规范
  结构化形态）。

## 一期承接记录（Phase 1，保留）

```
init   examples/demo-synthetic/analysis-pkg
intake --execution-card .../video-threshold-predict_synth01-b2/execution_card.json
       --registry       .../inputs/export-good/expected_registry.jsonl
       --design-card    .../inputs/export-good/design_card.json
→ 承接完成：5 行 — 可判 4、untested 预登记 1、undetermined 预登记 0、null 精度预警 1
validate → 校验通过：0 项错误
```

逐行可判性全文在 `analysis-pkg/audit.md`。承接期如实记录的退化：
登记行未带 claim_ref → 校正族退化为单族 `claim:all`（BH-FDR），
族 basis 已落字。
