---
name: light-experiment
description: Use when 需要按已冻结的设计书真正执行实验：逐 run 留痕、登记偏离与失败、与预期登记对账，或向分析阶段交付执行包时。
version: "1.3"
author: light-experiment contributors
license: MIT
---

# light-experiment

按 light-design 的**冻结设计书**执行实验：照单跑、逐 run 留全痕、与预期
登记逐行对账，把「跑了什么、得到什么、偏了什么、失败在哪」封装成
Analysis 可直接消费的**执行包**。
设计依据：`04-experiment/REDESIGN-DRAFT.md` v0.1（含 2026-10-20 用户
拍板 7 项）与 `04-experiment/LEARNING.md` 十三条硬约束。

**当前版本：v1.0（封版，2026-10-20）**——一期：项目骨架 + 执行包系统
（execution.yaml / run.yaml 四区 / events.jsonl / 对账占位）+ 确定性
校验器 + 双层状态机。二期：基线复现验收子流程（E1）、偏离登记与
闭包作废（E4）、失败分类与回流（E5）、对账实质化（E6）、预算闸
（E2 补）。三期：端到端演示（合成/预演设计、明示身份）全程实跑 +
本文件定版。演示结论见文末「三期演示小结」，局限见「已知边界」。

## 定位与边界

- 输入：light-design 交接四件套（只消费 **frozen** 设计）。哈希/行对应
  对不齐 → **逐条列缺口打回，不许执行端临场补设计**（E0 打回纪律）。
- 执行端零设计决策：不改判读标准、不改主指标、不改变量取值域、不放宽
  熔断线；一切不一致走偏离登记，构成设计修订的回 Design 转 amendment。
- 事实与判定分工：执行包做**事实对账**（跑没跑、读数是多少、偏没偏），
  readout 三向的正式统计判定回写归 **Analysis**；执行包不许出现
  「改进成立」式结论。
- 执行深度（拍板 ① = C）：v1 工具只管承接校验 / 记录 / 对账，实际执行
  由接入模型按规程调用用户环境完成；run 记录预留 `backend` 字段供
  v2 接内置运行器。

## 能力环（E0–E6）与落地

| 环 | 职责 | 落地 |
|---|---|---|
| E0 执行承接与对齐校验 | 消费四件套、冻结哈希与 amendment 链核对、缺项打回 | `intake` + intake_report + 打回门（v1.1 EXP-D04 补齐草案 §4 全集：零占位符扫描 + 干预核查点齐备检查 + 依赖计划产出 execution_plan.md） |
| E1 基线复现 | 照复现入口跑基线、rubric 对账、冷启动重跑验收（拍板 ③ 硬要求） | `acceptance init/record`：三层叶子验收表冻结、证据只认冷启动重跑、验收门挂 sanity → executing |
| E2 编排与预算 | 拓扑序调度、三层预算闸、熔断只许停不许改（拍板 ⑤）、恢复 = 新 run + 血缘（拍板 ②） | attempts 预算账 + budget_ledger 总账 + `budget check`（触发落事件 + killed_budget 候选；无放宽命令）+ run-new --retry-of 血缘 |
| E3 留痕与轨迹 | run 记录字段下限、事件只增、产物内容寻址登记 | run.yaml 四区 + events.jsonl + Sacred 下限校验 + 开跑自动捕获 / 内容寻址产物池 / 无进展巡检（第四批：capture.py 入池与实测落账、watchdog.py 扫描式巡检，validate 主动巡检池对象） |
| E4 偏离与异常 | 偏离登记、闭包作废（拍板 ④ 自动算 + 公示 + 显式覆写口）、处置 | `deviation raise/publish/apply/override`：出生证明逐维比对 + 依赖图传递闭包、生效清单公示、作废只追加；干预核查点机械核验（v1.1 EXP-D03：run-finish 时三类核验器比对声称 vs 实际生效值，不符自动转 deviated 候选）；`stale` 开工前预检视图（v1.1 EXP-D02：现行哈希链逐维比对出三态清单，只读） |
| E5 失败诊断与回流 | exit_status 分类学、MAST × IVE 双层分类、自动回流条目（拍板 ⑥）、失败预算制 | `failure classify/review` + `reflux list/update`：分类落定自动生成回流条目、同签名 2 补丁 + 2 重写上限报警 |
| E6 封装与交接 | 对账表逐行回填、三层事实判定、未清零不交付、向 Analysis 交付 | `reconcile fill/check`（只收分布不收单点）+ delivered 门 + `export-card` 投影 |

## 命令面

```bash
light-experiment init <dir> --direction <方向名>
light-experiment intake <project> --from-export <Design exports/<design_id> 目录>
light-experiment run-new <project> <exec_id> <design_run_id> [--spec <规格.yaml>] [--retry-of <run_id>]
light-experiment run-start <project> <exec_id> <run_id> [--spec <规格.yaml>]
light-experiment run-finish <project> <exec_id> <run_id> --exit-status <终止分类> \
    [--metrics-file <文件>] [--stdout-file <文件>] [--stderr-file <文件>] \
    [--salvage <抢救产物> ...] [--no-salvage] [--mark-deviated] \
    [--wall-clock-s N] [--gpu-hours N] [--api-cost N]
light-experiment event <project> <exec_id> --type <事件类型> [--run-id <run_id>] [--payload <JSON>]
light-experiment validate <project> <exec_id>
light-experiment advance <project> <exec_id> --to <包级状态> [--reason <阻塞原因> --unblock <解阻条件>]
light-experiment advance <project> <exec_id> --run <run_id> --to reconciled
light-experiment list <project> [<exec_id>]
light-experiment render <project> <exec_id>
# 二期
light-experiment acceptance init <project> <exec_id> [--runs <条目,逗号分隔>] [--threshold F] [--tolerance-pct F]
light-experiment acceptance record <project> <exec_id> <leaf_id> --verdict pass|fail \
    --evidence-run <冷启动重跑 run_id> [--evidence <文件> ...] [--observed X --expected Y --variance Z]
light-experiment acceptance show <project> <exec_id>
light-experiment deviation raise <project> <exec_id> --type <类型> --disposition <处置> \
    --description <偏离了什么> [--run-id <发现上下文 run>] [--dimension <触发维>] \
    [--claimed <声称值> --actual <实际值>] [--declared <人工估计集,逗号分隔>]
light-experiment deviation publish <project> <exec_id> <deviation_id>
light-experiment deviation apply <project> <exec_id> <deviation_id>
light-experiment deviation override <project> <exec_id> <deviation_id> --runs <豁免集> --by <覆写者> --reason <理由>
light-experiment deviation list <project> <exec_id>
light-experiment failure classify <project> <exec_id> --run <run_id> --mast <FM-x.y> \
    --class implementation|fundamental [--root-cause ...] [--boundary ...] \
    [--retry-guidance ...] [--attempt-kind patch|rewrite] [--idea-bound]
light-experiment failure review <project> <exec_id> <failure_id> --reviewer <抽验人> [--agrees|--no-agrees]
light-experiment reflux list <project> <exec_id>
light-experiment reflux update <project> <exec_id> <entry_id> --status pending|sent|resolved
light-experiment reconcile fill <project> <exec_id> <row_id> --readout <JSON> \
    --random-sources <JSON> --layers <JSON> [--evidence <指针> ...]
light-experiment reconcile check <project> <exec_id>
light-experiment budget check <project> <exec_id>
light-experiment export-card <project> <exec_id> [--out <路径>]
# 三期（v1.1）
light-experiment stale <project> <exec_id> [--spec <现行状态声明文件>] \
    [--out-json <路径>] [--out-md <路径>]
# 第四批（捕获 / 产物池 / 无进展巡检）
light-experiment artifact add <project> <exec_id> --run <run_id> --file <文件> [--kind <类别>]
light-experiment artifact verify <project> <exec_id>
light-experiment artifact list <project> <exec_id>
light-experiment watchdog scan <project> <exec_id> [--threshold-s <秒数>] [--now <ISO 时刻>]
```

run 规格（`--spec`）在身份下限五项之外可带 `cold_start: true`：声明本
run 是干净环境冷启动重跑——开跑时钉进 run_started 事件锚，作 E1 验收
证据的真伪凭据（事后回填冒充，锚不一致即被校验器检出）。

run 规格另可带 `command`（命令行文本）与 `input_files`（输入文件
路径清单）供开跑捕获（第四批）：路径与命令文本由 spec 声明
（provenance=declared），输入文件的 sha256 与字节数由工具在
run-start 时逐个实测落账（provenance=captured）；声明的输入
文件不存在即拦开跑，不许带病开跑。

run 规格的 `intervention_checks` 每条在 `point`（核查点名）与
`claimed`（声称值）之外应带 `verify`（v1.1 EXP-D03）：`verify.kind`
三类核验器之一——`equals`（数值/标量相等；声称给列表时按取值集比
对）、`range`（声称给 `{min, max}` 区间，实际值须全落区间内）、
`file_hash`（声称给 sha256，实际文件字节哈希须一致）；
`verify.source` 给实际值来源指针：`{file, key}` 从 JSON/JSONL 文件
机械取键，`file` 可写 `@metrics` 指代本 run 在 run-finish 登记的
`--metrics-file`。无 `verify` 的核查点是 v1.0 存档形态，终止时如实
报 not_verified，不冒充已验。

## 硬纪律（校验器/状态机写死）

1. **只消费 frozen**：四件套哈希与 design_card 现行哈希（amendment 链尾）
   对不上即打回；承接缺口未清零不许进 sanity、不许建 run。
2. **身份开跑冻结**：run-start 时 identity_hash（配置全文 + 代码快照哈希 +
   数据版本 + 环境声明）、params_hash、出生证明一次落字并钉进 run_started
   事件；之后改 params/身份任一维，校验器重算即报错——改参数 = 新 run。
3. **字段下限（Sacred 对表）**：配置全文、根种子 + 派生规则、代码快照
   哈希、数据版本、环境声明，缺一项点名一项，不许开跑。
4. **终止必须分类**：exit_status 只许词表内取值（completed / failed_* /
   killed_budget / killed_no_progress / killed_external / forfeited /
   stuck / context_exhausted）；「执行失败」式自由文本落不了字。
5. **失败先抢救**：失败终止必须登记抢救产物（文件 + sha256）或显式声明
   无可抢救，只留一句报错视为留痕不合格。
6. **轨迹只增**：events.jsonl 序号连续、时间戳不倒退、event_id 由序号
   派生；摘要视图（EXECUTION_REPORT）是投影不是本体；轨迹全量 + 摘要
   双份（拍板 ⑦）。偏离/失败/回流三本登记同为只增账，状态变更靠追加
   条目折叠呈现，没有改写入口。
7. **恢复 = 新尝试**：--retry-of 只接已终止的 run，新 run 独立成号、
   lineage 指回；复用段必须带被复用 run 的 identity_hash 作证据——
   复用判据是内容哈希，禁「同名即复用」（拍板 ②）。
8. **终态不可逆**：run 的 completed/failed/deviated 只许去 reconciled
   （或被偏离作废时先转 deviated），reconciled 无出边；结论区与
   run_finished 事件锚对不上即报错。
9. **未清零不交付**：delivered 门 = 全部 run 已 reconciled + 对账行与
   预期登记逐行对齐 + 无 run 停在 deviated；二期加：对账清零检查的
   硬问题（缺行 / blocked / 作废未替代）恒拦，包一旦进入实质对账
   （reconcile fill 用过）pending 行也拦；偏离登记在场时须全处置、
   失败登记在场时失败 run 须全分类。
10. **熔断只许停不许改**（拍板 ⑤）：熔断线随 brief 冻结交付（承接快照
    circuit_breakers 为准），`budget check` 触发即落 budget_event 并
    登记 killed_budget 候选；工具**没有**任何放宽熔断线的命令，
    ledger.limits 被抬到线之上由校验器点名「熔断线被执行端放宽」；
    上调只能回 Design 走 amendment。
11. **验收证据只认冷启动**（拍板 ③）：基线复现验收的每条叶判定必须
    指向一条带冷启动锚的独立重跑 run；执行期产物冒充在登记时即被
    拒。验收表生成后冻结（leaves_hash），改表走偏离登记。
12. **作废靠算不靠点名**（拍板 ④）：偏离的影响集由工具按出生证明
    逐维比对 + brief 依赖图传递闭包算出，与人工估计分开落字；生效
    清单先公示后作废；作废标记只追加 voided_by；覆写豁免必须留名
    留理由，且在报告中标红——被豁免 run 的溯源链自此带人工担责标记。
13. **失败双层分类**：exit_status → MAST 转译码（按根因不按症状）→
    IVE 二分类定回流；fundamental 须 root_cause + boundary_conditions、
    implementation 须 retry_guidance（与 Idea 杀卡同规则）；分类落定
    自动生成回流条目，改设计/修订想法的**决策仍归下游与用户**
    （拍板 ⑥）；自动分类只作初筛，进回流决策前人工抽验
    （failure review 落痕）。同签名失败 2 补丁 + 2 重写封顶，超限报警。
14. **对账只收分布**：readout_actual 只收 {mean, spread, n,
    replication_level} 分布摘要，单点/伪分布（n<2）登记时即拒；
    random_sources 逐行落字，只换种子且冻结其余自动标「有偏估计」。
15. **干预声称必须机械核验**（v1.1 EXP-D03）：带 verify 的干预核查
    点在 run-finish 时由工具从产物机械读取实际生效值与声称值比对
    （三类核验器），逐条结论落结论区 + intervention_check 事件锚；
    不符（fail）或实际值取不到（unverifiable）时 completed 终止
    自动转 deviated 候选并点名——工具没有手工标 pass 的入口，
    执行者自述的实际值一律不作数。校验器以事件锚对账核验记录，
    结论区回改即暴露。
16. **字段来源分开落字**（第四批）：开跑时工具实测落账的捕获字段
    （git 状态、环境指纹、执行者、声明输入的实测哈希）标
    provenance=captured，捕获块整体哈希钉进 run_started 事件锚，
    改捕获记录即锚不符；spec 声明字段（身份区、命令文本、冷启动
    标记）标 declared 或以身份锚钉住——声明不许冒充实测，实测
    不许覆盖声明。identity_hash 仍是声明身份（复现判据），捕获
    块是实测环境证据，两者并存对读，分工不混。
17. **产物入池、池可巡检**（第四批）：run-finish 的 metrics /
    salvage / stdout / stderr 与 artifact add 的产物一律按内容
    哈希拷入 executions/<exec_id>/artifacts/ 内容寻址池，run 记录
    以 sha256 + pool_ref 引用（同内容只存一份）；validate 主动
    巡检池对象（缺失 / 字节重哈希与地址不符逐条点名），登记在
    账、池里没货或货被改都不许静默过关。无 pool_ref 的旧登记条
    是存档形态，只验哈希登记本身。
18. **无进展判定只留痕不代杀**（第四批）：watchdog scan 对
    running 的 run 按最近进展事件（step / observation /
    heartbeat / 干预核验 / 人工检查点等）计时，闲置 ≥ 阈值（默认
    3600 秒，可配）判 no_progress——判定落 no_progress_verdict
    事件 + 列候选，同一进展状态只落一条；正式终止仍走
    run-finish --exit-status killed_no_progress，工具不代杀、
    不自动改 run 状态（与预算熔断候选同纪律）。

## 操作规程

### E1 验收规程（sanity 阶段内完成）

1. 进 sanity 后、开任何主清单 run 之前：`acceptance init` 冻结验收表
   （对象 = brief 的 baseline 条目；粒度自查：每片叶子应 15 分钟内可判）。
2. 照 reproducibility 入口在**执行环境**先跑基线（普通 run 留痕）；
   再在**干净环境**只凭提交物 + 单一入口脚本冷启动重跑（新 attempt，
   spec 带 `cold_start: true`）——验收证据只取后者。
3. 逐叶 `acceptance record`：判定二值、证据指向冷启动 run；结果层叶
   带 --observed/--expected（与报告方差），偏差超容差（默认 2%）且
   不在报告方差内判 pass，登记环节即拒收（D-EXP-1）；校验器对落盘
   状态同口径点名。
4. verdict=passed 才许 advance 到 executing，且 advance 前复跑叶级
   容差校验（与校验器同口径，落盘冒判不作数）；未过先走 E5 诊断归因
   （种子 / 数据版本 / 未报告技巧三项清单），修实现重试或回 Design
   报告基线不可复现——不许带病开跑主实验后在结论里解释。

### E4 偏离规程

1. 发现偏离**先登记后处置**：`deviation raise` 写明偏离了什么、声称
   vs 实际、触发维与处置意向；人工估计的影响集照实填（与闭包分开
   落字是纪律，不是走过场）。
2. `deviation publish` 生成生效清单公示（哪一维变了、将作废哪些
   run）；认为闭包有误 → `deviation override` 显式豁免（留名留
   理由），不许口头放行、不许先斩后奏。
3. `deviation apply` 生效：作废走 voided_by 追加 + run 转 deviated，
   随后 advance 以作废身份 reconciled 并新开替代 run；接受并声明的，
   声明文本进对账行；构成设计修订的（stop_and_return_design）在
   raise 时已自动生成 design_amendment_draft 回流 Design。
4. running / reconciled 的 run 在闭包内 → apply 逐个点名拦下：先终止
   或先 override 豁免，不许强行作废终态。

### E5 失败规程

1. run 失败终止后（对账清零前）`failure classify`：先按根因落 MAST
   码（同症状不同根因分开记），再落 IVE 二分类；诊断结论
   （experiment-craft 五步）写进 --diagnosis。
2. 回流条目自动生成：implementation → reflux/retry_queue（本技能
   按 retry_guidance 与失败预算制重试）；fundamental →
   reflux/design_inbox；指向想法本体的加 --idea-bound 附 dossier
   草稿（经 Design 中转，不直连 Idea 改卡）。
3. 条目被下游接收/处置后 `reflux update` 推进状态；分类进回流决策
   前由第二人 `failure review` 抽验落痕。
4. 同一签名（mast + root_cause）重试计数：补丁 ≤2、干净重写 ≤2，
   超限工具报警并停——报告「计划或环境错了」，回上游决策。

### E6 对账规程

1. 主清单跑完、包进 reconciling 后逐行 `reconcile fill`：分布摘要
   （多种子/多重复的均值 + 离散 + n + 重复层级）、随机源清单
   （重随机化了什么、冻结了什么）、三层事实判定、证据指针。
2. `reconcile check` 逐行清零：缺行 / 未填 / 作废未替代逐个点名，
   全清零才许 advance delivered。
3. 交付前 `export-card` 导出 execution_card.json 随包交 Analysis；
   readout 三向判定不在本包下结论。

### E2 预算规程

- 每批 run 终止入账后跑一次 `budget check`；触发熔断的行：把候选
  run 以 run-finish --exit-status killed_budget 正规终止留痕，不许
  工具代杀无痕；要继续烧，先回 Design 走 amendment 上调熔断线。

### 干预核查规程（v1.1 EXP-D03，run-finish 内置）

1. 开跑前在 run 规格里给每条干预核查点登记 verify（核验方式 +
   来源指针）；来源优先用产物文件（metrics/summary/配置件），
   metrics 用 `@metrics` 指代，避免路径在 run 间漂移。
2. run-finish 自动核验，逐条结论只有四态（pass / fail /
   unverifiable / not_verified）；出现 fail 或 unverifiable 且本
   run 本要 completed 的，工具自动转 deviated 候选——按 E4 偏离
   规程处置（登记偏离、开替代 run），不许改核查点登记或换个来源
   文件重跑 finish 蒙混（身份区已冻结，改登记即哈希不符）。
3. not_verified 的核查点是存档形态遗留：新设计承接后应在 spec
   层补齐 verify 再开跑；报告中如实呈现未核验条数，不许把
   not_verified 写成「已核验」。

### 捕获、产物池与无进展巡检规程（第四批）

1. 开跑不用另行登记系统标签：run-start 自动捕获 git 状态
   （文件级探针直读 .git，不起子进程）、环境指纹与执行者身份；
   要留命令与输入证据，在 spec 里给 command 与 input_files
   （输入开跑时实测哈希，缺失即拦）。捕获块与身份区对读：
   声明环境与实测指纹不符（如声明的机器档位与实测主机/CPU
   对不上）本身就是要上报的事实，不许改捕获块去迁就声明。
2. 产物随手入池：run-finish 带 --metrics-file / --stdout-file /
   --stderr-file / --salvage，终止后补产的用 artifact add 入池
   登记（planned 与 reconciled 拒收）；交付前跑 artifact verify
   全池体检（损坏 / 登记悬空必须清零），validate 已含逐条巡检。
3. 长 run 保活纪律：运行中周期性落进展事件（`event --type
   heartbeat` 或 step / observation），间隔须短于巡检阈值；
   每批 run 结束后（或定时）跑 watchdog scan——命中判定的 run
   二选一：确认仍在跑则补进展事件续命（新进展状态可再判），
   确认已死则 run-finish --exit-status killed_no_progress
   正规终止 + 按 E5 分类，不许对判定置之不理。

### 开工前 stale 预检规程（v1.1 EXP-D02）

1. 每批开跑前（尤其上游刚出新结果、设计刚 amendment、代码/数据
   刚动过时）跑一次 `stale`：无 --spec 时只比对设计链；要比对
   代码/数据/参数的现行状态，先把现行状态按条目写成声明文件
   再以 --spec 传入（声明制：工具不猜现行值）。
2. 清单里 stale 的 run 不许直接拿来对账消费：按逐条补跑建议
   新开 attempt；上游 stale 的条目等上游补跑完再跑。voided 是
   既成事实，不重复处置。
3. stale 只读：报告（stale_report.json + STALE_REPORT.md）之外
   不改包内任何状态；发现 stale 不等于作废——作废仍走 E4 偏离
   闭包流程（raise → publish → apply）。

## 交付前自检清单

- [ ] 承接缺口清零、四件套哈希与冻结版一致（validate 全绿）
- [ ] 作废 run 的替代已在原 run 进 reconciled **之前**以 --retry-of
      建好（reconciled 终态不许作恢复源）；任何对 run 记录的修复
      只许外科式改回被篡改字段，整文件回滚会抹掉 voided_by 等
      只追加记，本身即二次篡改
- [ ] 每条 run 身份下限齐全、哈希与事件锚一致；失败 run 均有抢救登记
- [ ] 干预核查结论已落字：带 verify 的核查点全 pass（不符已转
      deviated 并按偏离规程处置），not_verified 条数如实入报告
- [ ] 产物池体检过（artifact verify 无损坏、无登记悬空）；命中
      无进展判定的 run 已处置（补进展事件续命或以
      killed_no_progress 正规终止并落分类）
- [ ] 基线验收表已冻结且 verdict=passed（有基线条目时），证据全是冷启动 run
- [ ] 偏离全登记、全公示、全处置；override 均留名留理由
- [ ] 失败全分类（MAST × IVE），回流条目已生成且状态如实
- [ ] 预算账与熔断线对过（budget check 无未处置触发）
- [ ] 对账逐行清零（reconcile check 全绿），分布/随机源/三层判定齐全
- [ ] execution_card.json 已导出；EXECUTION_REPORT 已刷新（失败与偏离同版面）

## 状态机

- run 级：`planned → running → completed / failed / deviated → reconciled`
  （reconciled 终态；作废不是删除：被闭包作废的已终止 run 先转
  deviated，再以作废身份进 reconciled）。
- 包级：`intake → sanity → executing → reconciling → delivered`，
  旁路 `blocked`（原因 + 解阻条件齐全才许转入，只许回到受阻前状态）；
  sanity → executing 另挂 E1 验收门。

## 三期演示小结（合成/预演设计，2026-10-20）

真实 frozen 设计尚不存在（Design 演示停在 reviewed），三期演示按
草案 §1 时序声明用**合成四件套**（按 light_design.export 同形态
构造、哈希自洽、自签冻结，身份在演示目录 README 与报告中明示）
端到端实跑（examples/demo-synthetic/，报告 demo-report.md）：

- 承接：缺项变体打回 2 项（缺 reproducibility + 一行判读缺 null
  向）→ 合格件承接；sanity 内基线验收三叶全过（冷启动重跑为
  唯一证据，偏差 0.50% < 容差 2%）。
- 执行：三臂真跑（固定 72.638 / 神谕 77.887 / 预测 77.835，
  MOTA 逐段分布）；人为注入 params 篡改被校验器重算检出 →
  偏离闭包 {被篡改 run + 下游 2 条 planned} → 作废 + 替代 run
  重跑；人为注入数据版本缺段 → failed_data → fundamental 分类
  → design_inbox 回流条目自动生成。
- 恢复：长 run 中途杀进程 → 心跳静默 8.4s 判 DEAD 留痕 →
  killed_external 正规终止 + 抢救 → --retry-of 新 run 凭段输入
  内容哈希复用 2 段、重跑 4 段完成；对账 5 行清零 → delivered。
- 两处如实打折：冷启动「干净环境」以新进程 + 空目录 + 仅提交物
  近似（未做容器隔离；模拟为确定性种子，读数逐字一致是构造
  性质）；预算账为登记制，熔断触发实测在二期测试集。

v1.1 复跑（2026-10-21）：同一演示增补三项实测，终点仍 delivered
——承接三件（EXP-D04：设计级干预核查点声明承接零缺口、依赖计划
落盘、占位符扫描无命中；缺项变体仍恰打回 2 项）；干预机械核验
（EXP-D03：R-PRED 核查点 equals/@metrics 真核验，a1 与替代 run
a2 均 passed，a2 的核查点经 --retry-of 继承）；stale 预检
（EXP-D02：current 7 · stale 0 · voided 1，未比对维度如实列明）。
核验不符的反例链在单元测试集覆盖（见包 README v1.1 增补记录）。

## 已知边界（v1.0 封版口径，如实标注）

1. 对账只做事实层：readout 三向正式判定（positive/negative/null）
   由 Analysis 回写，本包 status=filled 只表示事实材料齐备可判。
2. 干预核查点机械核验已落地（v1.1 EXP-D03）：带 verify 的核查点
   在 run-finish 时机械比对声称 vs 实际生效值。残留边界：实际值
   只认文件来源（JSON/JSONL 取键、文件哈希）；非文件型证据
   （人工观察读数、外部系统界面值）无从机械读取，只能登记为无
   verify 的存档式核查点、如实报 not_verified。
3. 产物池已落地内容寻址（第四批）：run 产物（metrics / salvage /
   stdout / stderr / artifact add 补登）按内容哈希拷入包内
   artifacts/objects 池、去重存储，validate 主动巡检、artifact
   verify 全池体检。残留边界：池是**包内**池——跨执行包同内容
   不共享去重；验收证据文件（acceptance record --evidence）仍为
   路径 + sha256 登记制未入池；无 pool_ref 的旧登记条只有哈希
   登记、原文件被改只能在有人复核时发现（池内对象才是工具
   恒定巡检面）。
4. 自动捕获已落地（第四批）：run-start 工具实测 git 状态
   （文件级探针：commit / 分支 / 仓库 URL / index v2 口径的
   dirty）、环境指纹（OS/Python/主机/CPU）与执行者身份，捕获
   块哈希钉事件锚，与 spec 声明身份并存对读。残留边界：
   ①git dirty 只认 index v2 且只比跟踪文件，未跟踪文件不计、
   非 git 目录如实缺席；②stdout/stderr 是执行端交文件入池的
   交接式捕获——工具不托管子进程，无 Sacred 式 fd 级拦截，
   执行端不交即落 not_provided，不冒充；③GPU 无通用实测探针，
   仍走环境声明；④冷启动标记同为 spec 声明 + 事件锚钉住——
   锚保证「声明在开跑时作出、事后不可改」，但声明本身是否
   属实（环境是否真的干净）靠规程与抽验，工具验不了；演示
   的冷启动以新进程 + 空目录近似，未做容器/VM 级隔离。
5. 闭包口径为条目级依赖图：brief 的 depends_on 只到条目粒度，
   同条目内 attempt 间的先后污染靠锚匹配覆盖，条目内细粒度数据流
   （某 attempt 的中间产物喂给另一 attempt）不在图内。
   另：input 与 data 两类触发器在本工具出生证明里同属 data_version
   维（口径写死在 schema.TRIGGER_ANCHORS）。
6. 失败分类是登记纪律而非智能诊断：MAST 码由执行者按根因选，
   工具只验词表与二分类附带字段；分类质量靠人工抽验（κ 纪律），
   工具不代判根因。killed_external 等一切非 completed 终止在
   交付门前都须落分类（含外部中断，分类指向恢复路径）。
7. 执行为规程执行（拍板 ① = C）：工具不托管子进程/容器，run
   记录预留 backend 字段；预算账的 GPU 时/墙钟由 run-finish
   登记，工具不实测。无进展检测已落地为包内轻量巡检（第四批，
   PLAN 二选一定版）：watchdog scan 按需扫描、超时未进展机械
   判定落事件 + 列候选，工具不代杀（PLAN 的外部看门狗契约形态
   未取）；残留边界是巡检非实时守护——实时性取决于扫描调用
   频率，且只做超时判定、不做 StuckDetector 式的动作重复/
   打转语义检测；killed_no_progress 终止仍靠执行者按规程落字。
8. 篡改修复纪律（三期演示实测）：被篡改的 run 记录只许外科式
   改回锚定字段；整文件回滚会把 voided_by 等只追加记一并抹掉，
   终局校验以「作废标记未落字」检出——修复本身必须留痕
   （事件 + 偏离登记），且作废处置不因修复撤销。
9. 替代 run 的顺序约束（三期演示实测）：--retry-of 只接
   completed/failed/deviated 的尝试，reconciled 终态不可作恢复
   源——作废 run 的替代必须在其对账前建好。
10. 有偏估计自动警告按「只换种子 + 冻结其余」机械触发，在无
    调参成分的锚臂行上可能过度触发（三期演示 R-FIX/R-ORA 两行
    实测）：警告只作标记，逐行裁定靠人并记入报告，不改登记事实。
11. 承接校验已补齐草案 §4 全集（v1.1 EXP-D04）。残留边界：零
    占位符扫描的模式清单是冻结清单（schema.PLACEHOLDER_PATTERNS），
    清单外的新占位写法扫不出，靠修订清单补入；干预核查点齐备
    检查只验「声明在场」，声明内容是否对题归 Design 侧评审与
    EXP-D03 的执行期机械核验。
12. 演示输入为合成设计：真实链路（Design 定版冻结 → 真实
    四件套 → 本技能承接）待多模型环境补完 Design 侧异家族
    评审后才能走通，本技能的承接校验不为演示降低口径。
