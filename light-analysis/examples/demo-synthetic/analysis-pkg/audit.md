# A0 承接与可判性校验 — analysis-pkg

- 校验日期：2026-10-20
- 执行包：video-threshold-predict_synth01-b2（execution_card 哈希 `557af52f78f99e22…`）
- Design content_hash：`1ed8de06e50e7225…`
- 登记行集哈希：`55d1f9d66fdcd240…`
- 哈希对齐：pass

共 5 行：可判 4、untested 候选 1、undetermined 候选 0、null 精度预警 1。

| 登记行 | 角色 | 可判性 | 有效 n / 登记 n | 理由 |
|---|---|---|---|---|
| R-FIX | baseline | 可判 | 6 / 6 | — |
| R-ORA | control | 可判 | 6 / 6 | — |
| R-PRED | treatment | 可判 | 6 / 6 | — |
| R-NEG | treatment | 未检验候选（预登记 untested） | 4 / 6 | 事实层比对为 incomparable：数据版本 vnext 缺 seg-05/06，留出集只有 4/6 段，分布覆盖不完整，不可与登记预期比对；支撑 run R-NEG-a1 有 fundamental 失败 F-0001（FM-2.3）：主张未被检验，不许落 negative；覆盖 n=4 < 登记 repetitions=6：先天精度不足，null 不可判（undetermined 预警） |
| R-LONG | treatment | 可判 | 6 / 6 | — |
