---
name: light-write
description: Use when 需要把分析结论包写成可投稿的稿件：按登记的主张、数字与引用成稿，过审计门，或处理审稿返修意见时。
version: "1.3"
author: light-write contributors
license: MIT
---

# light-write SKILL（v1.1）

> 定位：把 Analysis 的结论包变成可投稿的稿件包。核心原则——**登记文件是权威源，正文只许引用登记过的东西**：主张、数字、引用、图表、声明全部先登记后使用，成稿门逐项对账。
> 设计依据：`06-write/REDESIGN-DRAFT.md`（含拍板 6 项）、`06-write/LEARNING.md`（16 条硬约束，对应表在分册 supplement-d）。v1.0 范围：数据模型、承接与主张登记、模板记录消费校验、验收合同冻结、五段状态机门（intake→outlined→drafted→audited→submission_ready）、审计四门、按刊披露生成、跨模型复核门、W7 返修子包、W5 图表回填三方对账与编号冻结。v1.1 增补（第二轮拍板）：卡内一致性校验（WRT-D05）、贡献确认回执（WRT-D04）、程式化核查 advisory 层（WRT-D01）、措辞词表实测与证据登记（WRT-D02）、溯源键三元组（WRT-D13）、校验小账清零（WRT-D08）、本文件分册化（WRT-D06）。端到端演示见 `examples/demo-fullrun/`（合成链，终点 audited + REVIEW_UNAVAILABLE 拦停），Phase 1 承接骨架演示见 `examples/demo-synthetic/`。
> 语言口径（拍板①修正版）：**语言按目标期刊定，一篇稿一个语言**。`manuscript.yaml` 的 `language`（en/zh）必填，跟随模板核查记录的期刊语言；逐节规程与措辞词表双语各备一份、结构同构；内部说明文件（工作注记、对账记录）语言不限。模板库范围含中文期刊模板。

---

## 路由表（先查表，再读分册）

主文件只留路由、规则表与段门规程卡；细则按需读分册，不许凭主文件的摘要猜细则。

| 任务 | 读哪里 |
|---|---|
| 承接结论包、登记主张/数字/引用 | 本文件 §1–§3、§7（规程卡即全量） |
| 定提纲、逐节起草 | `references/section-protocols.md`（原 §4/§10 细则）+ 本文件 §4 门卡 |
| 跑审计四门、处理门一到门四 findings | `references/audit-gates.md`（原 §8/§11 细则）+ 本文件 §4 门卡 |
| 程式化/AI 味核查（advisory） | 本文件 §4 门卡 + `schema.TONE_RULES` / `schema.TONE_NOT_CHANGE`（规则与不改表为权威实现，`tone` 命令产报告） |
| 生成按刊披露、走跨模型复核、处理返修、图表回填编号 | `references/disclosure-review-revision.md`（原 §12–§15 细则）+ 本文件 §4 ready 门卡 |
| 查失败形态与处置 | `references/failure-modes.md`（原 §17，F1–F16） |
| 补课 D 规程（分配/术语/风险分级/支撑量表等）、约束对应表 | `references/supplement-d.md`（原 §18/§19） |
| 投稿前逐项自检 | 本文件 §16 清单 |
| 导出投稿文件（DOCX / LaTeX / PDF） | 本文件 §9 `export` 命令；模板变量映射与实物见模板库登记（`libraries/journal-templates/registry.jsonl`，逐家规程在其 procedures/） |

## §1 稿件包文件群

| 文件 | 角色 |
|---|---|
| `manuscript.yaml` | 登记头（权威）：language、承接快照、目标期刊、作者与声明三态、AI 使用留痕 use_log、节登记表、合同状态指针 |
| `claims_register.yaml` | 主张登记：逐条主张 ← Analysis 主张 id + 强度档 + writable_form + wording_ceiling + text_hash |
| `numbers_ledger.yaml` | 数字溯源账：逐数字 ↔ Analysis 溯源表条目指针（起草期填充） |
| `references.lock.json` | 引用快照：verified 集快照子集（key、条目 ID、撤稿四态、entry_hash） |
| `references.bib` | **生成物，禁手改**：由 lock 回填渲染，文件头带 GENERATED 标记与条目集哈希 |
| `figures_manifest.yaml` | 图表清单：占位/交付/回填三态 + 编号冻结标记（与 light-figure 协同） |
| `submission_checklist.yaml` | 投稿检查落点映射（提纲期填充、投稿前门四复核） |
| `acceptance_contract.yaml` | 验收合同：动笔前断言清单，冻结后哈希锁定 |
| `template_record.json` | 目标刊核查记录快照（九组字段，register-template 落） |
| `sections/*.md` | 逐节稿：行内标记 `[claim:C###]`、`[num:N###]`，引用只许占位符 `[@key]` |
| `audit/` | 审计四门产物（audit_report.json + 逐门 MD + 总判定，绑稿件哈希）+ 程式化核查产物（tone_report.json + gate-tone.md，advisory） |
| `revision/` | W7 返修子包（comments.yaml / responses.yaml / response_letter.md） |
| `review_packet.md` | 跨模型复核包（review prepare 生成，自包含） |
| `export/<配置名>/` | 导出产物（pandoc 渲染链）：`combined.md` 组装源（机械变换留痕）、`manuscript.docx/.tex/.pdf`、`export_record.json`（工具版本/模板映射/变换日志/复核五项，绑稿件哈希——稿改即 STALE，`export check` 检出） |

## §2 承接规程（W0，intake）

1. **只承结构化产物**：输入 = Analysis 的 `conclusion_card.json` + Literature 的 verified 条目导出（候选池 JSONL 或条目列表）。承接时落四组快照哈希：结论卡文件哈希、卡内主张集哈希、数字溯源表哈希、verified 集哈希。任一上游文件事后变动 → validate 报承接失效，**须重新 intake，不许静默沿用旧快照**。
2. **上游状态如实落字**：结论卡 status 与 review 状态（含 `REVIEW_UNAVAILABLE`）原样进快照与 `upstream_flags`。非 delivered（如 graded/blocked）时包可建，但主张按降级口径登记，并在登记头显著标注。
3. **verified 过滤是硬规则**：只有 `identity_status=verified` 的条目入锁；未核实条目永不进锁（成稿层「未核实文献一律不用」）。去重按 Literature 条目 ID 归一，不按键字符串（防同一文献多键重复，Manubot 陷阱）。
4. **撤稿四态映射**：Literature 的撤稿状态映射为四态 `retracted / no_doi / unknown / clean`——无证据绝不落 clean（refchecker R11 口径）。`retracted` 条目虽入锁留痕，但被正文引用即报错；`unknown` 条目被引用须先复核并在 `retraction_note` 落字。
5. **主张登记初建**：逐条上游主张建行——`writable_form` 由规则表（§3）导出上限并落字，不许逐条临场决定；`wording_ceiling` 按**稿件语言**取对应词表导出。上游未给规范文本的主张，`claim_text/text_hash` 留空并落 gap 警告，**不许临场编造文本**（承 Analysis SESOI 教训的通则化）。
6. **新引用需求只走回流**：写作中发现需要新文献 → 在登记头 `reflux[]` 生成「送 Literature 核实」条目，不许现查直入、不许凭记忆写书目信息（约束 3）。
7. **卡内一致性先验**（WRT-D05）：intake 先验结论卡自洽——counts 与逐主张 line_verdicts 计数对账、溯源行指针自洽与同指针两值冲突、数值行 spec 指针齐备；卡同目录有 `spec_results.jsonl` 时按（登记行，spec_id）逐项比对登记值与所指 spec 结果（按呈现精度舍入后比对）。任一不一致 → 落 gap 拦 intake 并点名，不许带病承接；本校验只验卡内自洽，不重算 Analysis 模型。
8. **贡献陈述草案与签认**（WRT-D04）：intake 后由上游主张规范文本机械组装主导贡献陈述草案（`manuscript.contribution`），用户以 `confirm-contribution` 签认后回执（含陈述哈希与签认时点主张集哈希）才算数；未签认拦 outlined 门。签认文本与草案不一致时必须点名差异（drift_note），不许静默改写上游主张口径；签认后改陈述或上游主张漂移，validate 检出并要求重签。

## §3 writable_form 规则表（草案 §1.2，schema.writable_ceiling 为权威实现）

形态序：`full > qualified > downgraded > limitations_only > omit`。登记形态不许超过规则上限：

| 上游状态 × 强度档 | 上限 |
|---|---|
| untested × 任意 | limitations_only（只许进局限节或不写，三选一须落字） |
| undetermined × 任意 | downgraded |
| 任意 × insufficient | downgraded |
| partial × 其余 | qualified |
| supported × suggestive | qualified |
| supported × conclusive/strong | full |

措辞上限（wording_ceiling）同步由强度档导出：conclusive→demonstrative、strong→assertive、suggestive→hedged、insufficient→minimal；禁用词表全档生效——中文版含「证明了 / 显著 / 不显著 / 无影响」类，英文版含 proves / no effect / not significant 类。**正文措辞永远 ≤ 上游强度档**（约束 12）；上限在登记期落到每条主张，措辞门在审计期逐条比对（§11 门三）。

词表「冻结」口径（WRT-D02 实测定版）：冻结的是**版本与变更纪律**，不是经验内容本身——每条词条在 `schema.WORDING_EVIDENCE` 带证据指针与处置依据（无证据指针的条目校验报错）；词条内容可经实测修订，修订须附测量报告（首测：`06-write/WORDING-MEASUREMENT-v1.1.md`，复测脚本 `06-write/measure_wording.py`），被推翻的口径存档于报告、不静默删。首测已落地的口径修订：英文禁用词按**词界**匹配（子串口径下 proves/proved 的命中全为 improves/improved 误报，已证伪）；中文「显著」维持全形匹配（设想的「显著性」切分未被首测触发，结论存档于测量报告）。快修批新增口径（heldout 实测驱动，phase4-eval-report §8.1）：英文 significant 族禁用词（not significant / highly significant）匹配前做**变体归一**——首词与 significant 之间插入副词（statistically 等）或 at all 仍判命中；间隙成分是封闭清单，聚焦副词（only/just/also/simply/merely）不入间隙，防误杀 "not only significant" 类正向断言。

## §4 五段门规程卡（细则见分册，正向合同形态）

每段门的合同 = 前置条件清单 + 判定命令 + 过门产物；缺口逐项点名，补齐前不许 advance。审计只出判定、gates 持阻断权（约束 13）。

- **outlined 门**（`advance` 于 intake 段）：前置 = 承接快照四组哈希对齐 + 卡内一致性已过（§2.7）+ 主张全量登记 + 贡献回执已签认（§2.8）+ 模板记录已登记且未过期 + 声明骨架齐 + 验收合同已冻结（§5）。产物 = 状态落 outlined。
- **drafted 门**（`advance` 于 outlined 段）：前置 = 模板栏目序列逐栏有节且非空（title/references 由包级产物承担除外）+ validate 0 errors + 非 omit 主张全部以 [claim:] 锚定入稿、omit 主张零锚点 + 数字账行全部入稿且逐行带三元组溯源键（判定行 + 登记行 + 量名，`trace_ref` 量名后缀形态，见分册 audit-gates 门二）+ 已 delivered/backfilled 图表全部有正文引用点 + 未结 [directive:] 为零。产物 = 状态落 drafted + lock 收窄清单（实际引用子集与未引清单，只列不删）。提纲与逐节起草细则见 `references/section-protocols.md`。
- **audited 门**（`advance` 于 drafted 段）：前置 = 披露已生成（披露文本同为稿件内容，须一并受审）+ 审计四门全 pass 且产物哈希 = 当前稿件哈希（稿改即 STALE，须重跑）。四门 = 引用两段核对 / 数字三方对账 / 强度措辞门 / 落点映射复核，细则见 `references/audit-gates.md`。审计顺带产出**程式化核查报告**（`audit/tone_report.json`，advisory：只报不改、不阻断本门、与措辞门分开记账；触发标记与不改表以 `schema.TONE_RULES` / `schema.TONE_NOT_CHANGE` 为准，信息守恒——改写不许删限定词）。产物 = 状态落 audited。
- **submission_ready 门**（`advance` 于 audited 段）：前置 = 四门新鲜全过 + 落点底线层全 addressed + 声明无 absent + 披露齐备且新鲜 + 合同非 contested + 跨模型复核 approved 收据且哈希对齐当前稿。REVIEW_UNAVAILABLE 时停在 audited 并把 blocked 原因落字，与 Idea/Design/Analysis 同构——降级是落字停等，不是放行。披露/复核/W7 返修/W5 图表细则见 `references/disclosure-review-revision.md`。

## §5 验收合同规程（拍板⑥：硬门）

1. 动笔前（outlined 段）冻结验收合同：10–20 条断言（ARIS 口径），每条 = `assertion_id + text + checkable_via + status`。断言必须**只读终稿 + 上游产物即可判定**——写不出判定方式的断言不许入合同。
2. 冻结动作（`freeze-contract`）落内容哈希并同步登记头；冻结后改动断言文本 → validate 报 `contract.frozen_hash_drift`，须解冻重议，不许静默改。
3. 任一断言 `contested` → 合同状态落 contested：稿件包降级（`contract_contested=true` + `submission_blocked_reason` 落字），**后续不许达 submission_ready**，争议逐字留档待人类裁决。contested 不拦 outlined 本身——拦的是投稿就绪。

## §6 模板记录消费纪律（W4）

1. 消费对象是**核查记录**不是模板文件：记录按草案 §四 A–I 九组（46 字段）组织，`register-template` 逐组校验完整性后快照入包，登记头存记录哈希——快照被改 validate 即报错。
2. **限额一律数值**：D 组限额字段在场者必须为数值，且至少一项在场（散文式限额不许入记录）。
3. **AI 政策组**（G 组）：`disclosure_positions` 为**多值**（Science 双落点、PLOS 可落图注）；要求披露的刊应登记规定声明标题（`disclosure_title`）与措辞模板（`disclosure_wording_template`，Elsevier/MDPI 型）；`output_validity_evaluation` 单列子项（PLOS 独有）。期刊层与出版商层冲突时以期刊层为准并在 `publisher_conflict.resolution_note` 留取舍（约束 9）。
4. **时效**：H 组 `verified_at` 距今超过复核周期（记录自带 `review_cycle_days`，缺省 180 天）→ 过期警告；过期记录拦 outlined 门，须按官方原文重新核查后重新登记。
5. **语言一致**：记录 A 组 `journal_language` 必须与稿件 `language` 一致，不一致拒绝登记（一篇稿一个语言）。
6. **库存诚实**：`bundled` 只许 `official / generic_scaffold` 两值，generic 不许冒充 official（K-Dense Currency Rule 口径）。

## §7 正文与登记纪律（校验器执行口径）

- **占位符隔离**（约束 3）：正文引用只许 `[@key]` 或 `[@lit:<条目ID>]`，key/条目 ID 必须在 lock 内；正文中出现占位符之外的 DOI 形态字符串 → error；疑似手写作者-年份串（et al.+年份、Name (Year)）→ warning 并要求改占位符。
- **主张/数字标记**：`[claim:C###]` 必须指向已登记主张；`[num:N###]` 必须指向数字账行，且账行必须有 `trace_ref`（无溯源数字不许进成稿，约束 5）。
- **text_hash 绑定**（约束 11）：主张规范文本按「去标记、空白折叠」SHA-256 绑定；改词即漂移，validate 报错，须重验证据贴合度后才许更新哈希。哈希只证明文本未变，不证明科学为真。
- **声明三态**（约束：缺失不许样板话顶替）：data_availability / ethics / conflict / funding 四项各登记 `present / absent / na`；`na` 必须落理由；`absent` 已登记但投稿前必须清零。
- **AI 使用留痕**（约束 10）：`use_log` 逐条记 tool / model / **model_version（缺失即拒，Science 须版本号口径）** / purpose / section / date。披露靠这份流程留痕按刊生成，**任何环节不设 AI 检测器分数条目**。
- **fail-closed**（约束 15）：一切校验失败 = error 拦截，不留「只警告」的可关口子；校验器的绿灯只表示「未发现自动可判的失败」，不表示内容为真（non-scoring 立场）。

## §9 CLI

```
light-write init <root> --title <题> --language en|zh
light-write intake <root> --conclusion-card <card.json> --literature <pool.jsonl>
light-write confirm-contribution <root> --by <用户> [--statement <签认文本>] [--drift-note <差异点名>]
light-write register-template <root> --record <record.json>
light-write freeze-contract <root>
light-write validate <root>     # 0 errors 才 exit 0
light-write advance <root>      # 五段门推进，门不过逐项点名 gaps
light-write status <root>
light-write audit <root> [--online-records <records.json>] [--relevance <rel.json>] [--support <assessments.yaml>]
light-write audit-status <root>
light-write tone <root>         # 程式化核查（WRT-D01，advisory 只报不改；audit 亦顺带生成）
light-write disclose <root> / disclose-status <root>
light-write reverify-claim <root> --claim <C###> [--by <谁>]
light-write review prepare|record|import|unavailable <root> ...
light-write revision add-comment|respond|check|bind <root> ...
light-write figures add|sync|caption|delivered|check|freeze <root> ...
light-write terms <root> / allocation <root>     # 补课 D 两账校验（分册 supplement-d §18.1/§18.2）
light-write checklist add-stats <root>          # 统计报告底稿条目（分册 supplement-d §18.6）
light-write export run <root> [--format docx,tex,pdf] [--template <模板库条目id> --library <模板库根> | --generic]
light-write export check <root>                 # 既有导出复核重跑 + STALE 检出
```

导出纪律（渲染链）：源稿是权威，导出只做机械变换（`[num:]` 剥离留呈现值、`[claim:]` 剥离、`[@lit:]` 按 lock 归一、独行 `[fig:]` 落位、摘要节提升为元数据），逐项留痕于 export_record；渲染后复核六项与审计门口径同源（数字账值在场 / 引用键集合一致 / 禁用词重扫 / 占位符零残留 / 节标题齐全 / 图件在场），任一失败点名报错。工具缺失（pandoc / LaTeX 引擎 / SVG 转换器）如实落 PANDOC_MISSING / ENGINE_MISSING / SVG_CONVERTER_MISSING，不许假渲染。模板实物按模板库登记的 redistribution 档位取用：prohibited（如 MDPI）永不入导出实物。

## §16 成稿自检清单（submission_ready 前逐项勾）

- [ ] validate 0 errors；五段状态与产物一致（无 STALE 标记）
- [ ] 审计四门全 pass 且产物哈希 = 当前稿件哈希；门一为在线核查（非 honest-unverified）
- [ ] 门一 relevance_pending 已逐条人工处置或经复核确认，无 REPLACE/REMOVE 未批项
- [ ] 披露已按刊生成到全部登记位置，disclosures 记录新鲜；output_validity 子项（如适用）作者已落字
- [ ] 落点映射底线层全 addressed；声明四项无 absent（或 na 已落理由）
- [ ] 验收合同非 contested；复核收据在场、家族异于执行者、哈希对齐当前稿
- [ ] 图表编号已冻结；figures check 全过；返修轮次（如有）revision check ok 且未 STALE
- [ ] references.bib 为 lock 重渲染原样（未手改）；未引条目清单已人工过目

## §10 合理化反制表（借口 → 反制，原料取自失败模式附录与演示复盘的真实形态）

| 借口 | 反制 |
|---|---|
| 「离线先标 PASS，在线记录回头补」 | 门一离线即 honest-unverified，整门不许 PASS（F1）；补记录后重跑 |
| 「查无此条，八成是编造，先标了再说」 | 定罪须双路阴性证据；单路只许落未决拦门（F2） |
| 「年份差一届而已，按 error 拦下来更保险」 | 容差层是口径不是松紧带：±1 只 warning，私自升格即误杀（F3） |
| 「DOI 我记得，顺手写进正文省一步」 | 标识符只许 lock 回填与在线反查；凭记忆写 DOI 即违规（F4） |
| 「润色时顺手把数字改整齐了，账回头再对」 | 呈现串、账、溯源三方逐串比对，改数必同步账（F5） |
| 「结论卡数字肯定没错，不用验卡内」 | 卡内自洽由 intake 机械验（计数/指针/同指针两值），不靠信任（WRT-D05） |
| 「贡献陈述我帮用户润色得更好了，直接签」 | 签认是用户的动作；偏离草案必须点名差异，不许静默改写（WRT-D04） |
| 「AI 味太重，我把限定词删掉就自然了」 | 信息守恒：程式化核查只报不改，改写不许删限定词（WRT-D01） |
| 「同族模型审过了，收据先落上」 | 同族/同人自审拒落收据；无异家族复核者就落 REVIEW_UNAVAILABLE（F10） |
| 「编号冻结太麻烦，插一个号大家看得懂」 | 冻结后只许追加编号或全量重编并落日志（F15） |
