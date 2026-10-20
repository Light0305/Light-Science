# Light-Analysis 演示报告：对 Light-Experiment 合成执行包的端到端判定（Phase 3）

**身份明示**：承接对象是 Light-Experiment v1 演示的**合成自签执行包**
`video-threshold-predict_synth01-b2`（design 自签、非真实冻结设计，数据
turkey-barn-repro-v3 为合成集）。本报告的全部判定只验证 Analysis 的判定
链路（一期承接 → 规格冻结 → 逐行判定 → 强度合成 → 复核门 → 交接），
不构成对任何真实数据的结论。

## 1. 终点状态

包停在 **blocked**：`intake → checked → judged → graded` 四段全过，
`graded → delivered` 被复核门拦下——本环境为单一模型家族，跨模型复核
走 REVIEW_UNAVAILABLE 显式通道（收据未伪造、执行者未代判）。

补复核路径（复核恢复后从 blocked 续推）：异家族复核者（或人类专家）
按 `analysis-pkg/review_packet.md` 对 4 条边界行（R-FIX、R-ORA、R-PRED、
R-LONG，全部 undetermined 行）逐行给出 agree/disagree →
`review import --from-json <回填文件>` 或 `review record --reviewer <名>
--family <异家族>` 落收据 → `advance` 续推 delivered。

终局计数（机械汇总）：positive 0、negative 0、null 0、**undetermined 4、
untested 1**（登记行 5）。主张 C1：support = **untested**，强度
**insufficient**（含 untested 行的主张按冻结汇总规则落 untested，
未检验 ≠ 不成立）。`validate` 全量 0 错误。

## 2. 实跑链路（2026-10-20，light-analysis CLI + 账本 API）

一期已完成 init + intake（5 行：可判 4、untested 预登记 1、null 精度
预警 1——R-NEG 同时带预警与 untested 预登记，以 untested 落字）。本期：

1. **规格集账本冻结**：决策点 estimator（mean_diff / median_diff）×
   outlier_handling（keep_all / trim_extremes），逐点理论正当理由落字；
   可达组合 4 个全展开（≤512 上限内），S001（mean_diff × keep_all）标
   主规格，冻结哈希 `c8f21d2cf235d11e…`。
2. **SESOI 登记（F1 实测）**：先直接对合成 `design_card.json` 的判读
   文本指针 `evaluation.readout.positive.meaning` 登记——工具拒绝
   （取到的是文本『差 ≤2 点』，不是数值），失败模式 F1 按设计触发；
   改由演示转写件 `inputs/design-sesoi-source.json`（转写自上述冻结
   文本、来源与原文逐字留痕）以指针 `evaluation.sesoi` 登记成功，
   快照值 **2.0**（MOTA 百分点）+ 来源哈希落 `spec.sesoi`。同时生成
   standard_gap 回流条目 RX-A001 → Design（SESOI 应由 Design 原生给
   结构化字段，不应靠分析期转写）。
3. **judge**：材料 `judge-data.json`（逐可判行处理/对照两臂段级原始
   值，来源见 §5）→ 4 行落字、spec_results 新增 20 行（4 规格 × 5 行
   矩阵账平：16 computed + 4 not_judged）。
4. **grade**：C1 映射与强度合成 + 数字溯源 9 行（4 行 × 效应量与方向
   概率各一行 + R-NEG 空溯源行一行）；boundaries/limitations 由
   `grade-notes.json` 补入。
5. **review prepare**：复核包生成，边界行 4 条（全部 undetermined 行）。
6. **review record --review-unavailable**：如实落字。
7. **export**：`conclusion_card.json` + `ANALYSIS_REPORT.md` 已产出
   （卡内 status=blocked、review=REVIEW_UNAVAILABLE 随卡传递）。
8. **advance → delivered**：被拦，包落 blocked（见 §1）。

## 3. 逐行判定表（四象限与逐门）

判据口径：族 claim:all（登记行无 claim_ref 退化为单族，BH-FDR，
α=0.05）；γ=0.75；Type M 阈值 2.0；TOST bounds = 登记 SESOI ±2 点。

| 登记行 | 判定 / 象限 | 效应量 | p_raw → p_adj | P(判定方向) | 联合推断（份额 / 中位 / Stouffer） | Type S / M（功效） | TOST | 未过门 |
|---|---|---|---|---|---|---|---|---|
| R-FIX | undetermined / undetermined | 0.000 | 1.0000 → 1.0000 | 0.500 | 1.00 / 0.000 / 1.0000 | 0.070 / 4.35（0.086） | fail（p=0.296，90% CI ±6.55 出 ±2 界） | 方向门、分布门、联合门、等价门全未过 |
| R-ORA | undetermined / undetermined | +5.249 | 0.1006 → 0.1378 | 0.778 | 1.00 / 4.575 / 0.0012 | 0.032 / 3.34（0.113） | fail（p=0.861） | 方向门（校正后 p 未达 α）；校准门（Type M 3.34 > 2.0）同样未过 |
| R-PRED | undetermined / undetermined | +5.198 | 0.1033 → 0.1378 | 0.778 | 1.00 / 4.575 / 0.0012 | 0.032 / 3.34（0.113） | fail（p=0.858） | 同 R-ORA |
| R-LONG | undetermined / undetermined | +5.198 | 0.1033 → 0.1378 | 0.778 | 1.00 / 4.575 / 0.0012 | 0.032 / 3.34（0.113） | fail（p=0.858） | 同 R-ORA |
| R-NEG | **untested**（承接预登记） | — | — | — | — | — | — | 未检验，非判定失败（见 §4） |

四象限分布：significant_not_equivalent 0、significant_but_equivalent 0、
equivalent_only 0、undetermined 4（untested 行无象限）。

逐行说明：

- **R-ORA / R-PRED / R-LONG**：方向证据本身整齐——效应 +5.2 点、方向
  概率 0.778 过 γ 门、规格集全规格同向（份额 1.00）、Stouffer 合并
  p=0.0012，联合门是通过的。落 undetermined 的原因是两道硬门：
  ①方向门要求**主规格**校正后 p < α，实得 0.1378（原始 p≈0.10，
  n=6 段、固定臂 spread 5.717 使标准误≈2.74，t≈1.90）；②即便方向门
  通过，校准门也会拦：以 SESOI=2 为外部假设代入的设计分析给功效
  0.113、Type M=3.34 > 登记阈值 2.0——此量级下过线结果的量级预期被
  大幅夸大，不许落 positive。两门均未靠改数据或改阈值绕行（阈值只许
  开判前在 spec 区登记，本包未改）。这两行不是「没有效应」，是「按
  冻结判据证据强度不够落字」，扩段重开新包是唯一正路（见结论包
  boundaries 的 would_change_if）。
- **R-FIX**：处理臂为基线臂冷启动重跑、对照为执行期分布，两臂逐段
  数值完全相同（确定性重跑），效应 0、P=0.500。判不了 null 的原因
  不是效应不在零点，而是精度：v1 按独立样本口径算得 90% CI 半宽
  6.55 点，远超 TOST 界 ±2 点，等价挣不到 → undetermined 并逐项点名。
  这暴露了 v1 的真实局限——段级配对结构未建模（见 README 已知局限），
  如实记录，不以配对算法在本包内临时改判。
- 落字顺序说明：R-ORA 等三行的行内 note 只点名了先失败的方向门与
  TOST；Type M 未过门的事实落在各行 `type_sm` 字段组内（数值可复
  算），本表据字段组补列，不改变落字。

## 4. untested 行（R-NEG）的落字

承接期预登记、判定期未翻案，note 逐字为：「事实层比对为
incomparable：数据版本 vnext 缺 seg-05/06，留出集只有 4/6 段，分布
覆盖不完整，不可与登记预期比对；支撑 run R-NEG-a1 有 fundamental
失败 F-0001（FM-2.3）：主张未被检验，不许落 negative；覆盖 n=4 <
登记 repetitions=6：先天精度不足，null 不可判（undetermined 预警）」。
该行在规格矩阵中落 4 条显式 not_judged 行（矩阵账平），在数字溯源表
中落显式空溯源行（无数字进结论包，本身可审计）。主张 C1 因此落
untested / insufficient，而不是把其余四行平均成 partial。

## 5. 与 Experiment 事实层的数字一致性核对

judge-data 两臂取段级均值（独立重复层级 = 视频段，段内 3 种子先均值
化，取自各 run 的 `summary.json` 的 per_segment_mean）；逐臂以段级
均值重算 mean / spread（总体标准差口径），与 Experiment 对账
`reconciliation.yaml` 的 readout_actual 逐项比对：

| 臂（run） | 重算 mean | 对账 mean | 重算 spread | 对账 spread | n |
|---|---|---|---|---|---|
| fixed（R-FIX-a1） | 72.638 | 72.638 | 5.717 | 5.717 | 6 |
| oracle（R-ORA-a1） | 77.887 | 77.887 | 2.222 | 2.222 | 6 |
| predicted（R-PRED-a2） | 77.835 | 77.835 | 2.225 | 2.225 | 6 |
| predicted 长跑（R-LONG-a2） | 77.835 | 77.835 | 2.225 | 2.225 | 6 |

全部一致。判定行效应量与对账均值差互洽：predicted − fixed =
77.835 − 72.638 = 5.197（判定行由未取整段值计算得 5.198，差 0.001
为对账表三位小数取整所致）；oracle − fixed = 5.249 同理。冷启动分布
（R-FIX-a2）与执行期分布（R-FIX-a1）逐段相同，与 Experiment 期
「确定性种子使重跑数值由构造相同」的如实折扣记录一致。

## 6. 规格集稳健摘要

4 个 included 规格（S001–S004）× 4 条可判行全部 computed：

- 方向一致性：三条方向性候选行在 4 个规格下效应全为正（均值口径
  +5.20/+5.25，中位口径 +3.95/+3.90），方向份额 1.00，中位效应
  4.575，Stouffer 合并 p=0.0012——结论对估计量选择稳健，规格维度
  不是本包判不下来的原因，精度（n 与固定臂离散）才是。
- outlier_handling 决策点在 v1 只留痕不改计算口径：S001 与 S002、
  S003 与 S004 数值成对相同，这是已知局限的实测形态（见 README
  已知局限 1），方向份额因此只反映 estimator 一个决策点的稳健性，
  不许解读为两个决策点都验过。
- R-FIX 四规格效应全为 0.000、p 全为 1.0000（两臂同分布的构造性
  结果）。

## 7. 演示中发现并修复的产品缺陷

grade 首次运行时 notes 的 boundaries 用了自由字符串条目（规范形态
应为 {claim_id, conditions, not_extrapolatable, would_change_if}
结构），随后 `validate` 在扫描结论包时抛 AttributeError 而非落结构
化错误。处置：①演示 notes 改用规范结构（本报告所述流程为修正后
的实跑）；②`validate.py` 对 conclusions 四类条目加类型守卫，形态
不对落明确错误信息；③新增回归测试
`test_conclusions_malformed_entries_error_not_crash`。修复后全量
109 个测试通过、本演示包 validate 0 错误。

## 8. 复核包与交接产物

- `analysis-pkg/review_packet.md`：自包含复核包（口径宪法 + 全部判定
  摘要 + 4 条边界行全字段），哈希已登记进 analysis.yaml。
- `analysis-pkg/conclusion_card.json`：给 Write 的结构化投影
  （status=blocked、review=REVIEW_UNAVAILABLE、C1 support/grade、
  逐行判定、边界/局限、9 行数字溯源、回流 RX-A001）。
- `analysis-pkg/reflux/RX-A001.json`：standard_gap 回流（SESOI 结构
  化字段缺失 → Design）。
- 探索区为空：本演示无探索条目，未为演示而虚构。
