# light-write

承接 light-analysis 结论包的稿件包工具：**先登记后使用、成稿门逐项对账**。主张、数字、引用、图表、声明全部先登记进稿件包，正文只许引用登记过的东西；引用只来自 light-literature 的 verified 集，数字只来自 Analysis 溯源表，措辞永不超过 Analysis 强度档。

当前版本：**v1.2（封版，2026-10-21）**。v1.1 增补：intake 卡内一致性校验（WRT-D05）、贡献确认回执（WRT-D04）、程式化核查 advisory 层（WRT-D01）、措辞词表实测与证据登记（WRT-D02）、溯源键三元组（WRT-D13）、模板记录校验小账清零（WRT-D08）、SKILL 分册化（WRT-D06，细则见 `references/`）。端到端演示见 `examples/demo-fullrun/`（合成链：承 Analysis 演示结论卡走完 intake → outlined → drafted → 披露 → 审计四门 → audited，跨模型复核 REVIEW_UNAVAILABLE 如实拦停，另含 W7 返修全环；v1.1 复跑附记在 demo-report 末尾）；Phase 1 承接骨架演示见 `examples/demo-synthetic/`。

## 能力

### 承接与登记

- **稿件包数据模型**：`manuscript.yaml` 登记头（`language` 按目标期刊定、en/zh 必填）、`claims_register.yaml`、`numbers_ledger.yaml`、`references.lock.json` + 生成物 `references.bib`（禁手改）、`figures_manifest.yaml`、`submission_checklist.yaml`、`acceptance_contract.yaml`、`template_record.json` 快照、`sections/`。
- **承接（intake）**：读 Analysis `conclusion_card.json` + Literature verified 导出，落四组快照哈希（上游变动即承接失效）；上游状态原样落字（非 delivered / REVIEW_UNAVAILABLE 显式标注并降级登记）；主张登记初建——`writable_form` 由上游状态×强度档规则表导出（untested 只许 limitations_only/omit），`wording_ceiling` 按稿件语言取双语词表；verified 过滤 + 撤稿四态映射（retracted/no_doi/unknown/clean）。**卡内一致性校验**（WRT-D05）：承接前先验结论卡自洽（counts 对账、溯源指针自洽、同指针两值冲突、spec 指针齐备；卡同目录有 spec_results 时逐项比对登记值与所指结果），不一致拦 intake 点名——堵住「三方一致地错」。**贡献确认回执**（WRT-D04）：intake 生成主导贡献陈述草案，用户 `confirm-contribution` 签认落回执才许 outlined，偏离草案须点名差异。
- **模板记录消费**：九组 46 字段的核查记录登记与校验——限额数值化、AI 政策组（规定声明标题/措辞模板/多值披露位置/输出有效性评估子项）、过期拦截、期刊语言与稿件语言一致性、快照哈希防篡改。消费的是**核查记录**不是模板文件（模板库姊妹仓未建，记录由人工按官方原文登记）。
- **验收合同**：动笔前 10–20 条可核查断言冻结 + 哈希锁定；任一 contested 即降级且不许 submission_ready（拍板⑥硬门）。
- **校验器**：主张覆盖与形态上限、措辞词表语言、text_hash 漂移、占位符纪律（未知 key 拒、裸 DOI 拒、手写引用串警告）、撤稿条目被引拒、bib 手改检出、承接快照过期检出、声明三态、use_log 缺模型版本拒、数字无溯源拒、合同冻结哈希防篡改。

### 起草门与成稿门

- **drafted 段门**：逐节稿按模板栏目序列齐备 + 三类标记（`[claim:]`/`[num:]`/`[@key]`）全量校验 + 主张/数字锚定覆盖 + 图表占位对齐 + 未结指令标记拦截；过门落 lock 引用子集收窄清单（未引条目只列不删）。
- **审计四门**（`audit`，fail-closed，产物绑稿件哈希、稿改即 STALE）：
  - 门一 引用两段核对：身份核（双路阴性证据才许落 `identity_level_fabrication`）+ 字段核（`field_level_hallucination_screen` 口径 + 容差层：年份 ±1 只 warning、venue 只 warning、DOI 可解析降级、页码差 ≤4 warning/≥5 error、形近字符 error）；在线权威记录经**注入接口**复核，离线整门 honest-unverified 不许 PASS；相关性轴只标记不自动定罪，REPLACE/REMOVE 须人类批准；支撑判定五级量表 + 双角色对抗协议（无逐字支撑句不确认）。
  - 门二 数字对账：正文呈现串 ↔ 数字账 ↔ Analysis 溯源表逐串比对（半上舍入到呈现精度）；溯源键为（判定行，登记行，量名）三元组（WRT-D13，同行多量各自独立锚定，裸键多量落 ambiguous 点名迁移）；未登记数字串逐个点名；附一致性清扫（同量异精度/异单位只警告）。
  - 门三 强度措辞门：逐主张句比对按稿件语言的 wording_ceiling（中英双语词表），超限/禁用词拒并给降格建议；text_hash 漂移须 `reverify-claim` 重验落字才许过门。词表已经第一次实测（WRT-D02，报告 `../06-write/WORDING-MEASUREMENT-v1.1.md`）：英文禁用词按词界匹配（子串口径的 proves/improved 误报已证伪），全部词条带证据指针与处置依据。
- **程式化核查层**（`tone`，WRT-D01，advisory）：审计后、投稿就绪前查成稿的程式化与 AI 味——规则只收可定位触发标记（翻案腔/套话/序数脚手架/相邻句同构，中英分开立规、逐条带正反例），配同等地位的不改表（句长参差/被动/名词化等永不报警）与信息守恒纪律（只报不改、改写不许删限定词）；产物 `audit/tone_report.json`，不阻断定版、不设检测器分数。
  - 门四 落点映射复核：检查清单全条目落点实位机械复核（节锚点/声明三态/文件），报告规范条目只复核落点不做声明式自查。
- **按刊披露生成**（`disclose`）：use_log × 模板 G 组政策 → 披露文本落到每个登记位置（锚点块可重跑替换）；政策缺字段点名不编造；`output_validity_evaluation` 子项须作者落字；生成记录带双哈希，变动即 STALE。
- **复核门与 submission_ready**：跨模型复核子流程（`review prepare/record/import/unavailable`，收据 `RV-<sha256[:10]>`，同族拒、带异议不落收据），与 Idea/Design/Analysis 同构；ready 门 = 四门新鲜全过 + 落点底线层全 addressed + 披露齐备 + 声明无 absent + 合同非 contested + 复核收据哈希对齐；REVIEW_UNAVAILABLE 停 audited 并落 blocked 原因。
- **W7 返修子包**（`revision/`）：审稿意见逐条登记（原文）→ 逐条回复（决策+理由+改动锚点）→ 双向对账（意见全覆盖 × 正文 `[rev:]` 改动全回指）→ 回复信绑稿件哈希，稿改信未更即 STALE。
- **W5 图表回填三方对账**（`figures`）：清单 ↔ 正文 `[fig:]` 实位 ↔ 图注（哈希对齐 + 同位出现）；编号冻结后只许追加编号或全量重编，均落变更日志。
- **补课 D 账本**（nature-skills 生态簇，采纳 16 条 D-W01–D-W16）：正文分配纪律（位置图 + 结果功能八分类 + 删除日志）、术语账（锁定后变体入稿即 error）、AI 使用风险分级（evaluative_interpretive 须 human_verified 落字、prohibited 硬拦）、数据集访问路径七路映射、清单 stage/readiness、承重陈述保护、草稿标记纪律、统计报告底稿条目（`checklist add-stats`）。

## 快速开始

```bash
pip install -e .
light-write init ./my-manuscript --title "My Paper" --language en
light-write intake ./my-manuscript --conclusion-card conclusion_card.json --literature candidate_pool.jsonl
light-write register-template ./my-manuscript --record journal_record.json
# 在 acceptance_contract.yaml 登记 10–20 条断言后：
light-write freeze-contract ./my-manuscript
light-write validate ./my-manuscript
light-write advance ./my-manuscript   # → outlined
# 逐节起草（标记纪律见 SKILL §10），登记数字/清单/声明后：
light-write advance ./my-manuscript   # → drafted（落 lock 收窄清单）
light-write disclose ./my-manuscript  # 按刊生成披露（先于审计）
light-write figures freeze ./my-manuscript   # 编号冻结须在终审审计之前
light-write audit ./my-manuscript --online-records online_records.json
light-write advance ./my-manuscript   # → audited（四门全过）
light-write review prepare ./my-manuscript
light-write review record ./my-manuscript --reviewer "GPT Reviewer" --family openai
light-write advance ./my-manuscript   # → submission_ready
```

投中文期刊时 `--language zh`，模板记录的期刊语言同为 zh；逐节规程与措辞词表双语同构（见 SKILL.md §3/§4）。

## 设计依据

- `../06-write/LEARNING.md`：16 条硬约束（引用两段核对、占位符隔离、措辞 ≤ 强度档、披露靠留痕不靠检测……），SKILL §19 附逐条对应表
- `../06-write/REDESIGN-DRAFT.md`：稿件包草案 + 用户拍板 6 项 + 模板接口九组字段
- `../06-write/SUPPLEMENT-D-DISPOSITION.md`：补课 D 18 条逐条处置（采纳 16 条落 SKILL §18；D-W17 留 v1.1 评估；D-W18 五项已评估不采）
- `../06-write/00-census-summary.md` 纠错记录第 11 条：6 条构建期差异已逐条落实（幻觉口径分名、容差/定级层、撤稿四态、九组字段为准、AI 政策组补字段与多值位置）

## 测试

```bash
python -m pytest   # 183 个测试（v1.0 的 129 + v1.1 新增 47 + v1.2 快修新增 7）
```

## 已知局限（v1.0）

1. **在线权威记录为注入接口，v1 不内嵌网络调用**：门一的在线核对靠 `--online-records` 注入操作者自备的权威记录（如 Crossref 拉取）；演示中的注入记录是构建时现拉的真实记录（原始响应存档），但工具本身不联网、不缓存、不自动刷新。
2. **同一稿件不支持双语双版**：language 按目标期刊登记 en/zh 二选一，同稿不维护双语平行版本（拍板①修正版口径）。
3. **D-W17（组织形态重构）已由 WRT-D06 落地**：SKILL 主文件只留路由表、规则表与段门规程卡（156 行），细则下沉 `references/` 五册，结构 lint 进测试。
4. **导出渲染层不在 v1**：v1 只出 MD 稿件包 + 模板登记；pandoc/LaTeX/Word 导出排 v1.1（拍板⑤）。
5. **模板库姊妹仓未建**：模板核查记录须人工按期刊官方原文逐项登记（工具只校验形态与时效）；姊妹仓 v0（元数据登记 + 官方渠道 + 条款、不打包模板文件）排在 Write v1 封版后启动。
6. **溯源表共键遮蔽已由 WRT-D13 关闭**：溯源键细化为（判定行，登记行，量名）三元组，同行多量各自独立锚定；裸键只在单量时兼容解析，多量落 ambiguous 点名须显式迁移。
7. **措辞门是词表级机械比对**：抓得到标记句内的越档词，抓不到无标记断言与语义级夸大；未标记的事实断言仍须人工补审（约束 11 的诚实边界）。词表实测的语料面有限（两篇同领域已发表论文 + 本包演示稿，无中文自家稿），后续真实项目稿应按同一脚本扩样复测。
8. **相关性/支撑判定只验机械面**：工具校验判定词表合法、逐字句在场、双角色落名，不判语义真伪；判定本身由人/模型按对抗协议给出，工具不代判。
9. **跨模型复核依赖外部异家族模型**：本环境单一模型家族时只能落 REVIEW_UNAVAILABLE 停在 audited（演示即此终点）；收据不可自签自赦是设计而非缺陷。
10. **图件只登记指针 + 哈希**：figures 只对账清单/正文标记/图注三方一致性，不验图-文内容一致性（图内数据与正文数字的语义核对归 light-figure/人工）。
11. **撤稿态无自动订阅**：成稿时点的撤稿复核靠 lock 快照 + 注入记录的 retraction_state 字段；无自动更新通道，投稿前应重新注入最新记录复核。

## 封版记录

- **v1.0（2026-10-20）**：SKILL 定版（§1–§19：文件群/承接/规则表/提纲/合同/模板消费/登记纪律/核查口径/CLI/逐节规程/审计四门/披露/复核门/W7 返修/图表对账/成稿自检 16 项/失败模式 F1–F16/补课 D 采纳规程/LEARNING 16 条对应表）；129 测试全绿；端到端演示 `examples/demo-fullrun/`（合成链）终点 audited + REVIEW_UNAVAILABLE 拦停、四门终审全过、W7 返修双向对账全过。
- **v1.1（2026-10-21 夜班构建，待全套统一封版）**：七个必做项落地（构建单 `../20-build/phase3-write.md`）；176 测试全绿（129 基线零变红 + 新增 47）；演示复跑终点 audited、四门全过、卡内一致性 0 gap（附记见 demo-report 末尾）。
- **v1.2（2026-10-21 快修批）**：冻结措辞表变体绕过修复——significant 族禁用词（not significant / highly significant）匹配前做变体归一（间隙只许 -ly 副词或 at all、至多 2 个成分，聚焦副词 only/just/also/simply/merely 排除，防误杀 "not only significant" 让步结构）；183 测试全绿（新增 7，含阴性对照）。开放类变体（wasn't significant 等）未覆盖、只登记待语料证据。
