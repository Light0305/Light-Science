# Light-Literature 技能说明

> 版本：**v1.0 定版（2026-10-20 封版）**。开发历程为八个增量（地基 → 笔记线/翻译对齐/证据行 → Find 线 → 解析补强 → Doc2X 适配器与对照评测 → 图组与端到端验收 → 视觉引擎实测 → 解析改双轨制），每步的主题与结论见 README「开发记录（节略）」，完整验收记录属开发档案、不在本仓库；本文件只写定版口径。**定版原则：模型无关——质量下限靠流程、质量门与 §8 自检清单保证，不靠执行模型的临场发挥；任何模型接入都照本文件逐步执行、逐步勾检。** 执行顺序：§4 流水线 → §5 对应轨道规程 → §3 硬规则全程生效 → 交付前 §8 逐项勾检 → 遇异常先查 §9 失败模式附录。
> 定位：把外部论文变成项目内**可核查、可复用**的研究材料。本文件是给执行 agent 的操作规范，不是宣传文案：每条规则都可执行、可检查。**定版原则：模型无关——质量下限靠流程、质量门与 §8 自检清单保证，不靠执行模型的临场发挥；任何模型接入都照本文件逐步执行、逐步勾检。** 执行顺序：§4 流水线 → §5 对应轨道规程 → §3 硬规则全程生效 → 交付前 §8 逐项勾检 → 遇异常先查 §9 失败模式附录。

## 1. 触发与模式

用户给出论文、主题或文献相关请求时进入本技能，按意图选模式：

| 模式 | 输入 | 产出 | v1.0 状态 |
|---|---|---|---|
| Find | 主题 / 研究问题 | 候选清单 + 纳入/排除记录（不自动下载全文，清单经用户确认才下载） | **已实现**（见 §5 Find 线）；下载仍走 Read 的 ingest |
| Read | DOI / 链接 / PDF | 四件套 + 证据行 | **已实现**（见 §5）；**产品解析走 §5 双轨制**：`parse` 命令（Doc2X 轨）或模型直读轨；翻译/笔记的正文由 agent 按本规范逐块填写；本地管线为研究/对照工具，非产品路径 |
| Compare | ≥2 篇已入库论文 | 证据矩阵行 + 冲突清单 | 未实现（v1.0 范围外） |
| Reuse | 已入库论文 | 方法/代码资产登记（复现执行交 Light-Experiment） | 未实现（v1.0 范围外） |

## 2. 产物规范（不可协商）

单篇目录 `Literature/<slug>_<sha256前6位>/`：

```text
paper.yaml        # 标识、版本档位、来源、SHA-256、状态机（含 parse 后端/状态记录）、分诊结果（审计源）
原文.pdf
原文.md           # 块级锚点；Doc2X 轨由 parse 锚点化生成，模型直读轨由模型亲撰（provenance=model-direct）；未解析页显式标注，不许假装已解析
原文_中文翻译.md   # 块级同 ID 对齐；公式共享 E 块不重复渲染（translate-scaffold 生成脚手架）
阅读笔记.md        # 默认直接精读卡 16 节；速读卡只是中间检查点（notes 生成骨架）
source_map.json   # 锚点与溯源（含分诊逐页数值）
content_list.json # MinerU Content List V1 对齐导出（export-content-list 生成，导出交换格式）
assets/figures/、assets/tables/、supplementary/
verify_report.json
```

项目级：`Literature/` 下 `00-文献总览.md`、`文献索引.csv`、`证据表.jsonl`、`研究证据矩阵.md`、`参考文献.bib`、`术语账本.md`。

**锚点纪律**：正文 `S`、图注 `C`、图 `F`、表 `T`、公式 `E` 五命名空间，格式 `<字母><三位序号>`；块必带 `page / type / order / bbox / confidence / provenance`。ID 只增不改不复用。原文↔译文↔笔记一律用同一套 ID 互链；笔记指针格式 `[Paper: PDF p.N, Sxxx]`。

## 3. 硬规则（写死，执行时不许漂移）

1. **未核实文献：成稿层一律不用**。候选/筛选层可以保留并打 `[UNVERIFIED]` 标记留痕；进入成稿（笔记结论、证据矩阵定稿、交给 Write 的材料）时，未核实文献一律排除。没有例外通道。
2. **不要 Zotero 的任何东西**：不对接、不导入、不生成 Zotero 专用格式。对外引用数据只走通用 BibTeX / CSL-JSON 导出（供 Light-Write）。
3. **入库默认直接精读**：Read 的终点是 16 节精读卡；速读卡只是精读流水线中的中间检查点。仅当用户显式说「先速览」时才停在速读卡。
4. **版本诚实**：没有正式全文时 `paper.yaml.source_version` 必须如实写 `preprint` / `abstract_only`，锚点链随之降级（structure-grounded / source-limited），笔记未见部分标 `Not assessable`。不许把摘要当全文读，不许生成假锚点、假页码。
5. **证据纪律**：数字逐字可溯；直接引文上限一句且必填页码；作者自述局限与 Agent 批评分开写、互不冒充；结论措辞受强度动词表约束（`causes`、`demonstrates` 等强动词需有对应证据档位；`first/novel/SOTA` 须查新后才许用）；正文与图表矛盾时两值并记并写明消解条件，不静默选一。
6. **出处五标签**：笔记与矩阵中的每条陈述标 `[Paper] / [External] / [Analysis] / [Hypothesis] / [User]` 之一，最小适用；Agent 的分析不许用用户口吻写。
7. **撤稿/更正检查独立成步**：在身份核实门之后、粗筛之前执行；命中撤稿默认排除并留痕，用户显式覆写须把理由写入记录。
8. **核实成本三级**：全库只跑字段级核实；入选精读的跑存在+准确性；被写进我方稿件的主张级引用才跑上下文支持。不许全库跑最贵档。
9. **质量门**：交付前逐项自检——主要数字可溯、主要图表已盘点、覆盖范围不冒充、作者局限与 Agent 批评不混写、想法未查新不称新颖、无为填模板而编的内容。不过门则状态标 `Partial` 并在总览写明缺口，不许标完成。
10. **解析双轨制（2026-10-20 用户裁决，覆盖原「解析诚实 / 超越 Doc2X」口径）**：产品解析只有两个后端——**Doc2X 轨**（用户自配 Key，`parse` 命令）与**模型直读轨**（未配置 Doc2X 时由接入模型亲自撰写四件套，见 §5「解析双轨制」）；本地自研管线（extract / MinerU / 对照线）**退出产品路径**，仅作研究/对照工具保留，**不许拿来顶替产品产物**。原「超越 Doc2X」正式判定已出结论「未超越」（LS-HardSet 封存集：已配对 25 篇总分差 −0.0970、95% CI [−0.1128, −0.0816]，正文/公式/表格/顺序/图注五项全破非劣界值；已知差距构成 = 公式 LaTeX 转写、复杂表格结构、个别页阅读顺序；判定含一处执行偏离——MinerU basic 路由因部署 config 未切换致公式路由任务全灭，属可修复 bug 而非能力问题，数字与结论不变）。用户据此裁决走 Doc2X：一个完整科研项目的文章量有限，¥0.01–0.02/页的成本可接受。Doc2X 纪律（硬规则）：参数冻结（model=v3-2026, formula_mode=dollar, formula_level=0, merge_cross_page_forms）；**提交前先按页数估算费用并核对剩余额度或向用户确认**（额度曾在判定运行中耗尽）；uid 提交后立即落盘，崩溃恢复优先、**不许无记录重提烧钱**；结果只存 24 小时，**24 小时内取回**；`parse` 失败置 paper.yaml 的 parse 状态为 `awaiting_model_direct` 并明确报错，**不静默切换后端、不回退本地抽取**。

## 4. Read 流水线（agent 执行顺序）

```text
获取原文（合法路径：OA → 出版社/作者自存档 → 机构订阅指引；失败留状态码）
→ ingest 入库（SHA-256、paper.yaml）
→ triage 逐页分诊
→ parse 解析建锚（产品双轨，见 §5：Doc2X 轨 = `parse` 命令整篇送 Doc2X 并锚点化为 source_map + 原文.md；模型直读轨 = 模型逐页读 PDF 亲撰带锚点产物，provenance=model-direct）
→ verify 锚点校验 + 图注配对（全过才许进入翻译/笔记）
→ 翻译：`translate-scaffold <paper_dir>` 生成脚手架（术语账本先行、块级同 ID 对齐、置信标注），agent 逐块填译文，再跑 verify 的译文校验
→ 精读卡：`notes <paper_dir>` 生成骨架（速读段 S1–S7 为中间检查点，默认终点是精读 16 节），agent 逐节填写；证据行双产出：`evidence add` 同步写入 证据表.jsonl
→ 质量门 → 更新 00-文献总览.md 与文献索引状态
```

证据行字段：`evidence_id`（格式 `E` + 三位序号，由证据表统一分配，只增不改不复用；与公式锚点同字母但分属不同文件与命名空间）、`finding`、`statistic`（逐字片段或空）、`page`（必填）、`quote`（≤1 句，超限拒绝写入）、`supports_claim`、`claim_strength`（direct/indirect/conflicting/background，相反结果照样入表）、`limitations`（仅作者自述）、`note_path` + 笔记内锚点。纠错不改原行：用 `evidence correct --corrects E0xx` 追加带 `corrects` 字段的新行，原行保留，审计链完整。

## 5. 解析子系统：双轨制（产品）

### 解析双轨制（第八增量，2026-10-20 用户裁决——产品口径；两轨之外无产品解析路径）

- **轨一：Doc2X 轨（用户自配 Key）**——`parse <paper_dir>` 命令（`light_literature/parse.py`）。流程：分诊（未分诊自动补）→ Doc2XEngine 整篇解析（冻结参数见 §3 规则 10 与下文 Doc2X 适配器条）→ 把 Doc2X 的 layout 块 / 逐页 MD 转成锚点化 `source_map.json` + `原文.md`：S/C/F/T/E 按块类型与阅读序分配；图组划分与图注配对按 parse 内置的分组/距离规则（图注的 `caption_of` 指向优先认领）；表格 HTML → Markdown 进 `table_md`（HTML 原件另存 `table_html` 不丢信息）；公式 LaTeX 直达 E 块；图资产优先从 convert 导出 zip 物化（按 src 参数推导导出文件名 `{页}_{x}_{y}_{w}_{h}_{r}.jpg`），未命中走 PDF bbox 裁片兜底、再不行整页渲染兜底，逐块记 `asset_source`；confidence 取 Doc2X 页 score/100（无 score 则不写）。paper.yaml 写 `parse` 段（backend=doc2x、status=done、engine_params、uid、锚点计数、估算费用）。**操作规程（硬纪律）**：提交前先按分诊总页数估算费用（¥0.01–0.02/页）并**核对剩余额度或向用户确认**（额度曾在判定运行中耗尽，不许盲目提交）；uid 提交后立即落盘于 `doc2x/run_record.json`，崩溃/失败后先查记录恢复，**不许无记录重提**；Doc2X 结果云端只存 24 小时，适配器在 success 后立即下载落盘、**取回必须在 24 小时内完成**。**失败处置**：未配置凭据 / 额度不足 / 超时 / 服务错误 → `parse` 明确报错并把 paper.yaml 的 parse 状态置 `awaiting_model_direct`，提示转轨二；**禁止回退本地管线顶替、不许静默切换**。
- **轨二：模型直读轨（未配置 Doc2X 时；流程规范，无专用代码）**——接入智能体的模型亲自读 `原文.pdf` 撰写四件套，锚点与证据纪律与轨一完全一致。操作步骤（逐步执行、逐步自检）：
  0. **先分诊**：先跑 `triage <project_dir> <paper_id>`（分诊是体检工具、不是解析后端，轨一的 `parse` 亦先自动补分诊），逐页 `page_kind` 写入 paper.yaml 与 source_map 溯源；`scanned` 页只登记标注、不硬读硬写（扫描件不做专门适配，见 §3 规则 10 的用户裁决）；`source_version` 为 preprint/abstract_only 时先按 §3 规则 4 定降级档位再开读。
  1. **逐页读**：把每一页渲染成图逐页看，同时取该页文本层（有则用）交叉核对；逐页登记内容类型（正文/图/表/公式），不许跳页、不许凭印象或摘要写。
  2. **边读边建 source_map.json**：按阅读顺序给每个块分配锚点（标题/正文 = S、图注 = C、图 = F、表 = T、公式 = E），每块写 page / type / order / text，provenance 标 `model-direct`；字段契约与轨一一致，下游 verify / translate-scaffold / notes 照常消费。
  3. **图表逐个登记**：每幅图从页面渲染图裁出图片文件存 `assets/figures/`，与 F 块一一对应，块内记 `asset_source=page_crop`（与轨一的资产来源标记同字段）；每张表转写为 Markdown 存入 T 块 `table_md`；图注与宿主配对（图注写 `host_id`、宿主写 `caption_id`，多分片图写 `host_ids`），配不上如实标孤儿，不许硬配。
  4. **公式转 LaTeX 并过检**：每个公式块转写 LaTeX 存入 E 块 `latex`，并逐个用 `checks.check_formula_compilable` 校验可编译；不过检就回看原图修正，仍拿不准在 原文.md 对应处标「⚠ 转写存疑」并计数——**不许编造、不许留空冒充转写**。
  5. **写 原文.md**：按 source_map 顺序渲染（标题层级、图片引用、公式 `$$…$$`、表格 Markdown），文件头注明「模型直读生成（model-direct）」与转写存疑数。
  6. **翻译与笔记**：跑 `translate-scaffold` 出块对齐骨架后逐块译；跑 `notes` 出骨架后填精读卡 16 节；跑 `export-content-list` 出对照交换格式（与轨一下游链一致）；证据行照常 `evidence add`——锚点回指、引文限一句带页码、强度动词纪律一律不变。
  7. **过 verify 并如实标置信**：`verify` 照常校验（锚点闭环、图资产存在、表格/公式契约、图注配对、编号序列）；证据状态头的 **Extraction confidence 按实际如实标**——模型直读是转写而非确定性抽取，拿不准就标 Medium/Low 并在笔记 S16 写明局限，不许自产自标 High；paper.yaml 记 provenance=model-direct 与直读页数，parse 段状态由 `awaiting_model_direct` 更新为直读完成记录。Doc2X 日后补配时可重跑 `parse` 覆盖（覆盖前先留档）。**直读失败处置**：中途失败或某页实在读不清，该页在 原文.md 显式标「未解析（模型直读失败：<原因>）」、source_map 不为该页造假块，整篇状态按 §3 规则 9 标 `Partial` 并在总览写明缺口页与原因——与轨一「失败置 awaiting、不静默切换」同级诚实，不许拿别页内容或印象填补。
- **双轨对称对照（交付自检依据）**：两轨只差「地基从哪来」，其余环节必须一一对应；任一格缺项即不对称缺陷，按缺项一侧的规程补齐后才许交付。

  | 环节 | 轨一：Doc2X 轨 | 轨二：模型直读轨 |
  |---|---|---|
  | 前置分诊 | `parse` 未分诊自动补 `triage` | 步骤 0 先跑 `triage` |
  | 解析来源 | Doc2X layout 块优先、逐页 MD 兜底 | 模型逐页读渲染图 + 文本层交叉核对 |
  | 锚点与字段契约 | S/C/F/T/E，块带 page/type/order/bbox/confidence/provenance | 同左（字段契约一致，下游无感知） |
  | 图资产 | 导出 zip → PDF 裁片 → 整页渲染三级物化，逐块记 `asset_source` | 页面渲染裁片，记 `asset_source=page_crop` |
  | 表格 | HTML → MD 进 `table_md`，原件存 `table_html` | 转写 MD 进 `table_md`，拿不准的单元格标存疑 |
  | 公式 | LaTeX 直达 E 块 | 转写 LaTeX 进 E 块，逐个过 `check_formula_compilable`，存疑标注计数 |
  | 图组与图注配对 | parse 内置分组/距离规则，`caption_of` 优先认领 | 同规则手工执行：`host_id`/`caption_id`/`host_ids` 留痕，配不上标孤儿 |
  | provenance / 置信 | Doc2X 系标记；confidence = 页 score/100 | `model-direct`；Extraction confidence 如实标，不许自产自标 High |
  | 失败处置 | 报错 + 置 `awaiting_model_direct`，不回退本地、不静默切换 | 失败页显式标未解析、不造假块，整篇标 `Partial` 写明缺口 |
  | 状态落盘 | paper.yaml `parse` 段（backend/status/参数/uid/费用估算） | paper.yaml 记 provenance=model-direct 与直读页数，parse 段由 awaiting 更新为直读完成 |
  | 下游链 | verify → translate-scaffold → notes → evidence add → export-content-list | 同左，一步不少 |
  | 交付自检 | §8.1–§8.4 | §8.1–§8.4（同一份清单） |

- **研究存档说明**：开发期另有一套本地文本层抽取管线与第三方视觉解析引擎（MinerU）的实测接入，曾作研究对照与「超越 Doc2X」正式判定的本地侧实现；判定结论为「未超越」（见 §3 规则 10），其后按用户裁决退出产品路径——**相关代码与实测记录不在本仓库**，产品解析只有上文双轨。§9 附录中标注（研究线）的条目是该阶段的事故教训存档，仅有警示价值。下文为产品组件说明。

### 产品组件说明

- **分诊**（已实现，`triage` 命令）：逐页四项体检——文本层字符数、乱码率、字体 ToUnicode/可解码抽查、图文覆盖粗估；输出 `page_kind ∈ {born_digital, mixed, scanned}` 与全部数值，写入 `paper.yaml` 与 `source_map.json`，可审计。第六增量起 mixed 再细分可用性：字符 ≥300、乱码率 ≤5%（放宽以字体可解码率过关为前提，依据是 ResNet p5 那类数学字体括号分片顶高乱码率的形态）、覆盖不 suspicious、非整页大图，四关同过标 `mixed_usable`，否则 `mixed_unusable`。
- **content_list 导出**（已实现，`export-content-list <project_dir> <paper_id>` 命令）：source_map → `content_list.json`，与 MinerU Content List V1 对齐（type/text/text_level/img_path/image_caption/table_body/page_idx/bbox，其中 bbox 为 0–1000 相对坐标）；图注按该格式的形态折入宿主的 image_caption/table_caption，孤儿图注退化为 text + `is_caption` 不丢弃；每条带扩展字段 anchor_id/provenance/confidence/verify。这是统一的导出交换格式——只统一格式，不提升内容质量（table_body 的保真度继承其来源：轨一为 Doc2X 结构化结果、轨二为模型转写）。
- **校验**（已实现，`verify` 命令）：锚点集合一致性、F/T/E 资产/内容对应、图注配对（图按图组口径：组内共享同一 caption_id 才算配对、组内标记不一致=错误、no_caption 整组只警告一次；表逐块判 caption_id 或 no_caption 必居其一；第六增量）、编号序列（重号=错误，跳号/不单调/孤儿图注=警告）、待处理页标注完整性；**译文校验**（第二增量并入同一报告）：原文_中文翻译.md 存在时，锚点 ID 集合须与 source_map 完全一致、每块回指行 `**原文:** 原文.md#Sxxx（p.N）` 格式与页码须正确，无译文文件时该节标 `skipped` 不算失败。另有纯函数 `checks.check_table_grid`（HTML 表格网格自洽）与 `checks.check_formula_compilable`（matplotlib mathtext 代理，非 KaTeX 等价）供轨二公式过检等场景调用。
- **翻译脚手架**（已实现，`translate-scaffold <paper_dir>` 命令）：从 source_map 生成 原文_中文翻译.md——S/C 块同 ID 对齐 + 回指行 + 待译占位；F 块只给资产引用与图注待译占位；T 块只给表头/表注待译占位，**不复制表格数据**；E 块不重复渲染公式本体，只留译注占位。文件头写明术语账本引用与逐块置信标注要求。
- **精读卡骨架**（已实现，`notes <paper_dir>` 命令）：文件头由 paper.yaml 自动生成（作者/venue/年份在 paper.yaml 中无此字段，留待填，**不许凭记忆补**）；证据状态头四项按 source_map 与 verify 结果自动填初值；速读段 S1–S7 中 S4 图表清单由 source_map 的 F/T/E 块自动盘点；精读 16 节逐节带证据纪律注释（如第 10 节「不支持的更强结论」必填、第 12 节只许作者自述局限、第 16 节想法六道门）；文末原子卡附录（金句/概念/反直觉/方法/结构，微结构：出处 → 复述 → 启发）。**速读卡只是精读流水线的中间检查点，默认终点是精读卡**，与 §3 硬规则 3 一致。
- **证据行与术语账本**（已实现）：`evidence add <project_dir> --paper <id> --finding ... --page N [...]` 只增追加（page 必填、quote 超一句拒绝、claim_strength 枚举校验、finding 空拒绝）；`evidence correct` 追加纠错行；`glossary add <project_dir> --term ... --zh ...` 向 术语账本.md 追加，中英任一重复即拒绝并提示已有行。
- **Find 线**（已实现，`light_literature/find.py`）：五条命令与硬规则的代码落点——
  - `find <project_dir> --query … [--query …] [--sources …] [--per-source N] [--mailto …]`（`find()`）：OpenAlex / Crossref / Semantic Scholar / arXiv / Europe PMC 五源免 Key 检索，原始响应缓存 `Literature/.find-cache/`；**单源失败只记入检索报告「失败源」一节，不中断全程**。产物 `候选池.jsonl`（一行一个 study）+ `检索报告.md`（各源命中、三层对账计数、合并样例、模糊合并复核队列、失败源）。
  - **三层对账**（`dedup_records()`，规则在 `_same_report()` / `_same_study()`）：records → reports（L1 DOI 精确合并；无 DOI 时题名规范化精确 + 姓氏/年份相容；**预印本与正式版绝不并入同一 report**）→ studies（题名精确或 token Jaccard ≥ `TITLE_JACCARD_THRESHOLD=0.9` 且姓氏相容才合并多版本；主记录正式版优先，非主记录以 `version_of` 指向主记录，合并全程留痕 `merged_from`）。靠 Jaccard 近似合并的 study 标 `needs_review` 进复核队列，不静默自动判重。
  - `verify-identity <project_dir> [--limit N]`（`verify_identity()` / `_verify_one()`）：逐条查 Crossref（按 DOI）与 Europe PMC，字段级比对题名相似度（difflib ≥ `TITLE_SIM_THRESHOLD=0.85`）/ 第一作者姓氏 / 年份 ±1，结果只回写 `verification` 字段（identity_status ∈ verified/mismatch/unverifiable），**永不删条**——这是硬规则 1「候选层保留打标」的落点。注意与 ref-verifier 的有意偏离：Crossref 对 DOI 返 404 不直接判 mismatch（DataCite 注册的 DOI 如 arXiv 的 10.48550 本就不在 Crossref），先 Europe PMC 兜底，两边都查无才判 unverifiable；mismatch 只用于「查到权威记录但对不上」。
  - **撤稿/更正检查独立一步**（`check_retraction()`，硬规则 7 的落点）：在身份核实内、粗筛之前执行。双源信号——Crossref 反查 `filter=updates:{doi}` 读通知记录 `update-to[].type`（retraction/correction/expression_of_concern 等；注意 update-to 挂在通知记录上指向原文，不是原文记录自带）+ Europe PMC 的 `pubTypeList` / `commentCorrectionList` / `isRetracted`；优先级 retracted > concern > corrected > clear，双源都查成才算 clear、都查不成是 unknown。retraction_status 与 identity_status 一并回写。
  - `screen <project_dir>` 与 `screen check <project_dir>`（`generate_screen()` / `check_screen()`）：生成 `粗筛表.csv` + `粗筛说明.md`（**判定先行格式**写在说明里：先填 decision 再写 reason；六维 1–5 分，dim_relevance 为门控维）。check 硬规则：decision 枚举必填、**retracted 条目 decision 非 exclude 直接报错**；unverifiable 条目 include 只警告留痕（候选层允许跟进）。粗筛表已存在时不覆盖（防冲掉人工填写）。
  - `matrix <project_dir>`（`generate_matrix()`）：**成稿层硬规则 1 的执行点**——只有 `identity_status=verified` 且 `retraction_status != retracted` 的 study 进矩阵主体；unverifiable / mismatch / retracted / 尚未核实的全部进文末「排除清单」并注明原因，禁止静默丢弃。corrected/concern 进主体带 ⚠ 标记；仅预印本标「仅预印本」；撤稿状态 unknown 的进主体但备注明示。证据列按 DOI/题名从 `证据表.jsonl` 关联已入库论文（纠错链已消解：被 corrects 取代的原行不呈现），无证据显示「待精读」。
- **Doc2X 适配器（轨一后端）**（`engines/doc2x.py`）：整篇解析（无页范围选项、按整篇页数计费，`pages` 只过滤输出）。流程：preupload → PUT 预签名地址 → status 轮询（间隔 2s / 上限 600s / HTTP 超时 60s）→ convert 导出 md（zip 落盘）→ 转统一 middle_json（v3-2026 的 layout 块优先、逐页 MD 兜底）。冻结参数：model=`v3-2026`、formula_mode=`dollar`、formula_level=`0`、论文类默认开 `merge_cross_page_forms`，全部写入 `doc2x/run_record.json`；**uid 在 submit 后立即落盘**，后段任何失败凭 uid 续查，**不许无记录地重复 submit（重复计费）**；结果云端只存 24 小时，success 后立即取回落盘到 `<paper_dir>/doc2x/`；调用前按页数估算费用（¥0.01–0.02/页）并记账。Key 只经连接器凭据 surrogate 注入（连接名 `custom.doc2x`），**不许落盘到项目文件、不许出现在日志/命令行/异常信息里**（适配器异常全脱敏）。REST 端点与枚举以 Doc2X 官方 API 文档为准（开发期已逐项核实）。`parse` 命令以本适配器为后端做锚点化（见上「解析双轨制」轨一）。

## 6. 接口契约（只写边界，不展开对方实现）

- → **Light-Memory**：证据行、阅读结论、失败/撤稿记录以带来源与版本的事件提供；Memory 不反向改写四件套。
- → **Light-Idea**：证据矩阵 + 矛盾清单 + 笔记第 15/16 节；Idea 的查新请求走 Find 全价模式。
- → **Light-Write**：`参考文献.bib` 与证据行是引用的唯一来源；成稿层未核实禁用规则在此交接处执行。
- → **Obsidian 视图**：只投影阅读笔记与关系边，不投影 PDF/全文/译文。
- → **Light-Science**：状态机（已获取/已解析/已翻译/速读/精读/Partial 及缺口）经 `paper.yaml` 与总览上报。

## 7. 验收标准（v1 完成定义）

1. ≥5 篇真实论文（双栏、跨页表、复杂公式、中文论文各 ≥1 篇）跑通 Read 全链：四件套齐全、锚点校验全过、笔记过质量门。
2. Find 跑一个真实主题：纳排留痕可复查、未核实分层规则无漂移、撤稿检查有实际命中或注入测试命中。
3. 解析子系统已完成开发集对照与封存集正式判定，分项成绩与最差页清单如实报告（判定结论「未超越」见 §3 规则 10；判定材料属开发档案，不在本仓库）。
4. 至少一篇论文的证据行被 Idea/Write 侧实际消费一次。

> v1.0 定版状态（不许超报，细节以 README「开发记录（节略）」为准）：八个增量全部完成——第 1 条已由五篇端到端验收（双栏、跨页表、复杂公式、中文论文、合成扫描件）与双轨解析覆盖；第 2 条机制侧就位（Find 全链 + 一次真实联网冒烟），粗筛打分仍靠人工/agent 填表、程序只校验结构与硬规则；第 3 条已由正式判定收口（结论「未超越」，见 §3 规则 10），判定与开发集对照的详细数字属开发档案；第 4 条待下游（Idea/Write）实际消费验证，不在本技能内自证。脚手架/骨架不等于内容成品：译文与笔记正文由执行 agent 按本规范逐块逐节填写，完成度靠 §3 规则 9 质量门与 §8 自检清单把关，程序只保证结构、对齐与纪律约束可校验。v1.0 范围外：Compare/Reuse 未实现；研究线未竟事项只影响研究/对照，不影响产品双轨。

## 8. 交付前自检清单（逐项勾检，任一项不过不许交付）

用法：每件产物交付前由执行者逐项核对，判定方法写在条目里——能跑命令的不许凭感觉，能查文件的要真打开查。勾不下去就按 §3 规则 9 标 `Partial` 并在总览写明缺口（哪一项、缺什么）。§8.1–§8.3 按单篇勾，§8.4 按项目勾。

### 8.1 原文.md（两轨通用；标〔轨一〕/〔轨二〕的只查对应轨）

- [ ] 跑 `verify <project_dir> <paper_id>` 退出码为 0，`verify_report.json` 的 errors 为空（警告逐条看过并在交付说明里交代）。
- [ ] source_map 块数与 原文.md 锚点数一致，S/C/F/T/E 分项计数与 paper.yaml 记录对得上。
- [ ] PDF 每一页都有块产出或显式「未解析」标注；未解析页清单与分诊的 scanned / mixed_unusable 页一致，没有整页静默消失。
- [ ] 每个 F 块在 `assets/figures/` 有对应图片文件且可打开、非空；块内 `asset_source` 已记。
- [ ] 〔轨二〕抽查 ≥3 幅图裁片与 PDF 对应页渲染图一致（没裁错页、没裁串图）。
- [ ] 每个 T 块有 `table_md`；〔轨一〕`table_html` 原件在位。抽查 ≥5 处单元格数字与原文逐字一致（重点防小数点脱落，如 25.03 被写成 2503）。
- [ ] 每个 E 块有 `latex` 且逐个过 `checks.check_formula_compilable`；不过检的已回看原图修正，仍拿不准的在 原文.md 对应处标「⚠ 转写存疑」且计数写入文件头——不存在空 latex 或拿正文冒充转写的块。
- [ ] 图注配对查完：每条 C 有 `host_id`/`host_ids` 或显式标孤儿待复核；每个图组组内 `caption_id` 一致；无图注的 F/T 已标 `no_caption`。
- [ ] 图/表/公式编号无重号；跳号已定位原因（原论文跳号 / 图在未解析页 / 检出遗漏）并写进交付说明。
- [ ] 每块 provenance 在位：〔轨一〕为 Doc2X 系标记且 paper.yaml `parse` 段 status=done、uid 与费用估算已落盘；〔轨二〕全为 `model-direct` 且 paper.yaml 已记直读页数。文件头注明本篇走哪一轨。

### 8.2 原文_中文翻译.md

- [ ] `verify` 的译文校验 `status=checked`：锚点 ID 集合与 source_map 完全一致，退出码 0。
- [ ] 每块回指行 `**原文:** 原文.md#<ID>（p.N）` 在位；抽查 ≥5 条点开定位，页码与 source_map 的 page 一致。
- [ ] 全文搜脚手架占位符（如「待译」）计数为 0——没有未填块冒充成品。
- [ ] 术语一致：本篇新术语已先 `glossary add` 进术语账本；抽 ≥5 个高频术语全文检索，同一术语只有一种译法。
- [ ] 数字逐字核：抽 ≥10 处数字/百分比/年份/区间与原文对应块逐字比对，小数点、负号、量级无一走样。
- [ ] 形态纪律：E 块未重复渲染公式本体（只有译注）；F 块只有资产引用 + 图注译文；T 块只译表头/表注，表格数据未被改写或重排。
- [ ] 脚手架要求的逐块置信标注已填；低置信块（转写存疑、原文残缺处）在译文中如实带出标记，没有被译得比原文更确定。

### 8.3 阅读笔记.md（精读卡 16 节）

- [ ] 速读段 S1–S7 已填（S4 图表清单与 source_map 的 F/T/E 盘点一致），S7 精读决策已下且与实际完成状态一致。
- [ ] 精读 16 节无残留待填占位；逐节达到 `notes` 骨架纪律注释的最低要求，重点四节：第 10 节「不支持的更强结论」非空必填；第 12 节只含作者自述局限（作者没写则用固定句），Agent 批评只在第 13 节且全标 `[Analysis]`；第 16 节每条想法六道门字段齐（源指针/可为假假设/delta/验证方案/≥2 个失败模式/创新状态），未查新不许用 novel/first 类措辞。
- [ ] 数值逐字核：S5 关键结果速览与第 10 节表中的每个主要数字已逐个回 原文.md 对应锚点核对一致（不是抽查，是全查主要数字）。
- [ ] 指针存在性：笔记里每个 `[Paper: PDF p.N, Sxxx]` 与 `原文.md#Xxxx` 指针，其锚点在 source_map 中真实存在、页码对得上（逐个查，不许有悬空指针）。
- [ ] 出处五标签齐：每条陈述带 `[Paper]/[External]/[Analysis]/[Hypothesis]/[User]` 之一；第 04 节 paper-framed 与 externally verified 分开写；Agent 分析未用用户口吻。
- [ ] 证据行双产出齐：笔记引用的每个主要结果在项目 `证据表.jsonl` 有对应行（`evidence add` 已执行、note 锚点回指本节），证据行的 `note_path` 指向本笔记；笔记有而证据表无、或反之，都算不过。
- [ ] 证据状态头四项（Source coverage / Extraction confidence / Locator mode / Context verification）与实际一致；〔轨二〕Extraction confidence 如实标（转写非确定性抽取，不许自产自标 High），局限已写入第 16 节与状态头。
- [ ] 文件头作者/venue/年份已从原文首页逐字核对填入；paper.yaml 无此字段处保持「待填」标注，不许凭记忆补。

### 8.4 项目级（交付一批论文或阶段收尾时勾）

- [ ] 本批每篇 `verify` 0 错误；每篇 paper.yaml 状态机与 `00-文献总览.md`、文献索引.csv 的记录一致，无「总览写完成、实际 Partial」的漂移。
- [ ] 证据表与矩阵口径一致：重跑 `matrix` 后，主体篇数 = 已入库且 `identity_status=verified` 且未撤稿的 study 数；排除清单条数 = 候选池总数 − 主体数，逐条有原因，无静默丢弃。
- [ ] 未核实文献未进成稿层：抽查矩阵主体与各篇笔记结论的引用来源，无 unverifiable / mismatch / `[UNVERIFIED]` 文献被当作成稿证据使用（§3 规则 1）。
- [ ] `参考文献.bib` 与文献索引条目和入库论文一一对应，无多无少；导出只走 BibTeX/CSL-JSON（§3 规则 2，无 Zotero 专用格式）。
- [ ] 术语账本无重复行（`glossary add` 的重复拒绝即证据），本批新术语全部入账。
- [ ] 〔轨一〕每篇 `doc2x/run_record.json` 在位、uid 已落盘、本批费用估算已汇总向用户交代；无任何一篇是无记录重提产生的重复计费。
- [ ] 不过质量门的论文状态标 `Partial` 且缺口写进总览；本批交付说明里列明走了哪一轨、各篇页数与已知缺陷，不用「全部完成」笼统带过。

## 9. 失败模式附录（先查这里，再动手处置）

八个增量实测过的典型翻车，按「症状 → 原因 → 处置」记。每条都是真发生过的，不是假想。遇到清单外的新翻车，处置完把新条目补进本附录（只增不改旧条）。

1. **Doc2X 提交批量失败 / 费用异常** → 账户额度耗尽（正式判定运行中实际发生：25 篇成功后额度见底、16 篇失败、7 篇未提交）。→ 立即停一切新提交；先按分诊总页数估算费用并核对剩余额度或向用户确认；已提交的凭 run_record 里的 uid 续查状态，不许重提。
2. **Doc2X 上传或轮询超时** → 网络/服务侧慢，任务本身可能已在云端成立。→ 先查 `doc2x/run_record.json` 的 uid 并续查 status；uid 在就不许重新 submit（重复计费）；结果只存 24 小时，恢复后优先取回落盘。
3. **Doc2X 解析成功却在落盘阶段崩溃** → 第五增量 materialize 相对路径 bug，uid 一度随进程丢失。→ 现行引擎在 submit 后立即落盘 run_record（含 uid）；万一仍崩，凭已落盘的 `doc2x_result.json` 离线重建产物，不重新提交。
4. **图注大面积成孤儿（尤其跨页图注全丢）** → 转换层 `caption_of` 用了页内下标、未加页偏移（第五增量实测，9 条图注一度全成孤儿，已修并加跨页回归测试）。→ 再现时先查 parse/转换层的页偏移与 `caption_of` 认领逻辑，不要手动硬配图注掩盖。
5. **MinerU basic 路由整批全灭（研究线教训）** → 部署 config 未真正切换：`parse_server.local.mode` 仍为 disabled，驱动打印了「已切换」但没生效，29 个任务全灭，正式判定中本地公式分因此归零（执行偏离，非能力问题）。→ 批量跑前先单任务验活并回读服务端实际配置确认生效，再放量；「打印已切换」不算证据。
6. **MinerU flash 把整页正文塞进一个图块（研究线）** → flash 的 txt 模式对某些 born-digital 版面整页分段失败（Adam p1–10 实测，8 页只剩 header + 巨型 image 块）。→ born-digital 正文永远以文本层/双轨产品路径为准，flash txt 只作研究对照；见到整页单图块先怀疑此模式，不要据此判论文无正文。
7. **公式 LaTeX 形态正确但内容转错**（案例出自研究线实测，教训对两轨通用） → MinerU basic 曾把行内公式 β₁=0.9 转成 `\vec{\beta_{1}} = \vec{0.9}`（凭空加箭头、小数点移位）。→ 公式过 `check_formula_compilable` 只证明可编译、不证明对；关键公式必须回原图逐字抽查，转错按证据纪律纠错留痕。
8. **表格数字小数点脱落（25.03 → 2503）** → 文本层抽取的已知缺陷（ResNet 成品样例自查实测）。→ 表格数字被引用（译文、笔记、证据行）前必须回原文 PDF/Doc2X 结构化结果逐字核；产品轨表格以 Doc2X HTML 或模型直读转写为准，不引文本层表格文本。
9. **选篇语言误判** → 原定中文验收篇 ChatGLM 正文实为英文（中文只在图片化示例里），凭题名与印象选篇导致验收目标落空。→ 选篇后先程序化验证再定口径（如中文字符占比 ≥40% 才算中文正文），不凭题名、摘要语言或印象判定。
10. **图组误并 / 漏并** → 分组是几何 + 图注亲和的启发式：某图图注未被图注规则检出时，其图可能被并入邻图一组共享图注；版式疏朗时几何规则也可能链式误并。→ 查 source_map 的 `group_id`/`group_role`/`host_ids` 留痕人工复核推翻，并留痕记录；阈值先攒误判案例再整体校准，不许为单篇回调。
11. **版面家具冒充图块** → 分隔线、刊徽、Open Access 图标等小 XObject 被抽成 F 块并触发 no_caption 警告（中文期刊篇实测 4 条警告全源于此）。→ 看 F 块的放置尺寸与长宽比识别家具，人工剔除并留痕；verify 的 no_caption 警告是这类问题的暴露面，不许为了清警告把警告关掉。
12. **引文与原文不逐字（引号/标点被规范化）** → 弯引号被改直引号、标点被顺手修正后，quote 不再逐字可溯（ResNet 成品自查抓到 3 处引文瑕疵）。→ quote 一律从原文块逐字复制（含标点与引号形态）；`evidence add` 因一句上限拒绝时，先回原文核对再改选引文，不许改引文字句迁就工具。
13. **Find 某源整源无结果** → OpenAlex / Semantic Scholar 免 Key 限流 429（第三增量真实冒烟两源均被挡）。→ 单源失败只记入检索报告「失败源」一节，不中断全程、不拿别源结果冒充该源；给 OpenAlex 配 `--mailto` 礼貌池，Semantic Scholar 无 Key 配置位是已知局限（如实报告召回缺口）。
14. **公式密集论文的 E 块碎片淹没清单（研究线）** → 文本层公式候选判定把行内数学逐片标 E（Adam 实测约 400 个，多为单字符碎片），notes S4 被淹没。→ 产品轨不经文本层，无此问题；研究线产物引用时只盘点 F/T 与关键公式，碎片 E 只作定位计数，不逐条进笔记。
15. **Doc2X 图注碎片拆分（轨一）** → layout 把一条表注拆成「标签块 + 正文块」（如 "Table 1" 与 "Video lengths ..." 两块 caption_of 同指一表），宿主 caption_id 只认领其一：正文块成孤儿、正文里的数字（如 2.5-minute）被编号兜底误当图号、附录 Table A.1 型编号与正文编号混查撞号（CEA 110856 首跑实测：12 孤儿 + 编号重复报错）。→ 转换层已修：`parse.build_source_map` 按 caption_of 合并同宿主图注碎片（merged_from 留痕），附录编号单列 caption_series=appendix、verify 按 series 分组查序列；再现时先查合并逻辑，不要手动硬配或改 verify 迁就。已付费结果凭 doc2x_result.json 离线重建，不许重提。
