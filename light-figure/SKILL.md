---
name: light-figure
description: Use when 需要为稿件生产可交付的图表：生成数据图、为方法与机制图做提示词与原生重绘（Visio / PowerPoint / Illustrator 三路平权），或过图审计门交付图包时。
version: "1.1"
author: light-figure contributors
license: MIT
---

# light-figure SKILL（v1.1）

> 定位：把 Write 稿件包的图表占位变成可交付的图。核心原则——**登记文件是权威源**：每张图的合同、后端、提示词、重绘清单、provenance、审计产物全部先登记后使用；交付时只产 `delivery.yaml` 供 Write 回填，Figure 不直接改 Write 的清单。
> 设计依据：`07-figure/REDESIGN-DRAFT.md`（含用户拍板 D1–D7，文末附录）、`07-figure/LEARNING.md`（16 条硬约束，对应表见 §15）。实现范围：图包数据模型与确定性校验器、样式编译、双线生产（数据图 matplotlib 执行 / 方法图提示词→参考图登记验收→重绘 manifest 与文件级 .vsdx 构建）、provenance append-only 一本账、审计引擎七门、五段状态机全门（含 delivered 交付段：账行逐行复验 + 编号冻结配合）。v1.1 增补（第二轮拍板，FIG-D02–D11）：PowerPoint 文件层生产路线（与 Visio 文件层同级、合同字段分流）、manifest 三件（User.* 语义 ID 钉扎 / renderer-effective-fields 生效字段对账 / arrow_plan 箭头计划 + round_noop 无效轮次门）、合同调色板决定字段、图库参考图六维拆解、交付前本地复核环、Illustrator 精修路线（SVG 桥）、交付 correspondence 对应件清单、工具层执行规程（§16）。2026-10-21 平权补丁（用户明确推翻第二轮 FIG-D03 的 Illustrator 精修定位）：Visio / PowerPoint / Illustrator 三路均为能对参考图做原生 1:1 复刻的对等生产路线——合同后端集扩为三值、共用同一 redraw manifest 契约与语义 ID 纪律；PowerPoint COM 路线由只立规程升为实现形态（manifest 生成 COM 构建脚本 + export-to-verify + com-verify 登记对账）；Illustrator 升为第三条生产路线（manifest 生成 ExtendScript 构建脚本驱动 DOM 从零重建 + DOM 枚举回读审计，印前五项降为交付前终检段，SVG 桥降为导入备选路径）。三路 verified 纪律同构：未经实机证据登记不许置真，gap 如实登记（§8.2a/§8.2b/§16.3/§16.4）。工具层 T2 补丁（2026-10-21）：vsdx 后处理库正式 vendored 进包（0.6.1 版本钉死、BSD-3 许可与署名落字）并落 `redraw post` 命令组（改字/改色/抽取/diff）；ai manifest 跨路线构建账隔离裁决落地——构建账按后端隔离（user-delegated 主会话裁决 2026-10-21）：manifest 内容跨路线继承、rounds/build 构建记录不跨后端继承，派生时剥离外来账并留痕（§8 第 2b 项、§16.2、§16.6）。

---

## §1 图包文件群

| 文件 | 角色 |
|---|---|
| `figure.yaml` | 登记头（权威）：承接快照、目标期刊区（模板记录 id + 图形合同指针 + AI 政策快照）、逐图状态表、回流区 |
| `contracts/<fig_id>.yaml` | 图合同（F0 五点合同，每图一份，字段见 §4） |
| `backend.json` | 数据图后端登记：解析顺序五级的落盘结果 + 逐图覆写表（§5） |
| `journal_contract.yaml` | 期刊图形合同登记：栏宽/字号/格式白名单/色板指针/容差参数（§6），逐刊一份、可被同刊多包复用 |
| `provenance.yaml` | 一本账：每图一条（§9），随图合同开立，哈希钉住 |
| `data/` | 数据图线：`scripts/`（绘图脚本，与图一一对应）、`source-data/`（源数据或指针+哈希）、`previews/`（预览渲染）、`styles/`（样式编译产物：`bundle.json` + `light.mplstyle` + `theme.R`） |
| `schematic/` | 方法图线：`prompts/`（提示词产物，§7；改版旧版存 `prompts/archive/`）、`reference/`（用户参考图，入包即登记哈希）、`redraw/`（重绘清单 +.vsdx 源，§8） |
| `audit/` | 审计产物：`<fig_id>.audit.json`（七门判决，绑定交付物哈希，产物变更即 STALE 必重跑）+ `<fig_id>.alignment-input.json`（produce 落的 plot-area 量测清单）+ `<fig_id>.recheck.json`（交付前本地复核记录，v1.1，§10） |
| `schematic/redraw/`（续） | PowerPoint：`<fig_id>.pptx` + `<fig_id>.pptx-manifest.json`（文件层，§16.3）；COM 实现形态另产 `<fig_id>.com-build.ps1`（构建脚本）+ `<fig_id>.com-export.png/.pdf`（export-to-verify 导出物）+ `<fig_id>.com-verify.json`（实机枚举回读记录，登记后入 manifest 的 `com_route` 段）；Illustrator：`<fig_id>.ai` + `<fig_id>.ai-manifest.json` + `<fig_id>.build.jsx` / `<fig_id>.readback.jsx`（ExtendScript 构建/回读脚本）+ `<fig_id>.dom-readback.json`（DOM 枚举回读记录，§16.4）；SVG 桥导入备选的入口 SVG 放 `schematic/refine/`（§16.4） |
| `exports/` | 交付物（数据图最终 PDF）+ `delivery.yaml`（交付清单，§11） |
| `FIGURE_REPORT.md` | `report` 生成的权威汇总，手工区（MANUAL 标记之间）刷新不覆盖 |

## §2 双线总览

- **数据图线（data）**：定量图一律由代码生成（Python/R），不走图像生成、不走 Visio 重绘（约束 3）。流程：图合同 → 后端决定落盘 → 样式编译（期刊合同 + 色板登记）→ 脚本绘制 → 最终产物审计。
- **方法图线（schematic）**：图库匹配风格 → GPT Image 提示词（核心交付）→ 用户生成并提供参考图 → 按图合同 `schematic_backend` 在 Visio / PowerPoint / Illustrator 三条对等生产路线中选一做原生 1:1 重绘（约束 11/12，三路平权见 §8/§16）。AI 生图只进草稿段，成品必须是所选宿主的原生对象。
- 承接 kind 为 `table` 的条目归数据线登记（表格本体由 Write 承担，Figure 只登记合同与交付指针）。
- 两线在同一图包内并行，状态与审计分线记录、包级汇总。

## §3 状态机

```
intake → contracted → produced → audited → delivered
```

逐图同构推进，包状态由逐图状态机械汇总（`advance` 执行，门不过逐项点名）：

| 段 | 入口门（现行落点） |
|---|---|
| contracted | 承接快照齐全且哈希对齐；目标刊图形合同已登记；AI 政策快照在有效期内（schematic 线）；每图合同五点齐；数据图后端已按解析顺序决定并落盘；方法图已过配色确认门；**每图调色板决定已落字**（合同 `palette_decision`：来源 + 依据 + 确认人/时点，v1.1） |
| produced | 产物齐备性深门：数据图——脚本 + 源数据 + 预览齐备、源级预检全过（样式哈希绑定/禁用色标/轴口径登记）、账面哈希与实物相符、实际用色与调色板决定一致并落 `palette_decision_record`；方法图——提示词产物落盘、参考图入包登记且验收三项落字、重绘 manifest 落字且成品反抽对账无未登记差集（后端按合同 `schematic_backend` 分流：visio → .vsdx / powerpoint → .pptx / illustrator → .ai 且 DOM 回读对账已过、印前终检五项落字无未处置问题；各路证据级如实标注）、provenance 账行齐（提示词版本/生成模型/逐标签核对） |
| audited | 审计门按线全跑且审计记录绑定当前交付物哈希（FRESH）；无 FIX_BEFORE_DELIVERY、无 NOT_AUDITABLE；REVIEW_REQUIRED 逐门有处置理由落字（`audit note`）。过门时逐图行落 `audit_final = pass` |
| delivered | `delivery.yaml` 在场且为现行版（字段与 Write 回填一一对应，§11）；编号已冻结；逐图交付行主文件哈希与图注哈希与现状一致；交付前账行逐行复验全过（账面哈希按实物重算）；逐图审计 FRESH |

`deliver` 命令在 audited 段生成 `delivery.yaml` 并同步冻结编号；冻结后变更交付物须先 `deliver --unfreeze --reason` 登记解冻（旧清单标 superseded），重新交付 version 递增并重新冻结（§11）。

## §4 图合同规程（F0，约束 1）

任何一条线动手之前先落**五点合同**，合同不过不许出图（`contracts/<fig_id>.yaml`）：

1. **核心结论**：`core_conclusion`（一句话主张）+ `results_question`（该图回答的 Results 级问题）。一图一主要主张。
2. **证据链**：`panel_map[]` 每面板一行——`panel_id`、推理角色（十类词表：setup_schematic / representative_example / primary_quantitative_evidence / baseline_or_control / decomposition / stratification / orthogonal_validation / perturbation_or_stress_test / boundary_or_failure_case / mechanistic_evidence）、内容摘要、证据层级（hero / validation / controls_robustness）。判据：**角色多样性 > 指标多样性**。
3. **原型**：`archetype` 四分类——quantitative_grid / schematic_led_composite / image_plate_quant / asymmetric_mixed_modality。
4. **后端**：数据图在 `backend.json` 落盘（§5）；方法图无绘图后端（policy_check 代之，§7）。
5. **期刊/导出合同**：`export_contract_ref` 指向 `journal_contract.yaml`，本图覆写项（如高宽比）必须带理由。

合同固定附带：`evidence_requirements`（统计/源数据/图像完整性注记，无需求显式记 `"none"` 不许留空）、`density_stance`（密度优先/简洁优先 + 理由，约束 7 的取舍落点，不许默认）、`reviewer_risk[]`（审稿风险自问，至少一条，落 risk + disposition）、`data_integrity.exclusions`（无排除显式记 `"none"`；有排除逐条记前后计数/规则/理由——**不得为画图方便删数据**）、`sister_library_refs`（姊妹仓条目引用，§12）。

## §5 后端排他规程（F1，约束 2 / 拍板 D2）

1. **解析顺序五级写死**：①当前请求显式指定 → ②输入明显属某语言 → ③本任务内已确立 → ④落盘偏好 → ⑤皆无则一次性提问。决定结果落 `backend.json`（`backend` + `decided_via` + `decided_at`），粒度按包 + 逐图覆写登记。
2. **默认 Python**（拍板 D2）。**R 的启用条件**（满足其一，逐图在覆写行登记 `reason_code` + `reason`）：`r_decisive_advantage`（图种在 R 侧有决定性优势）/ `pipeline_in_r`（数据管线本身在 R 内）/ `library_r_only`（数据图库只有 R 侧条目）/ `user_specified`（用户明确指定用 R，2026-10-21 补设——用户按自身需求指定即成立，但仍须登记 `reason` 落字说明谁指定、为何指定，无 reason 照样拦）。包级整体采用 R 时同样在登记层落 `reason_code`；包级以 `user_specified` 为依据时同样强制 `reason` 落字。
3. **同图不混后端**：同图双后端登记（覆写重复、覆写与包级冲突、登记头行与解析结果不一致）一律 validate 报错。切换后端只许整图切换并重跑该图全部审计（换后端后旧审计自动 STALE，`audit run` 整图重跑）。
4. **运行时缺失不许跨后端兜底**：选中运行时/包不可用时暂停渲染、报确切阻塞、给本后端安装命令，禁止用另一语言画替代图。唯一豁口是后端无关审计器（只查不绘）。

## §6 期刊合同与容差（F6 合同层，约束 14 / 拍板 D3）

1. `journal_contract.yaml` 逐刊登记：期刊、版本、核查日期、官方来源 URL、栏宽（mm，单/双栏）、最大高度、字号区间与字形地板、字体、主图格式白名单、预览规格、色板登记指针（分类/连续各一，须带 entry_id + version）。数值锚以目标刊官方指南**现行版**为准（Nature 现行：89/183 mm、最大高 170 mm、字号 5–7 pt）；官方新旧口径并存时以现行 Figure Guide 类文件为准并登记核查日期。
2. **尺寸从栏宽确定性推导**（多面板尺寸 = 栏宽 + 行列数），禁止逐图手填 figsize。执行者是样式编译（`style build`）：期刊合同 + 色板登记 → 编译产物落 `data/styles/`（`bundle.json` 含 rcParams 全集与解析后的色板、尺寸参数；`light.mplstyle`；R 侧只产 `theme.R` 文本不执行）。编译结果记 `style_build_hash`（规范化内容哈希，同输入同哈希、无时间戳成分）；期刊合同或色板版本一变哈希即变，旧 bundle 判漂移必须重编译。数据图脚本只许消费编译产物：脚本头声明 bundle 哈希，produce 预检逐项比对（哈希不符、脚本自带 figsize/set_size_inches、自选禁用色标一律落 gap 不许执行）；脚本字体不可用时以 DejaVu Sans 替换并在生产结果落 `font_substituted`，不许静默换字。
3. **容差是期刊合同参数**（D3）：默认照 Yuan 实测参数集——对齐/gutter 1.5 pt、碰撞四阈值（内缩 0.6 pt / 重叠比 0.05 / 裁剪 0.5 pt / 背景豁免 20%）、字形地板 5 pt（`schema.TOLERANCE_PARAMS` 为权威表）。刊方更严从刊（收紧不设限）；**放宽只许经 `tolerance_exemptions` 逐项登记（参数 + 值 + 理由），不许改全局默认放行**——validate 对无豁免登记的放宽值报错。
4. 色板纪律（约束 4）：分类色板默认 Okabe-Ito、连续色图默认 Crameri 感知均匀系、**彩虹色标禁用**；分类与连续机制分开，分类色板不许由连续色图插值生成。色板登记六列（类型/感知均匀/色盲安全/灰度有序/许可/数据版本）在姊妹仓登记表侧执行（§12），Figure 消费时钉版本。

## §7 方法图线：提示词与政策（F3/F4，约束 6/7/8/9，拍板 D1）

1. **配色确认门先行**：生成任何提示词之前先定角色色板（预设选定或用户指定），落合同 `palette_confirmation`（确认人 + 时点）；未定不许出提示词。色值按元素角色登记，提示词只引角色名不写散色值。**v1.1 起配色决定升格为合同正式字段** `palette_decision`（两线通用）：`source` 三值词表（journal_contract 沿用期刊合同登记色板 / gallery_anchor 源自图库条目锚点 / user_specified 用户指定）+ `basis` 依据落字（journal_contract 时须点名色板条目 id 与版本）+ `confirmation{confirmed_by, confirmed_at}`；缺失 = contracted 门拦下点名，来源不在词表或无依据 = validate 报错。`palette_confirmation` 保留为方法图线的确认收据（与 palette_decision.confirmation 同源落字），不再单独充当决定本体。审计合同门与交付前复核（§10）核对实际用色与决定一致，数据图 produce 把决定快照落账面 `palette_decision_record`。
2. **提示词是结构化产物**（已实现：`prompt build` 生成 `schematic/prompts/<fig_id>.md`）：YAML 文件头登记（prompt_id、version、图库三元组引用 {条目 id + 版本、风格锚、绑定提示词版本}、风格规则 {id = 风格锚、版本}、角色色板指针、配色确认记录、政策快照指针）+ 正文六段——**全局 / 分区 / 全局标注 / 风格规格 / 负面约束 / 政策段**（草案旧命名对应：风格锚入全局段与风格规格段、构图与元素清单入分区段逐面板、文字标注约束即全局标注段）。纪律：正文只引色板角色名、不落 hex 色值（生成后自检正文无 hex）；每个模块框必须有子内容、不许空白占位与「...」省略；**度量数字不许入图**（px/pt/% 类字面量严禁写进会进图的文本，只有语义数字可入图；生成前逐标签机械拦截）。改版 = version 递增 + 旧版存 `prompts/archive/<fig_id>.v<n>.md`；首版 version 取图库条目绑定的提示词版本。生成后回填账面 `prompt_version` 与政策快照指针。**参考图六维拆解（v1.1，FIG-D09）**：合同引用图库条目时，`sister_library_refs.method_gallery.reference_breakdown` 必须落**六维结构化拆解**——`palette_hex`（参考图主色实测 hex 列表）/ `layout_flow`（布局流向）/ `module_style`（模块形态）/ `annotation_style`（标注字体风格）/ `information_density`（信息密度）/ `special_elements`（特殊元素）；缺任一维 validate 报错点名。拆解是提示词风格段的事实源：`prompt build` 把五个文字维写进风格规格段，`palette_hex` **只以指针出现、绝不进正文**（沿用正文无 hex 纪律）——色从角色色板来，拆解只供构图/形态/密度判断。**提示词多版变体（2026-10-21 补设）**：同一图库三元组与角色色板之下，`prompt build --variants <id,...>` 可并行产多版超级提示词供用户按项目与论文实情选版——变体只在**构图 / 密度 / 布局流向**三维上区分，词表三值（工具 `schema.PROMPT_VARIANTS`）：`compact` 紧凑型（单行主流向紧凑排布、高密度、左入右出水平流）/ `spacious` 舒展型（宽松网格、低密度、水平流分段留白）/ `layered` 分层型（自上而下分层成带、中密度、自上而下纵向流）。每版独立文件 `schematic/prompts/<fig_id>.<variant>.md`，各自六段完整、正文无 hex 与标签度量拦截等既有纪律逐版适用、独立 version 迭代与归档（`archive/<fig_id>.<variant>.v<n>.md`）；变体不改三元组与色板（front matter 的 gallery / role_palette / palette_confirmation 与单版同源），只改三维执行口径（风格段落「变体执行口径（本版为准）」，与六维拆解口径不一致处以变体口径为准）。变体集合登记进合同 `prompt_variants{variants[], selected_variant}` 与账面；用户选定经 `prompt select` 落字（账面 `prompt_version` 取所选变体 version），重建变体集时已选变体不在新集合内则选定自动清空须重选。**选定门**：变体模式下参考图登记须以 `reference add --variant` 指明所据变体且与 `selected_variant` 一致——未选定 / 未指明 / 不一致均拦下点名；验收同口径复核并把所据变体记入验收记录（账面 `reference_variant`）。produced 门认「变体集文件齐备 + 已选定」与单版产物等价；不带 `--variants` 的单版构建行为不变（N=1 兼容）。
3. **政策口径（拍板 D1：「一条硬拦 + 一本账 + 一次逐刊核对」）**：
- 立场（用户拍板）：人工原生重绘成品不算 AI 生图（Visio / PowerPoint / Illustrator 任一宿主同理）——成品无任何 AI 生成像素、每个形状都是人放的原生对象。**不设把重绘图当 AI 图的阻断门**。政策文本依据见 LEARNING 约束 8（受禁对象只限 AI 直接产出的图像物件；无条款及于构思/参考；具体情形属文本沉默，残余风险为编辑裁量）。
- **一条硬拦**（全线唯一政策硬拦，机械执行）：AI 参考图本体文件不得进入交付/投稿包（已实现：审计 `policy_block` 门按 SHA-256 比对 provenance 账面参考图哈希，交付集 = `exports/` 全部文件 + 重绘成品，任一同哈希即 FAIL 点名文件；重绘成品哈希天然不同、不拦。合同 `policy_check.reference_not_in_delivery` 为自检落字，落 false 即 validate 报错）。
- **一本账**：provenance 逐图留痕（§9），是披露生成的唯一事实源。
- **一次逐刊核对**：投稿前经 Write 模板记录的 AI 政策组逐刊核对（字段 + `verified_at`，过期自动失效）；Science 系在核对环节标红提示「投稿前向编辑部书面问询」；目标刊从严或编辑答复否定时，该刊切**无 AI 参考降级路径**（合同 `policy_check.degradation_path = no_ai_reference`：方法文本 + 组件库按 spec 先行拼装，跳过 GPT Image 段）——路线不断，只换入口。
- **政策依据三问（口径修订条文，v1.1 落字；学习期定版，依据 `07-figure/LEARNING.md` 约束 8）**：本立场不是「我们觉得没问题」，而是逐条核对政策文本后的结论——(1) 各刊 AI 政策的受禁对象只限 **AI 直接产出的图像物件**（生成/编辑出的图像本身），三宿主（Visio / PowerPoint / Illustrator）原生重绘成品不含任何 AI 生成像素与 AI 图像对象，不在受禁集合内；(2) **没有任何条款及于构思或参考环节**——用 AI 图作构图/风格参考再由人重绘，政策文本未设禁止；(3) 对「AI 参考 + 人工原生重绘」这一具体情形政策文本**属沉默**，因此残余风险不在文本层而在**编辑裁量**（个别编辑部可能从严解释，其中 Science 系最严）——这正是逐刊核对与 Science 书面问询提示存在的原因，而不是给重绘成品加阻断门的理由。**逐刊核查依据纪律**：核对时以目标刊**当期**作者指南/AI 政策页原文为准（政策文本会移动改版，学习期摘录只作定位线索、不作当期依据），核对记录落指南页面引用 + 核查日期（`verified_at`），过期即失效、须按当期原文重核；披露文本由 provenance 账生成（§9/§11），不凭记忆手写。
4. **科学复核独立于政策**（约束 9）：披露 ≠ 免责。参考图验收与重绘两处各执行一次复核清单：逐个标签逐字对原文核对、每个结构对领域事实核对、公式/分子式/数值算对。**照描而不核事实是红项**（Frontiers「AI 大鼠图」撤稿案：作者已披露，败在三道关无人核事实）。

## §8 Visio 重绘（F5，约束 11/12，拍板 D4）



1. **重绘清单是单一真相源**（`schematic/redraw/<fig_id>.manifest.json`，PPT 线同构为 `<fig_id>.pptx-manifest.json`，Illustrator 线同构为 `<fig_id>.ai-manifest.json`——三路共用同一 manifest 契约：同一参考图锚点、画布标定、面板系、形状/箭头计划/位图残留/生效字段全集）：面板四角标定（全局像素框 + 面板局部坐标系）动手前落字，对象清单（稳定语义 ID、类型、局部坐标框 0–1、样式 token、逐字文本、连接语义、z 序）足以不读其他文件重建本图；不在清单里的东西按漏画处理；要加形状先改清单。成品可反抽形状清单与正向清单闭环对账。状态只经工具推进、不许手写。命令面（已实现）：`redraw init`（按合同面板 + 已登记参考图生骨架，标定待补）→ 补齐标定后 `redraw install`（全量契约校验 + 与账面参考图哈希对表）→ `redraw build` → `redraw extract`（反抽对账）；Visio 线后处理命令组 `redraw post extract|text|fill|diff`（vendored vsdx 格，不承担重建，§16.2）；PPT 线同构命令面 `pptx init/install/build/extract` + COM 实现形态 `pptx com-script/com-verify`（§16.3）；Illustrator 线同构命令面 `ai init/install/build/extract`（build = 生成 ExtendScript 构建/回读脚本，extract = 登记 DOM 回读对账，§8.2b/§16.4）。坐标变换只在一处实现（面板局部 0–1 → 全局像素 → 英寸、Y 翻转），校验与构建共用，三路的脚本生成与回读换算都只许消费这一处变换。
1a. **User.\* 语义 ID 钉扎（v1.1，FIG-D04；三路同构）**：构建出的每个图对象必须把语义 ID 写进宿主原生字段——.vsdx 形状写 ShapeSheet 的 User 段（`User.SemanticId`，连接形状另写 `User.ArrowPlan/ConnectFrom/ConnectTo`）；.pptx 对象写形状名 + `cNvPr descr` 标记（`light-figure:user-id=<id>`）双写；.ai 对象写对象名（`PageItem.name` = 语义 ID）+ `PageItem.note` 标记（`light-figure:user-id=<id>`，连接线另以 `light-figure:arrow=<pid>;from=..;to=..` 记绑定）双写——Illustrator 没有 ShapeSheet 对应物，等价钉扎 = 对象命名 + note 标记 + manifest 边车，三者由 ExtendScript 枚举回读（`ai extract`）逐个核对。`extract` 回读语义 ID 与清单逐个对账，缺失/被改即对账失败点名——语义 ID 不是清单里的自说自话，是钉进成品、可被第三方工具读出的事实。
1b. **renderer-effective-fields 生效字段对账（v1.1，FIG-D05）**：manifest 可落 `renderer_effective_fields` 声明渲染器实际消费的字段集（权威全集见工具 `schema.RENDERER_CONSUMED_FIELDS`）；校验逐项比对——**声明生效但渲染不消费**的字段点名（写了等于没写）、**形状用了但未声明生效**的字段点名、渲染词汇表之外的字段点名。没落声明时按形状实际用到的字段机械推导，不许靠声明掩盖未生效字段。
1c. **arrow_plan 箭头计划 + round_noop 门（v1.1，FIG-D06）**：manifest 升版（version ≥ 1.1）或落了 `arrow_plan` 键即进严格模式：箭头先行登记成计划（`arrow_plan_id` + from/to + 事实依据），每个 connect 必须绑定计划 id 且端点与计划一致，计划登记了却没有形状实现的箭头同样点名；v1.0 格式 manifest 不追溯（宽容读、产出端升版）。每次 build 把内容投影哈希（形状/面板/残留/画布/箭头计划，不含时间戳与构建元数据）追加进 manifest 的 `rounds` 轮次账；**内容零变化的重复 build 被 round_noop 门拒绝并点名**——metadata-only 的往返不许冒充新一轮构建。
2. **Visio 路线内三格分工**（此「三格」是 Visio 路线内部形态，与 §8.2a/§8.2b 的三宿主平权是两层概念）：COM 原生重建（Visio 路线内主形态，有 Windows + Visio：两级坐标标定、局部坐标越界即断言、参考图只作临时锁定描图层且交付前移除、.vsdx 为唯一真相源、同源导出；PPTX 导出物是渲染幻灯片不是原生形状，交付说明须标注。v1.0 只立规程与接口——`redraw build` 对 route=com 如实落 gap，不冒充执行）/ 文件级从零构建（正式路线，**已实现**：手写 OPC 从零拼 .vsdx——内容类型/各级 rels/文档属性/pages/page1，Shape 内 Cell 必在 Section/Text 之前，几何走多段线近似，zip 条目时间戳固定保确定性；位图残留以 ForeignData 形状嵌入并绑 media rel，未在清单绑定的位图形状构建期报错）/ 文件级后处理（vsdx 库做批量改字改色、形状抽取与两文件 diff，**没有从零绘制 API，不承担重建**；T2 补丁已实现：dave-howard/vsdx 0.6.1 vendored 进包、版本钉死，命令面 `redraw post` 命令组，纪律见 §16.2 后处理格）。COM 路线的连接/枚举/坐标/保存校验细则见 §16.2，后处理工具的真实身份与许可见 vendored 目录的 LICENSE 与 VENDOR.md（署名 Dave Howard，BSD 3-Clause）。
2a. **PowerPoint 文件层（v1.1 正式路线，FIG-D02）**：方法图后端由合同字段 `schematic_backend: visio | powerpoint` 逐图分流（缺省 visio；数据图不许落此字段）。powerpoint 线以 python-pptx 文件层从 manifest 生成原生形状 .pptx（幻灯片尺寸 = 图尺寸、一页一图、形状全原生），与 Visio 文件层同级：同样的 manifest 契约、同样的语义 ID 钉扎与箭头计划、同样的原生性审计（OPC 口径）。文件层产物恒标 `powerpoint_verified: false` + 证据级 `file_layer`——文件层结构核验 ≠ PowerPoint 实机验证，实机冒烟（Windows + PowerPoint 打开/导出比对）属环境依赖项，规程见 §16.3，无实机时如实登记 gap、不许声称验过。**PowerPoint COM 路线（2026-10-21 平权补丁升为实现形态）**：manifest 经 `pptx com-script` 生成 COM 构建脚本（PowerShell + COM 对象模型直建原生形状，落 `schematic/redraw/<fig_id>.com-build.ps1`），在装有 PowerPoint 的 Windows 机器上执行——COM 直建 .pptx（落回标准成品路径，其后照常走 `pptx extract` 文件层反读对账）、同轮导出 PNG/PDF 做 export-to-verify、枚举形状写 com-verify JSON，再经 `pptx com-verify` 登记对账（枚举几何/文本/ID 钉扎/实连端点/导出物哈希逐项比 manifest）。`com_route.powerpoint_verified` 只许在登记对账无差 + 回读带 PowerPoint 版本 + 执行者 `--by` 落字时置真；脚本生成本身只给 script 级证据，无实机时脚本与规程落地 + gap 登记即为完成口径，不冒充执行（§16.3）。
2b. **Illustrator 生产路线（2026-10-21 平权补丁，FIG-D03 精修定位就此作废）**：方法图后端由合同字段 `schematic_backend: visio | powerpoint | illustrator` 逐图分流（缺省 visio；数据图不许落此字段），三路对等——同一参考图在任一路线的目标都是宿主原生对象的 1:1 复刻，不存在「只有某一路能生产」的分工。Illustrator 路线形态：ai manifest 经 `ai build` 生成 ExtendScript 构建脚本（`<fig_id>.build.jsx`，驱动 Illustrator DOM 从零新建文档、逐形状落原生对象：路径/区域文本框/连接线与箭头头/登记残留置入项，几何由 manifest 经单一变换算成文档坐标写成字面量）与回读脚本（`<fig_id>.readback.jsx`，枚举全部 PageItem 的名/note/类型/几何/逐字文本 + 置入项与印前事实，换算回包口径写 `<fig_id>.dom-readback.json`）；在装有 Illustrator 的机器上依次执行两脚本、把 .ai 存回本包，再经 `ai extract` 登记回读对账——几何（容差 0.02 in）/文本逐字/User ID 钉扎/箭头端点/置入项对残留登记逐项比对，未登记对象与未登记置入项一律点名。证据级两档：`script`（只生成脚本）→ `dom_readback`（回读对账已过）；`illustrator_verified` 只许在对账无差 + 回读带 Illustrator 版本 + .ai 已存回本包 + 执行者 `--by` 落字四件齐时由 extract 置真。**印前五项**（rgb_mixed / broken_links / low_res_images / white_overprint / pdfx）由 extract 按回读事实机械计算落 ai manifest 的 `preflight` 段，是本路线交付前的终检（produced 门逐项验：未落字或任一项为真未处置即拦），不再是路线身份。**SVG 桥降为导入备选路径**：仅当用户已有 SVG 素材要导入 Illustrator 时用——入口先过 `svg-check` 受限子集校验，导入后必须以 SVG 文本清单逐字对账（导入会静默丢字形/改字体，丢字以清单抓），本路线的主生产路径是 ExtendScript 从零重建、不是 SVG 导入。本包环境无 Adobe 软件：脚本生成 + 回读契约 + gap 登记即为本路线当前完成口径，实机执行未跑通前交付行 `illustrator_verified: false` 如实标注（§16.4）。**构建账按后端隔离（user-delegated 主会话裁决 2026-10-21）**：同一图跨路线重产时，manifest 内容（形状/文本/语义 ID/标定/箭头计划）跨路线继承，rounds/build/dom_readback/reconciliation 等构建记录不跨后端继承——从 visio / powerpoint 路线的 manifest 派生 ai manifest（`ai install` 登记外来 manifest）时，外来构建账被剥离归零、本路线独立起账，剥离全数记进 ai manifest 的 `derived_from` 留痕（源路线、被剥轮次数、被剥 build 记录摘要、裁决出处）；round_noop 只在本路线自家账内比对——外来 rounds 的内容投影哈希不许拦本路线首轮 build（工具规划 P5 实测的故障形态：整份继承 file_build 账的 ai manifest 首轮 build 被误拦，回归测试已钉住）；外来 reconciliation 的对账结论更不许冒充本路线已对账。本路线自家 ai manifest 重登记不触发剥离（backend 自证身份者账皆自家账）。
3. **无宿主环境交付口径**：文件级路线产出的 .vsdx 是正式交付物，但交付清单中该图须带 `visio_verified: false` 与「未过 Visio 实机验证」注记（如实落字，不许声称通过 Visio 验证）。PowerPoint COM 与 Illustrator 两条实机路线同口径：交付行分别带 `powerpoint_verified`（顶层字段仍只由文件级 extract 对 .pptx 落字，COM 路线的登记结论记在 manifest `com_route` 段与交付注记中）/ `illustrator_verified` 与证据级注记，未经实机证据登记的结论一律 false 并注明未验证原因。
4. **位图残留预先声明**：只许照片/视频帧/显微图/热图/复杂纹理/极密证据条六类、且为精确裁剪局部；未登记者不许以位图形态出现在成品中。原生性靠机械审计验（包内 media 清单 + 形状数 +「1 形状 1 位图」警告），不靠声明。

## §9 provenance 一本账（约束 10）

`provenance.yaml` 逐图一行，随图合同开立：

- 方法图：`prompt_version`、生成模型 + 版本、参考图哈希、重绘源.vsdx 路径 + 哈希、逐标签核对完成标记（核对人/时点）、政策快照指针、人工修正日志指针。变体模式另记 `prompt_variants`（变体 id 集）、`selected_variant`（选定变体）与参考图 `reference_variant`（所据变体，验收记录同记）。
- 数据图：后端 + 运行时版本、脚本哈希、源数据哈希、样式编译产物哈希、色板登记版本。

纪律：账行只增不改历史——更新命令已实现（`provenance set`，append-only）：旧行组件哈希记入 `history[].supersedes`、新行带 `row_hash`、逐字段 from→to 与更新人/时点同账留痕，`provenance show` 可查全链；哈希字段强制 SHA-256 格式，`redraw_source` 须 {path, hash} 成对。生产命令（produce / reference add / prompt build / redraw build）自动回填各自负责的账面字段，produced 门逐项验账实相符（账面哈希 ≠ 实物哈希即点名）。图进入 produced 段起必填项缺项即 validate 报错（方法图缺参考图哈希或重绘源、数据图缺脚本/源数据哈希）；交付前由 `deliver` 逐行复验哈希（`verify_provenance_rows` 按实物重算比对），被改即拒交付。账同时供 Write 的 use_log 对接与逐刊披露文本生成消费。

## §10 审计门（F6，约束 13/15）



审计对象一律是**最终产物文件**（数据图 = `exports/<fig_id>.pdf`，方法图 = `schematic/redraw/<fig_id>.vsdx`，powerpoint 后端 = 同目录 `<fig_id>.pptx`，illustrator 后端 = 同目录 `<fig_id>.ai`），产物哈希写入每份审计 JSON，产物变更后审计即 STALE 必重跑。PPTX 的原生性门按 OPC 口径执行：未登记的图片对象、整页单图、对象命名与清单不一致任一即 FAIL（登记的残留图片对象按清单核对、带 media 哈希）。合同门对 powerpoint 后端核对 pptx 构建记录在场与 `powerpoint_verified: false` 如实标注，落 true 即以「虚假声称实机验证」点名拦截；illustrator 后端同构：合同门核对 ai 构建记录在场、`illustrator_verified: true` 必须有合格登记（DOM 回读对账 ok + 回读带应用名/版本 + verified_by 落字）支撑，无支撑即以虚假声称点名；原生性门对 .ai 不解析二进制——证据面是登记在案的 DOM 枚举回读对账记录：无回读记 NOT_AUDITABLE（不许声称已审），回读在场时对账未过、未登记置入位图、无原生对象只有整页置入图、登记置入项分辨率不足任一即 FAIL（与另两路整页图硬拦同口径）。七门：对齐门（plot-area 量测 vs 可比组，豁免须登记理由，禁止调大容差掩盖例外）/ 碰撞门（FAIL 三类阻断、WARN 记录理由）/ 字形门（内容流 Tf 实测 ≥ 地板）/ 合同门（尺寸/格式白名单/可编辑文本未转曲/色板合规）/ 原生性门（方法图，§8.4)/ 诚实门（数据图，拍板 D6 分层硬度：反转轴检出阻断；截断轴声明对照——未声明阻断、已声明放行留记录；宽高比与面积编码先登记 + 警告）/ 政策硬拦（§7.3，参考图本体不入交付集）。NOT_AUDITABLE 不许声称审计通过。

**运行法（已实现）**：`audit run [--fig <id>]` 按线全跑并落 `audit/<fig_id>.audit.json`（绑定 `artifact_sha256`、容差快照、工具版本）；`audit-status` 逐图报 FRESH / STALE / MISSING / NO_ARTIFACT。判决四态：PASS / REVIEW_REQUIRED / FIX_BEFORE_DELIVERY / NOT_AUDITABLE（门不适用记 `applicable: false`，不占判决）。实测口径：对齐/碰撞/字形三门在最终 PDF 上真量测（PyMuPDF 抽文字行框/描边/填充/图像与内容流 Tf 算符），量测清单由 produce 同源生成、清单哈希与产物不符即 NOT_AUDITABLE；诚实门消费脚本头登记（判据在登记层，缺登记落 REVIEW 不许默认诚实）；原生性门解 .vsdx 包做 media 清单 + 形状计数（整图嵌入、未登记位图、登记残留缺失、描图层未移除均 FAIL）。**STALE 处置**：产物任何变更后先重跑 `audit run` 再谈过门，STALE 状态下不许落处置理由。**REVIEW 处置**：`audit note <fig> --gate <门> --reason <理由>` 逐门落字（仅 FRESH 时许落，同哈希重跑保留既有处置）；audited 门逐门核对，无落字即点名拦下。

**交付前本地复核环（v1.1，FIG-D11）**：`recheck [--fig <id>] [--panels a,b]` 在交付前对最终产物做一轮**纯本地机械复核**，不依赖任何外部服务：数据图查整页尺寸 vs 期刊合同栏宽与最大高、字体真嵌入（查 FontDescriptor 的 FontFile 键，不许用会误报的抽取缓冲判据）、矢量描边/填充实际用色 vs 调色板决定（中性色豁免）、位图有效分辨率 vs 合同 dpi 地板（无位图时抽查预览 PNG ≥300 dpi）；方法图查页/幻灯片尺寸 vs manifest 画布标定、User 语义 ID 齐备、包内 media vs 残留登记、实际用色 vs 角色色板；illustrator 线无 .ai 二进制可量测，复核消费 `ai extract` 登记的 DOM 回读（页尺寸 / 对象 User ID 钉扎 / 置入项对残留登记 / 对账结论），无回读即 fail 点名，回读口径在记录中如实声明。结论落 `audit/<fig_id>.recheck.json` 并**如实声明量测口径**（文件层结构量测，不是渲染量测，不冒充像素级一致性）；`--panels` 为局部复检（只查指定面板的用色/ID 并在记录 scope 里落字，不冒充全图复核）。复核只产 findings、不改七门判决——发现问题回对应生产段修，不许在复核层放行。

## §11 与 Write 的接口（交付回填）

Figure **不直接改** Write 的 `figures_manifest.yaml`，交付只产 `exports/delivery.yaml`（`deliver` 命令生成）：顶层含包状态、清单版本（`version`，解冻后重交付递增）与现行标记（`status: current`；被取代的旧清单标 `superseded` 不删）、编号冻结块、逐图交付行。

| Write figures_manifest 需要 | delivery.yaml 提供 |
|---|---|
| figure_id + 交付状态 | 逐图交付行（`delivery_status: delivered`，deliver 时落字） |
| 交付文件 + 版本 + 文件哈希 | 逐图交付文件路径 + SHA-256（deliver 时按实物重算；数据图含风格构建哈希，见下行） |
| 图注哈希对账 | 图注哈希（承接快照值，与现状逐图比对一致才许交付） |
| 图件 provenance | 数据图：脚本/源数据/样式构建三哈希 + 运行时版本；方法图：账行指针 + 提示词版本/生成模型/参考图哈希 + 图库三元组与组件许可汇总 |
| AI 披露素材 | 方法图 `ai_disclosure` → Write use_log 对接字段（模型、提示词版本、重绘方式、参考图本体不在交付集标记） |
| 对应件清单（v1.1，REV-D09） | 逐图 `correspondence`：源资产映射（路径 + SHA-256；参考图本体只给哈希、路径记 null 不进交付集）+ 内容级哈希（数据图 = 对齐量测面板组件哈希、方法图 = 反抽形状集哈希），供 Write/Review 按图追溯「这张交付图由哪些源资产、哪一版内容生成」 |

**编号冻结配合（与 Write 冻结纪律同构）**：首次 deliver 与编号冻结同步发生（`figure.yaml` 落 `numbering_freeze{frozen, at, by}`）；冻结后任何交付物变更，`deliver` 一律拒绝，须先 `deliver --unfreeze --reason <理由>` 登记解冻（旧 `delivery.yaml` 标 superseded、解冻事实追加进 `numbering_changes[]` 只增不改），变更后重新审计、重新 deliver（version 递增、重新冻结）。delivered 后新增/删除图走变更登记并通知 Write 重对账（回流条目记 `figure.yaml` 的 `reflux[]`，只生成条目不越权改上游）。

**交付前复验**：deliver 先逐行复验 provenance 账（账面组件哈希按实物重算，任一不符即拒交付并点名分量），再验逐图主文件与图注哈希；delivered 门复跑同一套校验，含 delivery.yaml 已被取代或与产物漂移均拦下。

## §12 姊妹仓消费接口（F7，约束 16，拍板 D5/D7）

Figure 消费的是三库的**登记表**（条目记录），不是仓内文件；消费时把条目版本钉进图合同与 provenance 账：

- **方法/机制图库**：条目 = **三元组**（风格锚 {构图类型/密度档/角色色板/线条 token} ↔ 参考图 ↔ 绑定提示词版本）+ 引用的风格规则文件（按刊/会成册、独立版本化）；已发表图只登记出处 + 哈希 + 风格标签、**不打包原图**；许可字段口径统一为「图内容复用许可」，空许可条目不许进可用集。合同引用字段：`sister_library_refs.method_gallery = {entry_id, version, style_anchor, prompt_version}`。
- **Visio 组件库**：组件 = {component_id + 版本、原生源指针 + 哈希、稳定语义名、逐条许可（无标准许可位时写进形状名或 Shape Data 随形携带）、分类}。合同引用：`sister_library_refs.visio_components[]`。
- **数据图库**：样式条目 {.mplstyle/theme + 版本 + 核查日期 + 期刊数值出处}、色板条目 {族/变体/[(语义名， HEX）]、类型、感知均匀/色盲安全/灰度有序、许可、数据版本 + DOI}、图种成例。合同引用：`sister_library_refs.data_gallery = {entry_id, version}`；期刊合同色板指针同口径（§6.4）。

三库启动时机（D7）：Figure v1 先定本接口与 schema，封版后按数据图库 → 组件库 → 方法图库序启动 v0 种子批。

## §13 交付自检（v1.0）

- [] 每图合同五点齐、词表合法（validate 无 contract.* error）
- [] 后端决定已落盘且无冲突，R 覆写逐图带 D2 依据
- [] 期刊合同已登记、数值合法、容差放宽均有豁免登记
- [] provenance 账行与逐图状态表一一对应
- [] 承接快照哈希与源文件对齐（无 snapshot_drift）
- [] 方法图政策快照在有效期内、配色确认已落字（contracted 门）
- [] `style build` 已跑且 bundle 与现行期刊合同一致（无漂移）；脚本头哈希与 bundle 相符
- [] 数据图脚本头登记齐（panels/axes/aspect/area_encoding/palette），源级预检零 gap
- [] 参考图已入包登记且验收三项由核对人落字；参考图本体不在 `exports/`
- [] 重绘 manifest 状态 built/verified、反抽对账 ok；文件级构建的图带 `visio_verified: false` 落字
- [] 逐图审计 FRESH：无 FIX、无 NOT_AUDITABLE，REVIEW 门逐门处置理由落字
- [] 账实相符：账面脚本/源数据/参考图/重绘源哈希逐项与实物一致
- [] `deliver` 已生成现行版 `exports/delivery.yaml`：交付前账行逐行复验全过、逐图主文件哈希与图注哈希与现状一致
- [] 编号已冻结（`numbering_freeze` 落字）；冻结后的变更均有解冻登记与理由、旧 delivery.yaml 标 superseded
- [] delivery.yaml 中方法图的 `visio_verified` 标记与构建路线相符（文件级构建恒为 false 并带注记）
- [] （v1.1）每图合同 `palette_decision` 已落字（来源词表合法 + 依据 + 确认人/时点）；数据图账面 `palette_decision_record` 在场
- [] （v1.1）引用图库条目的图 `reference_breakdown` 六维齐备；提示词正文含五维文字、无 hex
- [] （补丁）走多版变体的图：变体集已构建并登记合同 `prompt_variants`（每版六段齐、无 hex）、`selected_variant` 已选定；参考图登记与验收的所据变体与选定一致（账面 `reference_variant` 在场）
- [] （v1.1）manifest v1.1：arrow_plan 与 connect 逐条绑定、语义 ID 已钉进成品（extract 对账含 SemanticId 校验）、rounds 轮次账在场且无 noop 轮
- [] （v1.1）powerpoint 后端的图：pptx manifest 对账 ok、交付行 `powerpoint_verified: false` + 注记在场
- [] （v1.1）交付前 `recheck` 已跑且记录在场（全图或如实标注的局部 scope），findings 中的 fail 已回生产段修复
- [] （v1.1）delivery.yaml 逐图 `correspondence` 在场：源资产哈希可按实物复算、内容级哈希与审计/反抽产物一致
- [] （平权补丁）illustrator 后端的图：ai manifest 对账 ok（DOM 回读：对象/文本逐字/User ID 钉扎/箭头端点）、`preflight` 五项落字且无未处置问题；交付行 `illustrator_verified` 与登记结论相符（如实标注证据级 script / dom_readback）
- [] （平权补丁）走 PowerPoint COM 路线的图：`com_route` 在场（构建脚本哈希可复算）；已登记者 verify 对账 ok 且导出物哈希在场，未登记者 gap 如实标注、不许声称实机验证
- [] （遗留兼容）合同落了 `illustrator_refinement` 段的旧图：按 FIG-D03 遗留口径校验通过（新图不许再以精修段代替生产路线登记）

## §14 失败模式（v1.0）

| 编号 | 失败 | 处置 |
|---|---|---|
| F1 | 承接源变动致快照漂移 | 重新 intake，不许静默沿用旧快照 |
| F2 | 同图双后端登记 | validate 报错定位冲突来源（覆写/登记头行），改登记后重跑 |
| F3 | 容差被私自调大 | 无豁免登记即报错；确需放宽走 tolerance_exemptions 逐项落理由 |
| F4 | R 覆写无依据 | 补 reason_code（D2 四条件之一，含 user_specified）+ reason，否则改回 Python |
| F5 | 政策快照过期 | 按目标刊当期原文重新核对并重新登记，旧快照不许沿用 |
| F6 | 参考图本体混入交付集 | `policy_block` 门按哈希机械拦并点名文件；移出交付集后重跑审计 |
| F7 | 审计后改图致 STALE | 旧审计作废，重跑 `audit run`；STALE 下不许落处置、不许过 audited 门 |
| F8 | 整图嵌入冒充重绘 | 原生性门 FAIL（未登记位图/整图尺寸比对/1 形状 1 位图）；回 manifest 逐形状重绘，位图只许登记过的六类残留 |
| F9 | 反转轴 / 未声明截断 | 诚实门阻断；改脚本登记与画法（截断须声明落字），不许改登记造假过门 |
| F10 | 样式哈希漂移 | 期刊合同或色板变更后重跑 `style build`，同步脚本头哈希后重跑 produce 与审计 |
| F11 | 反抽对账有未登记差集 | 成品与清单不一致：先改清单再重建，或按实物补登记形状；对账 ok 前不许过 produced 门 |
| F12 | 参考图被静默替换 | 入包登记后哈希钉账，重复登记直接拒绝；换图须撤销验收并走账面更新留痕 |
| F13 | 交付前账行复验哈希不符 | `deliver` 拒交付并点名分量；正当变更走对应生产命令回填账面（produce / redraw build / provenance set），不明变更按 F12 同纪律核查来源 |
| F14 | 编号冻结后改图 | `deliver` 拒绝：先 `deliver --unfreeze --reason` 登记解冻，改图后重新审计、重新交付（version 递增、重新冻结） |
| F15 | delivery.yaml 已被取代或与产物漂移 | delivered 门点名拦下；重新 `deliver` 生成现行版后再 advance |
| F16 | manifest 声明了渲染不生效的字段（declaration≠consumption） | effective-fields 对账点名字段：删声明或改形状让字段真生效，不许改声明造假 |
| F17 | 无变化往返被 round_noop 门拒绝 | 这是预期拦截：确有修改先改 manifest 内容再 build；只想刷新元数据走对应登记命令，不许绕门 |
| F18 | 成品语义 ID 被改/丢失（User 段被其他工具洗掉） | extract 对账点名：回 manifest 重建成品；第三方工具处理过 .vsdx 后必须重跑 extract 对账 |
| F19 | 合同缺调色板决定 / 实际用色与决定不符 | contracted 门/合同门点名：补落 palette_decision（来源+依据+确认）；用色不符回样式编译或脚本改色，不许改决定追认既成事实而不留痕（决定变更走合同修订） |
| F20 | 本地复核查出字体未嵌入/位图分辨率不足 | 回 produce 段修（换嵌入字体、提位图 dpi 或改矢量）；复核层不放行、不改判决 |
| F21 | 参考图在变体未选定、或所据变体与选定不一致时登记/验收 | 先 `prompt select` 选定变体，再按选定版生成参考图并以 `--variant` 指明所据登记；选定变更后已登记参考图的验收口径失效，须按新选定重新登记验收，不许改登记追认 |
| F22 | Illustrator DOM 回读对账失败（漏建/文本不符/User ID 未钉扎/未登记置入项） | 按 diff 回实机逐项修（对象命名与 note 标记照构建脚本口径），重跑 readback.jsx 后重新 `ai extract` 登记；对账 ok 前不许过 produced 门，更不许手工把 illustrator_verified 改 true（合同门以虚假声称点名） |
| F23 | PowerPoint COM 枚举/导出对账失败（com-verify diff） | 按 diff 回清单或 COM 构建脚本修（几何/文本/实连端点/导出物缺件逐项对），实机重跑脚本后重新登记；`com_route.powerpoint_verified` 只许登记对账通过时由工具置真，不许手工改 |

## §15 LEARNING 16 条硬约束对应表

约束编号与标题见 `07-figure/LEARNING.md`（学习期文档，随项目留存，不进发布树）。本表是定版核对表：每条约束给出规程落点与工具实现，缺一即视为未定版。

| # | 约束（短名） | 规程落点 | 工具实现 |
|---|---|---|---|
| 1 | 图合同先行 | §4 五点合同 | `contracts.py` 词表与 validate 校验（role/轴语义/复现级别/角色色板/证据契约） |
| 2 | 后端排他三件套 | §5 | `contracts.py` backend 解析五级 + `project.py` 双线物理分区 + R 启用条件词表（四值，含 user_specified） |
| 3 | 定量图代码分流 | §5 | `produce.py` 脚本契约（登记头 + `draw()`）与同源执行；定性阶段不落代码工件 |
| 4 | 色板双类登记六列必填、彩虹禁用 | §6.4 | `style.py` 内置登记表（色盲类 + 感知均匀类 + Crameri LUT）+ validate 逐列强制 |
| 5 | 组图证据架构十角色 | §4 | `ROLE_VOCAB` 十角色 + `primary_quantitative_evidence` 一图唯一机械校验 |
| 6 | 图库三元组 + 风格规则双形态 | §12 | 合同 `sister_library_refs` schema + prompt 头部登记三元组指针与风格块版本 |
| 7 | 提示词结构化 + 配色确认门 | §7.2/§7.3 | `prompt.py` 六段模板 + `palette_confirmed` 未落字即 contracted 门拦；度量字面量拦截 |
| 8 | 政策三件套（一硬拦 + 一本账 + 一次核对） | §7.1/§10 | `audit.py` policy_block（唯一硬拦）+ provenance 账 + intake 政策快照时效门 |
| 9 | 科学复核独立（逐标签核事实） | §7.4 | `reference.py` 验收单三项（labels_verbatim/structures_factual/formulas_values_checked）落字 |
| 10 | provenance 一本账、交付前复验 | §9/§11 | `provenance.py` append-only + `delivery.py` verify_provenance_rows 交付前逐行复验 |
| 11 | 重绘 manifest 单一真相源 | §8 | `redraw.py` manifest schema/校验 + 反抽对账 + manifest_hash 绑审计 |
| 12 | 复刻三路平权分工 + 原生性机械审计 | §8/§10/§16 | 三宿主路线（Visio COM + 文件级 / PPT 文件级 + COM 实现形态 / Illustrator ExtendScript 生产路线）；`audit.py` native 门三后端分流（media 清单/形状数/整幅尺寸比对/残留登记 + Illustrator DOM 回读对账口径） |
| 13 | 最终产物实测审计（Yuan 参数） | §10 | `audit.py` 对齐 1.5 pt、碰撞四阈值、字形地板 5 pt，均在最终 PDF 实测 |
| 14 | 导出合同硬数字（期刊侧） | §6.3 | `style.py` 按栏宽推导图尺寸 + contract 门对刊硬数字实测（89/183 mm 等） |
| 15 | 数据诚实四项分层硬度 | §10 | `audit.py` honesty 门：反转/未声明截断阻断、宽高比与面积登记+警告 |
| 16 | 姊妹仓登记纪律七项 | §12 | 合同/账面只引条目 ID + 版本 + 哈希；已发表图只登记出处 + 哈希不打包 |


## §16 工具层执行规程（v1.1 新增，诊断 §2.2 工具层总规划落点）

本节管「执行者怎么操作真实软件与文件层工具」，与 §4–§15 的图包规程分工：那边管登记与门，这边管手艺与工具纪律。规程形态参考 CLI-Anything 式 harness（trsdn/mcp-server-visio 等同类工具的公开形态），**纪律可迁移、生成法不迁移**——三家宿主的可编程内层形态各异且都是真实对象模型：Visio / PowerPoint 走 COM 对象模型、Illustrator 走 ExtendScript DOM（唯一完整控制面，.ai 格式本身不开、没有文件级从零构建路线）。本包只按各宿主的真实对象模型生成构建脚本与回读规程；任何脱离宿主对象模型的「一键生成原生图」承诺都不许采信。路线形态共三类：COM/脚本驱动真软件从零重建、文件层从零构建、文件层后处理（不承担重建）。三宿主的生产能力对等（用户 2026-10-21 裁决），路线间的不对等只许来自本包实现进度，且必须如实登记为 gap，不许写成能力上限。

### §16.1 执行者五纪律（一切工具路线通用）

1. **探针先行（probe-before-mutate）**：改任何真实产物前，先跑只读探测并落盘结果——软件路线先查进程/文档/页面/对象清单，文件层先读 manifest 与成品现状；探测结果与预期不符就停，不许带着错误的世界模型动手。
2. **双通道输出（--json）**：每条工具命令同时给人话摘要与机器可读 JSON；后续步骤只消费 JSON 通道，不许从人话输出里猜状态。
3. **真软件硬依赖、不降级冒充**：路线声明依赖某软件（如 COM 路线依赖 Visio）时，软件不在场就如实停摆并点名缺什么；不许用文件层产物、截图或其他软件的近似结果冒充该路线已执行。文件层路线本身是正式路线，但必须以自己的名义交付（`visio_verified: false` / `powerpoint_verified: false`），不许借真软件的名头。
4. **E2E 真产物核验**：一条路线算「跑通」的判据是最终产物文件过审计（形状数/语义 ID/media 清单/尺寸逐项机械核对），不是命令返回成功、不是日志好看。核验对象永远是产物文件本体。
5. **预览真实性**：预览图必须由最终产物渲染导出（同源），不许用另一条管线（如绘图库重画一张）冒充成品预览；无渲染环境时如实声明「无预览」，不许拿示意图顶替。

配套收窄：执行面的工具白名单按图合同收窄（本合同没声明的路线/操作不许顺手执行）；每次变更如实汇报改了什么、没改什么，自动化卡死（COM 无响应、文件锁）时安全停机、保留现场、报告卡点，不许强杀后假装完成。

### §16.2 Visio COM 规程细则（有 Windows + Visio 时的主路线）

候选驱动形态以 trsdn/mcp-server-visio 类工具的公开接口为首选参考（进程外 COM 驱动 Visio.Application，分层 = 连接层/文档层/形状层/校验层），其能力分层按其 FEATURES.md 自述的 Validated / MVP 口径引用——**只许调用已验证层能力，MVP 层能力先在副本上试**；该工具自带的 Validation 输出是**证据材料**，不是本包的通过判决（判决只认 §10 审计门）。

- **连接**：先探针——枚举已运行的 Visio 进程与打开的文档，能接管就不新开；新开实例要登记（进程/版本/文档路径落 provenance 修正日志）。连接失败按五纪律 3 停摆报告，不许转文件层冒充 COM 已跑。
- **对象枚举与命名**：动手前全量枚举当前页形状（ID / NameU / 文本 / 类型）落盘，与 manifest 逐条对表；新建形状当场按 manifest 语义 ID 命名（NameU = 语义 ID），并把语义 ID 写进 ShapeSheet 的 User 段（`User.SemanticId`，连接形状加 `User.ArrowPlan/ConnectFrom/ConnectTo`，与文件层构建同口径，§8.1a）。枚举里出现 manifest 之外的形状先停下问清来源，不许顺手删。
- **面板局部坐标助手**：一切落位走「面板局部坐标（0–1）→ 全局英寸」单一换算（与文件层共用变换，含 Y 翻转）；助手函数只接受局部坐标（RectRel/TextRel 形态），落位后立即断言全局框不越出面板框，越界即停、不许静默钳制。
- **写入纪律**：写前备份（同目录时间戳副本）+ 另导出一份 base 副本供 diff；写后当场回读枚举复核（数量/命名/文本逐字），再走 `redraw extract` 对账。
- **保存校验**：保存后重新打开成品复验（不信任保存返回值）；导出物（PDF/PNG）从 .vsdx 同源导出，.vsdx 始终是唯一真相源。
- **后处理格**（不承担重建，T2 补丁已实现）：批量改字/改色/形状抽取/两文件比对走文件级后处理工具格——dave-howard/vsdx **0.6.1**（BSD 3-Clause，Copyright (c) 2020 Dave Howard）已 vendored 进包（`light_figure/vendor/vsdx/`，逐字节收编自官方 wheel，逐文件 SHA-256 与许可全文在该目录 `VENDOR.md` 与 `LICENSE`；版本钉死，升级须重走 VENDOR.md 核对流程），命令面 `redraw post extract|text|fill|diff`，`vsdxpost` 为包内唯一加载口（其 Jinja 模板变体能力不在本包命令面内）。变更纪律（缺一不许称处理完成）：写前备份（同目录时间戳副本）→ 在临时目录的副本上操作（vsdx 会在源文件旁解压暂存，不许污染图包）→ 写回后操作明细落 manifest 的 `post_processing` 账、构建哈希刷新，并**强制重跑 extract 对账**（后处理把成品改得与清单分叉时对账如实报 diff：先改清单再后处理对齐、或后处理后同步清单，是执行者的顺序，本命令不替清单放行）→ provenance 的 `redraw_source` 哈希刷新、`manual_corrections_log` 指向该账；审计绑定产物哈希，变更后既有审计即 STALE，交付前必须重跑 `audit run`。

### §16.3 PowerPoint 路线规程（文件层已实现 / COM 实现形态）

- **文件层（已实现，`pptx` 命令族）**：与 Visio 文件层同构——manifest 驱动、幻灯片尺寸 = 图尺寸、一页一图、形状全原生（矩形/圆角矩形/文本/连接线箭头/登记残留图片）；对象语义 ID 双写（形状名 + cNvPr descr 标记）；构建后反抽对账；产物恒标 `powerpoint_verified: false`、证据级 `file_layer`。适用定位：需要 PPTX 交付形态（汇报/可编辑分发）或无 Visio 环境时的原生形状路线；与另两路是合同分流的对等生产路线，投稿主交付按合同与期刊格式白名单走。
- **COM 路线（实现形态，2026-10-21 平权补丁）**：`pptx com-script` 由 manifest 生成 PowerShell + COM 构建脚本（`schematic/redraw/<fig_id>.com-build.ps1`，BOM UTF-8 落盘防 PS 5.1 按 ANSI 读乱码）：坐标经包内单一变换算成磅值字面量（COM 口径左上原点、Y 向下），脚本以 COM 对象模型直建形状（`.Name` + `.AlternativeText` 双写语义 ID，与文件级 descr 同标记）、连接器真绑定两端形状并落箭头、登记残留以 AddPicture 置入；随后 export-to-verify——幻灯片导出 PNG、演示文稿导出 PDF、逐形状枚举（名/替代文本/类型/磅值几何/文本/实连端点）写 `com-verify.json`，成品 .pptx 以 SaveAs 落回标准成品路径（其后照常 `pptx extract` 文件层反读对账，顶层 `powerpoint_verified` 仍只由该路落字）。登记走 `pptx com-verify --record <json> --by <执行者>`：枚举换算回包口径与 manifest 逐项对账（几何容差 0.02 in、文本逐字、User ID 钉扎、AlternativeText 箭头绑定与 COM 实连端点、置入图对残留登记、导出物在场且哈希落字）；对账无差 + 记录带 PowerPoint 版本 + 执行者落字三件齐，`com_route.powerpoint_verified` 才置真（每次新登记先复位，旧真值不许残留）。脚本工程纪律参考 sbroenne/mcp-server-powerpoint 的公开形态（会话管理与 export-to-verify 是其差异点；本包只取规程与证据形态，不引其运行时）。同内容重复生成脚本被拒（round_noop 同构）。本包当前环境无 Windows/Office：脚本生成 + 登记契约落地 + `com_route.gap` 如实登记即为本项完成口径，实机未跑通前不许声称 COM 已验。
- **幻灯片化交付注意**：把成图放进汇报幻灯片是另一回事（标题层级/对比度/16:9 版式），属使用建议不是质量证据；交付 .pptx 本体时保持一页一图、尺寸 = 图尺寸，不许为了「像幻灯片」改图内容。

### §16.4 Illustrator 生产路线（第三条对等生产路线：ExtendScript 从零重建 + DOM 回读审计）

定位（用户 2026-10-21 裁决，取代 FIG-D03）：Illustrator 是与 Visio / PowerPoint 对等的第三条生产路线——对用户给出的参考图做原生 1:1 复刻，从零生产方法图。用户收集的仓库已证明此路可行（ExtendScript DOM 是 Illustrator 的完整控制面；ie3jp 的 Illustrator MCP 以对象 note 锚定对象身份、scientific-illustrator-agent 以 spec → 脚本 → DOM 回读登记对账跑通同构流程）。原「只精修」定位是本包的实现欠账而非能力上限，FIG-D03 就此作废（留痕见 §16.6）。

- **构建 = ExtendScript 从零重建（`ai` 命令族）**：ai manifest（与另两路同一契约，§8.1）经 `ai build` 生成两个脚本落 `schematic/redraw/`：构建脚本 `<fig_id>.build.jsx`——新建文档（尺寸 = 图尺寸、RGB 文档色空间）、按 manifest 逐形状落原生对象：闭合形状先落路径并上角色色填充/描边、带文本者经 `textFrames.areaText` 把路径转区域文本框承载逐字文本（Illustrator 里形状带字的原生形态）；连接线落线路径 + 三角箭头头；登记位图残留以 PlacedItem 置入（参考图本体永不置入）；末尾 saveAs 存 .ai。回读脚本 `<fig_id>.readback.jsx`——枚举 `doc.pageItems` 全部对象（name / note / typename / geometricBounds 换算回包口径 / TextFrame 逐字文本 / PlacedItem 文件名与链接存活），并探测印前事实（文档色空间与混色、白色叠印、PDF/X 预设可用性），手写序列化落 `<fig_id>.dom-readback.json`（不依赖宿主 JSON 实现）。两脚本均 BOM UTF-8 落盘；坐标只在生成侧经包内单一变换算成文档磅值字面量、回读侧在脚本内换算回英寸口径，Python 侧只消费英寸（构建单一变换纪律）。脚本头部写死使用法：先把 `PKG_ROOT` 改为图包在本机的绝对路径再经 Illustrator 的脚本菜单执行；构建脚本只新建文档、永不改已打开的文档。
- **语义 ID 钉扎（无 ShapeSheet 时的等价形态）**：Illustrator 没有 ShapeSheet 对应物——钉扎 = 对象名（`PageItem.name` = 语义 ID）+ 对象注释（`PageItem.note` 写 `light-figure:user-id=<id>`；连接线 note 写 `light-figure:arrow=<pid>;from=<a>;to=<b>`）+ manifest 边车三件套，回读时以 note 为准对账（对象改名或在第三方工具里被洗掉 note，extract 即点名，F22）。箭头头的 note 同钉 user-id（`arrow-<pid>-head`）。
- **DOM 回读审计（`ai extract --readback <json> --by <执行者>`）**：对账项与另两路 extract 同口径——几何逐形状容差 0.02 in、文本逐字（这是抓丢字/改字的基准：对账对象是文本清单本身，不许只核对象计数——SVG 导入静默丢字形的教训在此内化为纪律）、User ID 钉扎、箭头端点绑定、置入项集合与残留登记集合严格相等（多一个未登记置入项即差集点名）、清单外对象点名。对账结论 + 回读本体（对象清单 + 印前事实 + 形状集哈希）落 ai manifest 的 `dom_readback` / `reconciliation` 段，provenance 的 `redraw_source` 在 .ai 已存回且 对账 ok 时回填。原生性审计（§10）对本路线消费同一份回读记录，不另开证据面。
- **印前终检段（原 FIG-D03 五项的现行位置）**：印前五项（rgb_mixed 混色空间 / broken_links 断链 / low_res_images 低分辨率置入图，有效 ppi 按源图实测像素 ÷ 回读落位宽算、地板 200 / white_overprint 白色叠印 / pdfx 规格）由 extract 按回读事实机械计算落 ai manifest 的 `preflight` 段——是本路线交付前的终检，不是路线身份：produced 门逐项验（未落字点名缺项、事实缺失不许默认无问题、任一项为真即未处置问题拦下）。宿主探针不支持某项（如白色叠印探测不可用）时该项不落键、由门点名补验，不许默认通过。
- **SVG 桥 = 导入备选路径（降格保留）**：仅当用户已有 SVG 素材要进 Illustrator 时走——入口只收本包矢量产物导出的 SVG 且必须先过**受限子集校验**（`svg-check` 命令）：只许纯矢量基元（path/rect/circle/ellipse/line/polyline/polygon/text/g/use/defs）；image/script/filter/style/foreignObject 与一切外部 href 引用一律拒绝点名——防参考图位图与脚本混入。校验同时抽出 SVG 内全部文本成清单：**SVG 导入 Illustrator 会静默丢字形/改字体**（宿主缺字时整段字形被丢弃而不报错），导入后必须按本路线同一 extract 口径登记 DOM 回读、以 SVG 文本清单逐字对账，丢字以清单抓、不靠眼看；导入产物在对账齐备前不许冒充生产路线成品。合同 `illustrator_refinement` 段为 FIG-D03 遗留兼容（旧图照旧校验），新图不许再用它登记路线。
- **回退与 gap**：无 Illustrator 宿主时该图按合同改走另两路之一并在合同/账面留痕（路线可换、登记不许断），不许拿其他软件的近似处理冒充 Illustrator 已生产。实机执行属环境依赖项（本包环境无 Adobe 软件）：脚本生成 + 回读契约 + `build.gap` 登记即算本项当前完成口径，`illustrator_verified` 在合格登记前恒 false（置真四件套见 §8.2b），由用户在自有机器按 22-user-machine 清单补验。

### §16.5 附录：拍板 D4 修订条文与未采纳清单

**D4 修订条文**（第二轮拍板后定版，2026-10-21 经用户平权裁决再修订，取代此前一切「三格不对等」表述）：

> 方法图原生重绘的后端为三条对等生产路线，按图合同 `schematic_backend` 逐图分流：(一) Visio——COM 原生重建（§16.2 规程）+ 文件级从零构建 .vsdx（已实现）；(二) PowerPoint——文件层从 python-pptx 生成原生形状 .pptx（已实现，§16.3）+ COM 实现形态（构建脚本生成与登记对账已实现，实机待用户机器验证）；(三) Illustrator——ExtendScript 生产路线（构建/回读脚本生成与 DOM 回读对账已实现，实机待用户机器验证，§16.4）。三路共用同一 manifest 契约、语义 ID 钉扎与原生性审计口径，目标同为对参考图的原生 1:1 复刻；一切未经实机证据登记者如实标注未验证（visio_verified / powerpoint_verified / illustrator_verified 的置真各自只认本路线的合格登记），不许以文件层或脚本级证据冒充实机证据。

**未采纳清单**（学习期评估过、明确不做，防后人重提）：CLI-Anything 式「为闭源软件自动生成 CLI harness」的方法论本体（生成法不迁移；只借 harness 形态与执行纪律——三家宿主各自的对象模型才是生成依据）；以截图/渲染图冒充原生对象核验；把第三方工具的自检输出当本包审计判决；在 PPT 文件层引入主题母版/占位符体系（一页一图、空白版式写死）；SVG 全集（滤镜/样式/外链）进生产链。

### §16.6 v1.1 诊断条目对应表

| 条目 | 内容 | 落点 |
|---|---|---|
| FIG-D02 | PPT 文件层全链 + COM 规程 + powerpoint_verified 口径（COM 于 2026-10-21 平权补丁升实现形态，见末行） | `pptxbuild.py` + §8.2a/§16.3 |
| FIG-D03 | **superseded-by-user-2026-10-21**：原 Illustrator 精修定位（+ SVG 桥 + DOM 回读数据形状）已被用户平权裁决推翻——Illustrator 为第三条生产路线，SVG 桥降为导入备选，印前五项降为终检段；遗留物（`svgbridge.py` + 合同 `illustrator_refinement` 段校验）仅作兼容与导入备选保留 | 后继落点见末行平权补丁 |
| FIG-D04 | User.* 语义 ID 写入图对象、审计回读核对 | `redraw.py`/`pptxbuild.py` User 段与 descr 双写 + extract 对账 |
| FIG-D05 | renderer-effective-fields 生效字段清单与对账 | manifest 契约校验（`schema.RENDERER_CONSUMED_FIELDS`） |
| FIG-D06 | arrow_plan 先行登记 + 导出回读核对 | manifest 严格模式校验 + extract 端点比对 |
| FIG-D07 | round_noop 无效轮次门 | build 轮次账 `rounds` + 内容投影哈希 |
| FIG-D08 | 调色板决定入合同、审计核对实际用色 | 合同 `palette_decision` + contracted 门 + 合同门 + produce 落账 |
| FIG-D09 | 参考图六维拆解入图包、提示词消费 | 合同 `reference_breakdown` + `prompt.py` 风格段 |
| FIG-D10 | 执行者五纪律 + 工具面收窄 | §16.1 |
| FIG-D11 | 交付前本地复核环（纯本地机械复核） | `recheck.py` + `recheck` 命令 + §10 |
| D4 附则 | COM 规程细则（连接/枚举/命名/保存校验） | §16.2 |
| REV-D09 | 交付对应件清单（源资产 → 交付物 + 内容级哈希） | `delivery.yaml` 逐图 `correspondence` + §11 |
| 平权补丁（2026-10-21，用户裁决推翻 FIG-D03） | 复刻三路平权：合同后端集扩三值且对称登记；PPT COM 实现形态（脚本生成 + export-to-verify + com-verify 登记）；Illustrator 生产路线（ExtendScript 从零重建 + DOM 枚举回读审计 + 印前终检段）；门/审计/recheck/交付三后端分流 | `aibuild.py`（新）+ `pptxbuild.py` COM 段 + `schema.py` 后端集与证据级词表 + gates/audit/recheck/delivery 分流 + §8.2b/§16.3/§16.4 |
| 工具层 T2 补丁（2026-10-21） | vsdx vendored 化（0.6.1 钉死 + BSD-3 署名）+ `redraw post` 命令组（改字/改色/抽取/diff + 写后强制 extract 对账与账面刷新纪律）；ai manifest 构建账按后端隔离（user-delegated 主会话裁决 2026-10-21：内容跨路线继承、rounds/build 不跨后端继承、派生剥离留痕 `derived_from`、round_noop 只在本路线账内生效） | `vsdxpost.py`（新）+ `vendor/vsdx/`（新）+ `aibuild.derive_ai_manifest` + §8 第 2/2b 项、§16.2 后处理格 |
