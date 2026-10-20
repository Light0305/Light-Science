# light-review

投稿前内部评审包（Light-Science 子技能）。在 light-write 稿件包成稿后、投稿前运行：做**法医式一致性核查**（主张↔证据↔数字↔图四方对账 + GRIM 族相容性检查）、组织**模拟审稿人组**（可见性矩阵强制互盲、逐席报告冻结、共识门），并以**人工裁决位**守住交付阻断纪律。Review 不改稿、不回注、不改冻结报告；返修归 light-write 的 W7。

设计依据：`../09-review/REDESIGN-DRAFT.md`（拍板 R1–R6 全按推荐）、`../09-review/LEARNING.md`（硬约束 RV-01–RV-18）。

## 状态

**v1.0 已封版（2026-10-20）**，125 项测试全过。封版记录：

- Phase 1：包骨架 + 状态机六态、承接快照、法医层（四边对账 + GRIM 三件）、席位/可见性/冻结/共识 machinery、裁决位与 delivered 阻断。
- Phase 2：领域门三层（通用轴 + 按刊事实层同源现读 + 蒸馏覆盖层格式）、校准门四件 + 验证台、meta 合成与决定建议（full/degraded 双形态）、评审产物自审门、concern 回填清单导出。
- Phase 3 真实演示（`examples/demo-fullrun/`）：承 Write 演示稿件包 + Analysis 演示结论包 + Figure 演示 delivery + Journal-Select 演示 check-record，全程真跑至 **delivered**（隔离 degraded、交付带降档声明；法医四边全可检零发现、GRIM 登记 4 条、领域门 11 条、concern 6 条 4 条共识、decision full 形态 reject_risk、回填 6 条）；变体注入数字被法医咬出 confirmed error 并阻断、裁决位解除。演示中修复自审 wrong_object 库存范围缺陷一处（+3 回归测试）。详见 `examples/demo-fullrun/demo-report.md`，已知局限见 SKILL.md §10。

## 快速开始

```bash
pip install -e .            # 依赖仅 pyyaml
light-review init path/to/review-pkg --title "…" --round 1
light-review intake path/to/review-pkg \
    --manuscript path/to/manuscript-pkg --analysis path/to/analysis-pkg \
    --figure path/to/figure-pkg --intensity standard
light-review forensic path/to/review-pkg
light-review grim path/to/review-pkg --register summaries.yaml   # 可选：登记汇总量跑 GRIM
light-review seat path/to/review-pkg --id S1 --role methods --family claude
light-review panel path/to/review-pkg --seat S1 --draft s1-draft.md
light-review freeze path/to/review-pkg
light-review consensus path/to/review-pkg --file concerns.yaml
light-review advance path/to/review-pkg        # 逐段过门：…→ reported → adjudicated
light-review adjudicate path/to/review-pkg --finding F001 \
    --outcome overruled --by "张三" --reason "…"   # confirmed error 逐条裁决
light-review deliver path/to/review-pkg        # degraded 时须 --degradation-statement
light-review validate path/to/review-pkg
```

## 纪律要点

- **快照即权威**：承接时三包逐文件哈希冻结；上游漂移即 STALE，法医与过门先验快照。
- **两层分类**：数值不一致（error）是门，结论翻转（decision_error）只在不一致已成立且改变结论强度/符号时才许标。
- **共识门**：consensus 须 ≥2 席互盲下独立同向；severity 由代码取各席提案 MAX，佐证数永不抬级（落盘口与校验器双重钉死）。
- **阻断**：confirmed error 未裁决，delivered 过不去；裁决具名 + 理由，追加留痕、发现本体不改。
- **降档明说**：做不到全规格隔离（isolation_mode=degraded）必须登记理由，交付必须带降档声明。
