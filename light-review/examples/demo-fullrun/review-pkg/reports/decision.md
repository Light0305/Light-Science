# 决定建议 — review-pkg（round 1）

> bounded 非编辑判断：这是投稿前内部评审的建议姿态，不声称任何编辑决定；最终投稿决定由作者作出（RV-14）。

## 建议档位：reject_risk

## 不对称合成（数值登记可查）

- reject 权重 1.5、accept 权重 1.0（calibration.yaml 不对称登记）
- 风险分 13.5 − 支持分 0.0 = 净分 13.5
- RV-C001：severity=major 权重 2 × 因子 1.5 = 3.0（consensus=True）
- RV-C002：severity=major 权重 2 × 因子 1.5 = 3.0（consensus=True）
- RV-C003：severity=major 权重 2 × 因子 1.0 = 2.0（consensus=False）
- RV-C004：severity=minor 权重 1 × 因子 1.5 = 1.5（consensus=True）
- RV-C005：severity=minor 权重 1 × 因子 1.0 = 1.0（consensus=False）
- RV-C006：severity=major 权重 2 × 因子 1.5 = 3.0（consensus=True）

## 封顶规则（逐条评估）

- 触发封顶规则 0 条。

## 验证台背书

- bench 报表：reports/bench_report.json（config_hash 51e3bc3342a6…，当版在册且与当前配置一致）
- 判别力：误报率 0.0
