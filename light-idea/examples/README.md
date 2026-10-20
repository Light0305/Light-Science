# examples 说明

本目录只放**结构示意**，不放真实运行产物：没有真实想法卡全文、
没有查新证据池、没有链素材与对决记录原件。想看真实跑通的形态，
请用自己的一个研究方向按 [../README.md](../README.md) 的命令走
一遍。

## 一个方向项目（`init` 产物）的目录形态

```text
my-direction/                       # 一个研究方向 = 一个项目目录
├── project.yaml                    # 方向名与项目元信息
├── index.yaml / index.md           # 全池索引（list/report 刷新）
├── cards/
│   └── <idea_id>/                  # 一张想法卡一个目录（slug_hash6）
│       ├── idea.yaml               # 卡本体（字段总表见 README）
│       └── card.md                 # 卡面渲染（概念定版/试点标注横幅在此）
├── novelty/<idea_id>/              # 查新证据包（prepare 落盘）
│   ├── evidence.jsonl              # 证据池：每条含来源/题名/作者/年份/DOI/命中面
│   ├── queries.json                # 查询式与逐式日志
│   ├── pool_report.md              # 各源状态与已知盲区声明
│   └── verdict.json                # 判定收据存根（verdict 落卡时写入）
├── chains/<chain_id>/              # 演进链素材（chain 落盘，只取材不生成）
├── exports/<idea_id>/              # 交接三件套（只对定版卡）
│   ├── design_handoff.md           # 给 Light-Design 的交接说明
│   ├── idea_card.json              # 定版卡机器可读形态
│   └── memory_export.jsonl         # 跨周期留痕导出（等 Light-Memory 收编）
└── idea-stage/
    ├── IDEA_REPORT.md              # 唯一权威文档：折叠各环结论
    ├── candidates.md               # Landscape 缺口图 / 候选与切换日志
    ├── research_contract.md        # 方向契约
    └── dedup_report.md             # 去重报告（只报告不删卡）
```

## 端到端演示（脱敏摘要）

开发期曾以一篇已发表的家禽行为监测论文为种子做过一次完整演示
（方向：禽舍视频异常行为检测），全过程结论如下，原始产物属开发
档案、不在本仓库：

- `chain` 两跳实查百余条引文邻居落盘成链素材（其中一源全程限流
  429，盲区如实记录）；演进链算子产 4 卡、远域碰撞算子产 2 卡，
  全部真实落卡、provenance 完整。
- 去重率 0.0；5 卡过粗筛进 screened，1 卡被「数据不可得」客观门
  如实拦在 draft 并附复活条件。
- 两两对决 4 场定序，top 卡跑真实查新：证据池百余条（四源中两源
  全程 429，覆盖盲区写入卡面），判定 PROCEED_WITH_CAUTION。
- top 卡 pre-mortem 六项全过 → `pre_mortem_passed`；定版被两道门
  如实拦下：①跨模型收据硬门（演示环境为单模型家族，走
  REVIEW_UNAVAILABLE 降级，不伪造收据）；②最接近工作未过
  Light-Literature 核实口径——其后已补核实：三篇最接近工作逐条
  按 Literature 的 `verify-identity` 同标准（Crossref + Europe
  PMC 对账）全部核实通过并回填 `verified=true`，重跑定版后拦截
  项只剩跨模型硬门一道，卡保持 `pre_mortem_passed`，待多模型
  环境补判定收据后即可定版并导出交接三件套。
