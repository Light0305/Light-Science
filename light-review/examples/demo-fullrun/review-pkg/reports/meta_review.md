# Meta 评审综合 — review-pkg（round 1）

- 生成：2026-10-20；数据源只有冻结报告、共识账、法医发现账与领域门结果（RV-12：不引用未冻结材料）。

## 合成叙述

- 本轮共 6 条 concern，其中 4 条过共识门；风险分 13.5、支持分 0.0、净分 13.5（不对称合成，meta 决定形态见校准门）。
- 最高严重度关切 RV-C001（severity=major）：主张 C1 含未检验行 R-NEG（数据版本缺 seg-05/06、fundamental 失败 F-0001，untested 终态）而成稿：未检验状态须在摘要与讨论中保持 可见，不得被 limitations 定位稀释。
- 最高严重度关切 RV-C002（severity=major）：R-LONG 与 R-PRED 处理臂段级分布逐值相同、判定 inputs_hash 一致， 两行不构成独立证据；稿件并列陈述五行时须披露同源或合并陈述。

## 共识账

- RV-C001（severity=major，tally=2）：主张 C1 含未检验行 R-NEG（数据版本缺 seg-05/06、fundamental 失败 F-0001，untested 终态）而成稿：未检验状态须在摘要与讨论中保持 可见，不得被 limitations 定位稀释。
- RV-C002（severity=major，tally=2）：R-LONG 与 R-PRED 处理臂段级分布逐值相同、判定 inputs_hash 一致， 两行不构成独立证据；稿件并列陈述五行时须披露同源或合并陈述。
- RV-C004（severity=minor，tally=2）：判读标准 SESOI 只有文本形态，经演示转写件进入结论包（Design 登 记行无结构化 SESOI，RX-A001 未闭环）；方法节须声明其来源与冻结 时点。
- RV-C006（severity=major，tally=2）：外部效度边界须逐条对齐：单一合成数据集、6 段留出、无跨场/跨季/ 跨机位变异；结论包 boundaries 已登记，稿件讨论不得外推且合成 数据性质须在摘要层可见。

## 分歧账

- RV-C003（severity=major，代码取独立提案 MAX；提案：S2=major）：精度缺口须以数字呈现：校正后 p=0.1378、Type M 最差 4.35、TOST 90% CI 半宽 6.55 对等价界 ±2；结果叙述只写 undetermined 而不带 区间宽度会让读者低估不确定性。
- RV-C005（severity=minor，代码取独立提案 MAX；提案：S3=minor）：图 F001 引用侧溯源断裂：稿件侧源资产为 SVG，图包交付为 PDF/PNG， 无同名文件、哈希对应未检（法医边 not_assessable）；投稿包组装前 图源链应闭合。
- 裁断口径：severity 只由代码计算（RV-05），佐证数只影响排序，不抬级。

## 法医与领域门并账

- 法医发现 0 条，其中 confirmed error 未裁决 0 条
- 领域门 11 条，有效命中 1 条：DG-J05

## 优先修订序

- P1 RV-C001（severity=major）：关闭判据 稿件摘要与讨论明示 C1 含一行未检验（附缺段原因），且 limitations 定位与结论包 support=untested 一致。
- P2 RV-C002（severity=major）：关闭判据 稿件在结果呈现处注明 R-LONG 与 R-PRED 处理臂同源（或合并为一行 陈述），不再读作五份独立支持。
- P3 RV-C006（severity=major）：关闭判据 讨论逐条对齐结论包 boundaries 三项（段集/种子口径、合成集、不外 推），摘要出现合成数据性质声明。
- P4 RV-C003（severity=major）：关闭判据 结果段明示主比较的 CI 宽度与 SESOI 界的对比数字。
- P5 RV-C004（severity=minor）：关闭判据 方法节写明 SESOI ±2 点的来源（设计判读标准原文）与冻结时点，或 Design 侧补结构化 SESOI 字段后回指登记行。
- P6 RV-C005（severity=minor）：关闭判据 稿件图登记改指图包交付文件，或图包补登记 SVG 资产并给出哈希 对应。
