# light-review SKILL（v1.0 定版）

> 定位：投稿前内部评审包。Write 稿件包成稿（audited 之后、submission_ready 之前）运行，只做三件事——**法医式一致性核查**（四方对账 + GRIM 族）、**模拟审稿人组**逐席评审（可见性矩阵 / 报告冻结 / 共识门）、把发现装订成作者可执行的评审产物。Review **不改稿、不回注、不改任何已冻结报告**；修订回 Write 执行，复审走新 round。以「是否已收到真实审稿意见」为界：未收到归 Review，已收到（返修）归 Write 的 W7。
> 设计依据：`09-review/REDESIGN-DRAFT.md`（含拍板附录 R1–R6，全按推荐）、`09-review/LEARNING.md`（18 条硬约束 RV-01–RV-18）。
> v1.0 定版（2026-10-20）：Phase 1（包骨架与状态机、承接快照、法医层四边 + GRIM 三件、席位/可见性/冻结/共识 machinery、人工裁决位与 delivered 阻断纪律）+ Phase 2（领域门三层、校准门四件 + 验证台、meta 合成与决定建议降级、评审产物自审门、concern 回填清单导出，见 §5B–§5E）+ Phase 3 真实演示（承 Write/Analysis/Figure/Journal-Select 四个上游演示产物全程跑通至 delivered，隔离 degraded + 降档声明实测；变体注入数字被法医层咬出 confirmed error 并阻断，见 `examples/demo-fullrun/demo-report.md`）。

---

## §1 评审包文件群

| 文件 | 角色 |
|---|---|
| `review.yaml` | 登记头（权威）：承接快照（三包路径 + 哈希）、约束、隔离模式、冻结账、交付区、机械计数 |
| `seats.yaml` | 席位登记 + 逐席可见性矩阵（角色、模型家族、预设、知情范围、逐阶段可见工件类） |
| `consensus.yaml` | 共识与分歧账：concern 清点（stable ID）、raised_by、severity（代码计算）、consensus 标注、终态理由 |
| `forensic/reconciliation.jsonl` | 四方对账逐项结果 + 边级覆盖自报（summary 行） |
| `forensic/findings.jsonl` | 法医发现账（只增不改）：D-R02 分类、两层分类、双指针、raw；裁决以追加行留痕 |
| `forensic/compatibility.jsonl` | GRIM 族相容性结果（适用性元数据 + 算式证据） |
| `forensic/summaries.yaml` | GRIM 被检汇总量的登记（值/小数位/n/items/量表类型） |
| `reports/drafts/<seat>.md` | 逐席草稿（席间物理隔离，冻结前互不可见） |
| `reports/<seat>.md` | 逐席报告冻结件（内容哈希钉住，冻结后只许比较与引用） |
| `domain_gate.jsonl` | 领域门逐条判定（命中/未命中/不适用 + 证据指针）+ summary 覆盖自报行（Phase 2） |
| `calibration.yaml` | 校准登记：量表锚 / 封顶规则 / 不对称权重（Phase 2，改动即配置漂移） |
| `reports/bench_report.json` | 验证台判别力报表：按缺陷类检出率 / 误报率，绑评审配置哈希（Phase 2） |
| `reports/meta_review.md` | meta 合成：合成叙述 + 共识账 + 分歧账 + 优先修订序，只消费冻结报告（Phase 2） |
| `reports/decision.md` | 决定建议（bounded 非编辑判断）：仅校准门四件齐备时存在（Phase 2） |
| `reports/problem_list.md` | 降级产物：问题清单 + 风险分级（校准门不齐时与 decision.md 互斥，Phase 2） |
| `reports/selfcheck.json` | 评审产物自审门报表：五类命名测试 + 与冻结清单对账（Phase 2） |
| `handoff_to_write.md` / `.json` | concern 回填清单（字段白名单，只出清单不出补丁，Phase 2） |
| `REVIEW_DELIVERY.md` | 交付清单（deliver 渲染） |

## §2 承接规程（R0，intake）

1. **只承结构化产物**：输入 = Write 稿件包（manuscript.yaml + claims_register + numbers_ledger + references.lock + figures_manifest + sections/）+ Analysis 结论包（conclusions + verdicts + spec_results）+ Figure 图包（delivery.yaml，可缺但缺必须落字）。承接时逐文件取 SHA-256 并算包哈希冻结进登记头。
2. **缺项点名，不许静默默认**：强度档必填；图包/目标刊记录缺失落 figure_note / target.note，不许假装承接过。目标刊易变事实只存记录指针 + 哈希（RV-17，与 Journal-Select/Write 共用同一事实源，不另存第三份）。
3. **隔离登记**：`isolation_mode` 在此落字。`degraded` 必须带理由——做不到全规格隔离就明说（R1 硬纪律），交付时强制附降档声明（§6）。
4. **STALE 纪律**：上游任一文件事后变动 → 快照漂移，本轮评审标 STALE；法医开跑与每道状态门都先验快照，不许在旧快照上继续。

## §3 法医层（R2，forensic）

四方对账四边，逐边登记覆盖（每边 summary 行：应检 / 可检 / not_assessable / error / decision_error，校验器机械重算对账）：

| 边 | 对账物料 | 检查 |
|---|---|---|
| 主张↔证据 | claims_register ↔ conclusions / strength | 结论行存在否；grade、support、逐行判定是否被登记侧改写；writable_form 是否越过 writable_ceiling |
| 数字↔数字 | numbers_ledger ↔ 正文 `[num:N###]` 实印值 ↔ spec_results / number_provenance | 呈现值逐处一致；登记派生量复算——呈现值由其小数位导出真值区间（舍入区间法，RV-08），复算值落区间外即不一致，符号翻转再升第二层 |
| 数字↔图 | figures_manifest ↔ Figure delivery | 对应图存在否；同名文件哈希对应；图注小数数字是否已在 numbers_ledger 登记（Figure 审计管图内侧，Review 补引用侧） |
| 引用↔主张 | sections `[@key]` ↔ references.lock；claims evidence_refs ↔ 结论登记行；Write 审计归档件 | **只验指针存在性**，不重做 Write 的引用核对本体 |

两层分类（RV-08）：`inconsistency`（数值/指针不一致）是第一层门；`conclusion_flip`（结论翻转）只许出现在第一层已成立且改变结论强度/支持度/符号的发现上，校验器钉死不许越层。

发现分类沿 D-R02 六类（confirmed_error / aggregation_ambiguity / provenance_gap / suspected_duplication / unresolved_input / not_assessable），每条带 stable ID、claim/evidence 双指针、raw 原文片段。覆盖口径（RV-07）：一切「通过」只表述为「在已登记检查项与敏感性范围内未发现问题」。

## §4 GRIM 族（grim）

三件：均值粒度（mean×n×items 整数相容）、百分比粒度（计数相容）、合计相容性（分项和 vs 总计，容差 =(分项数+1)×半步长）。

- **适用性硬门**（RV-09）：被检量须在 `forensic/summaries.yaml` 登记全（值/小数位/n/items/量表类型）；量表非整数粒度（连续量）或元数据不齐 → `not_assessable`，不许猜测启动。
- **判败只作旗标**：判败进发现账时分类 confirmed_error 候选、`flag_only=true`、附算式证据，归因留人工裁决位（§6）。GRIMMER（mean/SD/n 三元组）押 v1.1。

## §5 席位、冻结与共识门（R1/R4，seat / panel / freeze / consensus）

1. **可见性即权限**（RV-01）：席位能读什么由 `seats.yaml` 矩阵决定，供料走 `read_for_seat` 接口按「包状态→阶段」放行。硬底线：panel 阶段任何席不许见 `other_reports` / `consensus`，自定义矩阵也不许绕过。席位预设（人格、知情范围）运行前登记、运行后可查（RV-02）；作者身份类信息默认不进席位，进了留痕。
2. **草稿隔离**：逐席草稿落 `reports/drafts/<seat>.md`，物理分开。
3. **报告冻结**（RV-12）：`freeze` 把草稿升为冻结件并以内容哈希钉住、冻结记录追加进登记头 `freezes` 账。冻结件已存在即拒绝再冻；冻结后文件被改，校验/过门报 STALE。冻结后修订走新 round，不许回改。
4. **共识门**（RV-05）：concern 的 `consensus` 只许在 ≥2 席互盲下独立同向时为真（落盘口强制，单席自称直接拒绝）；`severity` 由代码取各席独立提案的 MAX——佐证数（tally）只影响排序与抽查优先级，**永不抬升 severity**；手填 severity 与计算值不符即拒绝落盘。concern 关闭必须带理由（RV-11：不许静默丢弃）。

## §5B 领域门三层（R4，domain）

领域门是与法医层同类的**评审前确定性层**：只消费承接快照与目标刊事实，产出逐条判定，不依赖席位意见。

1. **通用轴地板（恒加载）**：`domain.UNIVERSAL_ITEMS` 五条（DG-U01–U05：主张证据指针、数字溯源、撤稿状态登记、图注、章节结构）。条目带条目卡元数据（稳定 ID / 轴 / 严重度 / 范围 / 执行层），判定 hit/miss/not_applicable + 证据指针逐条落 `domain_gate.jsonl`，末尾 summary 行做覆盖自报（校验器机械重算对账，与法医边同法，RV-07）。
2. **按刊事实层**：条目（DG-J01–J06）自目标刊九组核查记录的 D/C/G 组派生——与 Journal-Select 核查记录 / Write 模板记录**共用同一事实源**，承接时只存记录指针 + 哈希（§2），领域门按指针现读现判，**不复制第三份数据**（RV-17)。事实时效按记录 H 组的 `verified_at` + 复核周期（默认 180 天）判定：过期或不可解析 → `fact_status=unverified`，该层全部条目强制 not_applicable——**过期事实永不驱动判定**；校验器会重算时效，手改成 verified 也会被咬。
3. **蒸馏覆盖层（只落格式，v1 不预置学科内容）**：覆盖层文件（YAML）须含 overlay_id / 版本 / 来源四分标注（explicit_object / derived_object / historical_calibration / generic_quality）+ Explicit-or-Inferred + 置信度 / 双存指针（dual_store_pointer，保真形态另存的指针）/ 与核心冲突的优先序（`precedence.on_conflict`：overlay_wins | core_wins）/ 逐条条目卡。加载校验不全 → 拒绝加载。冲突解析由代码按优先序落字（被压方 effective=false + superseded_by 指向胜方），校验器重算解析结果，手改即报错。覆盖检查 v1 三种：keyword_present / keyword_absent / section_present。

**落点与理由（状态机不新增状态）**：领域门登记（`review.domain`）后，**reported 门**要求 `domain_gate.jsonl` 在册且含 summary 行。理由：领域门与法医层同为前置确定性层，其结论要进入席位评审的视野与报告冻结的内容域——报告一旦冻结，领域判定就不许再补跑或改动；放在 reported 门（冻结完成的那一段）校验，恰好钉住「先领域门、后冻结」的次序，又不新增状态。

## §5C 校准门四件与验证台（R3，calibration / bench）

决定建议是**条件给**（R3 拍板）：只有校准门四件齐备才许出 `decision.md`，四件逐项登记在 `calibration.yaml`，齐备性由代码评估（`assess_calibration`)：

1. **量表锚**：百分位锚成文（overall-10 模板：10=前 2%、8=前 10%、6=已录用中位、5=边界、3=后四分位、1=垫底）+ 反通胀口令成文登记（如「非卓越原创不许给 7 分以上」）。锚或口令缺一 → 不齐。
2. **封顶规则**：逐条登记（触发条件 / 封顶效果 / 出处），触发与档位走词表。模板三条：CAP-01 有未裁决 confirmed error → 不得优于 major_revision；CAP-02 按刊事实未核实 → 不得优于 minor_revision;CAP-03 问题全为文书级 → 不得劣于 minor_revision（防过度悲观）。
3. **不对称合成**：reject 向权重数值登记且必须**严格大于** accept 向（模板 1.5 / 1.0)，meta 合成按此计分（§5D)。
4. **验证台报表**：见下。

**验证台（bench)**：缺陷注入金标准集——五类已知缺陷（主张越界 / 证据缺失 / 数字不一致 / 引用缺口 / GRIM 不相容）各一例 + 四例干净对照，跑的是**生产检查器**（法医四边 + GRIM)，产 `reports/bench_report.json`：逐例结果、按缺陷类检出率、干净例误报率、全过标记。报表绑**评审配置哈希**（席位集 + seats_spec + 量表 + 封顶 + 权重，组件哈希）：配置任一变更（加席、改锚、改权重……）→ 哈希不符 → 报表判过期 → 校准门判不齐。无报表同理。

## §5D meta 合成、决定建议与自审门（meta / selfcheck）

1. **meta 合成**只消费冻结报告、共识账、法医账与领域门账，产 `reports/meta_review.md`（合成叙述 + 共识账 + 分歧账 + 法医与领域门并账 + 优先修订序）。合成叙述可由模型撰写（`meta --file`)，但**severity、共识与档位永远由代码计算**(RV-05/RV-14)。
2. **不对称合成计分**：每条共识 concern 按 severity 权重（minor 1 / major 2 / critical 4）× reject 权重计风险分，非共识 concern 按权重 1.0 计；未提出任何 concern 的席位按 accept 权重计支持分；净分映射档位（≤0 ready / ≤2 minor_revision / ≤6 major_revision / 其余 reject_risk)，再逐条过封顶规则钳制（触发留痕写进 decision.md)。
3. **降级纪律**：校准门缺任一件 → `decision_mode=degraded`，只产 `reports/problem_list.md`（问题清单 + 风险分级 + 缺件逐项点名），且**decision.md 不许存在**——校验器钉死：degraded 下发现 decision.md 直接报错；由 full 降回 degraded 时 `meta` 会删掉旧 decision.md 并登记 `decision_file_removed`。
4. **自审门（RV-13)**：`selfcheck` 对 meta/decision 产物跑五类命名可靠性测试，各有机械近似检查 + `model_judgment` 模型判定登记位（v1 恒 null，不许伪造）——vague_unsupported（合成叙述逐行须带库存 ID 锚或数字依据）、wrong_object（产物中的 ID 形 token 必须都在库存内）、praise_only（有 major/critical concern 未决时，无锚的表扬行判失败）、mere_restatement（叙述行与冻结报告行高度雷同且无锚 = 只是复述）、contradicts_frozen（decision 档位与登记不符、severity/consensus 行内标注与共识账不符、ready 却有未决硬伤）。另与冻结清单对账：报告**可少说**（叙述漏提只登记进 missing_from_meta，不判失败）、**不可矛盾**（矛盾判失败）。报表落 `reports/selfcheck.json` 并绑产物内容哈希（target_hash)：meta/decision 事后被改 → 自审过期。注：wrong_object 的库存含承接快照登记的上游对象 ID（结论登记行/图号）与 concern 双指针正式引用的对象——meta 原文渲染 concern 陈述时正当引用上游对象，不得误判凭空指认（v1.0 定版时据 Phase 3 演示实测补正，回归测试钉住；未登记且无指针引用的虚构 ID 仍判失败）。

## §5E concern 回填清单导出（R6，export）

`export` 产 `handoff_to_write.md` / `.json`：按 concern stable ID 逐条——severity（代码重算值，不信存量）、双指针锚（claim_pointer / evidence_pointer)、建议动作分类、来源席位、共识标记、关闭判据。动作分类由代码按指针形态判定：指向法医 conclusion_flip / 证据缺口类发现 → needs-new-evidence；双指针齐或仅主张指针 → fixable-in-text；无法医牵连的仅证据指针 → needs-new-evidence；双指针皆缺 → needs-author-decision；分类依据（action_basis）逐条留痕。**只出清单不出补丁**以结构校验实现：导出条目字段白名单（HANDOFF_ITEM_FIELDS）钉死，任何字符串字段超 500 字即判疑似正文偷渡报错；采纳与执行由 Write 侧决定，Review 不产稿件改写段落。

## §6 状态机与阻断纪律

`intake → forensic_checked → paneled → reported → adjudicated → delivered`，逐段过门、缺口逐项点名：

| 状态 | 门（要点） |
|---|---|
| forensic_checked | 承接已冻结且快照未漂移；法医三件齐；四边覆盖自报齐 |
| paneled | 席位已登记且逐席有草稿；隔离模式已登记 |
| reported | 逐席报告已冻结且哈希验合；共识账已生成；全包 validate 零 error；**已登记领域门时** `domain_gate.jsonl` 在册且含 summary 行（§5B 落点理由） |
| adjudicated | 全部 confirmed error 已裁决（逐条具名 + 理由）；**已登记 decision 时**：meta 产物与形态一致（full → decision.md 在册；degraded → problem_list 在册且 decision.md 不存在）+ 自审门已过且未过期（target_hash 验合，§5D） |
| delivered | 走 `deliver`：再验裁决清零 + 快照未漂移 + validate；degraded 时必须带降档声明；落 delivery 区 + `REVIEW_DELIVERY.md`（含领域门/决定形态/回填条数区段） |

Phase 2 各门均为**登记键触发**：未登记领域门/决定的包（一期流程）不被二期门拦——`phase2_pending` 随各件落地逐项销账，全销后交付清单明示「Phase 2 件已全部落地」。

**阻断纪律**（R2 硬度 a）：forensic 的 confirmed error（含 GRIM 旗标判败）未裁决时，adjudicated 与 delivered 都过不去。裁决走 `adjudicate`（--outcome confirmed|overruled --by 具名 --reason 理由），以追加行留痕、发现本体不改。findings 已有裁决留痕时法医层拒绝重跑（保护留痕，重跑开新 round）。

## §7 命令速查

```text
light-review init <pkg> [--title T] [--round N]
light-review intake <pkg> --manuscript <write_pkg> --analysis <analysis_pkg>
    [--figure <figure_pkg>] [--journal NAME] [--target-record FILE]
    --intensity light|standard|thorough [--isolation full|degraded]
    [--isolation-reason TEXT]
light-review forensic <pkg>
light-review grim <pkg> --register summaries.yaml
light-review seat <pkg> --id S1 --role methods --family claude [--persona TEXT] [--knows-authors]
light-review panel <pkg> --seat S1 --draft draft.md
light-review freeze <pkg>
light-review consensus <pkg> --file concerns.yaml
light-review domain <pkg> [--overlay overlay.yaml] [--today YYYY-MM-DD]
light-review calibration <pkg>     # 模板落盘（已存在不覆盖）+ 四件齐备性评估
light-review bench <pkg>           # 须先有 calibration.yaml
light-review meta <pkg> [--file narrative.md]
light-review selfcheck <pkg>       # 未过退出码 1
light-review export <pkg>          # handoff_to_write.md/.json
light-review adjudicate <pkg> --finding F001 --outcome overruled --by NAME --reason TEXT
light-review advance <pkg>        # delivered 除外
light-review deliver <pkg> [--degradation-statement TEXT]
light-review validate <pkg>
light-review status <pkg>
```

## §8 v1.0 定版状态

Phase 2 五件已全部落地（§5B–§5E)，`phase2_pending` 五项（domain_gate / calibration / meta_review / decision / handoff_to_write）随对应命令逐项销账，全销后交付清单明示「Phase 2 件已全部落地」；新包登记头仍带该清单，未跑的件在交付清单中如实列为未尽。

Phase 3 演示已完成（`examples/demo-fullrun/`，驱动脚本经 CLI 子进程真跑）：承接 Write 演示稿件包（audited 态）+ Analysis 演示结论包 + Figure 演示 delivery + Journal-Select 演示 check-record，全程 intake → forensic → domain → 席位三席 → freeze → consensus → calibration + bench → meta（full 形态 decision，档位 reject_risk）→ selfcheck → export（回填 6 条）→ **delivered**（隔离 degraded，交付带降档声明）。变体小节：注入正文数字与台账不符一处，法医层咬出 confirmed error 并阻断 adjudicated，人工裁决位解除后止步 adjudicated（不进交付）。演示中实测并修复一项产品缺陷（自审 wrong_object 库存范围，见 §5D 注与演示报告 §9），全量测试 125 项。

不在 v1.0（去向已登记）：

- **蒸馏覆盖层内容**：v1 只落格式与加载校验，不预置任何学科覆盖层；具体学科蒸馏待 Memory 阶段收编后按双存纪律投放。
- **GRIMMER**（mean/SD/n 三元组相容）：押 v1.1。
- **席位侧证据升格三查**（RV-04 后半）：未独立成门，v1 以法医侧检查 + concern 双指针准入顶着（见 §10）。

## §9 与 RV-01–RV-18 的对应（v1.0 落点）

| 约束 | 落点 |
|---|---|
| RV-01 可见性即权限 | seats.yaml 矩阵 + `read_for_seat` 放行 + panel 阶段互盲硬底线（panel.py / validate） |
| RV-02 预设登记与画像隔离 | seat 登记 persona/knows_authors；逐席 degraded_note 字段 |
| RV-03 确定性骨架 | 状态机门、共识 severity/tally、覆盖汇总全由代码计算（gates/panel/validate） |
| RV-04 证据准入 | 法医发现强制双指针 + raw；concern 准入强制双指针锚（席位侧升格三查未独立成门，见 §10） |
| RV-05 佐证不抬级与共识门 | panel.build_consensus 落盘口强制 + validate 重算钉死 |
| RV-06 法医确定性与四方对账 | checkers 四边 + grim 三件，模型不参与判定 |
| RV-07 覆盖自报与诚实降级 | 边级 summary 行 + 校验机械对账；交付清单措辞口径 |
| RV-08 两层分类与口径参数化 | 舍入区间法（grim.rounding_interval）；conclusion_flip 越层拦截（validate） |
| RV-09 相容性适用性硬门 | grim 元数据门 + 量表类型门，判败 flag_only |
| RV-10 金标准与条目卡 | 检查器 ID 体系（F-CE/F-NN/F-NF/F-CC/F-GRIM）；Phase 2 扩为验证台（bench.py 缺陷注入金标准集） |
| RV-11 永不静默丢弃 | concern 关闭带理由；裁决追加行；findings 只增不改 |
| RV-12 冻结纪律 | 快照哈希 + 冻结件哈希 + freezes 追加账 + STALE 检测 |
| RV-13 自审门 | selfcheck.py 五类命名测试 + 与冻结清单对账（可少说不可矛盾）；入 reported→adjudicated 门（§5D） |
| RV-14 严重度校准 | calibration.py 量表锚/封顶/不对称登记 + meta.py 代码计分与档位钳制（§5C/§5D） |
| RV-15 验证台与记账 | bench.py 判别力报表绑评审配置哈希，漂移即过期、校准门判不齐（§5C） |
| RV-16/RV-17 领域门与事实容器 | domain.py 三层：通用轴地板 + 按刊事实层（同一事实源指针现读、时效 UNVERIFIED 纪律、校验器重算）+ 蒸馏覆盖层格式与冲突优先序（§5B） |
| RV-18 防滥用与政策 | 交付清单明示产物为 AI 内部评审产物；决定建议 bounded 非编辑判断、degraded 不许偷跑 decision.md（§5D） |

## §10 已知局限（v1.0）

1. **单家族环境隔离只能 degraded**：席间独立性靠文件级隔离 + 可见性矩阵，跨模型家族互盲需真实多家族席位到位；降档不是缺陷遮掩——交付强制附降档声明，跨家族席位到位后应开新 round 重跑。
2. **领域门按刊层是机械口径**：字数统计与关键词检索式对措辞形态敏感（演示实测 DG-J05：稿件披露声明实存，但标题「Declaration of AI Use」不在检索式内而判 hit）——命中是「须人工复核」的旗标而非定罪；检索式扩形列 v1.1 候选。
3. **图哈希对应在跨格式交付时结构性 not_assessable**：稿件侧源资产与图包交付件不同名不同格式（演示：SVG 源 vs PDF/PNG 交付）时无从比对；需 Figure 侧提供对应件清单或内容级哈希约定后才能真检，v1 只落 not_assessable 并由 concern 侧提示图源链闭合。
4. **GRIM 族边界**：GRIMMER 未做（v1.1）；合计相容性依赖上游登记「分项—总计」型汇总量，无登记即无条目（演示轮无此对象，未登记、未造数）；均值/百分比粒度对连续量由适用性硬门挡下，覆盖面以登记为准并逐轮自报。
5. **自审只有机械近似**：五类测试的 `model_judgment` 判定登记位 v1 恒 null，语义级判定未接入；机械检查抓形态问题（无锚空话、库存外指认、表扬行、复述、与冻结清单矛盾），抓不了「有锚但论证不成立」。
6. **验证台规模小**：bench 金标准集为内置 9 例（五类缺陷各一 + 四例干净），检出率/误报率只作当版配置判别力的下限证据，不外推为真实稿件的检出保证。
7. **蒸馏覆盖层无内容**：只落格式、加载校验与冲突优先序；学科蒸馏内容待 Memory 阶段收编后按双存纪律投放，v1 不预置任何学科条目。
8. **范围边界**：v1 只做自家稿件投稿前内审（R5）；受邀评审协助不在 v1；收到真实审稿意见后的返修归 Write 的 W7，不在本包。
