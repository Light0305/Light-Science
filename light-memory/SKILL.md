# light-memory SKILL（v1.0）

> 定位：独立的研究记忆——沉淀前序八包 + 选刊的结构化产物与事件，支持跨会话恢复、跨项目复用、失败经验防重复试错，并为 Obsidian 轻量图谱视图供给精选笔记与真实关系。**Memory 独立于 Obsidian**：不用 Obsidian 时记忆照常工作，视图只是投影。Memory 只收编、永不反向改写任何上游产物；条目与上游冲突时以上游为真，记忆走取代或争议流程。
> 设计依据：`10-memory/REDESIGN-DRAFT.md`（含拍板附录 8 条，2026-10-20 全按推荐定版）、`10-memory/LEARNING.md`（33 条硬约束 MM-01–MM-33）。
> 状态：**v1.0 已封版**（Phase 1 + Phase 2 全部落地，102 测试；Phase 3 真实演示走完至 validate 零错误、评测首测完成，见 §8 末封版记录与 `examples/demo-fullrun/demo-report.md`）。通过线已由用户定版（2026-10-20，§8 第 5 条）。

---

## §1 记忆项目文件群

一个记忆项目 = 一个目录（项目内 `memory/`，跨项目层为用户级记忆根，文件群同构）。

| 文件 | 角色 |
|---|---|
| `memory.yaml` | 登记头（权威）：项目标识与隔离范围、嵌入提供者登记、沉淀配置、逐包水位线、索引状态摘要、机械计数、phase2_pending |
| `objects.jsonl` | 对象注册（只增）：对象类型 + 上游 ID + Memory 派生 ID（MM-01）、当前版本指针、状态（active/superseded/archived/referenced）、别名 |
| `events.jsonl` | 事件层（只增）：阶段/失败/决策/取代/判定/争议/传播事件；每条带溯源五字段与去重键 |
| `facts.jsonl` | 事实层（现行状态文件）：陈述 + 对象键 + 双时间四字段 + 溯源列表 + 状态（current/superseded/disputed）+ 取代指针 + 派生 stale 标记 + 强度记账；每次变更由命令执行并同步落事件 |
| `relations.jsonl` | 关系层（现行状态文件）：八类关系（§3 类型表）+ 端点 + 来源计数权重 + 状态（resolved/unresolved/superseded）+ 有效区间 |
| `disputes.jsonl` | 争议账：竞争组 + 双方事实指针 + 提名来源 + 裁决留痕（只登记不裁决，§5） |
| `promotions.jsonl` | 晋升账（Phase 2 已落地：promoted/withdrawn 只增记账，撤回对账） |
| `registry-view.json` | 对象注册统一视图只读导出（总控预留消费方，格式自本版冻结） |
| `notes/` | 笔记层（手工放入的 MD 会被索引收编；dossier 折返笔记形态已在 Phase 3 演示定版，见 demo-report §2） |
| `candidates/` | 判断性提炼候选区（Phase 2 已落地：candidates.jsonl 候选账 + distill-corpus.jsonl 已生效蒸馏语料 + distill-export.json 导出件） |
| `profile/` `obsidian/` | 画像视图（Phase 2 已落地：两文件可整删再生）与 Obsidian 投影（Phase 2 已落地：vault 笔记 + .projection.json 投影清单） |
| `.index/` | 索引层（唯一可整删目录）：FTS5 + 向量（sqlite 单文件）+ `index-state.json` 同步台账 |

**铁律（MM-03）**：真相在 MD/JSONL 文件，索引全派生——删掉 `.index` 不丢任何记忆，一条命令全量重建（有测试钉死）；`.index` 之外出现数据库文件即校验报错。摘要与画像都是派生视图，永不替代事件层原文。

## §2 承接规程（M0，ingest）

1. **收编面是既成接口**：九包 + 选刊的导出形态已定版，Memory 不另建 ID 体系、不要求上游改格式；对象 ID 由「对象类型 + 上游 ID」确定性派生（MM-01），同一对象跨次收编自动合并。
2. **一包一适配器，只读上游**：结构化直通五包（Idea `memory_export.jsonl`、Experiment 执行包、Analysis `conclusion_card.json`、Figure `provenance.yaml`、Journal-Select `selection.json`）走确定性字段映射；约定转译四包（Design `design.yaml` + amendment 链、Literature 证据表、Write `use_log`、Review `handoff_to_write.json`）字段值一律照抄上游。
3. **水位线与漂移**：登记头逐包记已收编到的快照哈希；快照未变跳过，变了只收变化部分并在报告中给出漂移前后哈希；收编失败停在水位线原处、逐项点名，不许半收编冒充完成，失败不拖垮其余包。
4. **缺项点名不假装**：字段缺失逐项进收编报告的缺口清单并跳过该条（如 Write 的 use_log 缺 model_version 只登记不入账；选刊未核验指标不落值；撤稿无结构化源如实点名）。溯源五字段（来源包/产物/锚点/版本/收编时间）是条目出生的必填项，适配器未给细锚点时以来源产物本身为锚（MM-02）。
5. **前向登记**：只被指针引用的对象（如结论卡引用的执行包）先以 `referenced` 落账，本体收编时就地转正；指向未出现对象的关系以 unresolved 落账并保留目标原文标识，目标出现自动补解析（MM-26）。

## §3 数据模型（M1）

- **三层分工（MM-06）**：事件只增（原文留存）、事实可失效（当前知识状态）、笔记给人读（Phase 2 模板产出）。
- **事实最小单位**：单句可判真伪的陈述 + 对象键。双时间四字段（MM-09）：`valid_at`/`invalid_at`（世界中生效/失效）+ `created_at`/`expired_at`（入系统/被失效化的事务时间）+ `reference_time`（来源事件发生时间）；相对时间以来源事件发生时间解析，禁止用写入日冒充发生日。
- **关系类型表 v1（MM-25）**：supersedes（取代，强）/ refutes（否定，强）/ supports（证实，强）/ depends-on（依赖，强）/ derived-from（出处，强）/ same-object-as（跨项目同源，中）/ backtracks-to（折返，中）/ inspires（启发，弱）。强关系只许机械生成；inspires 只许候选 + 判定两段式。否定与折返的传播权重下限受保护，不许被来源计数压过（MM-20）。关系只来自上游结构化导出，禁止对原文再抽取（MM-24）。
- **合并算子表（MM-14）**：结论类 supersede-only（不许 merge 稀释口径）；决策类 immutable（只许新决策取代）；教训/期刊事实/证据/方向/图出处/失败记录/评审关切类 merge-union；方法类 patch；其余 free。写入路径只查表。

## §4 沉淀判定与取代链（M3 核心）

判定走封闭五值词表（MM-14），经 `verdict` 命令落账（提名文件 JSON：逐条带 verdict / nominator / rationale / fact 草稿 / target_fact_id）：

| 判定 | 语义 | 代码执行 |
|---|---|---|
| store | 新信息新增 | 派生 ID 已存在则幂等返回 already_stored |
| skip | 旧的更好或无增量 | 只落判定事件，不落事实 |
| supersede | 同一事实的新版本 | 区间算术执行失效（见下），旧版保留可查 |
| merge | 互补不矛盾 | 先查算子表（结论/决策类拒绝）；时间跨度与溯源取并集，旧条目被吸收 |
| dispute | 存在争议 | 入争议账，事实本体一字不动（§5） |

- **提名归模型、执行归代码（MM-10）**：提名只给候选与依据；失效由代码按半开区间 `[valid_at, invalid_at)` 算术执行——区间不重叠不失效（两版可在不同时段同真，如实回报 both-current），重叠才失效且旧版 `invalid_at` 盖为新版 `valid_at`。
- **无时间戳不许静默处理**：任一方缺 `valid_at` 时 supersede 被明示阻断（blocked_no_timestamps），请走 dispute 或补登记。
- **取代闭环（MM-11）**：新版生效 → 旧版标 superseded（指针双向落账 + supersedes 关系边）→ 派生失效传播 → 落取代事件。永不就地覆写冒充更新。
- **派生失效传播（MM-12）**：事实失效时，沿 `derived_from` 传递性把派生事实标 `stale` 并写明理由（待按新版再生，Phase 2 执行再生）；关系端点同步标 `stale_endpoint`。标 stale 不改事实状态。
- **防环**：新事实若是目标的取代链后代，落账即成环，拒绝（cycle_rejected）。
- **as-of 回溯**：`facts --as-of <日期>` 按有效时间回溯当时为真的事实集（边界：`valid_at` 当天入选、`invalid_at` 当天不入选）；`--known-at` 再叠事务时间（当时系统已知）过滤。
- **衰减只记账（MM-30）**：事实带强度记账字段（调用计数/最近调用/休眠档），v1 无任何自动物理删除；delete 不在判定词表内。

## §5 争议账与裁决（MM-15）

争议只能靠语义发现、无法机械判定时入 `disputes.jsonl`：按（事实类型槽位，对象）登记竞争组，双方事实状态转 disputed、本体不动，检索与呈现必须带未裁决标记（Phase 2 消费）。裁决是独立动作（`dispute-resolve`，具名裁决人 + 理由必填）：

- `challenger_wins`：挑战方生效，代码按区间算术失效在位方（须有时间戳且区间重叠，否则拒绝、争议保持 open）；
- `incumbent_wins`：在位方维持，挑战方以零长区间转 superseded（从未生效）；
- `both_stand`：两方各表一时段/一面，并存回 current。

## §6 索引层

- **构成**：`.index/memory_index.sqlite`（chunks 表 + FTS5 虚拟表 + 向量列）与 `.index/index-state.json` 台账（逐真相文件哈希 + 状态、嵌入登记/有效信息、真相清单哈希）。
- **块 ID 含嵌入模型名（MM-04）**：换模型构造性失效、平行新索引不碰撞；建索引时校验维度，不符报错并指明重建路径。
- **嵌入提供者注册制**：登记头 `embedder` 登记 provider/model/dim；未登记者用确定性测试嵌入（哈希分桶词袋，跨运行一致），产物一律标注 `embedder=deterministic-test`。登记了 local/api 但本期无真实实现时，有效嵌入如实回落测试嵌入并在台账注明，不冒充已用登记模型。向量存储借嵌入式底层件：sqlite-vec 可用则优先建 vec0 表加速，不可用走 JSON 列 + 纯 Python 余弦，不阻塞。
- **FTS 切分纪律**：FTS5 的 unicode61 把连续中文当作单个 token，索引与查询两侧统一以同一 tokenizer 切分（中文单字 + 拉丁词）后入表，原文保留在 chunks 表。
- **对账**：`index status` 三态（absent/current/stale）明示；真相文件变化即 stale 并点名文件，校验器同口径报错。`index rebuild` 是唯一重建路径，只动 `.index` 内部。

## §7 校验（validate）

四账一致性逐条点名：文件群齐备；溯源五字段完整；对象 ID 唯一且与派生口径一致；事实→对象与取代指针双向对称；双时间合法（`invalid_at` 不早于 `valid_at`、`expired_at` 不早于 `created_at`）；取代链无环；争议账与事实 disputed 状态双向一致；关系类型在词表内且生成方式与类型表相符、unresolved 必留目标原文标识；判定事件的 verdict 必须在五值词表内；索引与真相哈希对账；真相目录出现数据库文件即报错（MM-03 硬约束自检）。

## §8 Phase 2 落地状态（六件全落地，102 测试）

登记头 `phase2_pending` 逐件登记，Phase 2 命令在对应包上成功执行后自动摘除对应条目。

1. **候选通道（MM-13c）已落地**（`candidates.py`）：判断性提炼只产候选进 `candidates/candidates.jsonl`，人工 `accept` 是独立生效动作（fact 类经一期判定落账执行、执行失败候选保持 pending；distill_rule 类入已生效语料；annotation 类落标注事件；promotion 类拒绝在候选通道代办、须走 promote confirm）；`reject` 留痕不删。通道分工在代码层分开：确定性提炼只走 ingest，候选类型表是封闭词表。与 Review 的双向接口已落地：蒸馏语料八字段（草案 §5.1）提名/收编共用同一校验；`distill-export` 以覆盖层压平形产出、每 rule_id 只供最新 version；`distill-import` 收编 Review 回流双存条目（八字段形与压平形都收，先归一化），只产候选不直入语料。
2. **检索三路与渐进披露（MM-19–MM-23）已落地**（`retrieve.py`）：作用域限定（项目默认、跨项目须显式给 extra_roots）→ 词法/向量/关系传播三路（边权 = 类型权重 ×（1 + ln 来源计数）、种子按度数降权、逐跳衰减）→ RRF（k=60）融合 → 效力过滤（superseded 默认不出、as-of 出当时有效集、disputed 带未裁决标记、dormant 默认不出）→ 三级披露（L0 索引行 / L1 全文 / L2 出处锚点）。五配方登记在案（default/paraphrase/failure-lookup/as-of/cross-project），`recipe set` 改权重/跳数留痕（登记头覆盖 + recipe_change 事件）；回供四封顶（默认 20 条/800 字/12000 字/5 秒，超时结构化失败）+ 投毒防线声明头（MM-33）；索引缺失/过期在结果头降级明示。回供顺带更新事实强度记账（MM-30，只记账不删除；`account_strength=False` 可关，评测运行器默认关）。嵌入提供者保持一期形态：登记位 + 确定性测试嵌入标注，真实模型接入只留配置与重建路径（块 ID 含模型名）。
3. **Obsidian 投影（MM-27–MM-29）已落地**（`obsidian.py`）：项目内独立 vault、单向投影、精选规则照草案第六节成文于代码（入选事实类型/状态集在模块头）；机器区/标注区以固定标记物理分隔，重投影只动机器区；关系以 wikilink 落边（端点事实映射到其对象笔记）；投影清单 `.projection.json` 带源哈希，源未变不重写；`readback` 把标注区新增内容整段收为 annotation 候选（水位哈希防重复提名，原文留视图内）；整册删除后可从记录全量重建。
4. **画像视图（MM-31）已落地**（`profile.py`）：`profile/` 两文件（静态处置：决策口径 + 方法偏好 + 裁决史索引；动态近况：近期事件 + 未决项）只装处置与指针（每条摘录一句 + 回指 ID），整删可从账本同内容再生；`profile check` 自检咬无指针行与悬空指针。项目立场视图 `stance` 以（项目，对象）键控现场组装、逐项目分组呈现，不落独立存储。
5. **评测集运行器（MM-32）已落地**（`bench.py`）：题集 JSONL 格式定版（问题/期望命中或拒答/类别/出处指针）；五类题（被否定旧结论/跨项目同名对象/失败经验复用/无答案拒答/释义基线）分项报表（逐类命中率、释义单列、拒答按「top-5 内无与查询共享 ≥2 个实义 token 的词法/关系有据命中」判、知识更新题单记旧答案误答）；报表随配置版本登记（配方权重 + 嵌入登记 + 配置哈希）；随包附迷你题集 `mini_bench.jsonl`（6 题，由一期冒烟数据派生的迷你世界作回归基线，`bench build-world` 构造、`bench run` 跑分）。**通过线（用户 2026-10-20 按 demo-report §9 建议线定版）**：知识更新旧答案误答率 = 0（硬线）、知识更新命中 ≥0.50、跨项目同名 ≥0.80 且混答 0、失败复用命中 ≥0.60、拒答编造率 ≤0.30（按本条判据操作化）、释义基线 ≥0.70（单列，与 v2.2 Recall@1 0.220 非同口径）、总命中 ≥0.65。首测（正式题集 50 题，报表 `examples/demo-fullrun/evidence/bench_report.json`，确定性测试嵌入配置）总命中 34/50 = 0.68，逐项均达线（多项恰在地板值——本线即首测回归地板）；真实嵌入接入后须重测并另行提线，配置变更无当版报表不称已验证。
6. **晋升通道（拍板 6）已落地**（`promote.py`）：`promote propose` 在全局层产 promotion 候选 → `confirm` 复制入全局层（原件留项目层；对象先在全球层登记；副本 derived_from 不留悬空指针、原样存 extra）并记 `promotions.jsonl` → `withdraw` 对账式撤销（删全局副本 + 记 withdrawn + 落事件，项目原件不动）；重复晋升与重复撤回均被拦。

**Phase 3 封版记录（v1.0）**：真实演示 `examples/demo-fullrun/` 沿火鸡主线把九包 + 选刊的真实演示产物收编进一个记忆项目（proj-a），全链经 CLI 子进程真跑——逐包 ingest（Idea 因演示卡未定版、无 memory_export 被点名拦下，死胡同改走 dossier 折返笔记）、构造第二代结论包的取代 + 派生 stale 传播 + as-of 分界、候选 accept/reject 各一、跨包 recall 四问、Obsidian 投影 15 文件 + 标注回读全链、跨项目晋升一条、终局三包 validate 零错误（proj-a：对象 26 / 事件 88 / 事实 30 / 关系 16）。评测首测：正式题集 50 题（五类）总命中 34/50，知识更新旧答案误答率 0；通过线已由用户按建议线定版（见第 5 条）。演示细节、逐项数字与已知折扣见 `examples/demo-fullrun/demo-report.md`。

## §9 硬约束映射（MM-01–MM-33，本期落地项）

承接与对象注册 MM-01/02（§2）；真相与索引 MM-03/04/05（§1/§6）；数据模型 MM-06/07/08（§3，笔记语义行随 Obsidian 投影的观察行落地）；双时间与取代链 MM-09/10/11/12（§4）；沉淀判定 MM-13（三段全落地：捕获/确定性段 §2、判断段 §8.1）/14/15（§4/§5）、MM-16（演化只动派生属性：配方调整与强度记账均落事件，事实内容变更仍只走判定/取代）、MM-17（反思规程的产物口已备——只进候选/派生属性，见 §8.1）、MM-18（触发阈值已登记在登记头 settle 段）；检索 MM-19–23（管线已落地，§8.2）；关系 MM-24/25/26（§3/§2，传播配方见 §8.2）；Obsidian MM-27/28/29（已落地，§8.3）；遗忘 MM-30（§4，强度记账由回供更新）；画像 MM-31（已落地，§8.4）；评测 MM-32（已落地，§8.5，通过线已定版）；本地性与隐私 MM-33（全本地运行、无常驻进程、回供头带投毒防线声明、跨项目须显式声明作用域）。

## §10 已知局限（v1.0）

1. 有效嵌入为确定性测试嵌入，无语义质量；真实本地/API 嵌入接入后须整索引重建（块 ID 含模型名，构造性失效已备）。评测集释义类的分数在此嵌入下只作管线回归基线，不代表语义检索质量。
2. 事件去重键是内容哈希：上游同一产物改写后重收编会产生新事件行（只增账语义下可接受），跨版本的事件级合并未做。
3. Literature 撤稿事件与 Idea 死胡同收编依赖上游回填结构化源（事件 schema / dossier 口径），一期以缺口点名留痕，未收编这两类；Obsidian 投影的撤稿入选钩子已备（事件 type 含 retract 即在索引页计数），待上游回填后生效。
4. Journal-Select 的已核验指标识别基于 verification 状态字段的约定形态；上游核验记录形态变更时适配器需随版本升级（登记头已记适配器版本）。
5. 关系端点签名（端点类型对约束）只登记类型表，未在校验器强制；inspires 的两段式生成可经候选 + verdict 落地（候选通道承接提名），未做专用命令。
6. 检索的向量路在 sqlite-vec 不可用时走 JSON 列 + 纯 Python 余弦（与一期同口径）；关系传播只在事实图上进行，笔记块不参与传播（笔记经词法/向量两路召回）。
7. 评测集通过线已定版（2026-10-20，见 §8 第 5 条；首测逐项达线，多项恰在地板值，属回归地板而非能力上限）；迷你题集为回归基线（6 题），正式题集随真实项目滚动扩充。首测失分以 top-5 排序稀释为主（小语料 30 条事实），语料增长后应复测。
8. 回供的超时封顶为阶段间检查点口径（非硬实时中断）：单次索引查询本身的耗时不在检查点内。
9. `candidate list` 的 `--kind` 默认值为 fact，annotation 候选须显式 `--kind annotation` 才列得出（Phase 3 演示发现；API 层无此问题）。
