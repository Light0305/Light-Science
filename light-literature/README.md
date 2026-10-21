# light-literature

Light-Science 的文献子技能：把外部论文变成项目内可核查、可复用的研究材料。
技能规范见 [SKILL.md](SKILL.md)。

当前版本：**v1.2**。light-literature 把一篇外部论文加工成「四件套」——
原文 PDF、带 S/C/F/T/E 锚点的原文 MD、块级对齐的中文翻译 MD、图文并茂的
精读笔记——并配套证据行、术语账本与 Find 线（多源检索 → 身份核实与撤稿
检查 → 粗筛 → 研究证据矩阵）。v1.1 增补四件：共享检索适配层
（Find 线与下游查新/选刊共用同一检索底座）、ingest 元数据自动回填、
claim-support 主张核查命令面、ask 问语料模式（块级证据 + 固定拒答）。

**解析双轨制**是 v1.0 的产品形态：

- **Doc2X 轨**：使用者自备 Doc2X API Key 后，`parse` 命令把整篇 PDF 送
  Doc2X 解析，并把结果锚点化为 source_map.json + 原文.md（按页收费，
  约 ¥0.01–0.02/页，提交前须先估算页数并确认额度）。
- **模型直读轨**：未配置 Doc2X 时，由接入的智能体模型直接读 PDF，
  按 SKILL.md §5 的步骤规范亲自撰写带锚点的四件套（provenance 标
  `model-direct`），不依赖任何其他解析工具。

两轨的锚点契约、校验（verify）、翻译/笔记脚手架与证据纪律完全一致。
翻译与笔记的正文由 agent 按 SKILL.md 逐块填写，程序只生成脚手架/骨架
并校验结构。Compare/Reuse 未实现（v1.0 范围外）。

> 开发说明：本项目在开发期另有一套本地文本层抽取管线与对照评测工具，
> 仅作研究/对照用途，**不属于产品的一部分，未包含在本仓库中**；
> 产品解析只有上述双轨。

## 安装

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[test,formula-check]"
# 或不装包、直接在项目根目录运行（包目录在当前路径下即可）
.venv/bin/pip install pymupdf pyyaml requests pytest matplotlib
```

依赖：PyMuPDF、PyYAML、requests；matplotlib 仅供公式可编译检查（mathtext 代理）。

## 命令用法

```bash
# 1. 初始化项目级 Literature 结构
python -m light_literature init <project_dir>

# 2. 单篇入库：建目录、复制 原文.pdf、算 SHA-256、写 paper.yaml
python -m light_literature ingest <project_dir> <paper.pdf> \
    [--doi 10.xxxx/xxxxx] [--title "论文题名"] \
    [--source-version preprint|version_of_record|abstract_only] \
    [--source "arXiv:1706.03762"]

# 3. 逐页分诊（四项体检 → born_digital / mixed / scanned，数值写入 paper.yaml；
#    mixed 页再细分 mixed_usable / mixed_unusable，见 paper.yaml 的 mixed_usable 字段）
python -m light_literature triage <project_dir> <paper_id>

# 4. 产品解析（Doc2X 轨）：整篇送 Doc2X 并锚点化为
#     source_map.json + 原文.md（S/C/F/T/E 锚点建在 Doc2X layout 之上；
#     按页收费，提交前先估算页数并确认额度，规程见 SKILL.md §5）。
#     Doc2X 未配置/失败时不回退本地抽取：报错并置 paper.yaml 状态
#     awaiting_model_direct，转 SKILL.md §5 模型直读轨。
python -m light_literature parse <paper_dir>

# 5. 校验（锚点一致性 + 图注配对（图按组判、表逐块判）+ 编号序列 + 译文对齐；有 error 时退出码为 1）
python -m light_literature verify <project_dir> <paper_id>

# 5b. 导出 content_list.json（与 MinerU Content List V1 对齐的交换格式）
python -m light_literature export-content-list <project_dir> <paper_id>

# 6. 翻译脚手架（块级同 ID 对齐；F/T 不复制数据、E 不重复渲染公式）
python -m light_literature translate-scaffold <paper_dir>

# 7. 精读卡骨架（速读检查点 S1–S7 + 精读 16 节 + 原子卡附录；S4 清单自动盘点）
python -m light_literature notes <paper_dir>

# 8. 证据行（只增追加；--page 必填、--quote 上限一句、--claim-strength 枚举）
python -m light_literature evidence add <project_dir> --paper <paper_id> \
    --finding "..." --page 3 [--statistic "逐字片段"] [--quote "一句引文"] \
    [--supports-claim "..."] [--claim-strength direct|indirect|conflicting|background]
# 纠错：追加带 corrects 的新行，原行不动
python -m light_literature evidence correct <project_dir> --corrects E001 [--page 4] [...]

# 9. 术语账本（中英任一重复即拒绝并提示已有行）
python -m light_literature glossary add <project_dir> --term "attention" --zh "注意力" [--note "..."]

# 10. Find 线：多源检索（OpenAlex/Crossref/Semantic Scholar/arXiv/Europe PMC，
#     均免 Key；单源失败只记入报告）→ 三层去重对账 → 候选池.jsonl + 检索报告.md
python -m light_literature find <project_dir> --query "主题查询式" [--query "另一视角"] \
    [--sources openalex,crossref,semanticscholar,arxiv,europepmc] [--per-source 10] [--mailto you@x.com]

# 11. Find 线：身份核实 + 独立撤稿检查（只打标不删条；--limit 只核实前 N 条）
python -m light_literature verify-identity <project_dir> [--limit N] [--mailto you@x.com]

# 12. Find 线：粗筛表（判定先行：先填 decision 再写 reason，六维留空供人工/agent 填）
python -m light_literature screen <project_dir>
python -m light_literature screen check <project_dir>   # 校验：撤稿条目非 exclude 报错退出 1

# 13. Find 线：研究证据矩阵（成稿层硬规则：仅 verified 且未撤稿进主体，其余进排除清单）
python -m light_literature matrix <project_dir>

# 14. 元数据回填（v1.1）：逐字段 value+source+verified 写回 paper.yaml 的 metadata 区
#     （默认只跑本地源；--online 联网查 Crossref；--confirm 为用户逐字核对原文首页后标已核实）
python -m light_literature metadata-backfill <paper_dir> [--online] [--confirm]

# 15. 主张核查（v1.1）：块级定位候选锚点（无命中如实回 not_mentioned）→ 三值判定经机械校验落账
python -m light_literature claim-locate <project_dir> --claim "..." [--paper <paper_id>]
python -m light_literature claim-check <project_dir> --paper <paper_id> --claim "..." --verdict supports|contradicts|not_mentioned [--anchors S001,S002]

# 16. 问语料（v1.1）：对已入库语料块级检索作答，引用只能取自命中块；证据不足固定拒答
python -m light_literature ask <project_dir> --question "..." [--answer "..." --cite <paper_id>#S001]
```

`paper_id` = 单篇目录名（题名 slug + `_` + SHA-256 前 6 位），ingest 输出中给出。

## 产物结构

```text
<project_dir>/Literature/
├── 00-文献总览.md、文献索引.csv、证据表.jsonl
├── 研究证据矩阵.md（matrix 命令生成）、参考文献.bib、术语账本.md
├── 候选池.jsonl、检索报告.md（find 生成）、粗筛表.csv、粗筛说明.md（screen 生成）
├── claim_support.jsonl（claim-check 判定账，只增；v1.1）、问答记录/（ask 产物；v1.1）
├── .find-cache/（各源原始响应，按 源+查询式 哈希命名，供复现；Find 线与共享检索适配层共用）
└── <slug>_<hash6>/
    ├── paper.yaml          # 标识/版本/状态/分诊审计数值；parse 段记解析后端/状态
    │                       # （done / awaiting_model_direct）/参数/uid/费用估算
    ├── 原文.pdf
    ├── 原文.md             # <a id="S001"> 式块锚点；待处理页显式标注
    ├── 原文_中文翻译.md     # 与原文同 ID 对齐的脚手架（translate-scaffold 生成）
    ├── 阅读笔记.md          # 速读检查点 + 精读 16 节骨架（notes 生成）
    ├── source_map.json     # 全部块（S/C/F/T/E + boilerplate/figure_text）与溯源
    ├── content_list.json   # MinerU Content List V1 对齐导出（export-content-list 生成）
    ├── verify_report.json
    ├── doc2x/              # Doc2X 轨产物（parse 命令）：doc2x_result.json、
    │                       # 导出 MD + images/、content_list.json、run_record.json；
    │                       # parse 的图资产即从此处导出 images/ 物化到 assets/figures/
    ├── assets/figures/、assets/tables/、supplementary/
```

## 测试

```bash
python -m pytest -q   # 发布版保留 88 个产品测试（全 mock / 合成数据，不联网、不用真实 Key）：
#   test_find 18（Find 线：解析器/三层去重/核实状态机/撤稿检查/粗筛校验/矩阵硬规则/CLI 冒烟，
#     fixture 为开发期捕获的真实 API 响应样本）
#   test_scaffold_notes_evidence 12（翻译脚手架/译文校验/精读卡/证据行/术语账本）
#   test_doc2x_adapter 10（Doc2X 状态机/layout 与 MD 双路转换/materialize/脱敏）
#   test_parse_doc2x 7（parse mock 全链/图资产三来源/awaiting_model_direct 双失败路径/表格转 MD）
#   test_checks 6（表格网格与公式可编译检查）
#   test_figure_groups 6（图组规则纯函数 + verify 组级口径）
#   test_parse_caption_fragments 2（图注碎片合并回归）
#   test_searchlayer 6（共享检索适配层：统一模型/缓存/失败隔离；v1.1）
#   test_metadata_backfill 7（元数据回填：逐字段来源与核实状态；v1.1）
#   test_claimcheck 7（主张定位与三值判定机械校验；v1.1）
#   test_ask 7（问语料：引用白名单/证据强度门/固定拒答；v1.1）
```

## 开发记录（节略）

v1.0 由八个增量逐步建成。各增量的完整验收记录（实测数据、事故复盘、
逐条局限）属于开发档案，不在本仓库中；此处只留每步的主题与结论：

1. **地基**：项目结构、ingest（SHA-256 与 paper.yaml）、分诊、锚点化
   原文与校验闭环。
2. **笔记线**：翻译脚手架（块级同 ID 对齐）、精读卡骨架、证据行
   （只增追加 + 纠错追加）、术语账本；verify 并入译文对齐校验。
3. **Find 线**：五源检索与三层去重、身份核实、独立撤稿检查、粗筛表、
   研究证据矩阵（成稿层硬规则：未核实文献一律不进主体）。
4. **解析补强**：矢量图捕获、图组、段落合并、content_list 导出。
5. **Doc2X 适配器**：真实 API 对接（提交/轮询/导出物化/凭据脱敏），
   并与本地管线在开发集上做了对照评测。
6. **图组与端到端**：多分片图组共享图注、mixed 页路由、五篇论文
   端到端验收。
7. **视觉引擎实测**：第三方视觉解析引擎真装实测，结论是其只适合做
   页级难例引擎，不适合当产品主通道。
8. **双轨定版**：正式对照判定显示本地管线未超越 Doc2X；按最终裁决
   改为双轨制——Doc2X 轨（用户自配 Key）+ 模型直读轨，本地管线退出
   产品路径。SKILL.md 同步定版（§8 交付自检清单、§9 失败模式附录、
   双轨对称对照表）。
9. **v1.1 增补（第二轮）**：LIT-D05 共享检索适配层（统一 Paper
   模型 + 五源适配器 + 缓存与失败隔离，find/verify 全改走，消费
   契约入 SKILL §6）；LIT-D03 元数据自动回填（逐字段来源 + 核实
   状态，自动回填恒未核实）；LIT-D04 claim-support（数字逐字对
   锚点机械校验，三值判定只增落账）；LIT-D01 ask 问语料（引用
   白名单 + 证据强度门 + 证据不足固定拒答）。开发树测试
   93 → 120 passed，发布版保留 88 个。
10. **v1.2 快修（第三批）**：ask 检索升级——块级 IDF 加权排序
    （词项 IDF 和 + 2 x 数字 IDF 和）、查询侧跨语言扩展（中文
    术语并入英文对应词）、CJK 证据单元改双字组（单字不再成
    证）、检索面扩入 E 公式块与 F 图内文字、证据单元门按证据
    构成路由并增两条问题级拒答（词表概念硬缺席 / 命名实体
    缺席）。冻结问答评测集 gold 实测：可答题全召回 57.1% →
    95.2%、金标锚进 top-5 7/21 → 19/21、拒答题与陷阱题均归
    零命中；heldout 未运行。开发树测试 120 passed（零回归）。

## v1.0 封版记录（2026-10-20）

八个增量全部完成并通过验收后定版封存。本记录只汇总定版状态；各增量的
完整实测数据与原始局限记录保留在开发档案中（见上文「开发记录（节略）」）。

**定版形态**

- **解析双轨制**（2026-10-20 用户最终裁决）：产品解析只有两个后端——
  轨一 Doc2X（用户自配 Key，`parse` 命令锚点化）；轨二模型直读（未配置
  Doc2X 时由接入模型亲自读 PDF 撰写带锚点的四件套，SKILL.md §5 七步
  规范）。本地管线（extract/MinerU/bench）退出产品路径，仅作研究/对照。
- **上层不变**：四件套、S/C/F/T/E 锚点、证据纪律、Find 线（五源检索、
  三层去重、身份核实、独立撤稿检查、粗筛、证据矩阵成稿层硬规则）在
  两轨下完全一致；「未核实文献成稿层一律不用」「不要 Zotero 的任何
  东西」「入库默认直接精读」三条口径写死于 SKILL.md §3。
- **模型无关原则**：质量下限靠流程与自检清单保证——SKILL.md 新增
  §8 交付前自检清单（原文 10 项 / 译文 7 项 / 笔记 8 项 / 项目级 7 项，
  共 32 项，每项可判定）与 §9 失败模式附录（14 条，均为八个增量实测
  过的翻车：症状 → 原因 → 处置）；§5 补双轨对称对照表，轨二规程
  补齐分诊前置、资产来源标记、失败页处置，与轨一一一对应。
- **版本**：pyproject 与包 `__version__` 升 1.0.0，CLI 与 SKILL.md
  版本行定版 v1.0；notes/translate/verify 三处过时报错文案已改为
  双轨口径（仅文案，无行为变更）。
- **测试**：封版时开发树全量 **91 passed**（本轮只有文档与版本/
  文案变更，无行为变更）；本发布版按白名单保留其中 61 个产品测试
  （见「测试」节），在其余 30 个随研究存档剔除后仍全数通过。

**v1.0 已知局限总表**（汇总自各增量记录，此处只列产品轨条目；
研究线条目随开发档案保留，不影响产品双轨）

| # | 局限 | 影响面 | 状态 / 处置 |
|---|---|---|---|
| 1 | Compare / Reuse 模式未实现 | 产品 | v1.0 范围外 |
| 2 | 模型直读轨无确定性保证，质量取决于执行模型 | 轨二 | 靠 SKILL 步骤 + verify + 证据纪律兜底；Extraction confidence 必须如实标，不许自产自标 High |
| 3 | parse 图资产映射依赖 Doc2X 导出命名同构 | 轨一 | 已在真实样本核实；未命中自动走 PDF 裁片兜底，质量不降级、来源标记可查 |
| 4 | 表格 HTML→MD 丢合并单元格语义（span 展开为重复填充） | 轨一 | `table_html` 原件保留，下游需精确结构时读原件 |
| 5 | Doc2X 只给页级 score，块 confidence 是页 score 代理 | 轨一 | 非块级真实置信，引用时按此口径理解 |
| 6 | Doc2X 整篇计费、无页范围选项、结果云端只存 24 小时 | 轨一 | 纪律：提交前估费并确认额度、uid 立即落盘、24 小时内取回 |
| 7 | 扫描件不做专门适配（用户裁决） | 全局 | 只做分诊识别与显式标注；老扫描件人工阅读 |
| 8 | OpenAlex / Semantic Scholar 免 Key 限流（429），Semantic Scholar 无 Key 配置位 | Find | 单源失败不中断并记入报告；召回缺口如实报告；OpenAlex 可配 mailto 礼貌池 |
| 9 | 身份核实题名阈值（difflib 0.85）有误判风险：出版方改写题名可致 unverifiable，同名异篇可误判 verified | Find | 阈值集中在 find.py 常量区，攒误判案例后整体校准，不单条改 |
| 10 | 撤稿信号依赖出版方登记，两源都未登记的撤稿查不出（clear ≠ 保证未撤稿） | Find | 重要稿件人工复核 Retraction Watch |
| 11 | 模糊合并靠题名 Jaccard + 姓氏，同作者同题系列（Part I/II）可能误并 | Find | 已标 needs_review 进复核队列，但无独立复核处置命令 |
| 12 | 粗筛六维打分靠人工/agent 填，程序只做结构与硬规则校验 | Find | 空表不等于已筛选 |
| 13 | verify 只查结构不查语义：译文锚点对但内容串行/译错查不出来 | 全局 | 靠 SKILL §8 抽读自检（回指抽查、数字逐字核） |
| 14 | 引文「一句」判定是启发式，英文缩写句点（如 et al.）可能误拒 | 证据行 | 口径宁严勿松；误判改用 statistic 字段或人工写入并注明 |
| 15 | `evidence correct` 未给字段继承原行，程序不做交叉校验 | 证据行 | 纠错人须自查继承的 quote/statistic 是否仍与新 finding 成立 |
| 16 | ingest 未自动回填作者/venue/年份，notes 文件头需人工从原文首页核对 | Read | **v1.1 已关闭**：metadata-backfill + ingest 自动本地回填（逐字段带来源，自动回填恒标未核实，核实仍须人工逐字核对原文首页） |
