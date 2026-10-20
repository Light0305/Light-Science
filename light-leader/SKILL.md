---
name: light-leader
description: Use when 需要总控一个 Light-Science 科研项目：建项目骨架、汇总各阶段状态、决定下一步推进哪个阶段，或查看对象注册统一视图时。
version: "1.1"
author: light-leader contributors
license: MIT
---

# light-leader SKILL（v1.0 定版）

> 定位：Light-Science 总控。只做编排，不做阶段内工作：建项目骨架、只读扫描各阶段包的登记头报告全项目状态、按规则表给下一步路由、只读消费 light-memory 的对象注册统一视图。各阶段的内部规程以各包 SKILL.md 为准，本文件只给全链规程与指针，接入模型照此执行总控动作即可。
> 位置：科研流水线 literature → idea → design → experiment → analysis → journal-select（write 前置扩展位）→ write → figure → review，light-memory 横贯全程负责沉淀。总控在每个阶段的开工点与定版点出现，不介入阶段执行过程。
> v1.0 定版（2026-10-20）：薄 CLI 四命令（init / status / route / registry）+ 本规程；演示见 examples/demo-fullrun/demo-report.md（对由各包真实 demo 登记头拼成的项目跑全链，三个 REVIEW_UNAVAILABLE 硬门被 route 逐一点名）。

---

## §1 定位与边界

- **只编排**：总控不重实现任何阶段包的逻辑，不写任何阶段包的文件。status / route / registry 三命令全只读；init 只在空位建骨架且拒绝覆盖。
- **状态只认登记头**：各包登记头的顶层 status 字段是阶段状态的唯一权威读数；总控不从文件存在性、目录新旧推断状态。读不到、解析失败、字段缺失一律逐项点名，不猜。
- **路由是建议不是执行**：route 给下一步与理由、点名硬门与解法指针；真正开工由接入模型按对应包的 SKILL 执行，总控不代跑阶段命令。

## §2 全链接口图

| 阶段 | 技能 | 开工输入（上游终态） | 状态载体 | 状态机 | 终态 | 交接产物与去向 |
|---|---|---|---|---|---|---|
| literature | light-literature | 项目启动即可 | Literature/文献索引.csv 逐篇 status 列 + 证据表.jsonl | 无状态机（逐篇：入库→速读→精读完成等） | 以出现精读完成篇目为可用标志 | 证据行与精读卡供 idea/design 承接；参考文献.bib 是 write 引用的唯一来源 |
| idea | light-idea | literature 证据表有可用证据行 | cards/<idea_id>/idea.yaml 的 status | draft → screened → novelty_checked → pre_mortem_passed → finalized_executable / finalized_conceptual（旁路 killed / parked） | finalized 两档 | 定版卡导出 design_handoff.md + idea_card.json + memory_export.jsonl 供 design 承接 |
| design | light-design | idea 有 finalized_executable 卡（conceptual 级不得直接开工） | designs/<design_id>/design.yaml 的 status | draft → reviewed → frozen（旁路 returned / blocked） | frozen | 冻结导出 experiment_brief.md + design_card.json + expected_registry.jsonl + reproducibility.md 供 experiment 承接 |
| experiment | light-experiment | design 已 frozen 且交接四件套齐备 | executions/<exec_id>/execution.yaml 的 status | intake → sanity → executing → reconciling → delivered（+ blocked） | delivered | 执行包（execution_card + events + reconciliation）供 analysis 承接 |
| analysis | light-analysis | experiment 执行包 delivered | analysis.yaml 的 status | intake → checked → judged → graded → delivered（+ blocked） | delivered | 结论包（conclusion_card + verdicts + conclusions）供 journal-select 指纹与 write 主张登记承接 |
| journal-select | light-journal-select | analysis 结论包 delivered（write 前置扩展位：先选刊再开写） | selection.yaml 的 status | draft → candidates_ready → verified → gated → decided → handed_off | handed_off | 定刊 handoff：journal/target/（check-record.json 九组 + download-manifest + handoff.md）供 write intake 消费 |
| write | light-write | analysis 结论包 delivered + journal-select 已 handed_off | manuscript.yaml 的 status | intake → outlined → drafted → audited → submission_ready | submission_ready | 稿件包供 review 承接；投稿后真实审稿意见的返修走 write 自己的 W7 |
| figure | light-figure | write 章节已 drafted（可与 write 后段并行） | figure.yaml 的 status | intake → contracted → produced → audited → delivered | delivered | 图包 delivery 供 write 的 figures_manifest 对账与 review 的数字↔图对账承接 |
| review | light-review | write 稿件包已 audited | review.yaml 的 status | intake → forensic_checked → paneled → reported → adjudicated → delivered | delivered | 评审交付 + handoff_to_write 回填清单供 write 修订；concern 关闭史供 memory 收编 |
| memory | light-memory | 任一阶段有产物即可建包 | memory.yaml + objects/events/facts/relations 四账 | 无流水线状态（横贯层；收编水位线逐包登记） | 无终态 | registry-view.json 供总控 registry 消费；recall 在各阶段开工点回供 |

三处既定接口（定版，不许另行发明）：

1. **选刊前置位**：journal-select 注册为 write 的前置扩展位，不占十件套编号。固定次序是 analysis 出结论 → 选刊 → 用户定刊 → handoff 落 journal/target/ → write intake；write 开工条件里必须含 journal-select 已 handed_off。
2. **对象注册统一视图**：memory 的 registry-view.json 是只读导出，总控是预定消费方。归属裁决采纳 10-memory/REDESIGN-DRAFT §5.2 预置三条件：(a) ID 分配权留在各上游包，注册视图只登记映射、不发号；(b) 注册记录只增，状态变更落 memory 的事件账，总控不写注册表；(c) 导出格式自 light-memory v1.0 冻结（kind = light-memory/registry-view，version 1.0），总控只读消费，kind 或版本不符时点名报错、不静默降级、不自行重建。视图的所有权归 light-memory，总控为消费方，此裁决定版。
3. **memory 收编触发**：各阶段的定版/终态点即收编触发点（见 §5），由本规程承载：阶段收尾时调用 light-memory 的 ingest 收编该阶段产物。总控的 route 会在提示区列出已达终态的阶段，提醒核对 memory.yaml 的 watermarks 是否漏收。
4. **扩展位登记（LD-02，v1.1 集成步）**：新三包不入十阶段主流水线，按选刊前置扩展位的先例分置登记——light-patent 与 light-software-copyright 为出口层扩展位（与 review 之后并列的权利固化出口），light-crawler 为通道层扩展位（供 literature / experiment 的数据入口）。总控只读其登记头呈现状态与点名（见 §4 规则 6、§7 映射表），不给必经下一步、不影响主流水线收官判定；三包状态流转由 light-memory 的对应适配器收编（见 §5 收编触发点）。

## §3 项目目录规范

一个科研项目的标准布局（init 生成）：

    <项目>/
    ├── project.yaml          总控登记头：项目名/标题/目标/阶段清单
    ├── literature/           light-literature 工作区（其 Literature/ 子目录存索引与四件套）
    ├── idea/cards/           light-idea 想法卡池
    ├── design/designs/       light-design 设计包
    ├── experiment/           light-experiment 执行包
    ├── analysis/             light-analysis 结论包
    ├── journal-select/       light-journal-select 选刊包
    ├── journal/target/       选刊 handoff 落点：guideline/ + templates/ + check-record.json（仅本地使用，不分发）
    ├── write/                light-write 稿件包
    ├── figure/               light-figure 图包
    ├── review/               light-review 评审包
    ├── memory/               light-memory 记忆项目（四账 + obsidian/ 投影 + registry-view.json）
    ├── patent/cases/         light-patent 案件目录（出口层扩展位，一案一目录：case.yaml + ledger.yaml）
    ├── 软件著作权申请资料/     light-software-copyright 案件根（出口层扩展位，copyright.yaml）
    └── data-sources/         light-crawler 工作区（通道层扩展位：crawler.yaml + targets/ + prechecks/）

纪律：

- 各包在自己的阶段目录内用自家命令建包与落产物，内部布局以各包 SKILL 为准；总控不规定包内结构。
- journal/target/ 在项目根、不在选刊包目录内：定刊后从期刊官网下载的模板与作者指南只落此处，仅本地使用，永不进任何公开仓库。
- memory/ 是项目内沉淀层；项目目录整体即完整材料（可整体拷贝迁移），与 light-memory 的本地口径一致。
- 已有历史项目不必迁就此布局：status / route 按登记头文件名全树扫描（见 §7），布局不同照样可读；新项目一律按本规范建。

## §4 阶段路由规程

接入模型每个工作回合的开局动作：先 `light-leader status <项目>` 看全貌，再 `light-leader route <项目>` 取建议，然后按被点名阶段的 SKILL 开工。route 的规则表（与 light_leader/route.py 同源）：

1. **硬门优先点名**：任一未达终态的阶段，其登记头在已登记的门字段族（§5 字段族登记表）有命中时，先点名其门与解法，不给含糊的推进建议。已达终态的阶段即使留痕门标记也不再点名。未登记的字段 route 一律不解读，不许临时加读。
2. **下一步沿流水线取第一个未达终态的阶段**：未建登记头的是开工（理由写明开工条件），进行中的是推进（理由写明当前状态与终态）。特例两处：idea 只有 finalized_conceptual 时 design 不许开工（理由点名 conceptual 级不得直接开工，先试点验证或回 idea 细化）；journal-select 未 handed_off 时 write 不许开工（先选刊）。
3. **并行提示**：write 已 drafted / audited 而 figure 未 delivered 时，提示 figure 可并行开工，不必等 write 定版。
4. **memory 提示**：memory 未建时提示先建并列出已达终态阶段；已建时提示按 watermarks 核对已达终态阶段的收编是否漏收。
5. **收官**：流水线各阶段均达终态且无挂起硬门时，报告收官：稿件可投稿；投稿后收到真实审稿意见走 write 的 W7 返修子流程，不归 review（边界线 = 是否已收到真实审稿意见）。
6. **扩展位点名（LD-02）**：三包永不成为 route 的下一步，也不参与收官判定；只按下列触发点名：patent 案件登记头的 blocked（blocked_gate 族的字段名变体，形态同 {gate_id, detail, fix_pointer}）并入规则 1 的硬门点名；patent 台账任一期限（ledger.yaml 的 deadlines）的到期日在 90 日内或已逾期时，点名案件、期限名与剩余/逾期天数（错过即权利受损，此窗口为集成步判断、常数在 route.py）；software-copyright 案件处于 correcting 时点名补正期限（逾期未补正视为撤回）；review 已 delivered 且项目内尚无案件时，给一条出口层提示（成果可启动 light-patent；若项目产出软件且已定版，可启动 light-software-copyright），措辞是非必经；crawler 逐目标点名预检 blocked（携 blocked_reasons）、未预检、pending_confirmation（待具名确认）、incomplete（携缺项）、expired（预检过期）与熔断目标（携熔断原因，解阻须具名 unblock），不点名采集内容；预检当前态按 crawler 自家折叠语义读（末条 precheck 记录为准，确认行可把 pending_confirmation 翻为 effective），不取追加日志的物理末行。project.yaml 的 extensions 段只登记扩展位清单，stages 十项不被污染。

逐阶段开工条件速查（与 §2 同源）：literature 随时；idea 需 literature 证据可用；design 需 idea finalized_executable；experiment 需 design frozen；analysis 需 experiment delivered；journal-select 需 analysis delivered；write 需 analysis delivered + journal-select handed_off；figure 需 write drafted；review 需 write audited；memory 随时可建、定版点收编。

## §5 跨包纪律汇总

**REVIEW_UNAVAILABLE 式硬门**（跨家族复核不可用时不许伪造收据、状态停在原地）在各包的落点：

| 阶段 | 门 | 登记头落点 | 被拦的跃迁 |
|---|---|---|---|
| idea | 定版跨模型判定门 | idea.yaml 查新区 review_status | pre_mortem_passed → finalized 两档 |
| design | 冻结门（Stage-1 五条 + 跨家族复核） | design.yaml 的 freeze.review.review_status | reviewed → frozen |
| analysis | 交付复核门 | analysis.yaml 的 review_status 与 blocked.reason | graded → delivered（现为 blocked） |
| write | 定版复核门 | manuscript.yaml 的 submission_blocked_reason 与 review 区 review_status | audited → submission_ready |

解法统一：把该包的复核包（review packet）交异家族模型复核，判定经该包自带的回填命令落账（如 idea 的 novelty verdict、design 的 freeze 回填、analysis 与 write 的 review 子流程）；复核恢复前不许绕门、不许手改状态冒充过门。总控 route 只点名与指路，不代办复核。

**门字段族登记表**（LD-04，v1.1 定版；与 light_leader/layout.py 的 GATE_FIELD_FAMILIES 同源）：route 只消费登记过的字段族，新门要被点名先在此登记并与对应包对表，不许在 route 里临时加读字段。

| 字段族 | 登记头落点 | 点名形态 |
|---|---|---|
| review_unavailable（现行） | idea / design / analysis 的 review_status、write 的 submission_blocked_reason 与 review_status（按字段名深搜）；analysis 另认 blocked.reason 含该字样 | 值含 REVIEW_UNAVAILABLE 即点名该包现行复核门 + 统一解法指针 |
| blocked_gate（v1.1 新约，任一阶段可用） | 登记头顶层 blocked_gate 映射：必备 gate_id，可带 detail 与 fix_pointer；字段名变体（LD-02 对表登记）：light-patent 案件头以顶层 blocked 字段承载同形映射 | 按 gate_id 点名，fix_pointer 即解法指针（无指针时回该包 SKILL 查该门规程） |
| return_block（design 先行） | design.yaml 的 return_record（status=returned 时）与 block_record（status=blocked 时） | returned 点名未回补的 returned_items 逐项作缺项指针；blocked 点名 reason 并以 unblock_condition 作解阻指针 |

字段缺失行为（落字，不许变通）：登记头缺某族字段 = 该族无命中，**不等于该阶段无门**；route 不据此断言无门、不解读未登记字段、不猜门义。blocked_gate 形态不合（非映射或缺 gate_id）时不点名、只在 status 落字说明形态不合。各包把既有门迁入 blocked_gate 字段族的动作随各包后续对表逐个登记，本表只增不改已登记族的语义。

**memory 收编触发点**（阶段定版即触发，逐个点名）：idea 卡定版（finalized 两档落定）、design 冻结（frozen）、experiment 交付（delivered）、analysis 交付（delivered）、journal-select 定刊交接（handed_off）、figure 交付（delivered）、write 定版（submission_ready）与 W7 返修收尾、review 交付（delivered，concern 关闭史随之收编）、literature 新篇精读完成。触发动作统一是 light-memory 的 ingest 对应包适配器；漏收以 watermarks 对账发现。扩展位三包同理（MM2-13）：patent 案件状态流转、台账期限与查新/值得结论在案件收尾时收编；software-copyright 案件的定版、段落确认、递交清单与登记号回填在定版/递交点收编；crawler 的抓取批次、预检留痕与目标变更在 run 收尾时收编；三个适配器与九包同构、幂等可重跑。

**会话沉淀触发点**（承 memory MM2-01 交接）：会话收尾或阶段收尾时，接入模型应提示或调用 light-memory 的 epilogue 会话沉淀（scan 切段 + apply 提名进候选通道，只产候选、人工 accept 才生效）；协议细节以 light-memory SKILL §2.5 为准，总控只负责在此触发点点名，不代跑沉淀。

**其余全链纪律（指针，不复述）**：未核实文献不进成稿层（light-literature / light-write 的核实纪律）；期刊专有数值不落库（light-journal-select 的核验纪律）；开源仓库只放干净最终产品、本地管线与用户数据不进仓（全项目发布口径）；交付物为 Markdown（全项目口径）。

## §6 命令速查

| 命令 | 作用 | 写入 |
|---|---|---|
| light-leader init <目录> [--name N --title T --goal G] | 生成 §3 标准骨架 + project.yaml 登记头；已有登记头拒绝覆盖 | 只建骨架 |
| light-leader status <项目> | 逐阶段报告登记头状态、硬门标记、memory 计数，并汇总三扩展位（patent 逐案、software-copyright 逐案、crawler 逐目标）；缺失逐项点名 | 只读 |
| light-leader route <项目> | 硬门点名 + 下一步建议与理由 + 并行/memory 提示 + 收官判定 | 只读 |
| light-leader registry <项目> | 定位并渲染 memory 的 registry-view.json（按类型分组、当前版本指针与状态）；缺失时点名并给生成方式指针 | 只读 |

## §7 状态读取口径

- 扫描范围：项目树内按登记头文件名递归定位（深度上限 7，跳过隐藏目录与缓存）；同一阶段有多个登记头时逐个报告（如多张 idea 卡、多个 execution），不合并、不挑一个冒充全阶段。
- 状态值原样呈现：总控只认各包已知的终态集合做路由判断，未知状态值照原字报告、不 reinterpret。
- literature 例外：无登记头状态机，读 文献索引.csv 的逐篇 status 列计数与同目录 证据表.jsonl 行数；索引不可读时落字报错。
- memory 例外：读 memory.yaml 存在性 + 四账行数 + registry-view.json 是否已导出；计数只报行数，不解读内容。
- 硬门标记按字段名深搜（review_status / submission_blocked_reason），因各包嵌套位置不同；值含 REVIEW_UNAVAILABLE 才算门未过，其余值（如已落收据的 review_id）不触发点名。其余字段族的读取口径见 §5 登记表。

**状态词规范化映射表**（LD-03，v1.1 定版；与 light_leader/statusmap.py 同源）：各包内部状态机不动，总控侧把逐包状态值翻译为规范态（进行中 / 已达终态 / 被门拦 / 旁路；阶段无登记头为「未建」），供 status 汇总呈现与 route 理由标注。映射表变更须与各包 SKILL 对表后显式修改本表与代码常量并跑覆盖断言，不许静默改；表外状态值原样呈现、规范态标注为无，不 reinterpret。

| 阶段 | 进行中 | 已达终态 | 被门拦 | 旁路 |
|---|---|---|---|---|
| literature（逐篇词汇） | ingested / find_failed / parsed / speed_read / 速读完成 / verified | 精读完成 | — | excluded |
| idea | draft / screened / novelty_checked / pre_mortem_passed | finalized_executable / finalized_conceptual | — | killed / parked |
| design | draft / reviewed | frozen | blocked | returned |
| experiment | intake / sanity / executing / reconciling | delivered | blocked | — |
| analysis | intake / checked / judged / graded | delivered | blocked | — |
| journal-select | draft / candidates_ready / verified / gated / decided | handed_off | — | — |
| write | intake / outlined / drafted / audited | submission_ready | — | — |
| figure | intake / contracted / produced / audited | delivered | — | — |
| review | intake / forensic_checked / paneled / reported / adjudicated | delivered | — | — |
| patent（扩展位） | intake / audited / mined / searched / drafted / checked / filed / office_action / responded | granted / closed | — | abandoned |
| software-copyright（扩展位） | draft / facts_confirmed / frozen / materials_ready / confirmed / release_checked | packaged | — | correcting |
| crawler（扩展位，工作区头） | active | —（通道层无终态） | attention | — |

扩展位归类注记：patent 的 granted（授权）与 closed（结案）为案件终局，abandoned 是权利人主动退出；software-copyright 的 packaged 是 v1 终点（材料包 + 递交清单产出），correcting 是补正旁路；crawler 的 attention 仅在存在熔断目标时由其代码机械置位——熔断即抓取被停、须具名解阻，与被门拦语义同构，故归被门拦。crawler 逐目标的预检状态词（effective / pending_confirmation / blocked / incomplete）是逐目标读数、非工作区状态，不入本表，只在 status 呈现与 route 点名中原样消费。

归类注记：blocked（design / experiment / analysis）均须带原因与解阻条件、解阻前不得推进，与门语义同构，故归被门拦；journal-select 的 gated 是主线步骤名（风险门核查步），归进行中，不因字面含 gate 误判；literature 逐篇词汇只服务 status 汇总呈现，route 不据此改变其「索引中有篇目即已起步」的既有判定；memory 横贯层无流水线状态机，不入表。

## §8 v1.0 定版状态

- 构建范围：layout 阶段规格表（接口图机器可读形态）、scaffold 骨架生成、scan 只读扫描、route 规则表、registry 视图消费、CLI 四命令；测试 32 项（骨架 / 十阶段状态读取 / 门标记深搜 / 路由正反例含四门点名与收官 / 注册视图有无与格式校验 / CLI 全链）。
- 演示（examples/demo-fullrun/）：init 建骨架后拼入各包真实 demo 的登记头（literature 索引与证据表、idea C1 卡、design 主设计、experiment 双 execution、analysis 结论包头、journal-select 选刊头、write 稿件头、figure 图包头、review 评审头、memory proj-a 四账复制自发布版演示世界），registry-view.json 由 light-memory 自家命令对副本导出后由总控消费。全链跑通：route 正确点名 idea / design / analysis / write 四处 REVIEW_UNAVAILABLE 硬门（证据均出登记头字段），下一步落在推进 idea 定版，并给出 memory 收编触发点提示。详见 demo-report.md。
- v1.1 增补（2026-10-21）：LD-03 状态词规范化映射表（§7 成文表 + light_leader/statusmap.py，覆盖断言守护）与 LD-04 门字段族登记（§5 登记表 + layout.GATE_FIELD_FAMILIES；route 点名扩至 blocked_gate 统一字段与 design 打回/阻塞记录），测试增至 44 项；演示复跑四门点名不变、status/route 新增规范态标注（demo-report §6 增补）。LD-01 路由准确率评测集归第 4 步与 X-01 合流，本节不含。
- v1.1 集成步增补（2026-10-21，LD-02）：三包纳管——layout 登记扩展位表（EXTENSIONS：patent / software-copyright 出口层、crawler 通道层），init 骨架含三落点目录与 project.yaml 的 extensions 段；status 汇总呈现三包状态（patent 逐案 status + blocked 门 + 台账期限，software-copyright 逐案 status + 补正信息，crawler 工作区状态 + 逐目标预检/熔断）；route 按 §4 规则 6 点名（patent 门与 90 日期限窗口、软著补正、出口层启动提示、爬虫预检与熔断），扩展位不进下一步与收官判定；§7 映射表补三包状态词（逐包对各包 schema 状态常量实核）。测试增至 58 项。

## §9 已知局限（v1.0）

1. route 是单线程流水线视角：只给一个下一步与并行提示，不做多项目组合调度与资源排期。
2. 状态扫描靠登记头文件名定位；上游包若在 v1.1 改名登记头，总控须同步改 layout 表（扫描会落到未发现并点名，不会静默误报状态）。
3. 硬门点名只认 §5 登记过的字段族（v1.1 LD-04 已扩：review_unavailable / blocked_gate / return_block 三族，design returned 携缺项清单、blocked 携解阻条件均可点名）；未登记的门与未登记的字段 route 仍不解读，只在 status 原样呈现。各包既有门向 blocked_gate 统一字段的迁移随各包对表逐个登记，未迁完前两套口径并存、以登记表为准。
4. registry 只消费 memory 的项目级 registry-view.json；跨项目全局层视图（global 记忆根的导出）留待真实跨项目使用出现后再定消费口径。
5. init 只建目录与登记头；各包的包级初始化仍由各包命令在阶段目录内执行，总控不代跑。

## §10 交付收尾格式（全套通用，v1.1 X-10 新增）

全套任何交付报告（各包 demo-report、封版记录、阶段交付说明与一切对用户的交付汇报）结尾必须带以下四行，逐行落字，不许合并、不许省略；没有内容的行写「无」并说明原因，不许整行消失：

- **完成项**：本次实际做完并已验证的事项，逐项带证据指针（文件、测试结果、清单条目）。
- **跳过项**：本次明确没有做的事项及原因（范围外、依赖未到、用户裁决缓行等），逐项点名，不许静默略过。
- **未验项**：做了但没有验证到位的事项（缺环境、缺原文、只达登记级等），逐项点名并注明验证缺口，不许与完成项混写。
- **风险**：用户须知的残余风险与后续触发条件（什么情况下需要回头处理、由谁裁决）。

口径：四行是全套交付的最低披露线。把跳过项写进完成项、把未验项写成已验证，均按造假论。新建的 demo-report 类文件由全套 lint 的收尾格式检查按登记清单强制（含本节标题与四行齐全）；存量报告只报告不拦，补齐与否随各包 v1.1 修订处理。
