---
name: light-analysis
description: Use when 需要对已交付的实验执行包下正式判定：逐登记行回写判定、做稳健性复判与结论强度分级，或向写作阶段交付结论包时。
version: "1.1"
author: light-analysis contributors
license: MIT
---

# light-analysis 操作规程

> **版本：v1.0（2026-10-20 封版）**。Phase 1 = 数据模型、校验器、
> A0 承接与可判性规程、状态机骨架；Phase 2 = 最小判定计算集（§7.0）、
> A1–A7 判定规程全文（§7）、判定/复核子流程、结论包填充与交接、
> 判定自检清单（§8）、失败模式附录（§9）；Phase 3 = 端到端演示
> （examples/demo-synthetic：承接 light-experiment 合成执行包判至
> graded，复核不可用如实停 blocked）+ 本定版。与 LEARNING.md 13 条
> 硬约束的逐条对应见文末附录。
> 本文件与 `light_analysis/` 工具同源：规程里写死的纪律，校验器逐条机械核。

## 1. 定位与边界

核心交付 = **可审计的分析结论包**：判定权在 Analysis（全流程只有本技能
能下 readout 三向正式判定），但**判定口径不自创**——判据只能来自
light-design 冻结登记行（方向/阈值/SESOI/重复层级）。分析期发现标准
缺失或不适用：该行落 undetermined 并生成回 Design 的报告条目，
不许在分析包里临时立标准。

不在本技能内：实验设计与判读标准（Design）、执行与事实对账
（Experiment）、写作（Write，只消费结论包结构化投影）、想法与设计的
决策（只生成回流条目）。

## 2. 数据模型（权威源 = 结构化文件群）

| 文件 | 内容 |
|---|---|
| `analysis.yaml` | 登记头：承接区（execution_card 哈希 + design content_hash + 登记行集哈希，intake 时冻结）、分析规格版本、校正族声明、状态与状态历史、复核记录、counts（**只许工具从 verdicts 机械汇总，不许手填**） |
| `verdicts.jsonl` | 逐登记行一行、只增。字段组：判定组（verdict/象限/basis_spec_id/criteria_ref/direction）、量组（effect_size/interval/p_ab/双 n）、校准组（type_sm 三元组）、等价组（tost）、诊断组（diagnostics）、校正组（family/p_raw/p_adj）、结构组（structure：mode/assumption/key/source/n_units/warnings，ANA-D03）、稳健性覆盖组（robustness_scope：computed/trace_only/trace_only_fraction，ANA-D04）、强度组（grade + cap_reason）。改判走新行 + `supersedes` 链 + `row_ref`（`<line>#v<n>`），不许回改旧行 |
| `spec_ledger.yaml` | 规格集账本：决策点（逐点落字理论正当理由）× 选项、约束、可达组合展开、逐规格三门（理论/统计/非冗余）、冻结哈希、自由度账本 expansions（只增） |
| `spec_results.jsonl` | 规格 × 登记行结果矩阵（judged 门要求账平：每格有结果或显式失败行） |
| `exploratory/exploratory.yaml` | 探索区登记：条目带 `exploratory: true`，只许叙述性 finding |
| `conclusions.yaml` | 结论包：claims_verdict 逐主张映射、strength 合成输入逐项落字、boundaries、limitations、number_provenance 数字溯源表、reflux 回流条目 |
| `audit.json` / `audit.md` | A0 可判性校验产物（双份，承接期落盘） |

受控词表（不许新造）：

- verdict：`positive / negative / null / undetermined / untested`
- quadrant：`significant_not_equivalent / significant_but_equivalent /
  equivalent_only / undetermined`（「存在但 <SESOI」= positive +
  significant_but_equivalent，不许压成普通 positive 也不许压成 null）
- strength_grade：`conclusive / strong / suggestive / insufficient`
  （undetermined/untested 是判定状态，**不入强度档**）
- 校正方法：`fdr_bh / holm / bonferroni / fdr_by`；默认按主张族 BH-FDR，
  primary 主张可在规格冻结前声明 Holm——声明先于看结果。

## 3. A0 承接与可判性规程（Phase 1 落地）

前置：执行包必须已 `delivered`（Experiment 状态机终态）；登记表取
Design 现行导出（amendment 后的新登记行只许出现在新分析包）。

1. `init` 建包骨架，`intake` 喂入三件套：
   `light-analysis intake <pkg> --execution-card <…> --registry <…>
   [--design-card <…>] [--analyst <名> --family <家族>]`。
2. **哈希对齐**（任一不过整包拦截、逐项点名）：
   execution_card.design_ref.content_hash ≡ 每条登记行 content_hash
   ≡ reconciliation.content_hash；登记行 id 不许重复。
3. **逐行可判性点名**（结果落 audit 双份），按序裁定：
   - 无对账行 → `untested_candidate`；
   - 支撑 run **全部**被作废 → `untested_candidate`（void_supported；
     有替代 run 回填的行不算——看对账行 run_ids 的现行集）；
   - 任一支撑 run 有 **fundamental** 失败 → `untested_candidate`
     （主张未被检验；**不许落 negative**，失败分类承 Experiment 登记）；
   - 对账未回填 / 无分布材料 / 事实层 `incomparable` →
     `undetermined_candidate`；
   - 分布材料不是 {mean, spread, n, replication_level} 四件套
     （单点冒充分布）→ **承接失败项**，整包拦下；
   - 覆盖 n < 登记 repetitions → 该行仍可判，但打
     **null 精度预警**：先天精度不足，这条行判不了 null
     （Phase 2 若结果逼近 null，只许落 undetermined 并引此预警）。
4. **不可判行预登记**：untested/undetermined 候选当场落 verdicts.jsonl
   一等终态行（decided_by=intake-audit，note 逐项写明理由）。
   判定期不许把预登记终态行"翻案"成三向判定——材料变化只能经
   新执行包 → 新分析包。
5. **校正族落字**：intake 按登记行 claim_ref 分族；登记行无 claim_ref
   时退化单族并把退化事实写进族 basis，不许假装分过族。
6. 列名/字段机械核对随分布四件套检查一并完成（登记行字段集与对账行
   字段集对齐在 intake 的结构校验里；Phase 2 计算前另有列名核对，
   防 BLADE 式幻觉列名）。

承接完成后包停在 `intake`；冻结规格集账本后 `advance` 过 `checked` 门。

## 4. 规格集账本规程（checked 门前完成）

1. 决策点逐点登记：概念变量/操作化与变换/模型设定/子集/异常值处置/
   先验（贝叶斯行）——每个决策点的每个选项成条，**理论正当理由逐点
   落字**（缺理由 → 理论门全灭、整集 excluded，校验器点名）。
2. 约束以 `forbids` 模式声明不可达组合；工具用 DFS + 剪枝枚举
   **可达组合**（惰性求值口径：规格数 = 可达数，非名义叉积）。
3. 规模上限写死：可达 ≤512 全展开；超限按种子无放回抽样 512，
   抽样规则/种子/可达总数入账本（`specs.build_ledger`）。
4. 逐规格过三门：理论（理由齐全）/统计（选项 valid 标记）/非冗余
   （枚举唯一性）；未过门规格 status=excluded 并落 exclude_reason，
   **不许删账**。
5. `freeze_ledger` 冻结：frozen_hash 覆盖决策点/约束/抽样/规格四区；
   冻结后改动任一区 → 校验器报「冻结后被改动」。看过结果后的扩增
   只许走 expansions 自由度账本逐项登记（动机 + 是否已见结果 +
   受影响行），不许动冻结区。

## 5. 校验纪律清单（校验器逐条机械核，`validate` 全量跑）

1. verdicts 行只许对应登记行 id，未知行拒（判定只认登记行）。
2. 作废支撑行 / fundamental 行落非 untested → 拒。
3. null 行缺 TOST 组、TOST result≠pass、90% CI 未全落界内 → 拒；
   bounds.source ≠ design_sesoi → 拒。
4. positive 行缺 Type S/M 三元组任一分量 → 拒；assumed_D.basis
   不在 {sesoi_frozen, prior_external} → 拒；type_sm 整组出现
   observed/posthoc 字样 → 拒（事后功效禁令的字段形态）。
5. 贝叶斯行（bayes=true 或区间 kind 为 hdi/eti）缺诊断字段 → 拒落
   判定；r_hat ≥1.01 或 ess_bulk/ess_tail ≤400 → 只许 undetermined
   且 note 须注明诊断未过。
6. 三向行缺 basis_spec_id / effect_size / interval / 校正组 / 双 n
   → 逐项拒；basis_spec_id 必须在账本 included 规格内。
7. 校正组 family_id 未声明、method 与族声明不一致、p_adj < p_raw → 拒。
8. undetermined/untested 行缺 note、或带 strength_grade → 拒。
9. 自由文本（note/cap_reason/结论包文本）出现禁用词
   （显著/证明了/无影响/significant/proved/no effect 等）→ 拒，
   提示改用象限与档位落字。
10. 探索条目出现判定/强度词表（整词匹配）或缺 exploratory 标记 → 拒。
11. counts 与 verdicts 机械汇总不一致 → 拒（汇总区不许手填）。
12. row_ref/supersedes 只增链断裂 → 拒。

## 6. 状态机与门

`intake → checked → judged → graded → delivered`，`advance` 逐段过门、
缺口逐项点名（不许整段含糊打回）：

- →checked：audit 落盘且无失败项、承接区已冻结、校正族齐备、
  规格集账本已冻结且哈希验过、逐行可判性已点名。
- →judged：每条登记行恰有一条现行判定行；判定行字段完备（校验器
  全量 0 错误）；规格 × 判定矩阵账平；行级终态行在场即算数，
  **不阻断**流转。
- →graded：每条 Design 主张有 claims_verdict 映射与强度分级
  （合成输入逐项落字）；边界与局限齐备。
- →delivered：数字溯源表覆盖全部被引用数字；复核记录齐备；
  review_status = REVIEW_UNAVAILABLE 时包落 **blocked** 停在此门前，
  复核恢复后从 blocked 续推（执行者永不代判）。

## 7. A1–A7 判定规程（Phase 2 落地）

### 7.0 前置：SESOI 登记与最小判定计算集

- **SESOI 只认登记快照**：judge 只读 analysis.yaml 的 spec 区快照
  （`spec.sesoi`），不许临场从 Design 文本猜。登记三路（v1.1
  ANA-D02，Design 侧结构化登记见 light-design 的 DES-D01）：
  (1) **主路** `register-sesoi <pkg> --from-registry`：直读 A0 承接
  时从登记行捕获的结构化 SESOI 块（七字段：value / unit /
  direction / bounds / basis / estimand_ref / summary_measure），
  整块快照并带登记表哈希与 design content_hash；(2) **结构化指针
  路** `--from <design 文件> --pointer evaluation.sesoi`：指针取到
  登记块时整块快照（块不完整直接拒）；(3) **兼容路**：指针取到裸
  数值时按 v1.0 形态快照并标 via=pointer_compat，只用于 DES-D01
  之前的旧登记表，新项目不许走。A0 承接时登记行块不完整或多行
  不一致即整包点名拦截；任一路登记前与开判前，快照都与登记行块
  比对，**两处不一致整包拒绝**（先对齐登记，不许带病开判）。
  未登记的行、以及快照在案但结构不完整（值非正数 / 块缺字段 /
  块值与快照值不符）的行，直接落 undetermined 并在 note 点名，
  绝不用分析时临时值。判定参数同在 spec 区：`spec.judge_params =
  {gamma: 0.75, type_m_max: 2.0}`（γ 承 Design/Experiment 既有
  口径；Type M 阈值可在开判前登记调整，判后不许改）。
- **计算集**（`light_analysis/calc.py`，纯标准库，全部带 provenance
  = method + 输入哈希 + 参数，落行后可机械复算）：
  `p_superiority`（经验 P(A>B)，并列 0.5，与 Mann-Whitney U/(n1·n2)
  恒等；只有摘要时正态近似变体）、`effect_and_ci`（Welch 均值差 +
  Hedges g + t 区间，t 分位数由不完全 Beta 自实现）、`tost`（双单侧
  t，bounds 只许登记 SESOI）、`corrections`（BH/Holm/Bonferroni/BY，
  与 statsmodels 文档口径对拍）、`design_analysis`（Type S/M 正态
  近似闭式，D 只许外部代入）、`stouffer_combine`（带方向合并）。
  复杂模型（混合模型/贝叶斯采样）不在计算集内：走外部登记，关键
  数字由计算集按登记材料复算抽验，不一致即拦（拍板①）。

### 7.1 A1 描述与分布核查（judge 前的规程步，工具做机械核对）

1. 备判定材料文件（judge-data JSON）：逐可判登记行登记两臂
   `treatment`/`reference` 原始值，或两臂分布四件套
   `treatment_summary`/`reference_summary`；可带 `reference_label`、
   `run_refs`、`bayes`+`diagnostics`（贝叶斯行）、`validity_residual`
   （结果期发现的效度残余，只登记不倒填）。
2. 机械核对（judge 内置，未过逐项点名、整包或整行拦）：
   材料行 id 必须 ⊆ 登记行集（多出行 = 幻觉行，拒）；材料字段集
   只许白名单键（未知字段 = 幻觉列名，拒）；原始值臂长必须与对账
   有效 n 一致（对不齐 → 该行 undetermined）；摘要必须是分布
   四件套（单点冒充分布 → 该行 undetermined）。
3. 形态核查（偏态/重尾/截断）结论只许驱动规格集内的变换选项，
   不许临时新立规格；「不变换」也须在账本决策点落理由（§4）。

### 7.2 A2–A4 判定计算与落字（`judge` 命令）

前置门：包状态 = `checked`（账本已冻结且哈希验过、承接点名齐备）；
已判行不许 judge 覆盖重跑（改判走 supersedes 新行）。

1. **主规格量组**（主规格 = 账本标 `primary` 的规格，无标记时取首个
   included 规格，结果落 `spec.primary_spec_id`）：按登记方向取向后
   算效应（Welch 均值差 + 95% CI + Hedges g）、SE/df、P(判定方向)
   ——positive 候选取 P(更优)、negative 候选取 P(更劣)。
2. **逐规格计算**：included 规格逐个算效应与双侧 p（estimator 决策
   点决定口径：mean_diff → Welch；median_diff → 中位差 +
   Mann-Whitney；摘要材料下秩类规格退化为 Welch 并在结果行 note
   落字）。全部落 `spec_results.jsonl`；终态行与材料缺失行落显式
   `not_judged` 行，矩阵账平（judged 门核）。
3. **联合推断摘要**（A4）：中位效应（逐规格取向效应中位数）、
   方向份额（同向规格占比；主效应与规格效应同 <SESOI 时按等价
   一致计同向——null 行的方向份额是等价口径不是符号口径）、
   Stouffer 带方向合并 p。三项齐入判定行 `joint` 区。
4. **校准**（A3）：Type S/M 三元组以 D = 登记 SESOI 快照值、
   SE = 主规格 SE 代入 `design_analysis`；TOST 以同一 SESOI 为
   bounds。贝叶斯行先过诊断门（§5.5）：诊断缺失/未过 → 该行只许
   undetermined 并在 note 注明诊断未过。
5. **落字规则**（四象限，逐门点名）：
   - 方向门：主规格校正后 p < 族 α 且 P(判定方向) ≥ γ；
   - 联合门：中位效应与主效应同向、方向份额 ≥ 0.5、Stouffer p < α；
   - 校准门（仅 positive）：Type M ≤ `type_m_max`（默认 2.0）。
   - positive = 方向门 ∧ 联合门 ∧ 校准门全过；象限：TOST 同时过 →
     `significant_but_equivalent`（存在但 <SESOI），否则
     `significant_not_equivalent`。Type M 超限被拦 → undetermined，
     note 逐字点名 Type M 与阈值。
   - negative = 方向门（逆登记方向）∧ 联合门；象限同上规则。
   - null = TOST 过 ∧ 方向门未过；象限 `equivalent_only`。承接带
     **null 精度预警**的行判不了 null：TOST 过也只许 undetermined
     并引预警。
   - 其余一律 undetermined，note 逐项写明未过哪门（p/γ/联合/Type M/
     TOST 逐项数值），不许只写「证据不足」。
6. **结构口径**（ANA-D03，贯穿第 1/2/4 步）：配对/区组结构靠声明
   驱动，不靠猜——声明两处对表：登记行 `pairing` 字段（Design/
   Experiment 侧声明配对来源，intake 验形状后透传进快照行）与
   judge-data 条目的 `pairing` 字段，形态 `{mode: paired|blocked,
   paired_by|blocked_by: 键名, source: 来源说明}`；两处不一致该行
   落 undetermined 点名。声明在案时两臂须逐元素给对齐键
   （`treatment_keys`/`reference_keys`）：paired 按键作差走差值序列
   口径（单样本 t 效应与 TOST、配对符号 P、median_diff 走差值
   中位数 + 符号检验）；blocked 先算区组内对照（区组内两臂均值差）
   再走同一口径，判定单位 = 区组。声明与数据不符（无对齐键、键长
   不符、键重复、配对缺对侧、区组缺臂、只有分布摘要）逐行落
   undetermined 并点名，**不许静默按独立样本判**。未声明结构时走
   独立样本口径，判定行 `structure` 区落
   `assumption = undeclared_independent_default`；两臂同源信号
   （`treatment_run_refs` 与 `reference_run_refs` 交叠、或两臂原始
   值逐元素完全相同）机械点名警告落 `structure.warnings` 与 note，
   警告不改判。差值序列零方差的退化情形 SE = 0 如实落字（CI 退化
   为点、TOST 按点落界判定、Type S/M 取极限值），不许编造 SE。

### 7.3 A5 按族校正与自由度对账

- 校正在全部可判行主规格 p 齐备后统一按族应用（`corrections_by_family`
  按登记头 `correction_families` 分组，方法与 α 以族声明为准），
  p_raw/p_adj/method/family_id 回填每行校正组；无族之行不许存在。
- 自由度对账：判定所用规格集 ≡ 冻结账本 included 集；看过结果后
  的扩增只许走账本 expansions 登记（§4.5），judge 不读未冻结规格。

### 7.4 A6 强度合成（`grade` 命令，机械合成不许手填总档）

- 行级强度在 judge 落字时由 `grading.row_grade` 给出：方向性行看
  方向份额 × Type M（全票且 Type M ≤1.5 → conclusive；份额 ≥0.75
  且 Type M ≤2.0 → strong；份额 ≥0.5 → suggestive；其余
  insufficient）；null 行以 TOST p 替代 Type M 作校准分量。
- 主张级（grade 填充 conclusions）：汇总规则先于判定冻结——任一行
  untested → 主张 `untested`；全 positive → `supported`；全
  negative/null → `not_supported`；混合 → `partial` 并逐行列明。
  强度 = 行级最低档起步，逐项封顶：partial 封 suggestive、稳健档
  low（最差行份额 <0.75）封 suggestive、Type M 最差值 >2.0 封
  suggestive、效度残余非空封 strong、untested 主张落 insufficient；
  合成输入（line_verdicts/line_grades/robustness_tier/
  type_sm_worst/validity_residual/evidence_cap）逐项落
  `strength[].inputs`，封顶来源写进 cap_reason。
- 边界与局限随 grade 落盘（`--notes` JSON 补入或预置 conclusions）：
  结果期效度威胁只记局限、不许倒填 Design 登记（约束 6 的分析侧）。
- **稳健性覆盖落字与封顶**（ANA-D04 短期）：真改计算的决策点只有
  `estimator`（代码以 `COMPUTED_DECISION_POINTS` 声明，与逐规格
  计算实现同源），冻结账本的其余决策点（如 outlier_handling）只
  留痕不改计算、其规格与主规格数值成对相同。每条判定行落
  `robustness_scope`（computed / trace_only /
  trace_only_fraction），把「方向份额到底覆盖了哪几个维度的
  稳健性」从文档局限升级为数据落字；留痕型决策点占比过半时，
  方向性行强度封顶 `suggestive` 且 cap_reason 点名留痕点与占比
  （null 行不读此封顶）。主张级只把 robustness_scope 落进
  `strength[].inputs` 供判读——行级封顶已由行级最低档合成传导，
  不叠加第二重封顶。outlier_handling 等决策点的真实计算属中期
  事项，未做前不许把方向份额解读为全维稳健性。

### 7.5 复核子流程（与 Idea/Design 同构、分工收窄）

1. `review prepare`：生成自包含复核包 `review_packet.md`——口径
   宪法（判据不重开）+ 全部判定摘要 + **边界情形行全字段**，边界
   只含三类：judge 落的 undetermined 行、四象限边缘行
   （significant_but_equivalent）、强度合成有争议行（方向份额 <1
   或档位 ≤ suggestive 的方向性行）。包指针与哈希登记进
   `analysis.review_packet`（不碰 review 区，防「备了包=复核过」）。
2. `review record --reviewer <名> --family <家族>`：落收据
   `RV-<sha256[:10]>`（锚定复核包哈希 + 复核者 + 范围）；同族、
   写者自审一律拒；带异议（disagree）不落收据——先改判后重核。
3. `review record --review-unavailable`：显式落 REVIEW_UNAVAILABLE，
   delivered 门拦停 blocked（gates 已接通）；复核恢复后 record
   正式收据、从 blocked 续推。执行者永不代判。
4. `review import --from-json <文件>`：外部判定回填，schema 写死
   （reviewer/family/decisions[{registry_line_id, agree, comment}]，
   未知字段拒收、边界行须逐行覆盖、任一 disagree 拒收并点名），
   收据哈希锚定回填文件本身。

### 7.6 A7 结论包交接与回流（`grade`/`export`/`reflux`）

- **数字溯源表**（grade 生成）：每个进入结论包的数字一行
  （effect_size 与 p_ab 各一行：值 → verdict row_ref → 登记行 →
  run_refs → 依据规格 → 计算 method）；终态行落显式
  `no_numeric_result` 空溯源行——「无数字」本身可审计，delivered
  门逐行核覆盖。
- `export`：投影 `conclusion_card.json`（kind =
  `light-analysis/conclusion-card`：主张支持度/强度/逐行判定 +
  边界/局限/溯源表/复核状态/回流，Write 只消费结构化字段、不许
  另行解读数字）+ 刷新 `ANALYSIS_REPORT.md` 渲染。
- **回流**（`reflux` 命令，只生成条目不越权）：补充消融
  `supplementary_ablation` → Experiment（全生命周期 ≤1 轮、一次
  提全，第二次请求直接拒）；标准缺失 `standard_gap` → Design；
  证据状态通知 `evidence_notice` → Idea。条目落 analysis.yaml +
  conclusions.yaml + `reflux/<RX-A###>.json` 文件。

## 8. 判定自检清单（定版前逐项过，缺一不许 delivered）

1. SESOI 快照在案且来源哈希与 Design 现行文件一致（被改过须重新登记并说明）。
2. judge-data 逐行字段集与登记口径对齐（无未知字段、无幻觉行），臂长与对账 n 一致。
3. 每条登记行恰有一条现行判定行；终态行 note 逐项点名理由。
4. positive 行双门证据齐：joint 三项数值在行内、Type M ≤ 阈值、D 的 basis = sesoi_frozen。
5. null 行 TOST 三件套齐（bounds 来源 design_sesoi、p_tost、90% CI 落界）；带精度预警的行未落 null。
6. 贝叶斯行诊断四字段齐且过门；未过门的行只落 undetermined 并注明诊断。
7. 校正组逐行齐：family 在声明内、method 与族一致、p_adj ≥ p_raw。
8. spec_results 矩阵账平：included 规格 × 登记行每格有 computed 或显式 not_judged 行。
9. 强度逐项可复算：行级份额/Type M 在行内，主张级 inputs 逐项落字、cap_reason 与封顶规则对得上。
10. 数字溯源表逐行覆盖 claims_verdict 全部行（含终态行的空溯源行）。
11. 复核收据在案（或 REVIEW_UNAVAILABLE 如实落字且包停 blocked）；复核者与执行者异族、非同一人。
12. 探索区条目未使用判定/强度词表；结论包文本无冻结词表禁用词（校验器已扫，人工再读一遍）。
13. 回流条目只生成未代决策；补充消融未超 1 轮。
14. `validate` 全量 0 错误；`ANALYSIS_REPORT.md` 计数与 verdicts 机械汇总一致。
15. 结构落字逐行核：判定行 `structure` 区在案（声明行 mode/key/source/n_units 与材料对得上，未声明行 assumption 已落字）；声明与数据不符的行已落 undetermined 并点名，未被静默按独立口径判；同源警告在 warnings 与 note 双落。
16. 稳健性覆盖逐行核：`robustness_scope` 与冻结账本决策点对得上；留痕过半时方向性行已封顶 suggestive 且 cap_reason 点名；conclusions 的 strength inputs 已带 robustness_scope。

## 9. 失败模式附录（v1.0 已知失效形态与处置）

| # | 失效形态 | 处置（写死） |
|---|---|---|
| F1 | SESOI 未登记进分析规格（或快照结构不完整） | judge 对该行落 undetermined 并点名；不许临场取数（先 register-sesoi：登记行带结构化块走 --from-registry 主路，旧登记表才走指针兼容路） |
| F2 | judge-data 出现登记外行 id / 未知字段（BLADE 式幻觉列名） | 整包拒，逐项点名；改材料后重跑 |
| F3 | 材料臂长与对账有效 n 不一致 | 该行 undetermined 点名；查执行包对账，不许就地改数 |
| F4 | Type M 超阈值的 positive 候选 | 落 undetermined 并点名数值与阈值；不许下调阈值事后放行（阈值只许开判前在 spec 区登记） |
| F5 | TOST 未过却想落 null（「不显著」滑移） | 落字规则不给出口：只许 undetermined 并写明 TOST 结果 |
| F6 | 精度预警行逼近 null | 只许 undetermined 并引预警；补材料只能走新执行包 → 新分析包 |
| F7 | 贝叶斯诊断字段缺失或未过门 | 只许 undetermined 并注明诊断未过；不许以图形观感替代数值门 |
| F8 | 复核不可用（单模型家族环境） | 落 REVIEW_UNAVAILABLE 停 blocked；不许执行者代判、不许伪造收据 |
| F9 | 复核带异议回填 | 拒收并点名行；按异议改判（supersedes 新行）后重新 prepare + 复核 |
| F10 | 补充消融想提第二轮 | 工具直接拒；证据不足如实落终局，不许逐轮挤牙膏 |
| F11 | judge 重跑覆盖已判行 | 工具拒；改判走新行 + supersedes 链，旧行不许回改 |
| F12 | 摘要材料下秩类规格无原始值 | 该规格退化为 Welch 口径并在 spec_results note 落字，不许假装算过秩检验 |
| F13 | grade --notes 补入的 conclusions 条目形态不对（自由字符串冒充 boundaries 等结构化条目） | validate 落结构化错误逐项点名（条目类型守卫，不许校验器自身崩溃）；notes 须按 schema 结构（boundaries 为 {claim_id, conditions, not_extrapolatable, would_change_if}）重给后重跑 grade |
| F14 | 声明了配对/区组结构但材料给不出对齐（无对齐键、配对缺对侧、区组缺臂、只有分布摘要），或登记行与材料的两处结构声明互相矛盾 | 该行落 undetermined 并逐项点名缺陷；补齐材料或对齐两处声明后重判，不许静默按独立样本口径凑判（ANA-D03） |
| F15 | 两臂同源（同批段/同一基线臂重跑）却未声明配对结构 | 工具按 run 引用交叠与两臂逐元素相同两路信号机械点名警告（structure.warnings + note），仍按独立口径判并落结构假设；要走配对口径须由登记侧或材料侧补结构声明后重判，不许分析者只在 reference_label 写散文了事（ANA-D03） |

## 附录：与 LEARNING.md 13 条硬约束的对应

| 约束 | 本规程落点 | 工具实现 |
|---|---|---|
| 1 判定只认冻结标准与分布 | §2、§3、§7.2（criteria_ref 只许引登记行） | judge 读登记表方向/SESOI 快照；validate 纪律 1–2 |
| 2 positive 双过门（规格集稳健 × Type S/M） | §7.2 落字规则（方向门 ∧ 联合门 ∧ 校准门） | calc.design_analysis + joint 摘要；validate 纪律 4 |
| 3 null 须 TOST 挣来、四象限不塌缩 | §7.2（null 出口 + 精度预警行禁判 null） | calc.tost；validate 纪律 3 |
| 4 贝叶斯量先过诊断硬字段 | §5 纪律 5、§7.2 诊断门 | judge 诊断检查（R̂<1.01、ESS>400）；validate 纪律 5 |
| 5 决策点逐点登记 + 列名机械核对 | §4、§7.1（材料字段白名单/未知行拒） | specs 账本理由落字；judge `_DATA_KEYS` 核对 |
| 6 校正族须声明（family 是字段） | §2 词表、§3 承接落族、§7.3 按族校正 | calc.corrections_by_family；validate 纪律 7 |
| 7 规格集三门入集 + 展开账本先行冻结 | §4（枚举/上限/冻结哈希/expansions） | specs.build_ledger/freeze_ledger；judged 门矩阵账平 |
| 8 强度 = 证据 × 稳健 × 效度残余、先封顶 | §7.4（行级/主张级机械合成、逐项落字） | grading.row_grade/claim_grade；§8 自检 9 |
| 9 探索/确认物理分离 + 自由度账本 | §2（exploratory 独立区）、§4 expansions | validate 纪律 10（探索区词表）；账本 expansions 只增 |
| 10 作废 run 不入判定、fundamental 落未检验 | §3 逐行可判性点名与预登记 | intake-audit 预登记终态行；validate 纪律 2 |
| 11 事后功效禁止、合法替代成对落字 | §5 纪律 4（type_sm 字段形态）、§7.0 计算集 | calc.design_analysis（D 只许外部代入）；validate 扫 observed/posthoc |
| 12 n 按独立重复层级计、双 n 并存 | §3（有效 n/登记 n 与精度预警）、§7.1 臂长核对 | judge 臂长 ≡ 对账有效 n；validate 纪律 6 |
| 13 判定门 fail-closed、执行者永不代判 | §6 状态机逐段门、§7.5 复核子流程 | gates（REVIEW_UNAVAILABLE → blocked）；review 同族/自审判拒 |
