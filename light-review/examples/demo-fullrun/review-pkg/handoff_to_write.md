# 回填清单（Review → Write）— review-pkg（round 1）

- 生成：2026-10-20；条目 6 条；决定形态：full
- 本清单只列建议修订（双指针 + 严重度 + 关闭判据），采纳与执行由 Write 侧决定；Review 不产稿件补丁、不回注（R6）。

- RV-C001（severity=major，consensus=True，动作=fixable-in-text）：主张 C1 含未检验行 R-NEG（数据版本缺 seg-05/06、fundamental 失败 F-0001，untested 终态）而成稿：未检验状态须在摘要与讨论中保持 可见，不得被 limitations 定位稀释。
  - 锚：claim=claims_register:C1；evidence=conclusions:C1#line_verdicts.R-NEG=untested；verdicts.jsonl R-NEG note（fundamental 失败 F-0001）；来源席位 S1、S2；关闭判据 稿件摘要与讨论明示 C1 含一行未检验（附缺段原因），且 limitations 定位与结论包 support=untested 一致。
- RV-C002（severity=major，consensus=True，动作=fixable-in-text）：R-LONG 与 R-PRED 处理臂段级分布逐值相同、判定 inputs_hash 一致， 两行不构成独立证据；稿件并列陈述五行时须披露同源或合并陈述。
  - 锚：claim=claims_register:C1；evidence=verdicts.jsonl:R-LONG 与 R-PRED inputs_hash 同为 62ccc7ade1…；来源席位 S1、S3；关闭判据 稿件在结果呈现处注明 R-LONG 与 R-PRED 处理臂同源（或合并为一行 陈述），不再读作五份独立支持。
- RV-C003（severity=major，consensus=False，动作=fixable-in-text）：精度缺口须以数字呈现：校正后 p=0.1378、Type M 最差 4.35、TOST 90% CI 半宽 6.55 对等价界 ±2；结果叙述只写 undetermined 而不带 区间宽度会让读者低估不确定性。
  - 锚：claim=claims_register:C1；evidence=conclusions:C1/strength.inputs.type_sm_worst=4.345；来源席位 S2；关闭判据 结果段明示主比较的 CI 宽度与 SESOI 界的对比数字。
- RV-C004（severity=minor，consensus=True，动作=fixable-in-text）：判读标准 SESOI 只有文本形态，经演示转写件进入结论包（Design 登 记行无结构化 SESOI，RX-A001 未闭环）；方法节须声明其来源与冻结 时点。
  - 锚：claim=sections/02-methods.md；evidence=analysis inputs/design-sesoi-source.json + reflux/RX-A001；来源席位 S1、S3；关闭判据 方法节写明 SESOI ±2 点的来源（设计判读标准原文）与冻结时点，或 Design 侧补结构化 SESOI 字段后回指登记行。
- RV-C005（severity=minor，consensus=False，动作=fixable-in-text）：图 F001 引用侧溯源断裂：稿件侧源资产为 SVG，图包交付为 PDF/PNG， 无同名文件、哈希对应未检（法医边 not_assessable）；投稿包组装前 图源链应闭合。
  - 锚：claim=figures_manifest:F001；evidence=delivery:fig-1（exports/fig-1.pdf、data/previews/fig-1.png）；来源席位 S3；关闭判据 稿件图登记改指图包交付文件，或图包补登记 SVG 资产并给出哈希 对应。
- RV-C006（severity=major，consensus=True，动作=fixable-in-text）：外部效度边界须逐条对齐：单一合成数据集、6 段留出、无跨场/跨季/ 跨机位变异；结论包 boundaries 已登记，稿件讨论不得外推且合成 数据性质须在摘要层可见。
  - 锚：claim=claims_register:C1；evidence=conclusions:C1/boundaries；来源席位 S2、S3；关闭判据 讨论逐条对齐结论包 boundaries 三项（段集/种子口径、合成集、不外 推），摘要出现合成数据性质声明。
