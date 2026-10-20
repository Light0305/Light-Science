# 程式化核查（advisory · 只报不改）

- 稿件哈希：`9544b862a48218c9…`
- 判定性质：建议层，不阻断定版；findings 共 0 处
- 时间：2026-10-20T18:45:55+00:00

## Findings

（无触发标记命中）

## 不改表（永不作报警依据）

- sentence_length_variance：句长参差：长短句交错是人类写作常态，不作 AI 味证据
- passive_voice：被动句：方法节被动语态是规范常态，不许以被动率报警
- nominalization：名词化：术语名词化是学术语体的构成方式，不许据此改写
- hedging_and_qualifiers：限定与对冲词：承载证据强度，信息守恒——核查只报不改，改写不许删限定词
- ordinal_real_sequence：真实时序的序数步骤：操作流程的真实先后用序数是合法结构；序数脚手架规则只提示复核是否为空转衔接
- intentional_parallelism：有意排比：内容逐项不同的平行结构是修辞选择，与同构空转的区别在内容，不在句式
