# light-review v1 演示报告（demo-fullrun）

驱动：`run_demo.py` 经 CLI 子进程真跑（日志 evidence/run-log.txt，机器事实 evidence/summary.json）。

## 1. 终点状态

- 主演示包终点：**delivered**（隔离 degraded，交付物含降档声明，见 review-pkg/REVIEW_DELIVERY.md）
- 机械计数：{"findings": 0, "confirmed_error_open": 0, "not_assessable": 0, "concerns": 6, "consensus": 4}

## 2. 法医层：逐边结果与覆盖自报

| 边 | 应检 | 可检 | not_assessable | error | decision_error |
|---|---|---|---|---|---|
| claims_evidence | 1 | 1 | 0 | 0 | 0 |
| numbers_numbers | 3 | 3 | 0 | 0 | 0 |
| numbers_figures | 1 | 0 | 1 | 0 | 0 |
| citations_claims | 5 | 5 | 0 | 0 | 0 |

- 发现账为空：在已登记检查项与敏感性范围内未发现不一致（覆盖口径见上表，RV-07）。

逐边要点：
- 主张↔证据：C1 的 grade（insufficient）、support（untested）、五行逐行判定与 writable_form 上限（limitations_only）与结论包逐项一致，登记侧无改写。
- 数字↔数字：N001 5.25 / N002 5.20 / N003 0.0 正文实印与台账一致；复算值（spec_results S001：5.249333… / 5.197833… / 0.0）均落入呈现值舍入区间。
- 数字↔图：F001 在 delivery 中有对应图（fig-1）；哈希对应 not_assessable——稿件侧源资产为 SVG（assets/fig1_threshold_arms.svg），交付文件为 fig-1.pdf / fig-1.png，无同名文件可比；v1.1 起消费图包对应件清单（correspondence）：清单源资产为绘图脚本/源数据/样式 bundle，未覆盖稿件侧登记的 SVG 源资产，按「未覆盖不等于不符」维持未检（RV-C005 仍开）；图注无小数数字，图注未登记数字一项无触发。
- 引用↔主张：正文引用键 3 个（bai2021-enet、dong2025-is、wang2022-attention）均在 references.lock 中有条目且带 entry_hash；C1 的 evidence_refs 五行在结论包登记行中全有着落；Write 审计归档件（audit/audit_report.json）存在。lock 中另有一条未被正文引用的条目（2023-review），本边只验正文侧指针，未引用不计缺失。

GRIM 族（登记 4 条，来源见 inputs/grim-summaries.yaml）：
- GS001 [percent] → **compatible**：存在整数计数 k=4 与报告百分比相容
- GS002 [percent] → **compatible**：存在整数计数 k=28 与报告百分比相容
- GS003 [mean] → **not_assessable**：量表类型 continuous 非整数粒度（连续量不适用 GRIM，硬检将造假阳性）
- GS004 [mean] → **not_assessable**：量表类型 continuous 非整数粒度（连续量不适用 GRIM，硬检将造假阳性）
- 合计相容性本轮未登记：承接范围内的稿件/结论包无「分项—总计」型汇总量，不造条目（接口实况 §7）。

## 3. 领域门结果

- 汇总：条目 11，命中 0、未命中 8、不适用 3（有效命中 0）
- 按刊事实源：../../../light-journal-select/examples/demo-fullrun/selection-pkg/journal/target/check-record.json（verified_at 2026-10-20，状态 verified）——同一事实源指针现读（Journal-Select check-record），未复制第三份。
- DG-U01 → miss：1 条主张证据指针齐全
- DG-U02 → miss：3 个数字溯源齐全
- DG-U03 → miss：4 条引用撤稿状态已登记
- DG-U04 → miss：1 幅图图注齐全
- DG-U05 → miss：方法类与结果类章节都在
- DG-J01 → miss：全文词数 1000 vs 限额 8000
- DG-J02 → miss：摘要词数 84 vs 限额 250
- DG-J03 → not_applicable：目标刊记录未登记 D.figure_limit，本条未触发
- DG-J04 → not_applicable：目标刊记录未登记 D.reference_limit，本条未触发
- DG-J05 → miss：目标刊要求 AI 披露，稿件章节中检出披露声明（多形检索命中形态：declaration of ai use）
- DG-J06 → not_applicable：稿件未登记关键词清单，本条无对象

## 4. 共识账

| concern | severity（代码 MAX） | tally | consensus | 提出席位 |
|---|---|---|---|---|
| RV-C001 | major | 2 | True | S1, S2 |
| RV-C002 | major | 2 | True | S1, S3 |
| RV-C003 | major | 1 | False | S2 |
| RV-C004 | minor | 2 | True | S1, S3 |
| RV-C005 | minor | 1 | False | S3 |
| RV-C006 | major | 2 | True | S2, S3 |

陈述全文见 review-pkg/consensus.yaml 与三席冻结报告 reports/S1.md、S2.md、S3.md（哈希钉住）。

## 5. 校准门与决定形态

- 验证台：9 例，passed_all=True，干净例误报率 0.0；逐类检出：{"citation_gap": {"total": 1, "detected": 1, "detection_rate": 1.0}, "claim_overreach": {"total": 1, "detected": 1, "detection_rate": 1.0}, "grim_incompatible": {"total": 1, "detected": 1, "detection_rate": 1.0}, "missing_evidence": {"total": 1, "detected": 1, "detection_rate": 1.0}, "number_inconsistency": {"total": 1, "detected": 1, "detection_rate": 1.0}}
- bench 前 calibration 评估 rc=1（缺验证台报表），bench 后四件齐备。
- 决定形态：**full**，档位 **reject_risk**（bounded 非编辑判断，见 reports/decision.md；封顶规则触发留痕在该文件内）。

## 6. 自审与回填

- 自审门 passed=True：vague_unsupported=pass、wrong_object=pass、praise_only=pass、mere_restatement=pass、contradicts_frozen=pass
- 回填清单：6 条（动作分类 {"null": 6}），handoff_to_write.md/.json 已导出；Review 只出清单不出补丁，采纳与执行归 Write。

## 7. 变体（注入数字不一致，不进交付）

- 注入：[num:N001] 正文实印值 5.25 → 5.52（稿件副本 sections/03-results.md，台账仍 5.25）
- 法医发现 F001 [confirmed_error/inconsistency] 数字 N001 正文实印 5.52 ≠ 登记 5.25
- adjudicated 门阻断：advance rc=1，缺口点名未裁决发现 ['F001']（confirmed error 未裁决不许过门，R2 硬度 a 成立）。
- 人工裁决位逐条 confirmed 落字后 advance 通过，变体包终点 adjudicated（未 deliver，按设计止步）。

## 8. 与上游包的接口实况

- 稿件包（Write demo-fullrun/manuscript-pkg，状态 audited）：五件核心文件 + sections 六节齐全，直接承接。
- 结论包（Analysis demo-synthetic/analysis-pkg）：conclusions.yaml / verdicts.jsonl / spec_results.jsonl 齐全；number_provenance 在 conclusions.yaml 内（法医边 (b) 的复算源），judge-data.json 在包外同级目录，未承接、仅作 GRIM 登记的数据来源注记。
- 图包：delivery.yaml 不在图包根，而在 figure-pkg/exports/delivery.yaml——承接按 delivery 所在目录（exports/）传入，图包快照只钉该文件；这是上游 Figure 包的交付件布局与 Review intake「包根 delivery.yaml」预期之间的真实错位，本轮以路径适配并在此落字。
- 目标刊记录：Journal-Select 演示 check-record（九组）与本稿件包内的 Write template_record.json 是两份不同演示的记录；本轮按任务口径用选刊记录（Smart Agricultural Technology，H 组 verified_at 2026-10-20）。intake 读顶层 verified_at 得 None（该记录的 verified_at 在 H 组内），领域门按 H 组现读判定为 verified——顶层字段口径差在此落字，不影响判定。
- GRIM 合计相容性无真实条目可登记（见 §2）。均值粒度两条因 MOTA 为连续量被适用性硬门判 not_assessable——这是硬门按设计工作，不是数据缺失。
- 本环境单模型家族：isolation 登记 degraded 并附理由，交付带降档声明（见 REVIEW_DELIVERY.md）——这是本演示的诚实终点。

