# light-memory

Light-Science 的研究记忆层：沉淀前序八包 + 选刊的结构化产物与事件，支持跨会话恢复、跨项目复用、失败经验防重复试错，并为 Obsidian 轻量图谱视图供给精选笔记与真实关系。Memory 独立于 Obsidian——不用 Obsidian 时记忆照常工作，视图只是可整删重建的投影。

## 核心设计

- **真相在文件，索引全派生**：真相层 = 人可读的 MD/JSONL 文件；向量/FTS 索引只是可整删重建的影子，删索引不丢任何记忆（测试钉死）。黑盒记忆后端整类排除。
- **三层数据模型**：事件只增（原文留存）、事实可失效（双时间 + 溯源）、笔记给人读；摘要与画像都是派生视图，永不替代原始证据。
- **取代链**：生态里最薄、Light 原料最厚的一环——模型只提名，失效由代码按双时间区间算术执行；旧版保留可查、派生失效自动标 stale、争议只登记不裁决、支持 as-of 回溯。
- **沉淀三段制**：捕获全自动、确定性提炼全自动、判断性提炼只产候选人工生效（Phase 2）；判定走封闭五值词表（store / skip / supersede / merge / dispute），物理删除退出词表。

## 状态

**v1.0 已封版（102 测试）**：登记头与四账（对象注册/事件/事实/关系）+ 争议账、九包 + 选刊的 M0 承接适配器（水位线、快照漂移、缺口点名）、取代链核心（五值落账、区间算术、派生 stale 传播、争议裁决、as-of 回溯）、索引层（FTS5 + 向量、同步台账、可整删重建）、校验器；候选通道（判断性提炼只产候选、人工 accept 生效、Review 蒸馏双向接口）、检索三路与渐进披露（五配方、效力过滤、四封顶）、Obsidian 单向投影与标注回读、画像视图与立场视图、自建评测集运行器（只报数不判线）、跨项目晋升通道。落地状态见 SKILL.md §8。

**v1.1 增量（v1.1 封版，测试 123 passed + 1 skipped）**：epilogue 会话沉淀规程（对话决策/死胡同六类清单扫描、只产候选）；真实嵌入接入（local ONNX / api 登记制）+ 正式题集 50 题重跑 39/50（报表 `bench_report_v11.json` 与首测并列存档；通过线状态仍以 SKILL.md §8 第 5 条为准，本文件不另行表述）；Obsidian 投影升级（frontmatter 可查询面、关系类型边双写、validate 视图层体检）；桥类与排除项封口；`candidate list` 默认值修复。

**v1.1 集成步增量（MM2-13）**：M0 承接面补新三包适配器——light-patent（案件即对象、状态流转/期限即事件、查新与 worth-it 判断即事实）、light-software-copyright（案件即对象、确认与工具留痕即事件、登记事实与源码冻结快照即事实）、light-crawler（工作区/目标即对象、批次/预检/变更即事件、留存凭据即事实）；适配器版本登记、水位线幂等与溯源五字段纪律与既有适配器同口径。

**封版记录（Phase 3）**：真实演示 `examples/demo-fullrun/` 沿火鸡主线把九包 + 选刊的真实演示产物收编进一个记忆项目，全链真跑至三包 validate 零错误（主项目终局：对象 26 / 事件 88 / 事实 30 / 关系 16）；构造第二代结论包实测取代 + 派生 stale 传播，Obsidian 投影 15 文件 + 标注回读全链走通，跨项目晋升一条。评测首测：正式题集 50 题总命中 34/50（知识更新旧答案误答率 0、跨项目 7/8、失败复用 6/10、拒答 7/10、释义 9/12），报表在演示 evidence 内；通过线状态以 SKILL.md §8 第 5 条为准（本文件不另行表述，建议线出处见 demo-report §9）。已知局限见 SKILL.md §10。

## 快速上手

```bash
pip install -e .

light-memory init <项目>/memory --project <项目ID>
light-memory ingest <项目>/memory --package analysis --source <结论卡 conclusion_card.json>
light-memory ingest <项目>/memory --package experiment --source <执行包目录>
light-memory verdict <项目>/memory --file nominations.json   # 判定提名落账
light-memory facts <项目>/memory --as-of 2026-10-01           # 双时间回溯
light-memory index <项目>/memory rebuild                      # 从真相重建索引
light-memory validate <项目>/memory                           # 四账一致性校验
light-memory status <项目>/memory

# Phase 2
light-memory epilogue scan --file <会话记录.md> --out scan.json   # 会话切段（MM2-01）
light-memory epilogue <项目>/memory apply --scan scan.json --file noms.json  # 只产候选
light-memory candidate <项目>/memory propose --kind fact --file cand.json --nominator <提名者>
light-memory candidate <项目>/memory accept --id <候选ID> --by <确认人>   # 未 accept 不入账
light-memory recall <项目>/memory "MOTA 提升" --recipe default --depth 1  # 三路回供 + 渐进披露
light-memory project-obsidian <项目>/memory                   # 精选笔记单向投影入 vault
light-memory readback <项目>/memory                           # 视图标注回读为候选
light-memory profile <项目>/memory build                      # 画像两文件再生（只装处置与指针）
light-memory bench build-world <世界目录> && light-memory bench run --world <世界目录> --set mini
light-memory promote <全局层>/memory propose --from <项目>/memory --fact-id <事实ID> --by <提名者>
light-memory distill-export <项目>/memory                     # 蒸馏语料按 Review 覆盖层格式导出
```

判定提名文件是 JSON 数组，逐条形如：`{"verdict": "supersede", "nominator": "<提名者>", "rationale": "<依据>", "target_fact_id": "fact_…", "fact": {"statement": "…", "fact_type": "conclusion", "object_id": "claim:C1", "valid_at": "2026-10-20"}}`。

## 纪律要点

- 对象 ID 由「类型 + 上游 ID」确定性派生，不另建 ID 体系；每条记忆出生即带溯源五字段，缺一不进长期层。
- 收编失败逐项点名并停在水位线原处；未核验的数据不落值、不假装。
- 嵌入未登记时用确定性测试嵌入并如实标注；登记 local/api 走真实嵌入（local 为本机 ONNX、零外发；api 密钥只经环境变量注入、永不落盘），登记不全或实现不可用时有效嵌入回落并注明原因，不冒充。

设计依据：`../10-memory/LEARNING.md`（33 条硬约束）、`../10-memory/REDESIGN-DRAFT.md`（含拍板附录 8 条定版记录）。
