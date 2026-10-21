---
name: light-design
description: Use when 已有定版想法卡、需要把它变成可直接开工且可被证伪的研究设计书，或需要冻结设计、修订已冻结设计并向实验阶段交接时。
version: "1.2"
author: light-design contributors
license: MIT
---

# light-design

把 light-idea 的**定版想法卡**变成**可直接开工且可被证伪的研究设计书**。
设计依据：`03-design/REDESIGN-DRAFT.md` v0.1（含 2026-10-20 用户拍板 7 项）
与 `03-design/LEARNING.md` 十三条硬约束。

**当前版本：v1.0（封版，2026-10-20）**——一期：项目骨架 + 设计书系统
（design.yaml 十一区）+ 确定性校验器 + 状态机（draft → reviewed →
frozen）+ amendment 追加协议。二期：定版评审子流程（review prepare/
record，REVIEW_UNAVAILABLE 正式通道）、交接四件套导出（D7）、
DESIGN_REPORT 刷新、D0–D7 逐环规程。三期：真实想法卡端到端演示
（见文末「三期演示小结」）与本定版。**v1.2（2026-10-21）：功效真
计算模块**——经典分组设计（双臂/配对/单因素 ANOVA）的样本量改走
包内精确解求解器（非中心 t/F，`light-design power` 命令），落
resources.power.design_size 原生落格，校验器做实际功效拦截与复算
拦截；立项与验收口径见 `03-design/power-module-acceptance.md`
（实测背景：21-benchmark/measured-round1.md §三）。

## 定位与边界

- 输入：light-idea 交接三件套（只消费**定版**卡）。交接字段缺失时
  **打回、不许临场发明**（AgentLaboratory 反面教训：输入只有主题+综述，
  模型/数据/基线/判读/预算全被现编）——走 intake 打回记录退回 Idea 补规格。
- 输出：冻结的设计书 design.yaml（权威源）+ design.md（渲染）+ 交接
  四件套（exports/<design_id>/）。拿到它，light-experiment 不需要再做
  任何设计决策就能执行；设计本身写明「什么结果会推翻这个想法」。
- 不做：实验执行（归 Experiment）、结果对账回填（归 Analysis，凭
  expected_registry.jsonl 逐条对）、查新（归 Idea/Literature）、长期
  记忆（只做结构化留痕，收编归 Memory）。

## 能力环（D0–D7）

| 环 | 职责 | 落地 |
|---|---|---|
| D0 输入与问题细化 | 消费交接、入口校验、原始问题逐字落盘、claim 细化（≤2 + anti-claim + 最低可信证据） | intake 区 + import_intake + 打回门 |
| D1 方法与方案设计 | 变量三组三型全枚举、随机化/种子政策、重复层级声明、干预生效机制与核查点 | plan 区 + 校验器 |
| D2 对照与消融设计 | status quo 一等对照、消融矩阵（what_it_tests / expected_if 先行）、不必要消融登记、对照先行依赖 | contract 区 + 校验器 |
| D3 评估协议与指标 | 主指标唯一 + 护栏、判读三向结构化、调参对等条款、种子/重复预先定明 | evaluation 区 + 校验器 |
| D4 效度威胁与稳健性 | 四分法逐类三态登记、结构错误清单、失败模式预案 | validity 区 + 校验器 |
| D5 资源与可行性核算 | 功效核算（SESOI→种子/重复/评估集规模 + 敏感性范围；经典分组设计走精确解求解器 + design_size 落格）、双货币预算、阶段表与转移条件、量化熔断 | resources 区 + 校验器 + power 求解器 |
| D6 设计定版与预注册 | 静态校验全过 → Stage 1 五条评审（异家族）→ 登记头落字 → 冻结（哈希）；修订只走 amendment | 状态机 + freeze 区 + review 子流程 |
| D7 向 Experiment 交接 | 运行清单（拓扑序）、预期登记表、复现字段、检查点 → 四件套导出 | handoff 区 + export 命令 |

## 命令面

```bash
light-design init <dir> --direction <方向名>
light-design new <project> --title <题名> --idea-id <idea_id> [--tier full|minimal] \
    [--from-handoff <idea_card.json|idea.yaml>]
light-design validate <project> <design_id>
light-design advance <project> <design_id> --to reviewed|frozen|returned|blocked|draft
light-design amend <project> <design_id> --field <路径> --value <新值> \
    --reason <为何改> --results-seen <改时可见性声明> [--user-signed] \
    [--category unforeseen|prewritten_branch] [--branch-ref <分支 id>]
light-design review prepare <project> <design_id>
light-design review record <project> <design_id> --from-json <判定.json>
light-design review prepare <project> <design_id> --amendment <n>
light-design review record <project> <design_id> --amendment <n> \
    --from-json <判定.json>
light-design review record <project> <design_id> [--checklist <清单.yaml>] \
    [--reviewer-model <模型> --reviewer-family <家族> --decision pass|reject]
light-design review record <project> <design_id> --review-unavailable [--note <附注>]
light-design export <project> <design_id>
light-design report <project>
light-design list <project>
light-design render <project> <design_id>
```

## D0 规程：入口承接与打回

1. `new --from-handoff` 消费交接件：exec_spec 六项（datasets /
   strongest_baseline / metrics / ablations / resource_budget /
   key_details）逐项承接进 intake.spec_intake，登记交接原值摘要与
   设计落点；original_question **逐字**落盘，不许改写成自己的话。
2. 有值 → accepted；设计中展开深化了口径 → expanded（须在对应区能
   找到展开后的实体，不许只改状态字样）。**跨区实体核查已命令化
   （v1.1 DES-D04）**：校验器对每项 expanded 承接按 schema 冻结的
   映射表到对应区查实体（datasets → evaluation.data_protocol /
   plan.variables；strongest_baseline → contract.controls 的
   status_quo；metrics → evaluation.primary_metric；ablations →
   contract.ablations；resource_budget → resources.budget/power；
   key_details → plan.intervention_mechanism /
   intervention_checkpoints / handoff.repro_fields），查无实体报错
   点名。缺失/为空 → status=returned + returned_items 打回记录 +
   intake_log.md 留痕。
3. **打回纪律**：六项未齐、或有未清打回项（resolved=false），设计
   不许离开 draft（reviewed 门硬拦并逐项点名）。回补后逐项置
   resolved=true 并经 returned → draft 回到主线；往返记录不许删。
4. 风险条目正面回应：交接件里的 risks / strongest_objection 必须在
   validity 或 plan 里有对应登记，绕开即评审（D6）必查项。
5. 概念级定版卡（若上游出现）：先按 facet 与证据把规格补齐到六项
   可承接，补齐前不许进 reviewed。

## D1/D2 规程：从主张反推实验清单

实验清单**从主张反推，不从好奇心正推**（约束 1）：

1. 先写 claims：primary_claims ≤2 条，每条带 minimum_convincing_evidence
   （什么证据能让强审稿人信服）；anti_claims 非空——要排除的竞争
   解释逐条登记，并指明由哪条消融/对照排除（excluded_by）。
2. 每条主张 → 推出能产生其最低可信证据的 run；每个 anti-claim →
   推出一条消融或对照。指不回任何主张的 run 是愿望清单，删。
3. 消融逐条先行落字：what_it_tests（测什么）与
   expected_if_component_matters（组件重要则预期看到什么）缺一不许
   入矩阵；「不做什么」同样登记 unnecessary_ablations + 理由，
   使其成为可审计产物而不是遗漏。
4. 对照先行排程（拍板 ⑥）：最强基线登记为 status_quo 一等对照；
   每个处理组 run 必须声明 control_run 并把对照列入 depends_on
   （校验器验 + export 按拓扑序排程，对照未跑完处理组物理上不开跑）。
5. 变量三组（treatment / outcome / covariate）× 取值域（range /
   choice / fixed）全枚举；run 级取值不许超出变量域（brief 中明示）。
6. 干预生效核查点（约束 4）：每个处理写明「干预如何生效」与执行后
   核查点——自变量必须真的被改变且留证（Beel 实锤：声称扫了参数
   实际恒定，产出的「改进」按设计原理不存在）。

## D3/D5 规程：评估协议与功效核算操作口径（拍板 ②）

功效核算强制，但计算实验不用经典样本量口径，用**替代口径**（经典
分组设计——双臂独立样本 / 配对 / 单因素 ANOVA——不走替代口径，
走第 8 条真计算口径）：

1. **效应量优先序**：SESOI（最小有意义效应，如「MOTA 2 个百分点」）
   > 收缩后的先行估计（先行结果按乐观偏差打折后取值）> 明说用了
   约定值。三者必居其一并登记 basis，不许凭空发明效应量。
2. **核算产出**：由 SESOI + alpha + target_power 经模拟/解析推出
   derived = {seeds, repetitions, eval_set_size}（种子数 / 重复数 /
   评估集规模），与 evaluation.seeds / repetitions 对账一致。
3. **交付物是敏感性范围**：sensitivity_range 写清「SESOI 在合理
   区间内变动时所需重复如何变」（如 1–3 点 → 4–11 段），不是单个 n。
4. **给不起就下调声称**：核算 sufficient=false（预算内给不起所需
   重复）→ 不许保留 confirmatory 主张：或下调为探索性，或缩声称
   范围，或扩预算重算；三选一落字，不许装作没看见（校验器硬拦）。
5. **禁令**：不许 observed power（用已见结果反推功效）；不许序贯
   偷看（看一次结果改一次 n）；种子清单预先生成并登记。
6. 比较三支柱（约束 7）：主指标唯一点名 + 惯例出处；护栏指标与主
   指标分离登记；tuning_parity 写明自家方法与每个基线的调参预算
   对等（试验次数/搜索空间同级），基线不许用默认参数凑数。
7. **SESOI 结构化登记（v1.1 DES-D01）**：SESOI 在 `evaluation.sesoi`
   登记为结构化块（全设计单一事实源），七字段缺一不可：`value`
   （正数）/ `unit` / `direction`（higher 或 lower，须与主指标方向
   一致）/ `bounds`（边界定义，如等价界取 ±value 对称双侧界）/
   `basis`（推导依据引用——优先序第 1 条的 basis 落点，无依据不许
   登记）/ `estimand_ref`（目标量引用，如 claims.primary_claims[C1]，
   使 SESOI 与估计目标绑定）/ `summary_measure`（汇总度量类型，如
   mean_diff）。带确认性主张的完整级设计**必须登记**（校验器硬拦）；
   resources.power.sesoi 文本保留为人类可读表述，两者不得互相矛盾。
   登记行（handoff.expected_registry 与导出登记表）只许携带登记块
   的**派生副本**并逐字段一致，不许登记行单独填（校验器与 export
   双重拦截）。evaluation.sesoi 是命门字段：冻结后变更只能走
   amendment + 用户签，派生副本在同一 amendment 内机械刷新。
8. **经典分组设计走真计算（v1.2，验收规格
   `03-design/power-module-acceptance.md`）**：设计形态为双臂独立
   样本 t / 配对 t / 单因素 ANOVA（等分配）时，样本量**只许**由包内
   求解器产出——`light-design power <项目> <design_id> --form
   two_arm|paired|anova --sigma/--sigma-diff/--cohen-f [--groups k]
   [--sesoi-points 1,2,3] [--simulate] [--apply]`（实现
   `light_design/power.py`，纯标准库非中心 t/F 精确解，与
   statsmodels 同题对拍至 1e-6 量级）。口径钉死如下：
   - **SESOI 消费路径**：求解器只读 `evaluation.sesoi` 登记块的
     value（DES-D01 单一事实源），命令不接受外部 SESOI 覆盖登记
     值；alpha / target_power 承 resources.power 登记值。σ /
     σ_diff / Cohen f 是设计前提（方差/效应尺度假设），其依据必须
     在 resources.power.basis 落字（先行估计收缩、文献或惯例），
     不许裸给一个数无出处。
   - **路线裁决**：最终 n 只认精确解（route = nct_exact /
     ncf_exact）；z 近似只作合理性速查、落 z_reference 并标注
     reference_only，**不许以 z 数充当达成功效的样本量**（校验器对
     z route 落格直接报错）；蒙特卡洛模拟只作交叉验证（口径：种子
     20261021、2000 次/点、双侧 alpha，落 sim_check 并登记 MC
     标准误）。精确解与模拟取整不一致时**以精确解为准**，分歧与
     MC 标准误写入 design_size.route_note，不许执行者自选路线。
   - **原生落格**：产出落 `resources.power.design_size`
     {form, route, alpha, target_power, sesoi_value, sigma/
     sigma_diff/cohen_f, raw_n（精确解原值）, per_group_n（取整）,
     groups, total_n, achieved_power（取整 n 的实际功效）,
     z_reference?, sim_check?, route_note?}，敏感性多点落结构化
     `resources.power.sensitivity_table` 逐行 {sesoi_value, raw_n,
     per_group_n, total_n, achieved_power}——交付物仍是敏感性
     范围，但每点都是精确解数字，不许只给文本范围。分组设计的
     每组 n **不许**再借 derived.repetitions 解释性落位（旧写法
     兼容读取，但校验器给警告点名；声明 caliber=grouped 而无
     design_size 直接报错）。
   - **实际功效拦截**：achieved_power < target_power 时校验器
     报错（不许 sufficient=true 静默通过）；校验器还按登记参数
     当场复算 achieved_power，落字与复算差 > 1e-6 报错——功效
     数字只许求解器产出，不许手填。给不起（预算内达不到取整 n）
     仍走第 4 条三选一（下调声称 / 缩范围 / 扩预算重算）。
9. **旧口径产出被取代标注**：v1.2 前按「模拟/解析」旧规程产出的
   经典设计样本量一律视为被精确解口径取代，引用时必须标注。
   已知两处：(a) measured-round1 中执行者按旧规程 z 公式产出的
   每臂 99（P1/P2）、18 对（P4）——实际功效 0.78/0.74，未达自设
   目标，已被精确解 100/20 取代；(b) 演示设计
   zero-tuning-tracker-thresholds_979ee7 的 power 块（段级配对差
   旧解析口径：SESOI 1/2/3 点 → 11/6/4 段、「6 段达 0.8」）——按
   配对 t 精确解（σ_diff=1.5）复算为 20/7/5 段，6 段实际功效约
   0.743 未达 0.80；演示 YAML 保留原字作历史记录，其 design.md
   已加被取代横幅，后续引用以本条复算为准。

## D4 规程：效度登记填法

1. 四分法逐类登记：conclusion（结论）/ internal（内部）/ construct
   （构念）/ external（外部），**整类缺失即设计不完整**（校验器拦）。
2. 每项三态：na（不适用，note 必写为何不适用）/ mitigated（已缓解，
   note 写措施落点）/ residual（残余风险，note 写残余声明与声称
   边界）。只写状态不写 note 不合格。
3. 结构错误清单逐项自查（structural_checks）：数据泄漏、伪重复
   （n 只按独立随机化层级计——处理被随机化到哪一层，n 就是哪一层）、
   基准污染、调参不公平、选择性报告等，status ∈ pass/flagged + note。
4. 登记发生在**设计期**：写在论文末尾的威胁节只是免责，不是设计。

## D6 规程：评审与冻结

定版路径：`advance --to reviewed`（校验 + 承接门）→ 评审落盘 →
`advance --to frozen`（评审门 + 落冻结哈希）。

1. **生成评审包**：`review prepare` 产出 review/<design_id>/
   review_packet.md（设计书全文 + Stage 1 五条标准 + 可见性声明 +
   评审者须知）与 review_checklist.yaml（逐项结构）。评审包自包含，
   交给异家族模型/专家时不需附带项目。
2. **评审者纪律**：评审者模型家族必须与设计生成者
   （registration.designer.family）**不同**；同族或同模型落盘时
   直接拒收（自评不作定版依据，约束 13）。逐项 verdict（pass/fail）
   + note（依据）五条缺一不可；decision=pass 与逐项有 fail 并存
   会被判「决议与逐项矛盾」拒收。
3. **落盘**（二选一，与 light-idea 复核包同构）：
   - 外部判定 JSON：`review record --from-json verdict.json`，JSON
     字段 = {reviewer_model, reviewer_family, decision,
     items: {五条: {verdict, note}}}；
   - 清单回填：评审者填 review_checklist.yaml 后 `review record`
     （可加 --reviewer-model/--reviewer-family/--decision 覆盖）。
   落盘写 freeze.review + 收据 review_id（RV-…）+ review_record.json 存根。
4. **降级通道**：跨模型评审不可得 → `review record
   --review-unavailable` 显式落 REVIEW_UNAVAILABLE 记录。frozen 门
   硬拦：**不定版、不停工、不伪造收据**；恢复后重新 record 覆盖
   降级记录再推进。
5. **冻结**：过门即落 frozen_at + content_hash。此后正文一字不回改
   （任何手改被哈希检出）；评审记录不许事后改写。

### amendment 分级操作（拍板 ⑤）

- 唯一通道：`amend`。每条必带 reason + results_seen（改时是否已见
  结果、见了什么——决定该修订的可信度等级）。
- **命门字段必须 --user-signed**：evaluation.readout（判读标准）、
  evaluation.primary_metric（主指标）、claims（主张）、
  resources.circuit_breakers（停止规则）、evaluation.sesoi
  （SESOI 登记块）。无签拒收，已落盘的伪造无签 amendment 会被
  validate 检出。
- 其余字段自动追加留痕（approved_by 记为工具自动留痕）。
- 命门字段 amendment 后，评审对象变更：引用该设计的结果在对账时
  须按 amendment 链核对版本（exports 的 content_hash 取现行哈希）。

### amendment 类别分流与增量评审（v1.1 DES-D02 + C-补04）

- **每条 amendment 必须声明类别**（`--category`，落盘不可改）：
  `prewritten_branch` = 执行定版时已预写的偏离分支；
  `unforeseen` = 未预见变更（默认，未声明取此最严口径）。定版时把
  可预见的偏离分支预写进 `plan.deviation_branches`（每条含 id /
  trigger / fields 影响面 / fallback 备援方法）；定版前的诊断迭代
  不是 amendment，走设计史留痕。
- **分流由代码执行**：声称 prewritten_branch 必须 `--branch-ref`
  点名预写分支，且变更字段必须落在该分支声明的 fields 影响面内；
  无此分支、或字段越界，apply 点名拒绝（类别与影响面不符），改按
  unforeseen 登记。拿不出预写证据不许自称预写。
- **命门 amendment 落盘即 pending_review**：增量评审落盘 pass 前
  `export` 被拦并点名；决议 reject 同样拦，须以补偿 amendment 回退
  变更（只追加纪律）。非命门 amendment 不触发增量评审。
- **增量评审流程**（只审变更项及其影响面，不重开全量评审）：
  `review prepare --amendment <n>` 生成自包含增量包（变更字段前后
  值 + 按字段依赖映射生成的受影响登记行/主张清单 + 原冻结评审
  收据指针）；异家族评审后 `review record --amendment <n>
  --from-json <判定.json>` 落盘（同族拒收，与定版评审同纪律）。
  分流两轨：预写分支走**轻评审**（只核 trigger_verified 触发条件
  成立与 fallback_as_predeclared 按预写执行两项）；未预见变更走
  **全评审**（只核依赖映射圈定的 Stage 1 条目子集）。
- **降级通道**：`review record --amendment <n>
  --review-unavailable` 显式落字解除待审，导出件（brief/repro）
  会注明该 amendment 增量评审未完成；恢复后重新 prepare/record
  补审覆盖降级记录。不许伪造评审收据。

## D7 规程：交接四件套与对账约定

`export` 仅对 frozen 设计开放（非 frozen 拒绝并逐条列缺口）：

| 件 | 内容 | 消费方 |
|---|---|---|
| experiment_brief.md | 运行清单：runs 依赖拓扑序逐个列明角色/对照/阶段/预期登记 + 变量表 + 判读三向 + 熔断线 + 阶段转移条件 | Experiment 照单执行 |
| design_card.json | design.yaml 的结构化全量 JSON 投影 | 程序消费 |
| expected_registry.jsonl | 每 run 一行：readout 三向 + 主指标 + 结构化 SESOI 派生副本（自 evaluation.sesoi 机械复制）+ 预期 + 种子/重复 + 现行内容哈希 | Analysis 事后逐条对账、判定直读 SESOI |
| reproducibility.md | 种子/环境/数据版本/调参对等/冻结锚点清单 | 复现与审计 |

对账约定：Experiment 逐 run 回填实际结果与干预生效证据；Analysis 按
expected_registry 的 readout 三向判定回写；执行中发现的偏离走偏离
登记回 Design（构成修订的转 amendment），不许执行端私自改设计。

## 极简级（minimal）使用边界（拍板 ③）

- 定位：判别实验级小设计的快速通道（对应 AsPredicted 8 问下限）。
- 底线六件缺一不可：主张 / 判读三向 / 对照 / 重复层级 / 可见性
  声明 / 熔断线（校验器按 tier 分级验）。
- **不许承载确认性主结论**：claims 不许 confirmatory=true（校验器
  拦）；渲染带「极简设计 · 不承载确认性结论」横幅。
- 要承载确认性结论：补全完整级字段（功效核算、干预核查点、主
  指标惯例出处等）、升 tier=full、重过 reviewed 与定版评审。

## 硬纪律（校验器写死，SKILL 规程只许加强不许放宽）

1. **主张先行**：primary_claims ≤2、anti_claims 非空、每主张带最低可信
   证据；实验条目指不回主张者即愿望清单（约束 1）。
2. **判读见结果前冻结**：readout 三向（positive/negative/null）写死；
   登记头声明结果可见性五档；第 5 档（results_seen）与功效不足时
   不许保留确认性主张——给不起就下调声称（约束 2/9，拍板 ②）。
3. **对照先行**：status_quo 对照必填；处理组 run 必须把其对照 run
   列入 depends_on，依赖图无环（约束 3，拍板 ⑥）。
4. **干预真改变且留证**：intervention_checkpoints 预置核查点（约束 4）。
5. **效度四分法**：结论/内部/构念/外部逐类登记、逐项三态
   （na/mitigated/residual 且必附注），整类缺失即不完整（约束 6）。
6. **比较三支柱**：种子数与重复数预先定明、调参对等条款必填、
   重复层级明示（约束 7/8）。
7. **冻结后只追加**：frozen 正文哈希校验防回改；修订只走 amendment，
   命门字段（判读标准/主指标/主张/停止规则）必须用户签（约束 12，拍板 ⑤）。
8. **打回纪律**：交接六项未齐不许离开 draft；缺项回 Idea 回补，
   Design 不许自行发明口径（草案 §4）。
9. **评审异族**：定版评审与设计生成不同模型家族；REVIEW_UNAVAILABLE
   只许停不许过（拍板 ①）。
10. **aux 物理分离**：辅助信号只进 aux 且不进任何判定（约束 13）。

## 状态机

```text
draft ──→ reviewed ──→ frozen（终态；修订只走 amendment）
  │           │
  ├─→ returned（打回 Idea，附缺项清单；回补 resolved 后回 draft）
  └─→ blocked（外部条件未备，附解阻条件；解阻后回 draft）
```

状态只许由产物驱动（校验记录、评审记录、冻结哈希），不许口头推进。

## 交付前自检清单（定版/交接前逐项过）

- [ ] validate 全过（不是「差不多」：逐条错误清零）
- [ ] intake 六项 accepted/expanded、无未清打回项、原始问题逐字在位；
  expanded 项已过跨区实体核查（DES-D04：对应区查得到实体）
- [ ] 承接卡的定版状态已核对：未定版卡只许作演示/预演承接且须在
      报告中明示，不许冒充正式定版交接；打回往返（returned ↔ draft）
      记录完整在案、未删改
- [ ] 每条 run 指得回主张或 anti-claim；无愿望清单条目
- [ ] 消融逐条 what_it_tests + expected_if 已落字；不做消融已登记理由
- [ ] status_quo 对照在场；处理组 depends_on 含其对照；拓扑序可排
- [ ] 功效：SESOI 有据、derived 与 seeds/repetitions 对账、敏感性范围已写；
      sufficient=false 时声称已下调并落字
- [ ] 功效（分组设计）：design_size 落格为精确解产出（route=nct_exact/
      ncf_exact）、achieved_power ≥ target_power、sensitivity_table 逐行
      达标；无 z 口径 n 冒充产出；σ/f 前提依据已在 power.basis 落字
- [ ] SESOI 结构化登记：evaluation.sesoi 七字段齐全、direction 与主指标
      一致；登记行派生副本逐字段一致（确认性设计缺一不可）
- [ ] 效度四类齐全、逐项三态 + note；结构错误清单逐项自查完
- [ ] 登记头可见性档位与实际进度相符（已看结果不许报 no_runs_yet）
- [ ] 评审包已 prepare；评审者异家族；五条逐项 + note 齐全；收据已落盘
      （或 REVIEW_UNAVAILABLE 显式降级并知会用户）
- [ ] 每条 amendment 类别已声明；命门 amendment 增量评审已落盘
  pass（或 REVIEW_UNAVAILABLE 显式落字且导出件已注明，DES-D02）
- [ ] 冻结后 export 四件套齐全；expected_registry 与 runs 一一对应
- [ ] DESIGN_REPORT 已 report 刷新；偏离/amendment 计数与实际一致
- [ ] aux 区无判定字段混入；所有分数类信号标注「暂定」

## 三期演示小结（2026-10-20，examples/demo-poultry-design/）

以 light-idea 演示 top 卡 C1「零调参阈值预测」（idea_id
`zero-tuning-tracker-thresholds-predicted_77cdb7`）为输入跑通全链，
全过程与逐字门记录见演示目录 demo-report.md。要点：

- **承接前提如实标注**：C1 在 Idea 侧未定版（pre_mortem_passed，
  跨模型硬门未过），本演示承接的是「规格完备但未定版」的卡，属
  演示安排、不冒充正式定版交接——正式流程只消费定版卡，本演示
  验证的是 Design 侧机制全链。
- 主设计（完整级）承接 6/6，一次校验零错误 → reviewed；review
  prepare 生成自包含评审包；本环境无异家族模型，走
  REVIEW_UNAVAILABLE 落盘（收据 RV-5baf031de4），advance frozen
  被 8 条门**如实拦下**，export 亦被拒（2 条缺口）。**演示终点 =
  reviewed + 评审包就绪**，与 Idea 演示同构：不定版、不停工、
  不伪造收据；多模型环境中一次异家族评审回填即可定版导出。
- 缺项变体（人为删交接件 metrics/ablations 两项）：new 当场列
  打回清单 → reviewed 被承接门逐项点名拦下 → returned → 回补
  （重新承接 + 逐项 resolved，往返记录不删）→ 回 draft，打回
  纪律全流程走通。
- 极简级小设计（MOT17 映射存在性判别）：底线六件齐全、校验
  通过、渲染带「不承载确认性结论」标注，停 draft 不评审冻结。

## 已知边界（v1.0 封版口径，如实标注）

- 本技能的真实定版（frozen + 四件套导出）尚未在多模型环境中
  走通：演示终点止于 reviewed + REVIEW_UNAVAILABLE，与上游卡
  的跨模型硬门是同一个环境限制；流程与补完路径已验证到门口。
- amendment 的**增量评审**已命令化（v1.1 DES-D02）：命门 amendment
  待审拦导出、两轨分流、降级落字均落代码；残余边界是评审判定质量
  仍靠评审者规程，工具只验结构、异家族与影响面圈定（与定版评审同界）。
- `advance --to returned` 的打回单（return_record）须由执行者
  先行写入 design.yaml：CLI 尚无把 intake 打回清单一键组装为
  打回单的命令（演示中为手工落字后推进）。
- intake 的 `expanded`（展开承接）已由校验器做跨区实体核查
  （v1.1 DES-D04，映射表在 schema 冻结）；残余边界是核查只验实体
  「在场」，实体内容与交接原值的口径一致性仍靠定版评审。
- 评审包的判定质量靠评审者规程（packet 内须知 + 五条标准），
  工具只验结构完整与异家族，不验判定内容质量（与 Idea 查新
  同界）。
- 功效替代口径中的方差前提（如段间 SD 估计）设计期无法验证，
  只能以敏感性范围 + 熔断线对冲，执行期须按实测复核。
- 功效求解器（v1.2）的覆盖面是等分配的双臂 t / 配对 t / 单因素
  ANOVA 三形态 + 结构化敏感性表；不等分配、协变量调整（ANCOVA）、
  多重比较校正后的功效、生存/计数结局与混合模型的功效未供给，
  这类设计仍走替代口径并在 power.method 落字说明不用求解器的
  理由。求解前提（正态、等方差、σ/f 取值）本身不被求解器验证，
  前提依据与敏感性对冲仍按 D3/D5 规程第 1/3 条办。
- 对账回填（Experiment 执行结果、Analysis 按登记表判定）不在
  本技能范围；本技能只保证登记表可对账（readout 三向 + 现行
  哈希）。
- 校验器只验可机械验项；抉择质量（基线够不够强、消融是否对准
  替代解释）靠规程 + 定版评审（拍板 ④双层），不假装可验。
