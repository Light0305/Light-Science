# light-figure SKILL（v1.0）

> 定位：把 Write 稿件包的图表占位变成可交付的图。核心原则——**登记文件是权威源**：每张图的合同、后端、提示词、重绘清单、provenance、审计产物全部先登记后使用；交付时只产 `delivery.yaml` 供 Write 回填，Figure 不直接改 Write 的清单。
> 设计依据：`07-figure/REDESIGN-DRAFT.md`（含用户拍板 D1–D7，文末附录）、`07-figure/LEARNING.md`（16 条硬约束，对应表见 §15）。实现范围：图包数据模型与确定性校验器、样式编译、双线生产（数据图 matplotlib 执行 / 方法图提示词→参考图登记验收→重绘 manifest 与文件级 .vsdx 构建）、provenance append-only 一本账、审计引擎七门、五段状态机全门（含 delivered 交付段：账行逐行复验 + 编号冻结配合）。

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
| `audit/` | 审计产物：`<fig_id>.audit.json`（七门判决，绑定交付物哈希，产物变更即 STALE 必重跑）+ `<fig_id>.alignment-input.json`（produce 落的 plot-area 量测清单） |
| `exports/` | 交付物（数据图最终 PDF）+ `delivery.yaml`（交付清单，§11） |
| `FIGURE_REPORT.md` | `report` 生成的权威汇总，手工区（MANUAL 标记之间）刷新不覆盖 |

## §2 双线总览

- **数据图线（data）**：定量图一律由代码生成（Python/R），不走图像生成、不走 Visio 重绘（约束 3）。流程：图合同 → 后端决定落盘 → 样式编译（期刊合同 + 色板登记）→ 脚本绘制 → 最终产物审计。
- **方法图线（schematic）**：图库匹配风格 → GPT Image 提示词（核心交付）→ 用户生成并提供参考图 → Visio 原生 1:1 重绘（约束 11/12）。AI 生图只进草稿段，成品必须是 Visio 原生对象。
- 承接 kind 为 `table` 的条目归数据线登记（表格本体由 Write 承担，Figure 只登记合同与交付指针）。
- 两线在同一图包内并行，状态与审计分线记录、包级汇总。

## §3 状态机

```
intake → contracted → produced → audited → delivered
```

逐图同构推进，包状态由逐图状态机械汇总（`advance` 执行，门不过逐项点名）：

| 段 | 入口门（现行落点） |
|---|---|
| contracted | 承接快照齐全且哈希对齐；目标刊图形合同已登记；AI 政策快照在有效期内（schematic 线）；每图合同五点齐；数据图后端已按解析顺序决定并落盘；方法图已过配色确认门 |
| produced | 产物齐备性深门：数据图——脚本 + 源数据 + 预览齐备、源级预检全过（样式哈希绑定/禁用色标/轴口径登记）、账面哈希与实物相符；方法图——提示词产物落盘、参考图入包登记且验收三项落字、重绘 manifest 落字且成品反抽对账无未登记差集、provenance 账行齐（提示词版本/生成模型/逐标签核对） |
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
2. **默认 Python**（拍板 D2）。**R 的启用条件**（满足其一，逐图在覆写行登记 `reason_code` + `reason`）：`r_decisive_advantage`（图种在 R 侧有决定性优势）/ `pipeline_in_r`（数据管线本身在 R 内）/ `library_r_only`（数据图库只有 R 侧条目）。包级整体采用 R 时同样在登记层落 `reason_code`。
3. **同图不混后端**：同图双后端登记（覆写重复、覆写与包级冲突、登记头行与解析结果不一致）一律 validate 报错。切换后端只许整图切换并重跑该图全部审计（换后端后旧审计自动 STALE，`audit run` 整图重跑）。
4. **运行时缺失不许跨后端兜底**：选中运行时/包不可用时暂停渲染、报确切阻塞、给本后端安装命令，禁止用另一语言画替代图。唯一豁口是后端无关审计器（只查不绘）。

## §6 期刊合同与容差（F6 合同层，约束 14 / 拍板 D3）

1. `journal_contract.yaml` 逐刊登记：期刊、版本、核查日期、官方来源 URL、栏宽（mm，单/双栏）、最大高度、字号区间与字形地板、字体、主图格式白名单、预览规格、色板登记指针（分类/连续各一，须带 entry_id + version）。数值锚以目标刊官方指南**现行版**为准（Nature 现行：89/183 mm、最大高 170 mm、字号 5–7 pt）；官方新旧口径并存时以现行 Figure Guide 类文件为准并登记核查日期。
2. **尺寸从栏宽确定性推导**（多面板尺寸 = 栏宽 + 行列数），禁止逐图手填 figsize。执行者是样式编译（`style build`）：期刊合同 + 色板登记 → 编译产物落 `data/styles/`（`bundle.json` 含 rcParams 全集与解析后的色板、尺寸参数；`light.mplstyle`；R 侧只产 `theme.R` 文本不执行）。编译结果记 `style_build_hash`（规范化内容哈希，同输入同哈希、无时间戳成分）；期刊合同或色板版本一变哈希即变，旧 bundle 判漂移必须重编译。数据图脚本只许消费编译产物：脚本头声明 bundle 哈希，produce 预检逐项比对（哈希不符、脚本自带 figsize/set_size_inches、自选禁用色标一律落 gap 不许执行）；脚本字体不可用时以 DejaVu Sans 替换并在生产结果落 `font_substituted`，不许静默换字。
3. **容差是期刊合同参数**（D3）：默认照 Yuan 实测参数集——对齐/gutter 1.5 pt、碰撞四阈值（内缩 0.6 pt / 重叠比 0.05 / 裁剪 0.5 pt / 背景豁免 20%）、字形地板 5 pt（`schema.TOLERANCE_PARAMS` 为权威表）。刊方更严从刊（收紧不设限）；**放宽只许经 `tolerance_exemptions` 逐项登记（参数 + 值 + 理由），不许改全局默认放行**——validate 对无豁免登记的放宽值报错。
4. 色板纪律（约束 4）：分类色板默认 Okabe-Ito、连续色图默认 Crameri 感知均匀系、**彩虹色标禁用**；分类与连续机制分开，分类色板不许由连续色图插值生成。色板登记六列（类型/感知均匀/色盲安全/灰度有序/许可/数据版本）在姊妹仓登记表侧执行（§12），Figure 消费时钉版本。

## §7 方法图线：提示词与政策（F3/F4，约束 6/7/8/9，拍板 D1）

1. **配色确认门先行**：生成任何提示词之前先定角色色板（预设选定或用户指定），落合同 `palette_confirmation`（确认人 + 时点）；未定不许出提示词。色值按元素角色登记，提示词只引角色名不写散色值。
2. **提示词是结构化产物**（已实现：`prompt build` 生成 `schematic/prompts/<fig_id>.md`）：YAML 文件头登记（prompt_id、version、图库三元组引用 {条目 id + 版本、风格锚、绑定提示词版本}、风格规则 {id = 风格锚、版本}、角色色板指针、配色确认记录、政策快照指针）+ 正文六段——**全局 / 分区 / 全局标注 / 风格规格 / 负面约束 / 政策段**（草案旧命名对应：风格锚入全局段与风格规格段、构图与元素清单入分区段逐面板、文字标注约束即全局标注段）。纪律：正文只引色板角色名、不落 hex 色值（生成后自检正文无 hex）；每个模块框必须有子内容、不许空白占位与「...」省略；**度量数字不许入图**（px/pt/% 类字面量严禁写进会进图的文本，只有语义数字可入图；生成前逐标签机械拦截）。改版 = version 递增 + 旧版存 `prompts/archive/<fig_id>.v<n>.md`；首版 version 取图库条目绑定的提示词版本。生成后回填账面 `prompt_version` 与政策快照指针。
3. **政策口径（拍板 D1：「一条硬拦 + 一本账 + 一次逐刊核对」）**：
- 立场（用户拍板）：Visio 人工原生重绘成品不算 AI 生图——成品无任何 AI 生成像素、每个形状都是人放的原生对象。**不设把重绘图当 AI 图的阻断门**。政策文本依据见 LEARNING 约束 8（受禁对象只限 AI 直接产出的图像物件；无条款及于构思/参考；具体情形属文本沉默，残余风险为编辑裁量）。
- **一条硬拦**（全线唯一政策硬拦，机械执行）：AI 参考图本体文件不得进入交付/投稿包（已实现：审计 `policy_block` 门按 SHA-256 比对 provenance 账面参考图哈希，交付集 = `exports/` 全部文件 + 重绘成品，任一同哈希即 FAIL 点名文件；重绘成品哈希天然不同、不拦。合同 `policy_check.reference_not_in_delivery` 为自检落字，落 false 即 validate 报错）。
- **一本账**：provenance 逐图留痕（§9），是披露生成的唯一事实源。
- **一次逐刊核对**：投稿前经 Write 模板记录的 AI 政策组逐刊核对（字段 + `verified_at`，过期自动失效）；Science 系在核对环节标红提示「投稿前向编辑部书面问询」；目标刊从严或编辑答复否定时，该刊切**无 AI 参考降级路径**（合同 `policy_check.degradation_path = no_ai_reference`：方法文本 + 组件库按 spec 先行拼装，跳过 GPT Image 段）——路线不断，只换入口。
4. **科学复核独立于政策**（约束 9）：披露 ≠ 免责。参考图验收与重绘两处各执行一次复核清单：逐个标签逐字对原文核对、每个结构对领域事实核对、公式/分子式/数值算对。**照描而不核事实是红项**（Frontiers「AI 大鼠图」撤稿案：作者已披露，败在三道关无人核事实）。

## §8 Visio 重绘（F5，约束 11/12，拍板 D4）



1. **重绘清单是单一真相源**（`schematic/redraw/<fig_id>.manifest.json`）：面板四角标定（全局像素框 + 面板局部坐标系）动手前落字，对象清单（稳定语义 ID、类型、局部坐标框 0–1、样式 token、逐字文本、连接语义、z 序）足以不读其他文件重建本图；不在清单里的东西按漏画处理；要加形状先改清单。成品可反抽形状清单与正向清单闭环对账。状态只经工具推进、不许手写。命令面（已实现）：`redraw init`（按合同面板 + 已登记参考图生骨架，标定待补）→ 补齐标定后 `redraw install`（全量契约校验 + 与账面参考图哈希对表）→ `redraw build` → `redraw extract`（反抽对账）。坐标变换只在一处实现（面板局部 0–1 → 全局像素 → 英寸、Y 翻转），校验与构建共用。
2. **路线三格分工**：COM 原生重建（主路线，有 Windows + Visio：两级坐标标定、局部坐标越界即断言、参考图只作临时锁定描图层且交付前移除、.vsdx 为唯一真相源、同源导出；PPTX 导出物是渲染幻灯片不是原生形状，交付说明须标注。v1.0 只立规程与接口——`redraw build` 对 route=com 如实落 gap，不冒充执行）/ 文件级从零构建（正式第二路线，**已实现**：手写 OPC 从零拼 .vsdx——内容类型/各级 rels/文档属性/pages/page1，Shape 内 Cell 必在 Section/Text 之前，几何走多段线近似，zip 条目时间戳固定保确定性；位图残留以 ForeignData 形状嵌入并绑 media rel，未在清单绑定的位图形状构建期报错）/ 文件级后处理（vsdx 库做批量改字改色与形状抽取，**没有从零绘制 API，不承担重建**）。
3. **无 Visio 环境交付口径**：文件级路线产出的.vsdx 是正式交付物，但交付清单中该图须带 `visio_verified: false` 与「未过 Visio 实机验证」注记（如实落字，不许声称通过 Visio 验证）。
4. **位图残留预先声明**：只许照片/视频帧/显微图/热图/复杂纹理/极密证据条六类、且为精确裁剪局部；未登记者不许以位图形态出现在成品中。原生性靠机械审计验（包内 media 清单 + 形状数 +「1 形状 1 位图」警告），不靠声明。

## §9 provenance 一本账（约束 10）

`provenance.yaml` 逐图一行，随图合同开立：

- 方法图：`prompt_version`、生成模型 + 版本、参考图哈希、重绘源.vsdx 路径 + 哈希、逐标签核对完成标记（核对人/时点）、政策快照指针、人工修正日志指针。
- 数据图：后端 + 运行时版本、脚本哈希、源数据哈希、样式编译产物哈希、色板登记版本。

纪律：账行只增不改历史——更新命令已实现（`provenance set`，append-only）：旧行组件哈希记入 `history[].supersedes`、新行带 `row_hash`、逐字段 from→to 与更新人/时点同账留痕，`provenance show` 可查全链；哈希字段强制 SHA-256 格式，`redraw_source` 须 {path, hash} 成对。生产命令（produce / reference add / prompt build / redraw build）自动回填各自负责的账面字段，produced 门逐项验账实相符（账面哈希 ≠ 实物哈希即点名）。图进入 produced 段起必填项缺项即 validate 报错（方法图缺参考图哈希或重绘源、数据图缺脚本/源数据哈希）；交付前由 `deliver` 逐行复验哈希（`verify_provenance_rows` 按实物重算比对），被改即拒交付。账同时供 Write 的 use_log 对接与逐刊披露文本生成消费。

## §10 审计门（F6，约束 13/15）



审计对象一律是**最终产物文件**（数据图 = `exports/<fig_id>.pdf`，方法图 = `schematic/redraw/<fig_id>.vsdx`），产物哈希写入每份审计 JSON，产物变更后审计即 STALE 必重跑。七门：对齐门（plot-area 量测 vs 可比组，豁免须登记理由，禁止调大容差掩盖例外）/ 碰撞门（FAIL 三类阻断、WARN 记录理由）/ 字形门（内容流 Tf 实测 ≥ 地板）/ 合同门（尺寸/格式白名单/可编辑文本未转曲/色板合规）/ 原生性门（方法图，§8.4)/ 诚实门（数据图，拍板 D6 分层硬度：反转轴检出阻断；截断轴声明对照——未声明阻断、已声明放行留记录；宽高比与面积编码先登记 + 警告）/ 政策硬拦（§7.3，参考图本体不入交付集）。NOT_AUDITABLE 不许声称审计通过。

**运行法（已实现）**：`audit run [--fig <id>]` 按线全跑并落 `audit/<fig_id>.audit.json`（绑定 `artifact_sha256`、容差快照、工具版本）；`audit-status` 逐图报 FRESH / STALE / MISSING / NO_ARTIFACT。判决四态：PASS / REVIEW_REQUIRED / FIX_BEFORE_DELIVERY / NOT_AUDITABLE（门不适用记 `applicable: false`，不占判决）。实测口径：对齐/碰撞/字形三门在最终 PDF 上真量测（PyMuPDF 抽文字行框/描边/填充/图像与内容流 Tf 算符），量测清单由 produce 同源生成、清单哈希与产物不符即 NOT_AUDITABLE；诚实门消费脚本头登记（判据在登记层，缺登记落 REVIEW 不许默认诚实）；原生性门解 .vsdx 包做 media 清单 + 形状计数（整图嵌入、未登记位图、登记残留缺失、描图层未移除均 FAIL）。**STALE 处置**：产物任何变更后先重跑 `audit run` 再谈过门，STALE 状态下不许落处置理由。**REVIEW 处置**：`audit note <fig> --gate <门> --reason <理由>` 逐门落字（仅 FRESH 时许落，同哈希重跑保留既有处置）；audited 门逐门核对，无落字即点名拦下。

## §11 与 Write 的接口（交付回填）

Figure **不直接改** Write 的 `figures_manifest.yaml`，交付只产 `exports/delivery.yaml`（`deliver` 命令生成）：顶层含包状态、清单版本（`version`，解冻后重交付递增）与现行标记（`status: current`；被取代的旧清单标 `superseded` 不删）、编号冻结块、逐图交付行。

| Write figures_manifest 需要 | delivery.yaml 提供 |
|---|---|
| figure_id + 交付状态 | 逐图交付行（`delivery_status: delivered`，deliver 时落字） |
| 交付文件 + 版本 + 文件哈希 | 逐图交付文件路径 + SHA-256（deliver 时按实物重算；数据图含风格构建哈希，见下行） |
| 图注哈希对账 | 图注哈希（承接快照值，与现状逐图比对一致才许交付） |
| 图件 provenance | 数据图：脚本/源数据/样式构建三哈希 + 运行时版本；方法图：账行指针 + 提示词版本/生成模型/参考图哈希 + 图库三元组与组件许可汇总 |
| AI 披露素材 | 方法图 `ai_disclosure` → Write use_log 对接字段（模型、提示词版本、重绘方式、参考图本体不在交付集标记） |

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

## §14 失败模式（v1.0）

| 编号 | 失败 | 处置 |
|---|---|---|
| F1 | 承接源变动致快照漂移 | 重新 intake，不许静默沿用旧快照 |
| F2 | 同图双后端登记 | validate 报错定位冲突来源（覆写/登记头行），改登记后重跑 |
| F3 | 容差被私自调大 | 无豁免登记即报错；确需放宽走 tolerance_exemptions 逐项落理由 |
| F4 | R 覆写无依据 | 补 reason_code（D2 三条件之一）+ reason，否则改回 Python |
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

## §15 LEARNING 16 条硬约束对应表

约束编号与标题见 `07-figure/LEARNING.md`（学习期文档，随项目留存，不进发布树）。本表是定版核对表：每条约束给出规程落点与工具实现，缺一即视为未定版。

| # | 约束（短名） | 规程落点 | 工具实现 |
|---|---|---|---|
| 1 | 图合同先行 | §4 五点合同 | `contracts.py` 词表与 validate 校验（role/轴语义/复现级别/角色色板/证据契约） |
| 2 | 后端排他三件套 | §5 | `contracts.py` backend 解析五级 + `project.py` 双线物理分区 + R 三条件词表 |
| 3 | 定量图代码分流 | §5 | `produce.py` 脚本契约（登记头 + `draw()`）与同源执行；定性阶段不落代码工件 |
| 4 | 色板双类登记六列必填、彩虹禁用 | §6.4 | `style.py` 内置登记表（色盲类 + 感知均匀类 + Crameri LUT）+ validate 逐列强制 |
| 5 | 组图证据架构十角色 | §4 | `ROLE_VOCAB` 十角色 + `primary_quantitative_evidence` 一图唯一机械校验 |
| 6 | 图库三元组 + 风格规则双形态 | §12 | 合同 `sister_library_refs` schema + prompt 头部登记三元组指针与风格块版本 |
| 7 | 提示词结构化 + 配色确认门 | §7.2/§7.3 | `prompt.py` 六段模板 + `palette_confirmed` 未落字即 contracted 门拦；度量字面量拦截 |
| 8 | 政策三件套（一硬拦 + 一本账 + 一次核对） | §7.1/§10 | `audit.py` policy_block（唯一硬拦）+ provenance 账 + intake 政策快照时效门 |
| 9 | 科学复核独立（逐标签核事实） | §7.4 | `reference.py` 验收单三项（labels_verbatim/structures_factual/formulas_values_checked）落字 |
| 10 | provenance 一本账、交付前复验 | §9/§11 | `provenance.py` append-only + `delivery.py` verify_provenance_rows 交付前逐行复验 |
| 11 | 重绘 manifest 单一真相源 | §8 | `redraw.py` manifest schema/校验 + 反抽对账 + manifest_hash 绑审计 |
| 12 | Visio 三格分工 + 原生性机械审计 | §8/§10 | COM 路线规程 + 文件级构建实现；`audit.py` native 门（media 清单/形状数/整幅尺寸比对/残留登记） |
| 13 | 最终产物实测审计（Yuan 参数） | §10 | `audit.py` 对齐 1.5 pt、碰撞四阈值、字形地板 5 pt，均在最终 PDF 实测 |
| 14 | 导出合同硬数字（期刊侧） | §6.3 | `style.py` 按栏宽推导图尺寸 + contract 门对刊硬数字实测（89/183 mm 等） |
| 15 | 数据诚实四项分层硬度 | §10 | `audit.py` honesty 门：反转/未声明截断阻断、宽高比与面积登记+警告 |
| 16 | 姊妹仓登记纪律七项 | §12 | 合同/账面只引条目 ID + 版本 + 哈希；已发表图只登记出处 + 哈希不打包 |
