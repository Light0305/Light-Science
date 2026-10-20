# Light-Idea 技能说明

> 版本：**v1.0（封版，2026-10-20）**。设计依据（重构草案与学习期
> 文档）属开发档案，不在本仓库；本文件即产品的完整执行规范。
> 章节地图：产物规范第 3 节 → 状态机与定版门第 5 节 → I3 查新
> 第 8 节 → I0/I1 生成算子第 9 节 → I4 对决排序第 10 节 → I5 打磨与
> pre-mortem 第 11 节 → I6 交接导出第 12 节 → 自检清单第 13 节。
> 执行顺序：按第 3 节产物规范建项目 → 按七环顺序推进（I0/I1 第 9 节 →
> I2 补卡 → I3 第 8 节 → I4 第 10 节 → I5 第 11 节 → 定版门第 5 节 →
> I6 第 12 节），交付前逐项过第 13 节自检清单；异常先查第 8.4 节
> 与第 14 节的边界口径，不许凭印象临场发挥。

## 1. 定位

Light-Idea 负责「把领域缺口变成经得起查新的定版想法卡」：输入是研究方向/问题
与 Light-Literature 的既有产物，输出是可直接交给 Light-Design 的**定版想法卡
+ 查新证据包**。核心交付不是灵感碎片，而是定版卡——生成只是七环中的一环，
查新与执行级规格化才是这个 skill 的质量所在。

七环总览：I0 趋势与缺口感知 → I1 想法生成 → I2 想法结构化 → I3 查新 →
I4 评估与排序 → I5 打磨迭代（含 pre-mortem 独立关）→ I6 交接。
（已全部落地：I0/I1 规程与取材工具见第 9 节；I2 的载体为想法卡与
状态机（第 4、5 节）；I3 见第 8 节；I4 见第 10 节；I5 见第 11 节；
I6 见第 12 节。未落地的只剩第 14 节明列的 v2 项，不许假装可用。）

## 2. 与 Light-Literature 的衔接（写死）

- 取材优先消费 Literature 的项目内产物（精读卡、证据矩阵、矛盾清单、笔记
  第 15/16 节的研究候选），不自建平行的文献库。
- 想法卡引用的每一篇文献**必须带 Literature 的 `paper_id` 或 DOI**，校验器
  拒绝裸文本引用；进入定版门时，最接近工作须全部 `verified=true`（已过
  Literature 的身份核实 + 撤稿检查）。未核实文献不许进想法卡的证据区与
  「最接近工作」表——与 Literature「未核实成稿层一律不用」对齐。
- Idea 需要新文献时向 Literature 回派任务（dossier 文件模式），不自己漫游
  找文献下结论。

## 3. 产物规范

单个研究方向一份项目（`init` 建立）：

```text
<project>/
├── project.yaml              # 项目元数据
├── index.yaml / index.md     # 项目级索引（自动维护：状态计数 + 卡清单）
├── idea-stage/
│   ├── IDEA_REPORT.md        # 唯一权威文档（折叠各环结论）
│   ├── candidates.md         # 候选池：幸存者 + 已杀区 + 切换日志 + 方向层留痕
│   └── research_contract.md  # 交接契约（定版选定后生成）
├── cards/<idea_id>/          # 一卡一目录
│   ├── idea.yaml             # 结构化字段（权威源）
│   └── card.md               # 人读版（由 idea.yaml 渲染，两区物理分离）
├── novelty/<idea_id>/        # 查新证据包：evidence.jsonl（证据池）
│                             # queries.json（查询式与逐式日志）pool_report.md
│                             # （池报告+盲区声明）verdict.json（判定与收据存根）
├── chains/<chain_id>/        # 演进链素材（chain 命令落盘）：
│                             # seed.json（根种子+已展开的跳）neighbors.jsonl
│                             # （双向邻居清单）chain_report.md（素材报告）
└── exports/<idea_id>/        # 交接三件套（只对定版卡）：
                              # design_handoff.md / idea_card.json /
                              # memory_export.jsonl（方向层条目）
```

idea_id 规则：`<slug>_<hash6>`——题名 ASCII 化 slug（截断 40 字符）+
`sha256(题名)` 前 6 位（沿用 Light-Literature 的 paper_id 习惯）。

## 4. 想法卡纪律

- **生成出处必填**：provenance 至少给出 chain_id / path_string / combo /
  note 之一，无出处不许入池。
- **facet 骨架**：purpose / mechanism / evaluation 三面，每面 = 结构化短语
  + 展开 + 来源登记（出处论文须带 paper_id/DOI，或演进链节点 / 算子 / 用户自创）。
- **负面字段是成熟标志**：最强反对意见（Reviewer's likely objection）、
  风险列表、Why not selected first——没有负面字段的卡视为未打磨。
- **判定区与辅助区物理分离**：查新判定（novelty 区）只许出现「在先工作 +
  逐面异同 + 结论 + 检索范围声明」；相似度分、非典型组合分、Elo 等一切
  分数信号只许呆在 aux 区，且一律标「暂定，未经执行验证」——分数永远
  不许进判定区、不许作定版/淘汰依据（硬约束 1、3）。
- **分数只作粗筛**：LLM 自评不当闸门（实证分档准确率仅约 53%）；新颖性
  结论只能来自对真实文献的实查证据。
- **试点标注诚实**（拍板 9.6-B）：试点环可选、默认关；未经试点验证的
  定版卡必须在卡面标注「未经试点验证」。

## 5. 状态机与定版门（确定性校验）

```text
draft → screened → novelty_checked → pre_mortem_passed
      → finalized_executable（可执行定版：规格全齐，可直接交 Design 开工）
      → finalized_conceptual（概念定版：核心+查新齐、规格未齐，卡面显式标注，
                              不得直接开工，只许交 Design 做规格化）
旁路：killed（留痕入已杀区）／ parked（附复活条件，可复活回 draft）
```

状态只许由产物驱动、经 `advance` 验门推进，不许口头推进、不许跳级。
每道门的规则见 README「状态机门规则清单」，校验器逐条报错、不静默放行。
其中写死的拍板口径：

- **查新判定宪法**（拍板 9.1-A，ARIS 宽松口径）：ABANDON 只有一个资格——
  点名一篇已包含该结果的已发表论文；「拥挤但有 delta」= PROCEED；
  CAUTION 必须说清 delta 薄在哪（caution_reason 必填），说不出就是 PROCEED。
  对偶面：因查新被杀（killed, source=novelty_named_paper）同样必须点名论文。
- **跨模型判定硬门 + 降级通道**（拍板 9.4-B）：定版须有跨模型判定收据
  （verdict_id + 判定模型 + 执行者模型，判定与执行不同家族；同家族自审
  的收据判无效）。判定后端不可用时 novelty.review_status 记
  REVIEW_UNAVAILABLE——想法可停在候选区流转，但不许定版，不许用执行者
  自评冒充判定。
- **两级定版**（拍板 9.2-B）：概念定版须先在卡上显式标注
  finalization_level=conceptual 才许过门，且渲染出的卡面带「不得直接
  开工」横幅——概念级不许冒充可执行级。
- **失败二分类**（硬约束 8）：killed 必填 failure_class——fundamental
  （附 root_cause + boundary_conditions）或 implementation（附
  retry_guidance）；分类决定该方向是永久剪枝还是可重试，不分类的黑名单
  会误杀可重试方向。

## 6. 去重工序

生成后必走去重（硬约束 5）：`dedup` 用字符 n-gram（3–5）TF-IDF 余弦
（纯离线、无外部 embedding 服务）标出疑似重复对与重复簇，并按
「生成总数 → 疑似对/簇 → 若裁决全成立的存活数与去重率」口径出报告
（落盘 idea-stage/dedup_report.md，同时回写各卡 dedup 字段）。
去重只报告、供人工裁决（卡上 adjudication 字段），**不自动删卡**；
被裁定 duplicate 的卡不许再推进 screened。去重率是生成健康的体检
指标（实证：单算子采样 4000 条去重后只剩约 5% 且平台化——多样性靠
算子并列，不靠加大采样）。

## 7. 已实现命令

| 命令 | 作用 |
|---|---|
| `light-idea init <dir> --direction <方向名>` | 建项目骨架 + 索引 |
| `light-idea new <project> --title … --one-liner … [--operator …] [--provenance …]` | 建 draft 卡（idea.yaml + card.md） |
| `light-idea validate <project> <idea_id>` | 结构校验，逐条报错 |
| `light-idea advance <project> <idea_id> --to <状态> [--by …] [--note …]` | 验门推进状态，不过门逐条列明 |
| `light-idea dedup <project> [--threshold 0.55] [--no-write]` | 去重报告 + 回写 dedup 字段 |
| `light-idea list <project>` | 列出全部卡与状态 |
| `light-idea novelty prepare <project> <idea_id> [--per-query 10] [--sleep 0]` | facet 查新取证（逐面构式 → 四源实查 → 证据包落盘 + search_scope 回填） |
| `light-idea novelty verdict <project> <idea_id> --verdict … --judge-model … --judge-family … --executor-model … --executor-family … [--caution-reason …] [--closest-file …] [--review-unavailable]` | 判定落卡（跨模型收据 + 逐面举证，纪律见第 8 节） |
| `light-idea chain <project> --seed-doi … [--chain-id …] [--per-direction 25]` | 演进链取材——拉一种子的参考文献+施引邻居落盘成链素材（不做自动生成，规程见第 9 节） |
| `light-idea duel <project> --a <id> --b <id> --winner <id\|draw> --by … [--note …]` | 两两对决落卡（双方 aux.pairwise_record，规程见第 10 节） |
| `light-idea rank <project> [--no-write]` | 对决汇总——胜率矩阵 + Elo 参考分（回写 aux.elo；分数不作淘汰依据） |
| `light-idea export <project> <idea_id>` | 交接三件套（只对定版卡；未定版拒绝并逐条说明缺口，见第 12 节） |
| `light-idea report <project>` | 生成/刷新 IDEA_REPORT.md（全池状态/定版清单/已杀区/去重率/对决摘要） |

## 8. I3 facet 查新规程

查新是两步命令 + 一道状态门：`novelty prepare`（取证）→ 跨模型判定
（人工/编排层把证据包交给另一模型家族）→ `novelty verdict`（落卡）→
`advance --to novelty_checked`。判定权只属于第二步的判定者，且其结论
只能引用证据包中真实存在的论文。

### 8.1 操作清单（照此执行，逐项打勾）

1. **前置**：卡已过 `screened`（结构合法、facet 三面短语与展开已填实；
   facet 是构式的唯一原料，空面构不出式）。执行者模型名先记下，
   verdict 落卡时要登记（executor）。
2. **取证**：跑 `novelty prepare <project> <idea_id>`。它自动完成：
   逐面构式（purpose / mechanism / evaluation 每面至少 2 条——短语式
   用 facet 短语原文、关键词式从短语+展开抽词；另加整想法召回式
   1–2 条，**只作召回层**，命中记录标 `whole`，不许据此单独判定）；
   四源实查（Crossref / OpenAlex / Semantic Scholar / Europe PMC，
   均免 Key）；归池去重（DOI 优先、无 DOI 用规范化题名）并离线粗排。
3. **查证据包**：打开 `novelty/<idea_id>/pool_report.md`——先看各源
   状态与**已知盲区声明**：某源 429/不可达会写明「覆盖不全」，
   某面零命中会点名；盲区已同步回填卡的 `search_scope`
   （sources / pool_size / known_blind_spots）。四源全灭时 prepare
   返回失败，**不许在此基础上落任何判定**，等源恢复后重跑 prepare。
4. **交判定**：按 §8.3 协议把证据包交给**另一模型家族**的判定者，
   收回结构化判定（verdict + closest_works + 逐面举证）后写成
   closest JSON 文件：`{"closest_works": [ {doi 或 paper_id, title,
   year, collided_facets[], delta, verified} ], "named_paper": {...}}`
   （ABANDON 时才需要 named_paper）。
5. **落卡**：跑 `novelty verdict`（命令见第 7 节）。校验不过会逐条
   点名拒绝——按报错补证据或改判定，不许绕过（没有「强制落卡」开关）。
6. **推进**：`advance --to novelty_checked`。verdict=ABANDON 的卡
   不许走这步：verdict 命令会打印转 killed 的路径（kill 记录
   source=novelty_named_paper + 点名论文），照此办理。
7. **补查**：判定者若认为池子漏了关键工作，先补查询重跑 prepare
   （证据包整包刷新），再落判定——池外论文写进 closest 会被拒，
   这是故意的：判定只能站在实查证据上。

### 8.2 判定者工作守则（写给判定者模型，逐条执行）

- **只引证据包**：closest_works 与 named_paper 只能来自
  `evidence.jsonl`；凭训练记忆想起的论文一律不许写进判定区。
- **逐面举证**：每条 closest 必填 `collided_facets`（撞了 purpose /
  mechanism / evaluation 中的哪几面，逐项列明）与 `delta`
  （本想法与该在先工作**逐面**的差异点，要具体到可核验，不许写
  「略有不同」）。没有 delta 的撞车陈述不成立。
- **判定宪法**（拍板 9.1-A，ARIS 宽松口径）：ABANDON 只有一个
  资格——点名一篇已发表论文、且该论文已经包含这个想法的结果
  （三面实质覆盖且无剩余 delta）；「拥挤但有 delta」= PROCEED；
  PROCEED_WITH_CAUTION 必须在 caution_reason 里说清 delta 具体
  薄在哪一面、薄到什么程度，说不清就给 PROCEED；**拿不准取
  PROCEED 或 CAUTION，不取 ABANDON**——误杀不可逆，误放会死在
  试点/pre-mortem（两类错误代价不对称）。同期工作（近一年内出现
  的同向工作）是竞赛信号，不是 ABANDON 理由，至多构成 CAUTION。
- **相似度分只作召回排序**：evidence 里的 similarity 是离线文本
  粗排分，**不许作为判定依据**，不许在判定理由里引用分数——
  只撞一面的论文整文相似度天然低，分数会系统性淹没它（约束 3）。
- **盲区要计入结论强度**：pool_report 声明某源不可用或某面零命中
  时，判定结论的可信范围随之收窄；覆盖明显不全时优先 CAUTION
  并在 caution_reason 注明覆盖缺口，而不是把「没查到」当「不存在」。
- **verified 标记诚实**：closest 的 `verified` 只在该论文已过
  Literature 核实口径（身份核实 + 撤稿检查）时才许标 true；
  未核实就留 false——定版门会拦未核实条目，标错是造假不是疏漏。

### 8.3 跨模型收据实操协议（拍板 9.4-B 硬门）

- **谁判**：判定者必须与执行者（生成/推进本卡的模型）**不同模型
  家族**（如执行者是 Claude 家族，判定者用 GPT/Gemini 家族，反之
  亦然）。同家族自审判在 verdict 落卡时被直接拒绝——不是警告。
- **交什么**：给判定者的材料包 = 想法卡全文（idea.yaml / card.md）
  + 证据包三件（evidence.jsonl、pool_report.md、queries.json）
  + 本节 §8.2 守则 + 判定宪法原文。判定者不需要也不应该拿到
  执行者的内部推理过程。
- **收什么**：结构化判定（§8.1 第 4 步的 closest JSON）+ 判定者
  模型名与家族名。口头结论不落卡。
- **收据怎么记**：`novelty verdict` 自动生成
  `verdict_id = NV-<sha256(idea_id|日期|判定模型|结论)[:10]>`，
  与 judge/executor 的模型名与家族名一同写入卡的 `novelty.receipt`，
  并在证据包留 `verdict.json` 存根。收据缺失或同族，定版门拦截。
- **无第二模型时**：确实拿不到任何异家族判定时，用
  `novelty verdict --review-unavailable` 显式降级——必须同时给出
  执行者侧的暂定结论与 closest 举证（举证纪律不降级），落卡后
  `review_status=REVIEW_UNAVAILABLE`。该卡可继续流转（查新门可
  过），但**定版门硬拦**，恢复判定通道后必须补一次真跨模型判定
  再重跑 verdict（新收据覆盖旧收据），不许拿降级记录定版。

### 8.4 失败与边界（如实口径）

- 单源限流/不可达是常态（免 Key 源的共享配额）：prepare 如实记录
  并写入盲区，不重试到把源打挂，不假装查全；赶时间可调大
  `--sleep` 降低触发限流的概率。
- 重排目前只有离线文本粗排一段（向量粗排 + 按面 LLM 重排的第二
  段在判定者阅读环节完成，没有独立命令）——这是已知边界，
  不许把粗排分包装成「两段重排」的结论。
- 本领域查新判例集（带判例判定是 facet 路线准确率的主要增益
  来源）尚未冷启动：判定者目前只靠 §8.2 守则与判定宪法，
  判例集建设列入后续工作，建成后按 §8.3 材料包一并交付判定者。

## 9. I0 缺口感知与 I1 生成算子规程

程序为主、工具为辅：工具只做确定性的取材与落盘（chain 命令），
缺口判断、建链、生成全部由执行智能体按本节步骤执行并留痕——
**工具不许假装生成，智能体不许跳过留痕**。

### 9.1 I0 缺口感知（生成前固定动作，至少做一种，建议两种都做）

本地优先：先扫 Literature 项目内材料（精读卡、证据矩阵、笔记
第 15/16 节），再上网补缺。然后用 challenge-insight 读图法把缺口
从结构里读出来，不许凭感觉列清单：

1. **建图**：把已读文献逐篇抽成「挑战（challenge）×洞察（insight）」
   多对多关系——每个挑战登记它被哪些论文以什么洞察回应，缺口条目
   必须回指具体论文（paper_id/DOI），回指不到的不许写进缺口清单。
2. **读图**（三种缺口形态，逐项过）：
   - **少洞察的挑战 = 未解问题**：挑战在场但回应它的洞察 ≤1 条，
     是优先选题位；
   - **未连边的洞察 = 迁移机会**：某洞察只回应过一个挑战、与相邻
     挑战之间无边，是跨问题迁移的候选；
   - **多洞察的挑战 = 红海**：回应者众——不是不能做，而是入场必须
     写明与全部在场洞察的 delta，否则粗筛阶段直接注释「红海慎入」。
3. **备查**：另用五类结构缺口清单（方法跨域未试 / 矛盾结论 /
   无人验证的前提 / 未探索的 scaling 区间 / 无人问的诊断问题）
   逐条对照同一批文献，两份清单的交集优先。
4. **落盘**：缺口清单人工维护在 idea-stage/candidates.md 的
   landscape 区（每条缺口带回指论文与读图依据）。注意
   IDEA_REPORT.md 由 report 命令全量生成/刷新，手写内容会被
   覆盖——缺口清单不许只写在 IDEA_REPORT 里。

### 9.2 镜头扇出与粗筛纪律（I1 通用，不许违反）

- **镜头扇出**：缺口清单冻结成「镜头」后才许生成；每个镜头独立
  生成一批候选，合并时记**覆盖回执**——哪个镜头没产出、为什么，
  显式上报，不许静默丢失。
- **只注释不预杀**：生成期的收窄（Phase 3 粗筛）只许按两条客观
  事实淘汰——**算力预算超限、数据集可证不可得**（落卡为
  feasibility 两项 + screened 门把守）；新颖性与影响在生成期只许
  annotate（写进卡面备注/aux），不许 eliminate。判定权全部推迟
  到 I3 查新与 I5 定版门。
- **生成者禁评判**：生成候选时不许顺手打分排名；生成与判定解耦
  是硬约束 1 的流程形态。
- 生成后必走 dedup 工序（第 6 节）并报告去重率。

### 9.3 演进链算子（evolution_chain）操作步骤

基质是文献演进链：节点 = {想法一句话， 实验， 实体， 参考文献}
四元组（CoI 形态）。工具（chain 命令）负责取材，建链与生成按
下列步骤由智能体执行：

1. **取材**：`light-idea chain <project> --seed-doi <种子 DOI>` 拉
   根种子的双向邻居（参考文献 = 向后，施引 = 向前）落盘
   `chains/<chain_id>/`。三源（OpenAlex / Semantic Scholar /
   Crossref）单源失败只记 chain_report.md，不中断；三源全灭时
   命令失败——**不许凭印象建链**，等源恢复重跑。
2. **选节点（相关性门）**：逐跳从邻居里选 **3–5 个**与方向问题
   真相关的节点（凑数选入不相关节点是建链第一大忌）；判据是
   「该节点的想法/实验是否改变了链的方向」，不是被引数——被引数
   只作背景列。**高被引（>1000）源头节点只作链的起点背景，
   不在其上继续外推**（源头太上游，外推必然空泛）。
3. **生长**：对选定的中间节点再跑 chain（`--chain-id <同一链>
   --seed-doi <该节点 DOI>`）取下一跳素材，邻居的 hop_of 由工具
   自动记为被展开节点（归因不许人工指定）；链长以 3–5 代为宜
   （种子代 + 向前 1–2 代 + 链尾现状代）。
4. **抽四元组**：逐节点从题名/摘要（素材里的 abstract_snippet，
   不够时回 Literature 取全文精读）抽 {想法一句话， 实验，
   实体， 参考文献}；抽不出的字段写「未登记」并说明，不许编造。
5. **趋势层小结（先于生成，独立产物）**：逐对相邻代际写「变了
   什么」（问题变了 / 机制变了 / 评测变了），折叠进候选池文件
   或 IDEA_REPORT；跳过趋势层直接生成 = 把一堆摘要塞给生成器，
   实证显示这是消融降幅最大的一项，不许省。
6. **生成候选**：在**链的末端**（现状代之后顺推下一步）与
   **断点处**（某代际的假设后来无人验证、某机制在相邻领域成功
   却未迁回本链）生成候选；同时显式写出「人类大概率会做的
   下一步」作为避让锚——候选与避让锚实质重合的，自己标注重合，
   留待查新裁决，不许假装没看见。
7. **落卡**：`new --operator evolution_chain`，provenance 的
   **chain_id 与 path_string 必填**（path_string 写链的节点序列，
   如 `ByteTrack'22 → Byte³Track'25 → 本想法`）；facet 来源凡出自
   链节点的标 source.type=chain_node 并登记节点序号。

### 9.4 远域碰撞算子（collider）操作步骤

基质不是概念名，而是 **active_principle**（open-collider 形态）：
一段反直觉机制叙事 + 一个桥接问题。裸概念名碰撞（「把 X 用到 Y」）
不许落卡。

1. **选远域**：从与本领域**学科族不同**的领域选源（学科族跨轮
   排除：同一学科族在多轮碰撞里只许用一次，防伪远域）；源领域
   优先选「机制成熟、与本领域问题结构同构」的（工业检测、生态
   监测、信号处理、临床筛查等均为已验证的富矿形态）。
2. **抽 active_principle**：把源领域的核心机制写成三段式——
   ① 反直觉之处（它违反了什么默认假设）；② 机制叙事（它靠什么
   起作用，写到可迁移的抽象层，不带源领域术语）；③ 桥接问题
   （「在本领域，什么东西扮演源领域里 X 的角色？」）。
   三段缺一不许进入碰撞步。
3. **结构强制**：碰撞时**禁用源领域的原始框架与术语**（只许用
   第 2 步的抽象叙事），防表面类比；每批候选至少 **5/20 条**
   须为「公理反转」型（显式反转本领域一条隐含假设，并写明被
   反转的假设是什么）。
4. **碰撞生成**：active_principle × 本领域缺口清单逐条配对，
   每对先答桥接问题再写候选；答不出桥接问题的配对当场弃，不许
   硬凑。生成者禁评判（同 §9.2）。
5. **落卡**：`new --operator collider`，provenance 的 **combo
   必填**（写成 `源领域机制（一句话） × 本领域缺口（镜头号）`）；
   facet 的 mechanism 面来源标 source.type=operator 并在 detail
   里登记 active_principle 出处。

### 9.5 bad_case 回流（查新 → 生成的负样本接口，写死上限）

查新判出撞车时，（撞车论文，在先工作与逐面异同）以 bad_case 形式
回流 I1/I5 作为下一轮生成的显式禁区（CoI 机制）。纪律写死：

- 回流**轮次上限 ≤3 轮**（硬约束 6：无上限回路是失控风险，CoI
  原实现即无上限，不许照抄）；超限仍未过查新的想法标记未决、
  交人裁，不许继续自动回流；
- 每轮回流在被修订卡的 lineage.bad_case_refs 与 revision_log
  里留痕（哪篇撞车论文、改了哪一面、第几轮）；
- 回流只许驱动「换掉被撞的那一面」（单 facet 替换，见第 11 节），
  不许借回流之名重写整卡。

## 10. I4 评估与排序规程

主机制两两对决（duel/rank 命令），相对判断优先、分数只粗筛：

1. **谁判**：对决判定者与生成者须不同模型家族（与查新同一纪律，
   约束 1）；判定者只看两卡的 facet + 正文 + 执行级规格，
   **可行性独立成维展示**，不许只给一个被新颖性主导的总评——
   判语里须分别说清「新颖性谁强、可行性谁强、综合谁先行」。
2. **怎么判**：正反序各评一次消位置偏倚（先 A 后 B 与先 B 后 A
   各一遍，结论冲突记 draw 并注明）；判语落 duel 的 --note，
   不许只给胜负不给理由。
3. **落卡**：`light-idea duel <project> --a <id> --b <id>
   --winner <id|draw> --by <判定者> --note <判语>`——结果写入
   双方卡 aux.pairwise_record（辅助区，标「暂定」）。
4. **汇总**：`light-idea rank <project>` 输出胜率矩阵与 Elo 风格
   参考分并回写 aux.elo。**Elo 与胜率只决定「先查新/先试点谁」
   的顺序，永不作淘汰依据**；淘汰只凭三类证据——查新 ABANDON
   （点名论文）/ 试点 negative / 客观不可行（第 9.2 节两条）。
5. **诚实条款**：rank 检出循环胜负（A 胜 B、B 胜 C、C 胜 A）时
   会明示「分不开」——此时不许引用 Elo 小数点硬排座次，按并列
   处理，并列组整体进下一环或交人裁。

## 11. I5 打磨规程与 pre-mortem 执行规程

### 11.1 修订算子与落痕纪律

- **单 facet 替换是默认修订算子**：查新撞在哪一面就只换哪一面
  （Scideator 闭环），换后**只重查被换的那一面**（重跑 prepare
  后判定者只就该面复核），其余面不许顺手改。
- 其他修订算子（逐字段深化、组合、简化、文献驱动转向）每次
  应用都必须落 lineage.revision_log：{date, 修订算子, 改了哪些
  字段, trigger（触发事件）, reason}；**每轮只动有限字段**——
  一轮改超过 facet 一面 + 正文一处即视为重写，须在 log 里
  说明为何不是新卡。
- **Problem Anchor 冻结**：purpose 面在 screened 后冻结，修订
  不许漂移问题本身；确需换问题的，走新卡 + 切换日志留痕。
- 审稿风险只用来选下一步测试（补哪个实验/查哪篇），**不许
  用来给方法加组件**讨好审稿人；死胡同必须 pivot（换面/换
  镜头），不许只打补丁续命。

### 11.2 事件触发停止规则（先到先停，触发项写入 revision_log）

打磨回路不许拿固定轮数冒充收敛（硬约束 7）。下列事件任一触发
即停本卡本轮打磨：

1. **查新结论翻转**：复查后 verdict 与上一轮不同（PROCEED↔
   CAUTION 等），结论已变，回到主线推进或转 killed 评估；
2. **pre-mortem 清单清空**：§11.3 清单逐项 pass/na 且 open_items
   为空——打磨的目标达成，不许再为「更好看」空转；
3. **无新证据不许空转**：本轮修订若拿不出新证据（新查到的
   论文、新算出的数据、新写死的规格），不许启动——修订必须
   由证据驱动，不许纯措辞抛光；
4. **连续两轮无字段变化即停**：连续两轮 revision_log 的字段
   变更集为空（或只有措辞），判定为平台期，停并注明；
5. **轮次上限（熔断器）**：单卡打磨总轮次 ≤6、其中 bad_case
   回流轮次 ≤3（§9.5）；上限是熔断不是目标，命中即停并交人裁。

### 11.3 pre-mortem 执行规程（定版前的独立关）

以**执行阶段评审者的问题清单**逐项过（清单六项写死在 schema
PRE_MORTEM_ITEMS，门的校验见第 5 节）。执行者逐项给出 pass 或
na（na 必须附理由，如「理论型想法无数据集，datasets 项 na」），
任一项答不出 = open_items 留项，清单不清空不许过门：

| 清单项 | 逐项怎么查（判定口径） |
|---|---|
| strongest_baseline_attack | 拿 exec_spec 点名的最强基线正面攻击本方法：基线加同样的数据/算力后，本方法的 delta 还在吗？答不出攻击面 = 未过 |
| metric_convention | 每个指标都能说出领域惯例出处（哪几篇本领域论文用此口径）；自创口径须写明为何不用惯例 |
| ablations_complete | 消融逐项对应机制主张：每个「因为 X 所以有效」都有一个去掉 X 的消融；多一个主张缺消融 = 未过 |
| resources_realistic | 资源预算逐项对账：GPU 小时、数据获取路径、工期，与实验室实际条件比对，写明比对依据 |
| null_result_learning | 方法无效/零结果时能学到什么，是否已写进判别实验的 readout_null；学不到东西的实验不值得做 = 未过 |
| method_instantiable | 核心方法逐步复述到可实例化：任一步出现「某种方法处理一下」式含糊 = 未过，须先写死关键细节（exec_spec.key_details） |

执行形态：执行者按上表逐项自查并把 {status, note} 写进卡的
pre_mortem.checklist、open_items 清空后 `advance --to
pre_mortem_passed` 验门；有条件时 pre-mortem 由**另一模型家族**
执行（与查新同一解耦纪律），执行者与复核者都登记在 checklist
的 note 里。最小判别实验 + 三向判读标准（正/负/零）必须在此关
之前写死（pre-mortem 门会验），判读标准事后不许改口径——改了
要在 revision_log 里留痕并说明。

## 12. I6 交接导出规程

1. **导出**：`light-idea export <project> <idea_id>` 只对
   finalized 两级定版卡产出三件套到 `exports/<idea_id>/`：
   design_handoff.md（给 Design：核心主张、执行级规格、判别
   实验与判读标准、最强基线、查新结论、风险与反对意见、
   next-step）、idea_card.json（结构化全量）、memory_export.jsonl
   （**方向层**条目：抽象到方向层级而非具体做法，带 Retrieval
   Tags 与 Evidence 指针，供 Light-Memory 日后收编 —— 拍板
   9.5-A：v1 只留结构化导出，不自建记忆系统）。
2. **未定版拒绝**：未定版卡 export 会被拒绝并逐条列明缺口
   （当前状态、主线还差哪几步、定版门未过条目）——导出不是
   绕过定版门的后门；killed/parked 同样拒绝（killed 的价值在
   已杀区留痕，不走 Design 交接）。
3. **契约同步**：导出后把 design_handoff 的核心主张与判读
   标准同步进 idea-stage/research_contract.md（选定想法唯一
   一份在此登记），候选池（含已杀清单与备选顺序）原样保留——
   当前想法失败时从池里取下一个，不重跑全流程。
4. **项目报告**：`light-idea report <project>` 生成/刷新
   IDEA_REPORT.md：全池状态、定版清单、已杀区摘要、去重率
   （现场重算）、对决摘要（分数标「暂定」、循环胜负提示）。
   每个周期结束（定版/杀卡/方向收官）必跑一次 report，
   IDEA_REPORT 与 candidates.md 是对外的两份权威文档。

## 13. 交付前自检清单（逐项勾检，全过才许宣称本周期完成）

**卡与状态机**
- [ ] 每张卡 `validate` 通过；状态与 status_history 一致，无口头推进、无跳级
- [ ] 每张入池卡 provenance 有出处（链卡 chain_id+path_string、碰撞卡 combo 齐）
- [ ] 已杀卡 kill 记录齐全：失败二分类 + 对应附件（fundamental 的 root_cause/boundary、implementation 的 retry_guidance）；查新杀的都点名了在先论文
- [ ] parked 卡复活条件已写明

**生成与去重**
- [ ] 镜头覆盖回执在案：每个镜头有产出或写明无产出原因
- [ ] dedup 已跑且报告落盘；被裁 duplicate 的卡未推进 screened
- [ ] 粗筛淘汰只凭两条客观事实（算力/数据），无一例以「不够新颖」在生成期被杀

**查新**
- [ ] 每张进 novelty_checked 的卡证据包四件齐（evidence/queries/pool_report/verdict.json）
- [ ] 判定逐面举证：closest 每条有 collided_facets + delta，且都在证据池中
- [ ] CAUTION 都写清了 delta 薄在哪；ABANDON 都点名了在先论文且转 killed 落痕
- [ ] 收据跨模型（异家族）或 review_status=REVIEW_UNAVAILABLE 如实登记；无一例自评冒充判定
- [ ] search_scope 的已知盲区与 pool_report 一致，未把「没查到」写成「不存在」

**打磨与定版**
- [ ] revision_log 每轮有触发事件与字段变更集；bad_case 回流 ≤3 轮、总打磨 ≤6 轮
- [ ] pre-mortem 六项逐项 pass/na（na 有理由）、open_items 为空、判读标准未事后改口径（如改已留痕）
- [ ] 定版卡执行级规格六项齐（可执行级）或概念级已显式标注且卡面有「不得直接开工」横幅
- [ ] 定版卡 closest_works 全部 verified=true；未试点定版卡卡面有「未经试点验证」标注

**交接与报告**
- [ ] 定版卡三件套已导出（exports/<idea_id>/ 三文件齐），research_contract.md 已同步
- [ ] `report` 已刷新 IDEA_REPORT.md；candidates.md 的已杀区/切换日志/方向层留痕与卡状态一致
- [ ] aux 区分数全部标「暂定」，且无一处被用作淘汰依据；novelty 判定区无分数混入

## 14. 已知边界与 v2 规划（未实现，不许假装）

- **图谱路径算子（graph_path）v2**：需离线建领域图谱（千篇级
  抽取）才成立，v1 不做；卡的 operator 枚举与 path_string 出处
  格式已预留（拍板 9.3-B）。
- **I3 第二段重排未独立成命令**：向量粗排 + 按面 LLM 重排目前
  在判定者阅读环节完成（第 8.4 节口径不变）。
- **本领域查新判例集未冷启动**：判定者目前只靠 §8.2 守则与
  判定宪法；判例集（想法+最相关论文+判定+理由）是最值得长期
  投入的自建资产，按领域持续扩充，建成后按 §8.3 材料包交付。
- **试点环（拍板 9.6-B）只落标注纪律**：pilot 字段与卡面标注
  已就位，试点执行归 Light-Experiment，本技能不代跑实验。
- **跨周期记忆只留导出**：memory_export 的方向层条目格式已定，
  收编与检索归 Light-Memory（总路线图最后做）；衰竭状态机
  （approaching exhaustion / claimed territory）在 candidates.md
  方向层留痕里人工维护，未做自动判定。
- **去重仍是字符级**：语义级嵌入去重未接入（离线、无外部服务
  的约束下字符 n-gram 口径如实标注，见第 6 节）。

## 15. 验收口径

见 README「开发记录（节略）」与「v1.0 封版记录」：schema 校验、
状态机每条门的正/反例、killed 分类必填、去重对构造样本的检出、
查新 fixture 测试与真实联网冒烟、交接导出与端到端演示，
测试全过才算完成。
