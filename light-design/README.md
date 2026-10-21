# light-design

Light-Science 的研究设计子技能：把定版想法卡变成**可直接开工且
可被证伪的研究设计书**。技能规范见 [SKILL.md](SKILL.md)。

**当前版本：v1.2（封版）**。能力环 D0–D7 全落地：D0 入口承接与
打回（交接六项逐项承接、缺项打回不许临场发明）→ D1 变量与方案
→ D2 对照与消融（对照先行）→ D3 评估协议（判读三向见结果前
写死）→ D4 效度四分法登记 → D5 功效核算（经典分组设计走包内
精确解求解器、余走替代口径）与双货币预算 →
D6 定版评审（异家族硬门 + REVIEW_UNAVAILABLE 降级通道）与冻结
（amendment 分级签核）→ D7 交接四件套导出。质量纪律写死：主张
先行（≤2 + anti-claim）、判读见结果前冻结、冻结后正文永不回改。

> 开发说明：学习期文档、重构草案与完整验收记录属开发档案，
> 不在本仓库；本仓库只有产品本体。

## 快速开始

```bash
python -m venv .venv && .venv/bin/pip install -e ".[test]"

.venv/bin/light-design init ./my-design --direction "番茄病害检测"
.venv/bin/light-design new ./my-design \
    --title "自监督预训练缓解小样本番茄病害分类：对照实验设计" \
    --idea-id <定版卡 idea_id> \
    --from-handoff ./idea-exports/<idea_id>/idea_card.json
# 若交接缺项，new 当场列出打回清单；补齐 designs/<design_id>/design.yaml 后：
.venv/bin/light-design validate ./my-design <design_id>
.venv/bin/light-design advance ./my-design <design_id> --to reviewed
# 定版评审：生成自包含评审包 → 异家族模型/专家评审 → 落盘记录
.venv/bin/light-design review prepare ./my-design <design_id>
.venv/bin/light-design review record ./my-design <design_id> --from-json verdict.json
# （评审不可得时：review record --review-unavailable 显式降级，定版会被硬拦）
.venv/bin/light-design advance ./my-design <design_id> --to frozen
# 交接四件套导出（仅 frozen）与项目报告刷新：
.venv/bin/light-design export ./my-design <design_id>
.venv/bin/light-design report ./my-design
# 冻结后修订只走 amendment（命门字段须 --user-signed）：
.venv/bin/light-design amend ./my-design <design_id> \
    --field evaluation.readout.positive.meaning --value '"..."' \
    --reason "..." --results-seen "未跑任何运行" --user-signed
```

## 设计书字段总表（design.yaml 十一区）

| 区 | 关键字段 | 说明 |
|---|---|---|
| 头部 | `design_id` / `idea_id` / `title` / `tier` / `status` | id = slug_hash6；tier ∈ full / minimal；status 为状态机当前状态 |
| 登记头 `registration` | `visibility` | 结果可见性五档声明（no_runs_yet / pilot_run_unseen / pilot_seen / main_partial_seen / results_seen），第 5 档只许探索性 |
| | `existing_assets` / `software_env` / `designer` | 定版时已有资产、环境版本、设计生成者（模型/家族，复核异族校验用） |
| 承接 `intake` | `source_handoff` / `original_question` | 交接件指针+哈希；原始问题逐字保留 |
| | `spec_intake[]` | 六项逐项承接 {item, handoff_value, design_location, status} |
| | `returned_items[]` | 打回记录 {item, reason, needed, date, resolved}，未清不许离开 draft |
| 主张 `claims` | `primary_claims[]` | ≤2 条 {id, statement, why_it_matters, minimum_convincing_evidence, confirmatory} |
| | `anti_claims[]` | 要排除的反主张 {id, statement, excluded_by}，非空 |
| 方案 `plan` | `variables[]` | 三组（treatment / outcome / covariate）× 取值域（range / choice / fixed 全枚举） |
| | `replication_level` | 独立重复层级声明（n 按此层计） |
| | `intervention_checkpoints[]` | 干预生效核查点（干预须真改变且留证） |
| 契约 `contract` | `controls[]` | 对照组列表，`status_quo=true` 的一等对照必须存在 |
| | `ablations[]` | 消融矩阵 {what_it_tests, expected_if_component_matters, …} 两项必填 |
| | `unnecessary_ablations[]` | 显式登记不做的消融及理由 |
| | `runs[]` | 运行清单 {run_id, role, control_run, depends_on}；处理组必须依赖其对照（对照先行） |
| 评估 `evaluation` | `primary_metric` / `guardrail_metrics[]` | 主指标唯一点名（带惯例出处）与护栏分离 |
| | `readout` | 判读三向 {positive, negative, null} × {meaning, action}，见结果前写死 |
| | `tuning_parity` | 调参对等条款 {statement, details}，必填 |
| | `seeds` / `repetitions` | 种子数与重复数预先定明 |
| | `sesoi` | 结构化 SESOI 登记块（v1.1 DES-D01）{value, unit, direction, bounds, basis, estimand_ref, summary_measure}：全设计单一事实源，确认性设计必登记；登记行只许携带逐字段一致的派生副本；命门字段（amendment 须用户签） |
| 效度 `validity` | `threats[]` | 四分法（conclusion / internal / construct / external）逐项三态 {status: na/mitigated/residual, note} |
| | `structural_checks[]` | 结构错误清单逐项自查 |
| 资源 `resources` | `power` | {sesoi, sensitivity_range, derived{seeds/repetitions/eval_set_size}, sufficient}；不足则须下调声称。分组经典设计另落 `design_size` 求解器落格（v1.2）{form, route, raw_n, per_group_n, groups, total_n, achieved_power, …} + 结构化 `sensitivity_table`，校验器做实际功效拦截与复算拦截，借 derived.repetitions 落每组 n 给警告 |
| | `budget` / `stages[]` / `circuit_breakers[]` | 双货币预算、阶段转移条件、量化熔断线 |
| 冻结 `freeze` | `review` / `frozen_at` / `content_hash` | Stage 1 五条评审记录、冻结时间戳、正文哈希 |
| | `amendments[]` | 只追加 {date, fields, reason, results_seen, user_signed, new_hash} |
| 交接 `handoff` | `expected_registry[]` / `repro_fields` / `checkpoints[]` | 预期登记表、复现字段、人类检查点（export 四件套消费：experiment_brief.md / design_card.json / expected_registry.jsonl / reproducibility.md） |
| 辅助 `aux` | 只许 info_gain_estimates / run_priority_notes / similar_design_refs / history_refs | 与判定物理分离，一律标「暂定」 |

## 状态机门规则清单

主线：`draft → reviewed → frozen`；旁路 `returned / blocked`
（returned 回补后回 draft，blocked 解阻后回 draft）。frozen 为终态，
修订只走 amendment。一切跃迁先过结构+硬规则校验，再过目标门。

| 目标状态 | 门规则（逐项验，任一不过即拦并点名） |
|---|---|
| reviewed | ① validate_design 全过（分级感知硬规则）；② 承接六项全部 accepted/expanded；③ 无未清打回项 |
| frozen | ① 同 reviewed 的校验；② freeze.review 齐全：reviewer/家族/日期落盘、Stage 1 五条逐项 pass、decision=pass；③ review_status ≠ REVIEW_UNAVAILABLE；④ 评审者与设计者不同模型家族；过门即落 frozen_at + content_hash |
| returned | return_record.missing_items 非空 + reason 非空（打回单） |
| blocked | block_record.reason + unblock_condition 非空 |
| draft（自 returned） | 打回项全部 resolved |

极简级（minimal）门：底线六件（主张 / 判读三向 / 对照 / 重复层级 /
可见性声明 / 熔断线）缺一不可，且 claims 不许 confirmatory=true
（不承载确认性主结论）；渲染时带「极简设计 · 不承载确认性结论」标注。

## amendment 分级签核（拍板 ⑤）

冻结后修订只走 `amend` 追加，每条必带 reason 与 results_seen
（改时是否已见结果）。命门字段——`evaluation.readout`（判读标准）、
`evaluation.primary_metric`（主指标）、`claims`（主张）、
`resources.circuit_breakers`（停止规则）——必须 `--user-signed`；
其余字段自动追加留痕。正文任何手改都会被冻结哈希检出
（validate 报错「正文与冻结哈希不一致」）。

## 开发记录（节略）

- 一期：项目骨架 + 设计书系统（design.yaml 十一区）+ 确定性校验器
  （硬规则）+ 状态机与定版门 + amendment 分级签核。测试 87 passed
  （schema 硬规则逐项反例、状态机全流、amendment 签核与哈希链、
  交接导入与打回清单、CLI 全流冒烟）。
- 二期：定版评审子流程（review prepare 生成自包含评审包 /
  record 落盘：同族拒收、五条逐项 + 决议一致性、REVIEW_UNAVAILABLE
  降级通道）、交接四件套导出（仅 frozen，非 frozen 拒绝并列缺口）、
  DESIGN_REPORT 刷新（手工区保留）。测试 119 passed。
- 三期：真实想法卡端到端演示（脱敏摘要见 examples/README.md）+
  SKILL 定版 v1.0。演示结论：完整级设计承接 6/6、校验零错误 →
  reviewed；评审因单模型环境走 REVIEW_UNAVAILABLE，frozen 被
  定版门如实拦下——终点为 reviewed + 评审包就绪，多模型环境
  补完路径明确；缺项变体走通 returned 打回与回补全流程；极简级
  小设计走通底线六件与标注渲染。测试仍 119 passed。
- v1.1（第二轮）：DES-D01 结构化 SESOI 登记块（七字段单一
  事实源、列入命门字段族，Analysis 直读消费）；DES-D02
  amendment 增量评审命令化（类别分流、待审拦导出）；
  DES-D04 intake 跨区实体核查。测试 119 → 161 passed，
  演示复跑 validate 0 错误、终点仍 reviewed（如实）。
- v1.2：功效真计算模块——新增 `light_design/power.py`（纯标准库
  非中心 t/F 精确解）与 `power` 命令：经典分组设计（双臂 t /
  配对 t / 单因素 ANOVA，等分配）的样本量只认精确解，落
  `resources.power.design_size` 原生落格 + 结构化敏感性表；
  校验器做实际功效拦截与登记值复算拦截，z 口径只作速查参照、
  不许充当产出。冻结验收四案全过（P1 每臂 100 / P2 逐点
  394·100·45 / P3 每组 53 / P4 20 对；与 statsmodels 同题
  同数，原值相对误差 1e-6 量级内；旧解析口径在低样本量下
  系统性少算并已被取代，沿革见 SKILL D3/D5 规程第 9 条）。
  测试 161 → 188 passed。

## 已知局限总表（v1.2 封版口径）

1. 真实定版（frozen + 交接四件套导出）尚未在多模型环境走通：
   演示终点止于 reviewed + REVIEW_UNAVAILABLE——与上游卡的跨
   模型硬门是同一个单模型环境限制；流程与补完路径已验证到
   定版门口，最后一步（异家族评审回填）只能等环境具备。
2. 演示承接的是未定版卡：Design 的产品口径只消费定版卡；
   未定版承接仅限演示/预演且必须明示，不构成正式交接路径。
3. amendment 的增量评审已命令化（v1.1 DES-D02）：类别分流
   （预写分支轻评审 / 未预见变更全评审）、增量评审包生成
   与落盘、待审拦导出、REVIEW_UNAVAILABLE 显式落字均已落代码；
   残余边界与第 7 条同：判定内容质量靠评审者规程。
4. 打回单（return_record）须由执行者先行写入 design.yaml 才
   能 advance --to returned：CLI 尚无把 intake 打回清单一键
   组装为打回单的命令（开发期演示中为手工落字后推进）。
5. intake 的 expanded 跨区实体核查已命令化（v1.1 DES-D04）：
   校验器按 schema 冻结映射表逐项到对应区查实体存在性，只改
   状态字不落实体的承接会被点名；残余边界：核查只验实体
   在场，内容口径一致性仍靠定版评审。
6. original_question 的逐字性依赖上游交接件：交接件无该字段
   时工具以卡题名落盘（开发期演示即此情形），逐字保留只对交接
   件自带原文时成立。
7. 评审判定质量靠评审者规程（packet 须知 + 五条标准），工具
   只验结构完整与异家族，不验判定内容质量（与 Idea 查新同界）。
8. 功效替代口径的方差前提（段间 SD 等）设计期无法验证：
   以敏感性范围 + 熔断线对冲，执行期须按实测复核（演示设计
   中已把 SD 恶化情形写进熔断线）。
9. 对账回填（Experiment 执行结果、Analysis 按登记表判定）不在
   本技能范围；本技能只保证登记表可对账。
10. 校验器覆盖可机械验项；抉择质量（基线强度、消融对准度、
    构念映射是否成立）靠规程 + 评审，不假装可验（拍板 ④）。
11. 功效求解器（v1.2）只覆盖等分配双臂 t / 配对 t / 单因素
    ANOVA：不等分配、ANCOVA、多重比较校正、生存/计数结局与
    混合模型的功效未供给，这类设计仍走替代口径并在
    power.method 落字理由；求解前提（正态/等方差/σ 与 f 的
    取值依据）不由求解器验证，靠 basis 落字 + 敏感性表对冲。
