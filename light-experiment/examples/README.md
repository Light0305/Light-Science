# examples

本目录只放结构示意与演示的脱敏摘要；真实演示产物属开发档案，
不在本仓库内。

## 执行包结构示意（intake 成功后的项目形态）

```
<project>/
├── experiment.yaml                 # 方向级配置（schema_version / version）
└── executions/<exec_id>/           # 一个执行包 = 一份冻结设计的全部执行
    ├── execution.yaml              # 包头：承接快照 + 状态 + 预算账 + 打回清单
    ├── runs/
    │   └── <run_id>/run.yaml       # 四区：身份（冻结）/ 结论（只追加）/ 血缘 / 注释
    ├── events.jsonl                  # 全包事件流（append-only，EV-xxxxxx）
    ├── baseline_acceptance.yaml    # 基线复现验收表（生成即冻结）+ .md 视图
    ├── deviations.jsonl            # 偏离只增账
    │   └── deviation_notices/      # 生效清单公示文件
    ├── failures.jsonl              # 失败只增账（双层分类）
    ├── reflux/
    │   ├── retry_queue.jsonl       # 可重试失败的恢复指引
    │   ├── design_inbox.jsonl      # 设计级失败回流上游
    │   └── idea_dossiers/          # 不可归因负结果档案
    ├── reconciliation.yaml         # 逐行对账表（与预期登记对齐）
    ├── artifacts/                  # 产物登记目录
    ├── execution_card.json         # 给 Analysis 的结构化投影
    └── EXECUTION_REPORT.md         # 人读报告（render 生成）
```

## 端到端演示（脱敏摘要）

开发期演示的输入不是真实冻结设计：上游 light-design 的真实演示
设计停在 reviewed（定版冻结需异家族评审）。演示按时序声明用与
上游导出**同形态的合成四件套**（哈希自洽、自签冻结，身份在演示
报告中明示）承接一个三臂判别实验的模拟计算（纯标准库、秒级），
执行包终点 delivered。实测结论：

- 承接：缺项变体被打回 2 项（缺一份交接件 + 一行登记判读缺
  一向），sanity 门拦截开跑；合格件承接后缺口清零。
- 基线复现验收：执行期读数只作对照，冷启动重跑（新进程 + 空
  目录 + 仅提交物）产物作唯一证据，三层叶子全过、结果叶偏差
  0.50% < 登记容差 2%。
- 执行与偏离：三臂按依赖序跑完；人为直改一条 run 的 params
  被校验器重算哈希当场检出，偏离闭包 = 被篡改 run + 下游
  两条 planned run（人工估计只点名 1 条），作废 + 替代 run
  （--retry-of 血缘）重跑回填。
- 失败与回流：一条 run 因数据版本缺段以 failed_data 终止，
  部分结果登记为抢救产物；分类为 fundamental（附根因与适用
  边界），上游回流条目自动生成，第二人抽验落痕；对账行以
  部分分布 + incomparable（原因落字）回填。
- 恢复：长 run 中途被杀进程 → 心跳静默超阈判 DEAD 留痕 →
  以外部中断正规终止 + 抢救登记 → 新 run 凭段输入内容哈希
  复用未变段、重跑其余完成；被杀尝试的成本已入包级总账。
- 收尾：对账逐行清零 → 整包校验合法 → delivered → 结构化
  投影导出 → 报告渲染。

两处如实打折（演示报告原文口径）：冷启动的「干净环境」以新
进程 + 空目录近似、未做容器/VM 隔离，且模拟为确定性种子
（冷启动与执行期读数逐字一致是构造性质）；预算账为登记制，
熔断触发由测试集覆盖、演示未重复。
