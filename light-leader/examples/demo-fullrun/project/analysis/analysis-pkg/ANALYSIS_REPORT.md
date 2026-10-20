# analysis-pkg 分析报告

- 状态：blocked
- 执行包：video-threshold-predict_synth01-b2
- Design：video-threshold-predict_synth01 (content_hash `1ed8de06e50e72257c1f57de3b3ce74fb39247e16cfe6de36280653a44d3475f`)

## 判定分布（机械汇总）

| positive | negative | null | undetermined | untested | 登记行总数 |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 4 | 1 | 5 |

## 逐行判定

| 登记行 | 判定 | 象限 | 强度 | 依据规格 | 备注 |
|---|---|---|---|---|---|
| R-FIX | undetermined | undetermined |  | S001 | 主规格校正后 p=1 未达族 α=0.05；分布判据未达门：判定方向概率 P=0.500 < γ=0.75；TOST 未过：等价未挣得，不许落 null |
| R-ORA | undetermined | undetermined |  | S001 | 主规格校正后 p=0.1378 未达族 α=0.05；TOST 未过：等价未挣得，不许落 null |
| R-PRED | undetermined | undetermined |  | S001 | 主规格校正后 p=0.1378 未达族 α=0.05；TOST 未过：等价未挣得，不许落 null |
| R-NEG | untested |  |  |  | 承接预登记：事实层比对为 incomparable：数据版本 vnext 缺 seg-05/06，留出集只有 4/6 段，分布覆盖不完整，不可与登记预期比对；支撑 run R-NEG-a1 有 fundamental 失败 F-0001（FM-2.3）：主张未被检验，不许落 negative；覆盖 n=4 < 登记 repetitions=6：先天精度不足，null 不可判（undetermined 预警） |
| R-LONG | undetermined | undetermined |  | S001 | 主规格校正后 p=0.1378 未达族 α=0.05；TOST 未过：等价未挣得，不许落 null |
