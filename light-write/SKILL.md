# Light-Write SKILL（v1.0）

> 定位：把 Analysis 的结论包变成可投稿的稿件包。核心原则——**登记文件是权威源，正文只许引用登记过的东西**：主张、数字、引用、图表、声明全部先登记后使用，成稿门逐项对账。
> 设计依据：`06-write/REDESIGN-DRAFT.md`（含拍板 6 项）、`06-write/LEARNING.md`（16 条硬约束，文末附对应表）。v1.0 范围：数据模型、承接与主张登记、模板记录消费校验、验收合同冻结、五段状态机门（intake→outlined→drafted→audited→submission_ready）、审计四门、按刊披露生成、跨模型复核门、W7 返修子包、W5 图表回填三方对账与编号冻结。端到端演示见 `examples/demo-fullrun/`（合成链，终点 audited + REVIEW_UNAVAILABLE 拦停），Phase 1 承接骨架演示见 `examples/demo-synthetic/`。
> 语言口径（拍板①修正版）：**语言按目标期刊定，一篇稿一个语言**。`manuscript.yaml` 的 `language`（en/zh）必填，跟随模板核查记录的期刊语言；逐节规程与措辞词表双语各备一份、结构同构；内部说明文件（工作注记、对账记录）语言不限。模板库范围含中文期刊模板。

---

## §1 稿件包文件群

| 文件 | 角色 |
|---|---|
| `manuscript.yaml` | 登记头（权威）：language、承接快照、目标期刊、作者与声明三态、AI 使用留痕 use_log、节登记表、合同状态指针 |
| `claims_register.yaml` | 主张登记：逐条主张 ← Analysis 主张 id + 强度档 + writable_form + wording_ceiling + text_hash |
| `numbers_ledger.yaml` | 数字溯源账：逐数字 ↔ Analysis 溯源表条目指针（起草期填充） |
| `references.lock.json` | 引用快照：verified 集快照子集（key、条目 ID、撤稿四态、entry_hash） |
| `references.bib` | **生成物，禁手改**：由 lock 回填渲染，文件头带 GENERATED 标记与条目集哈希 |
| `figures_manifest.yaml` | 图表清单：占位/交付/回填三态 + 编号冻结标记（与 Light-Figure 协同） |
| `submission_checklist.yaml` | 投稿检查落点映射（提纲期填充、投稿前门四复核） |
| `acceptance_contract.yaml` | 验收合同：动笔前断言清单，冻结后哈希锁定 |
| `template_record.json` | 目标刊核查记录快照（九组字段，register-template 落） |
| `sections/*.md` | 逐节稿：行内标记 `[claim:C###]`、`[num:N###]`，引用只许占位符 `[@key]` |
| `audit/` | 审计四门产物（audit_report.json + 逐门 MD + 总判定，绑稿件哈希） |
| `revision/` | W7 返修子包（comments.yaml / responses.yaml / response_letter.md） |
| `review_packet.md` | 跨模型复核包（review prepare 生成，自包含） |

## §2 承接规程（W0，intake）

1. **只承结构化产物**：输入 = Analysis 的 `conclusion_card.json` + Literature 的 verified 条目导出（候选池 JSONL 或条目列表）。承接时落四组快照哈希：结论卡文件哈希、卡内主张集哈希、数字溯源表哈希、verified 集哈希。任一上游文件事后变动 → validate 报承接失效，**须重新 intake，不许静默沿用旧快照**。
2. **上游状态如实落字**：结论卡 status 与 review 状态（含 `REVIEW_UNAVAILABLE`）原样进快照与 `upstream_flags`。非 delivered（如 graded/blocked）时包可建，但主张按降级口径登记，并在登记头显著标注。
3. **verified 过滤是硬规则**：只有 `identity_status=verified` 的条目入锁；未核实条目永不进锁（成稿层「未核实文献一律不用」）。去重按 Literature 条目 ID 归一，不按键字符串（防同一文献多键重复，Manubot 陷阱）。
4. **撤稿四态映射**：Literature 的撤稿状态映射为四态 `retracted / no_doi / unknown / clean`——无证据绝不落 clean（refchecker R11 口径）。`retracted` 条目虽入锁留痕，但被正文引用即报错；`unknown` 条目被引用须先复核并在 `retraction_note` 落字。
5. **主张登记初建**：逐条上游主张建行——`writable_form` 由规则表（§3）导出上限并落字，不许逐条临场决定；`wording_ceiling` 按**稿件语言**取对应词表导出。上游未给规范文本的主张，`claim_text/text_hash` 留空并落 gap 警告，**不许临场编造文本**（承 Analysis SESOI 教训的通则化）。
6. **新引用需求只走回流**：写作中发现需要新文献 → 在登记头 `reflux[]` 生成「送 Literature 核实」条目，不许现查直入、不许凭记忆写书目信息（约束 3）。

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

## §4 提纲规程（W1，outlined 门）

1. **提纲只从已登记证据长**：每节在 `manuscript.yaml` 的 sections 登记中写明 `goal`（功能目标）、`required_info`（必备信息元）、`claim_ids`（本节承接的主张集）。无支撑的内容进 unresolved 清单，不进提纲、不进正文。
2. **逐节规程卡的写法**（约束 6）：只写**功能目标 + 必备信息元 + 禁令**，不给模板句、不把结构定义（CARS move/step 等）写进生成提示——结构知识的位置是事后核对表。写功能目标时回答三个问题：本节要确立什么？读者读完应能做什么判断？本节特有的、只有本研究才有的信息是什么（对象、数字、边界条件）？
3. **双语同构**：en/zh 稿件的逐节功能目标结构同构（同为「目标 + 必备信息 + 禁令」三件），差异只在措辞词表与目标刊栏目序列；内部说明文件语言不限。
4. **栏目序列从模板记录取**：节的划分与排序以模板记录 C 组 `section_sequence` 为准，不写死 IMRaD 通用序。
5. **报告规范前置**（约束 7）：与本节相关的报告规范条目在提纲期就拆入该节的必备信息元，写作当下逐项落位；投稿前检查（§11 门四）只做落点映射复核，不是首次对照规范。
6. **outlined 门**（advance 执行）：快照齐全且哈希对齐 + 主张全量登记 + 目标刊记录已登记且未过期 + 声明骨架齐 + **验收合同已冻结**（§5）。缺口逐项点名，补齐前不许 advance。

## §5 验收合同规程（拍板⑥：硬门）

1. 动笔前（outlined 段）冻结验收合同：10–20 条断言（ARIS 口径），每条 = `assertion_id + text + checkable_via + status`。断言必须**只读终稿 + 上游产物即可判定**——写不出判定方式的断言不许入合同。
2. 冻结动作（`freeze-contract`）落内容哈希并同步登记头；冻结后改动断言文本 → validate 报 `contract.frozen_hash_drift`，须解冻重议，不许静默改。
3. 任一断言 `contested` → 合同状态落 contested：稿件包降级（`contract_contested=true` + `submission_blocked_reason` 落字），**后续不许达 submission_ready**，争议逐字留档待人类裁决。contested 不拦 outlined 本身——拦的是投稿就绪。

## §6 模板记录消费纪律（W4）

1. 消费对象是**核查记录**不是模板文件：记录按草案 §四 A–I 九组（约 37 字段）组织，`register-template` 逐组校验完整性后快照入包，登记头存记录哈希——快照被改 validate 即报错。
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

## §8 引用核查口径（两段核对门的命名与容差，两门消费见 §11）

- 两套幻觉口径分名，不得混用阈值（纠错 11(a)）：
  - `field_level_hallucination_screen`（Chelli）：题名/第一作者/年份任二错 → 字段级筛阳性；
  - `identity_level_fabrication`（refchecker LIKELY）：作品不存在或作者名单实质不符（不含年份/venue 漂移），落字须第二路阴性证据（约束 1）。
- 容差与定级表在 `schema.FIELD_TOLERANCES`：年份 ±1 只 warning、venue 变体 warning、DOI 可解析降级/不可解析才 error、题名容差以身份已确认为前提——零容差执行会与 no-false-positive（约束 14）冲突。
- 语境核对（约束 4）处置词表 KEEP/FIX/REPLACE/REMOVE（REPLACE/REMOVE 永须人类批准）；与三元组蕴含三值（entailment/neutral/contradiction + abstain）是不同粒度，不可混用（纠错 11(d)）。

## §9 CLI

```
light-write init <root> --title <题> --language en|zh
light-write intake <root> --conclusion-card <card.json> --literature <pool.jsonl>
light-write register-template <root> --record <record.json>
light-write freeze-contract <root>
light-write validate <root>     # 0 errors 才 exit 0
light-write advance <root>      # 五段门推进，门不过逐项点名 gaps
light-write status <root>
light-write audit <root> [--online-records <records.json>] [--relevance <rel.json>] [--support <assessments.yaml>]
light-write audit-status <root>
light-write disclose <root> / disclose-status <root>
light-write reverify-claim <root> --claim <C###> [--by <谁>]
light-write review prepare|record|import|unavailable <root> ...
light-write revision add-comment|respond|check|bind <root> ...
light-write figures add|sync|caption|delivered|check|freeze <root> ...
light-write terms <root> / allocation <root>     # 补课 D 两账校验（§18.1/§18.2）
light-write checklist add-stats <root>          # 统计报告底稿条目（§18.6）
```

## §10 逐节起草规程与 drafted 段门（W1/W2）

1. **逐节规程卡**（每节动笔前先答，吸收 Master-cai 写前问题形态）：本节功能目标是什么？必备信息元逐项列齐了吗（提纲期已拆入的报告规范条目在内）？本节承接的主张集与数字集是哪些？本节禁令是什么（不给模板句、不写结构定义进正文、不引入未登记主张/数字/文献）？四问答不出 → 不动笔，先回提纲补登记。
2. **行内标记纪律**：主张句尾挂 `[claim:C###]`；每个数字以 `[num:N###] <呈现值>` 形态出现（标记后紧跟呈现串，门二逐串比对的锚）；引用只许 `[@key]` / `[@lit:<条目ID>]`；图表以 `[fig:F###]` 标记占位与引用。标记之外的书目信息、未登记数字串一律不许出现在正文（validate + 门二双查）。
3. **数字先登记后入稿**：新数字先在 numbers_ledger 登记（value_as_printed + trace_ref 指向 Analysis 溯源表行 + 舍入口径），再写进正文；呈现精度只许标准舍入（半上舍入到显示位），不许改数凑呈现。
4. **措辞当场对表**：写主张句时对照该主张 wording_ceiling 的 allowed_terms 选词；禁用词全档生效。写完通读本节，凡强于本档的词当场降格——不要等门三来抓（门三是兜底，不是写作方式）。
5. **drafted 段门**（advance 执行）：模板栏目序列逐栏有节且非空（title/references 由包级产物承担除外）；validate 0 errors；非 omit 主张全部以 [claim:] 锚定入稿、omit 主张零锚点；数字账行全部入稿；已 delivered/backfilled 图表全部有正文引用点。过门时落 lock 收窄清单（`manuscript.lock_check`：实际引用子集 + 未被引条目清单——**只列不删**，未引条目保留待后续引用，bib 仍按全 lock 渲染）。
6. **披露在此段生成**：disclose 在 drafted 之后、audit 之前跑（披露文本同为稿件内容，须一并受审、一并绑哈希）。

## §11 审计四门规程（W3/W6，audited 段）

`audit` 逐门出报告（`audit/gate-*.md` + `audit_report.json` + `AUDIT_SUMMARY.md`），产物绑稿件哈希；**稿改即 STALE**，validate 与段门都检出，须重跑。审计只出判定，阻断权在 gates（审计与把门分离）。

1. **门一 引用两段核对**：范围 = 正文实际被引条目。第一段身份核：在线权威记录（经 `--online-records` 注入，形态为 {entry_id: 权威记录}）查无此条 → 只有第一路+第二路**双阴性证据**齐备才许落 `identity_level_fabrication`，缺第二路落未决拦门（不许单路定罪）。第二段字段核：执行 `schema.FIELD_TOLERANCES` 容差层——年份 ±1 只 warning、venue 变体只 warning、DOI 不一致时能解析降 warning/不能解析才 error、题名容差以身份已确认前提；题名/一作/年份任二错 → `field_level_hallucination_screen` 阳性整门 fail（两口径分名，不混用阈值）。**离线或记录未覆盖全部被引条目 → 整门 honest-unverified，不许 PASS、不许声称查过**。相关性轴：判定以蕴含四值（entailment/neutral/contradiction/abstain）登记，存疑只进 `relevance_pending` 待人工/复核，**不自动定罪**；已登记处置中 REPLACE/REMOVE 无人类批准拦门、FIX 无落字说明拦门。
2. **门二 数字对账**：正文每个 `[num:]` 呈现串三方逐串比对——呈现串 ↔ 账内 value_as_printed ↔ 溯源表数值按呈现小数位半上舍入。正文出现任何未登记数字串（披露生成块、列表序号除外）逐个点名 fail。溯源表不可得或承接哈希漂移 → 门 fail 并写明未核查（honest-unverified 的数字版）。
3. **门三 强度措辞门**：逐 `[claim:]` 锚点取其句子，按**稿件语言**词表比对该主张 wording_ceiling：全档禁用词出现 → 拒；术语的最低可用档高于主张强度档 → 拒；两种都给出降格建议（本档 allowed_terms）。主张 text_hash 漂移 → 先执行重验贴合度规程并 `reverify-claim` 落字，未重验不许过门（哈希只证明文本未变，贴合度靠人/规程重验）。
4. **门四 落点映射复核**：submission_checklist 全条目机械复核——status 合法、落点存在（section 落点：节文件在场且锚点字符串实位存在；declarations 落点：对应声明三态非 absent；file 落点：文件存在）。报告规范条目**只复核落点**，不做声明式自查（本地检查过 ≠ 声称遵循规范）。
5. 四门全 pass 才许 advance 到 audited；任一门 fail/unverified → 停在 drafted，逐项点名。

## §12 按刊披露规程（W4/W6）

1. `disclose` 以 use_log × 模板记录 G 组 `ai_policy` 生成披露：规定措辞模板在场时按模板回填占位符（{tool}/{model}/{version}/{purpose}/{section}/{date} 从 use_log 聚合），占位符无从回填 → 点名拦停；无模板时以留痕逐项渲染（数据呈现）。规定声明标题在场时作小标题。
2. **缺字段不许编造**：政策缺标题与模板两者 → 拦停点名，须先按期刊官方原文补全模板记录；use_log 为空 → 拦停（无留痕不编披露）；披露位置在稿件节登记中无对应节 → 点名。
3. `output_validity_evaluation` 子项在场（PLOS 口径）→ 须作者在 `manuscript.output_validity_note` 落字，工具只检查在场不代写，披露文本附该说明。
4. 披露落到 `disclosure_positions` 的**每个**位置（节内锚点块 `<!-- light-write:disclosure:<position> -->`，重跑替换不叠加）；生成记录落 `manuscript.disclosures[]`（含 policy/use_log 双哈希），政策或留痕变动 → STALE，投稿就绪门检出须重跑。
5. 披露靠留痕生成，全程不设 AI 检测器分数（约束 10）；该刊不要求披露时 disclose 返回说明即止，不生成文本。

## §13 复核门与 submission_ready（W6）

1. `review prepare` 生成自包含复核包 `review_packet.md`：成稿口径宪法 + 审计总判定 + 主张摘要 + **边界主张**全字段（正文在场且强度档 ≤ suggestive，或 writable_form 被降格者）+ 门一相关性待核清单 + 回填 JSON 形态。复核只判边界情形的落字属实性，不重开冻结口径。
2. `review record` 落收据 `RV-<sha256[:10]>`：复核者身份与家族必填；与执行者（`manuscript.executor`）同族拒、同一人拒；带异议（非 agree/agree_with_notes）不落收据，须先改稿/改登记后重审。`review import --from-json` 回填外部判定：schema 外字段拒、边界主张须逐条回填、任一 disagree 拒收。`review unavailable --reason` 显式落 REVIEW_UNAVAILABLE。
3. **submission_ready 门** = 审计四门新鲜全过 + 落点**底线层**全 addressed + 声明无 absent + 披露齐备且新鲜 + 合同非 contested + 复核 approved 收据且其稿件哈希与当前稿一致。REVIEW_UNAVAILABLE 时 advance 停在 audited 并把 blocked 原因落字（`submission_blocked_reason`），与 Idea/Design/Analysis 同构——降级是落字停等，不是放行。
4. 置真后稿件任何内容变动 → 审计/复核/披露连环 STALE，validate 报错；要改稿先回退状态重走对应段。

## §14 W7 返修规程（revision 子包）

1. **意见登记**：`revision add-comment` 逐条登记审稿意见**原文**（不许转述替代）、来源审稿人、分类（major/minor/editorial）、关联主张/节、轮次。意见到了先全登记再逐条处置，不许边回边漏。
2. **逐条回复**：`revision respond` 每条意见恰一回复——决策 accept/partial/reject + 理由必填（reject 也要说清依据）；accept/partial 必须登记改动锚点 change_anchors（{file, marker}），正文改动处落 `[rev:<comment_id>]` 标记。
3. **双向对账**（`revision check`）：正向——意见全覆盖、回复锚点实位存在；反向——正文每个 `[rev:]` 标记都被对应回复锚点回指，无无主改动。对账不过不许 bind。
4. **回复信绑定**（`revision bind`）：对账全过后渲染 `revision/response_letter.md` 并绑当前稿件哈希；此后稿改而信未更新 → check 报 STALE，须更新回复后重绑。resubmit 前必查：`revision check` ok 且 stale=False。

## §15 W5 图表回填对账与编号冻结

1. **登记与回填**：图表先 `figures add` 登记（F###/T###、kind）；正文以 `[fig:F###]` 标记占位/引用；`figures sync` 从正文回填 intext_refs 账（唯一回填口，check 只判不改）；Figure 交付后 `figures delivered` 记 source_ref + 文件哈希，图注以 `figures caption` 登记（落 caption_text_hash），回填完成标 `--backfill`。
2. **三方对账**（`figures check`）：清单行 ↔ 正文标记实位 ↔ 图注文本——intext_refs 账实一致；backfilled 行图注在场、哈希对齐、图注原文出现在放置节文件中；display_number 同 kind 内不重复。
3. **编号冻结**：时点在 audited 段前（投稿就绪前编号不再动），且**必须排在终审审计之前**——冻结改动图表清单的 `numbering_freeze` 字段（在稿件哈希覆盖范围内），冻结后先前的审计产物即 STALE 须重跑（demo-fullrun 实测教训）。`figures freeze` 按正文首次出现次序（节登记序 × 行号）分 kind 派号并落冻结日志。冻结后新增图表**只许追加编号**（add 自动派尾号 + 落 `append_after_freeze` 日志）或**全量重编**（`freeze --renumber`，落 `renumber_all` 日志）——不许静默插队改号。

## §16 成稿自检清单（submission_ready 前逐项勾）

- [ ] validate 0 errors；五段状态与产物一致（无 STALE 标记）
- [ ] 审计四门全 pass 且产物哈希 = 当前稿件哈希；门一为在线核查（非 honest-unverified）
- [ ] 门一 relevance_pending 已逐条人工处置或经复核确认，无 REPLACE/REMOVE 未批项
- [ ] 披露已按刊生成到全部登记位置，disclosures 记录新鲜；output_validity 子项（如适用）作者已落字
- [ ] 落点映射底线层全 addressed；声明四项无 absent（或 na 已落理由）
- [ ] 验收合同非 contested；复核收据在场、家族异于执行者、哈希对齐当前稿
- [ ] 图表编号已冻结；figures check 全过；返修轮次（如有）revision check ok 且未 STALE
- [ ] references.bib 为 lock 重渲染原样（未手改）；未引条目清单已人工过目

## §17 失败模式附录

| 编号 | 失败形态 | 检出点 | 处置 |
|---|---|---|---|
| F1 | 离线自称已核引用 | 门一状态 unverified 冒充 pass | 整门不许 PASS；注入在线记录重跑 |
| F2 | 单路查无此条即定罪编造 | 门一 identity_unresolved | 补第二路阴性证据再落字 |
| F3 | 零容差误杀（年份 ±1、venue 变体） | 门一 warning 被当 error | 按 FIELD_TOLERANCES 定级，不许私自升格 |
| F4 | DOI 凭记忆写进正文/账本 | validate 裸 DOI 检出 + 门一 doi 核 | 标识符只许 lock 回填，在线反查修正 |
| F5 | 润色改数字串、账未同步 | 门二 printed_vs_ledger/trace | 回改呈现串或更新账（溯源值不许动） |
| F6 | 正文夹带未登记数字 | 门二 unregistered_in_text 点名 | 登记入账（须溯源）或删 |
| F7 | 措辞强于强度档（如 suggestive 用 demonstrates/证实） | 门三 exceeds_ceiling + 降格建议 | 按建议降格；不许升档绕行 |
| F8 | 主张改词后哈希漂移未重验 | 门三 hash_drift_unreverified | 重验贴合度后 reverify-claim 落字 |
| F9 | 披露缺字段临场编期刊口径 | disclose 点名拦停 | 补模板记录官方原文 / 补 use_log |
| F10 | 同族自审、同人自赦 | review record/import 拒 | 换异家族复核者；无则落 UNAVAILABLE |
| F11 | 带异议收据放行 | record/import 拒收 disagree | 先改稿/改登记，重新备包复核 |
| F12 | 稿改后沿用旧审计/旧收据/旧披露 | validate audit.stale + 段门 STALE 检出 | 重跑 audit / disclose / review |
| F13 | 回复信与稿脱节（稿改信未更） | revision check letter_stale | 更新回复后重新 bind |
| F14 | 声称改动无实位 / 无主改动 | revision 双向对账 | 补 [rev:] 标记与锚点，或撤销声称 |
| F15 | 编号冻结后静默插队改号 | figures check 编号不符 | 追加编号或全量重编并落日志 |
| F16 | contested 合同稿件强行置真 | ready 门点名拦停 | 争议由人类裁决并重议合同后再走门 |

---

## §18 补课 D 采纳规程（nature-skills 生态簇，deep-read-D-supplement）

补课 18 条（D-W01–D-W18）逐条处置见 `06-write/SUPPLEMENT-D-DISPOSITION.md`；本节只落已采纳的
规程与机制，未采纳项（D-W17 组织形态重构留 v1.1 评估；D-W18 五项：
Zotero 同步、CNS 白名单过滤、逐页生图翻译、行为宪法式写法、词表式去
AI 味）不进本 skill，理由在报告中逐条交代。

### 18.1 正文分配纪律（D-W01，`body_allocation.yaml` + `allocation` 命令）

现有约束管「能不能写、写多强」；本纪律管「写在哪、占多少、重复几处」：
结果先按功能八分类（core_discovery / necessary_support / qualification /
robustness / heterogeneity / provenance_detail / alternative_inference /
edge_case）再定目的地（正文/图注/Methods/SI），建最短充分证据链；每处
主张出现入位置图（introduce/demonstrate/interpret/synthesize/shorten/
delete）；结论改变型证据不许埋 SI（校验硬拦）；每次增补触发全段删除
检查（删除日志 + 字数增量留档）；返修时回复信答全、正文改动取最短
（与 W7 对齐）。`enforced=true` 时位置图未覆盖的出现处拦 audited→ready。

### 18.2 术语账（D-W02，`terminology.yaml` + `terms` 命令）

起草前建账（canonical / 首现全称 / 已见变体 / 裁决），W0 承接时从上游
材料首建；锁定后全稿强制：变体入正文 = 校验 error（只报不改）；改名 =
全稿替换 + 账本更新；不许自创术语，缺定义标旗问作者。

### 18.3 一致性清扫（D-W03，数字门子项）

数字门附带机械清扫：同量异精度、同量异单位、SD/Std 变体只报警告、
逐条读语境裁决，永不自动改（与约束 14 相容）。

### 18.4 AI 使用风险分级（D-W04，use_log.risk_tier）

逐条留痕加分级：assistive（留痕即可）；evaluative_interpretive（解释
结果/回复框架/统计解释——须 human_verified 强核验落字 + 按刊披露）；
prohibited（代写核心论证、未核查引用/数据入稿、未发表稿与评审材料上传
公共模型、AI 图像造假——流程直接禁，披露不能洗，校验硬拦）。

### 18.5 引用门补强（D-W05/D-W06/D-W07/D-W12）

- 容差矩阵校准：DOI 可解析性是最便宜的第一步；页码差 ≤4 warning /
  ≥5 Critical；文章号形近误判（T/7、l/1、O/0）Critical；Early Access
  漂移以权威现值为准记 warning；作者漏人 Critical（经作者人数核）。
- 核查状态四级：verified / check_suggested / needs_fix / unverifiable，
  逐条落审计报告；**Unverifiable 是合法终态**（内部报告、老旧学位论文
  查不到 ≠ 编造），与「判编造须第二路阴性证据」互证。
- 作者完整性门：lock 作者名单必须取结构化源完整有序名单，禁从 et al.
  显示串推导；authors_complete=false 停生成，紧急覆盖须 author_override
  落字并把警告写进记录。
- 支撑五级量表 + 双角色对抗协议：引用语境核查的组织方式——proposer
  给源 + **逐字支撑句**，skeptic 在新上下文默认拒绝、无逐字句不确认、
  不确定向拒绝侧裁决；判定分五级（strong / partial / background /
  contradictory-limiting / metadata-only，metadata-only 不许作支撑），
  与处置词表 KEEP/FIX/REPLACE/REMOVE 分层并用；失败原因用五类分类学
  （does_not_support_claim / metadata_wrong / wrong_site_or_population /
  not_primary_but_required / paywalled_unverifiable）。判定落
  `audit/support_assessments.yaml`（或 audit --support 注入），机械面由
  引用门校验。校准注脚：实测一篇 Review 中 139 个提议源被独立 skeptic
  拒 55、零编造——存在性核查会全数放行这 139 条，故语境核查不可省。

### 18.6 声明与清单补强（D-W08/D-W09/D-W14）

- 数据可用性：先盘点再起草——每数据集分类七路访问路径之一，声明按
  dataset→location 显式映射写（manuscript.datasets）；"available upon
  request" 无具体限制落字 = 弱声明待改（校验警告）。
- 清单条目带 stage（initial/revision/production，规则不许跨阶段套用）
  与 applicability 四态；status 输出 readiness 三态（ready /
  ready_with_author_checks / blocked）。
- 统计报告底稿：`checklist add-stats` 加入两条底线条目（独立单元 n
  定义与分层、主张→分析映射字段集）；缺项一律 AUTHOR_INPUT_NEEDED，
  不许编造样本量/检验/校正（与 Analysis 的 n 纪律同构互证）。

### 18.7 编辑组织（D-W10/D-W11/D-W13/D-W15/D-W16）

- 分层编辑顺序：结构 → 章节 prose → 段落逻辑 → **姿态** → 句子，只修
  有问题的层；姿态层查五种声音（audit / defensive / self-critical /
  developer / commitment，覆盖正文、SI、图注与声明）。两条停机规则：
  主张层级未稳不做姿态编辑；Review 稿先 drift audit 后润色。去 AI 味
  只采 information test（删无信息内容），不采词表替换（D-W18⑤）。
- 承重陈述保护（manuscript.protected_statements）：重复单元与 n、无 P
  值声明、盲法与排除、访问路径、决策背后的计数、估计量假设、阴性
  结果、Methods scope 条件、目标刊必查声明——登记后只许移位、只述
  一次、改写为正向 scope；校验逐条核对实存，删/移即报错。
- 草稿标记纪律：[todo-fact:] 只许事实/来源问题（开放计数 = 证据就绪
  度，status 输出）、[note-edit:] 编辑意见、[directive:] 必改指令
  （未结拦 drafted 门)、[superseded:] 冻结替换留痕；未注册标记 = 纯度
  违规；开放项按解决路径分诊；字数口径排除草稿装置。
- 经验值证据规则（D-W15）：逐节规程里任何数值型经验区间（摘要句数、
  引言段数、数字密度等）须附语料证据文件与采样框（库/年份/期刊/
  检索式/纳入排除 + 脚本复跑），不许凭印象写数；证据带「描述 ≠ 因果」
  边界。
- 蒸馏路线（D-W16）：范文/句式证据层采用「固定抽取 schema + verbatim
  ≤25 词 + grep 可回查 + 语料附录逐篇登记」的生产方法（转交模板库
  姊妹仓执行）；规律分三档（常见模式/子门类倾向/强约定）标注置信；
  **句级模板与 language bank 只许诊断对照、不许进生成侧**（与约束 6
  Sadallah 实证一致）；SyntaxSmith 的提交前 checklist 与 5-pass 自审
  只作成稿前事后诊断参照。

---

## §19 附录：LEARNING 16 条硬约束对应表

每条约束在 v1.0 的落点（规程节 → 工具实现）。补课 D 18 条（D-W01–D-W18）的处置摘要：采纳 16 条（D-W01–D-W16）落 §18（规程 + 工具），D-W17 组织形态重构未采纳（留 v1.1 评估），D-W18 五项（Zotero 同步 / CNS 白名单过滤 / 逐页生图翻译 / 行为宪法式写法 / 词表式去 AI 味）已评估不采——**逐条全文见 §18 与 `06-write/SUPPLEMENT-D-DISPOSITION.md`**。

| # | 约束（一行） | 规程落点 | 工具实现 |
|---|---|---|---|
| 1 | 引用核对两段式：存在性判定 + 逐字段核对 | §8、§11 门一 | `audit._check_one_entry`：双路阴性才落 fabrication、单路落 unresolved；字段容差层逐项定级 |
| 2 | 标识符默认不可信，只许权威源反查回填 | §2.3、§7 | lock 只收 Literature verified 集；validate 裸 DOI/疑似手写引用检出；标识符不许手填进正文 |
| 3 | 起草期占位符隔离，参考文献表只许回填生成 | §2.6、§7 | validate 占位符外引用报错；`references.bib` 由 lock 渲染 + 条目集哈希，未手改校验 |
| 4 | 相关性是独立于真实性的第二道核查 | §8、§11 门一、§18.5 | 支撑五级量表 + 双角色对抗（support_assessments）；相关性轴缺失只落 relevance_pending 不定罪 |
| 5 | 正文数字只许来自溯源表；改数字串触发复核 | §7、§10.3、§11 门二 | numbers_ledger 逐行 trace_ref 必填；门二三方逐串比对 + 裸数字扫描 |
| 6 | 逐节规程只写功能目标 + 必备信息元 + 禁令 | §4.2、§10.1 | 节登记 schema（goal/required_info/claim_ids）；规程卡四问，无模板句字段 |
| 7 | 报告规范条目前置拆入逐节规程 | §4.5 | 提纲期条目拆入 required_info；门四只复核落点 |
| 8 | 投稿前检查 = 条目 → 稿件位置映射，逐条实位判定 | §11 门四 | checklist location 三形态（section 锚点逐字 / declarations 三态 / file 在场）机械复核 |
| 9 | 披露按目标刊记录逐刊生成，规程不写死政策 | §6.3、§12 | disclose 以模板记录 G 组 × use_log 生成；期刊层优先、冲突留 resolution_note |
| 10 | 合规靠留痕 + 披露，不靠检测分数 | §7、§12.5 | use_log 逐条留痕（model_version 缺失即拒）；全包无检测器分数字段 |
| 11 | 主张-证据行内标记 + 文本哈希绑定，改词即漂移 | §7、§11 门三 | [claim:]/[num:] 行内标记；text_hash 漂移未 reverify 拦门三与 validate |
| 12 | 措辞强度永远 ≤ 上游强度档 | §3、§10.4、§11 门三 | writable_form 规则表 + wording_ceiling 双语词表；门三逐句比对 + 降格建议 |
| 13 | 审计与把门分离；审计产物必达且绑哈希 | §11、§13 | audit 只出判定、gates 持阻断权；产物绑 manuscript_hash，稿改即 STALE；阴性/未核查落字不 silent-skip |
| 14 | 检查者三纪律：honest-unverified / no-false-positive / no-overreach | §8、§11 | 离线整门 unverified 不许 PASS；容差层防零容差误杀；门只报判定不改稿 |
| 15 | fail-on-errors 写死为开，无可关口子 | §7 | validate/audit/各 check 命令 error 即 exit 1；绿灯语义在 §7 明示证明边界 |
| 16 | 核对强度与模型版本/自评脱钩 | §11、§13 | 核对走确定性代码与注入记录；放行只认状态机门 + 异家族复核收据，自评永不作依据 |
