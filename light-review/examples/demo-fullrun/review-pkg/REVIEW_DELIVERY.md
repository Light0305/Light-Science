# 评审交付清单 — review-pkg（round 1）

- 状态：delivered（2026-10-20）
- 承接稿件：zero-tuning-tracker-thresholds-predicted_c8d0fc（快照哈希 b75d3ab37d9e…）
- 隔离模式：degraded
- **降档声明**：本轮评审隔离降档（degraded）：三席同属单一模型家族（claude），席间独立性仅由文件级隔离（reports/drafts 物理分开、冻结前互不可见）与可见性矩阵保证，无法实现跨模型家族互盲；法医层与领域门为确定性代码检查、不受此限；共识标注与决定建议的置信上限受单家族同源偏差约束。跨家族席位到位后应开新 round 重跑本轮评审。

## 法医发现

- 无（在已登记检查项与敏感性范围内未发现问题）

## 共识账

- RV-C001 severity=major tally=2 consensus=True：主张 C1 含未检验行 R-NEG（数据版本缺 seg-05/06、fundamental 失败 F-0001，untested 终态）而成稿：未检验状态须在摘要与讨论中保持 可见，不得被 limitations 定位稀释。
- RV-C002 severity=major tally=2 consensus=True：R-LONG 与 R-PRED 处理臂段级分布逐值相同、判定 inputs_hash 一致， 两行不构成独立证据；稿件并列陈述五行时须披露同源或合并陈述。
- RV-C003 severity=major tally=1 consensus=False：精度缺口须以数字呈现：校正后 p=0.1378、Type M 最差 4.35、TOST 90% CI 半宽 6.55 对等价界 ±2；结果叙述只写 undetermined 而不带 区间宽度会让读者低估不确定性。
- RV-C004 severity=minor tally=2 consensus=True：判读标准 SESOI 只有文本形态，经演示转写件进入结论包（Design 登 记行无结构化 SESOI，RX-A001 未闭环）；方法节须声明其来源与冻结 时点。
- RV-C005 severity=minor tally=1 consensus=False：图 F001 引用侧溯源断裂：稿件侧源资产为 SVG，图包交付为 PDF/PNG， 无同名文件、哈希对应未检（法医边 not_assessable）；投稿包组装前 图源链应闭合。
- RV-C006 severity=major tally=2 consensus=True：外部效度边界须逐条对齐：单一合成数据集、6 段留出、无跨场/跨季/ 跨机位变异；结论包 boundaries 已登记，稿件讨论不得外推且合成 数据性质须在摘要层可见。

## 领域门

- 条目 11：命中 0、未命中 8、不适用 3（有效命中 0）
- 按刊事实：../../../../light-journal-select/examples/demo-fullrun/selection-pkg/journal/target/check-record.json（verified_at 2026-10-20，状态 verified）

## 决定建议

- 形态 full：建议档位 reject_risk（bounded 非编辑判断，校准门四件齐备）

## 回填清单

- handoff_to_write（6 条）已导出：采纳与执行由 Write 侧决定

## 未尽件（Phase 2）

- 无（Phase 2 件已全部落地）
