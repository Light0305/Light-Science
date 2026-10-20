# Light-Experiment

按 Light-Design 的**冻结设计书**执行实验，产出与设计书逐项对账的**执行包**
（Light-Science 子技能）。

**当前版本：v1.0**。三条质量纪律：承接对不齐逐条打回、执行端不许
临场补设计；一切留痕只增不改（事件流 append-only、身份开跑冻结、
作废只追加）；对账只做事实层，正式判定归 Analysis。设计依据
（普查/深读/设计草案）属开发档案，不在本仓库内。

## 快速开始

```bash
python -m venv .venv && .venv/bin/pip install -e ".[test]"

.venv/bin/light-experiment init ./my-direction --direction "番茄病害检测"
# 消费 Light-Design 导出的交接四件套（exports/<design_id>/ 目录）：
.venv/bin/light-experiment intake ./my-direction \
    --from-export ../design-proj/exports/<design_id>
# → 承接齐全时按 brief 条目各建一条 planned run，并生成对账占位表；
#   有缺口时逐条列打回清单（执行包停在 intake，不许开跑）。
.venv/bin/light-experiment run-start ./my-direction <exec_id> R01-a1 \
    --spec ./run-spec.yaml        # 身份下限全过才许开跑，开跑即冻结哈希
.venv/bin/light-experiment run-finish ./my-direction <exec_id> R01-a1 \
    --exit-status completed --metrics-file ./metrics.jsonl --gpu-hours 2
.venv/bin/light-experiment validate ./my-direction <exec_id>
.venv/bin/light-experiment advance ./my-direction <exec_id> --to sanity
.venv/bin/light-experiment render ./my-direction <exec_id>
# 验收 / 偏离子流程（详见 SKILL.md 操作规程）：
.venv/bin/light-experiment acceptance init ./my-direction <exec_id>
.venv/bin/light-experiment acceptance record ./my-direction <exec_id> R02:result \
    --verdict pass --evidence-run R02-a2 --observed 99.1 --expected 100
.venv/bin/light-experiment deviation raise ./my-direction <exec_id> \
    --type config --dimension config --description "..." --disposition void_and_rerun
.venv/bin/light-experiment failure classify ./my-direction <exec_id> \
    --run R01-a1 --mast FM-1.3 --class implementation --retry-guidance "..."
.venv/bin/light-experiment reconcile fill ./my-direction <exec_id> R01 \
    --readout readout.json --random-sources sources.json --layers layers.json
.venv/bin/light-experiment budget check ./my-direction <exec_id>
.venv/bin/light-experiment export-card ./my-direction <exec_id>
```

run 规格（`--spec`，JSON/YAML）字段：`config`（最终配置全文）、`params`、
`code_snapshot{hash, git_commit, git_dirty}`、`data_version`、
`environment{declaration, machine_tier}`、`root_seed`、
`intervention_checks`（可选）、`cold_start`（可选：声明本 run 为
干净环境冷启动重跑，开跑时钉进事件锚，作验收证据真伪凭据）。

## 执行包结构（executions/<exec_id>/）

| 文件 | 内容 |
|---|---|
| `execution.yaml` | 登记头：design_ref（design_id + 冻结哈希 + amendment 数）、包级状态、budget_ledger 预算总账（limits/spent + 设计侧预算与熔断线快照）、intake_report（缺口清单 + 登记行 id）、brief/registry 快照 |
| `runs/<run_id>/run.yaml` | 逐 run 记录（见下表四区）；run_id = `<brief 条目 id>-a<attempt 号>` |
| `events.jsonl` | 轨迹事件日志（只增）：seq 连续、event_id 由序号派生、ts 不倒退 |
| `reconciliation.yaml` | 对账表（行与 expected_registry 逐行对齐；实质回填：分布读数 + 随机源清单 + 三层事实判定，`substantive` 标记进入实质对账） |
| `baseline_acceptance.yaml` / `.md` | 基线复现验收表：三层叶子 + 冻结哈希 + 逐叶判定与冷启动证据指针（.md 为渲染视图） |
| `deviations.jsonl` + `deviation_notices/` | 偏离只增账（raise/publish/apply/override 折叠）与生效清单公示文件 |
| `failures.jsonl` | 失败只增账（classify 落双层分类，review/reflux_status 追加） |
| `reflux/` | 回流条目：retry_queue.jsonl / design_inbox.jsonl / idea_dossiers/*.md |
| `execution_card.json` | 给 Analysis 的结构化投影（export-card 导出） |
| `artifacts/` | 内容寻址产物池目录（产物以路径 + sha256 登记在 run.yaml） |
| `EXECUTION_REPORT.md` | 渲染报告（摘要视图）：状态/退出分布、预算总账、验收/对账/偏离/失败分布、事件摘要 |

### run.yaml 四区 + 注释区

| 区 | 字段 | 可变性 |
|---|---|---|
| 承接区 | `intake.design_ref` / `brief_row` 快照 / `registry_line` 指针 / `depends_on` | 冻结 |
| 身份区 | `config` 配置全文、`code_snapshot`、`data_version`、`environment`、`seeds{root_seed, derivation, derived_seed}`、`params` + `params_hash`、`identity_hash`、`birth_certificate`（逐维成分哈希）、`intervention_checks[]`、`lineage{origin_run, retry_of, reused_segments[]}`、`backend`（预留） | run-start 时定型冻结，校验器逐项重算 |
| 观测区 | `timeline`、`attempts_budget`（attempts/墙钟/GPU 时/API 成本）、`metrics_ref`（文件 + sha256）、`artifacts[]` | 只增 |
| 结论区 | `exit_status`（终止分类词表）、`failure_ref`、`salvage[]` + `salvage_note`、`reconciliation` 指针 | 终态落字后不可改（与 run_finished 事件锚互验） |
| 注释区 | `tags` / `note` | 唯一可变区 |

身份哈希口径（草案 §2.7，写死在 schema）：`identity_hash =
sha256(规范化JSON{config, code_snapshot.hash, data_version, environment})`；
派生种子：`int(sha256(f"{root_seed}|{run_id}")[:8], 16)`。

## 状态机门规则清单

run 级：`planned → running → completed / failed / deviated → reconciled`

| 跃迁 | 门 |
|---|---|
| planned → running（run-start） | 身份下限五项齐全（配置全文 / 根种子+派生规则 / 代码快照哈希 / 数据版本 / 环境声明），缺项逐条点名；过门即冻结 identity_hash、params_hash、出生证明并写入 run_started 事件锚 |
| running → completed/failed/deviated（run-finish） | exit_status 必须属终止分类词表；failed 必须有抢救产物登记或显式无可抢救声明 |
| completed/failed → deviated（deviation apply） | 偏离闭包作废：生效清单已公示、run 不在 running/reconciled；作废标记 voided_by 只追加 |
| */terminal → reconciled（advance --run） | exit_status 已落字；failed 须有抢救登记；deviated 须有处置依据（voided_by 或推进注记） |
| reconciled → * | 终态，无出边（校验器对 status_history 同步验） |

包级：`intake → sanity → executing → reconciling → delivered` + `blocked` 旁路

| 跃迁 | 门 |
|---|---|
| intake → sanity | intake_report.gaps 为空（承接缺口未清零不开跑） |
| sanity → executing | 至少有一条 run；且基线复现验收门：brief 有基线条目或验收表已生成时，验收 verdict 必须 passed |
| executing → reconciling | 无 run 停在 planned/running |
| reconciling → delivered | 全部 run 已 reconciled + 对账行与登记行逐行对齐 + 对账清零硬问题（缺行/blocked/作废未替代）为零；已进入实质对账的包 pending 行也拦；偏离在场须全处置、失败在场须全分类 |
| * → blocked | 须带阻塞原因 + 解阻条件；只许回到受阻前状态；delivered 不许转 blocked |

## 开发记录（节略）

- 一期：项目骨架 + 执行包系统（execution.yaml / run.yaml 四区 /
  events.jsonl / 对账占位）+ 双层状态机 + 确定性校验器，
  51 个测试。
- 二期：基线复现验收子流程（E1）、偏离登记与闭包作废（E4）、
  失败分类与回流（E5）、对账实质化（E6）、预算闸（E2 补），
  85 个测试；反例集逐项覆盖（缺出生证明拦截、篡改 params
  重算检出、自报结果冒充验收证据拦截、熔断线被执行端放宽
  点名、闭包漏算校验、作废未替代对账拦截等）。
- 三期：端到端演示实跑 + SKILL 定版。因上游真实冻结设计尚
  不存在（其定版需异家族评审），演示用与上游导出同形态的
  **合成四件套**（哈希自洽、自签冻结，身份在演示报告中明示，
  不冒充真实评审冻结）承接一个三臂判别实验的模拟计算：
  缺项变体打回 → 基线冷启动重跑验收过门 → 三臂执行 →
  params 篡改检出与偏离闭包作废 + 替代 run → 数据版本缺段
  的 fundamental 失败分类与回流 → 长 run 杀进程后凭内容
  哈希复用恢复 → 对账清零 delivered。演示中另实测两条纪律：
  篡改修复只许外科式改回锚定字段（整文件回滚会抹掉作废
  标记）；替代 run 须在原 run 对账前建（终态不可作恢复源）。
  冷启动的「干净环境」在演示中以新进程 + 空目录 + 仅提交物
  近似，未做容器隔离，如实标注。演示产物属开发档案，不在本
  仓库内（结构示意见 examples/README.md）。

## 已知局限总表（v1.0 封版口径，如实标注）

1. 对账只做事实层：readout 三向正式判定归 Analysis 回写；本包
   status=filled 只表示事实材料齐备可判。
2. 干预核查点只存档不核验：intervention_checks 随 spec 落身份区，
   声称值 vs 实际生效值的机械核验未做。
3. 产物池仍为登记制：salvage/metrics/验收证据以路径 + sha256
   登记，内容寻址拷贝入 artifacts/ 池未做；登记文件事后被改，
   哈希可复核但工具不主动巡检。
4. 自动捕获未做：git/环境等系统标签仍由 spec 声明；冷启动标记
   亦为 spec 声明 + 事件锚钉住——锚保证声明在开跑时作出且事后
   不可改，但「环境是否真的干净」验不了，靠规程与抽验；开发期
   演示的冷启动以新进程 + 空目录 + 仅提交物近似，未做容器
   /VM 级隔离，且模拟为确定性种子（读数逐字一致是构造性质）。
5. 闭包口径为条目级依赖图 + 锚匹配：brief depends_on 只到条目
   粒度；条目内 attempt 间经中间产物的数据流污染不在图内。
   另：input 与 data 两类触发器在本工具出生证明里同属
   data_version 维（口径写死在 schema.TRIGGER_ANCHORS）。
6. 失败分类是登记纪律而非智能诊断：MAST 码由执行者按根因选，
   工具只验词表与附带字段；分类质量靠人工抽验。交付门要求
   一切非 completed 终止都落分类（含 killed_external 外部
   中断——分类指向恢复路径而非追责）。
7. 预算账为登记制：GPU 时/墙钟由 run-finish 登记，工具不实测；
   无进展检测（StuckDetector 式）未做，killed_no_progress 与
   心跳/DEAD 判据均为规程 + 事件留痕，工具不内置守护巡检。
8. 承接校验仍为草案 §4 子集：零占位符扫描、干预核查点齐备
   检查、依赖计划产出未补。
9. 执行为规程执行（拍板 ① = C）：工具不托管子进程/容器，run
   记录预留 backend 字段。
10. 篡改修复纪律（演示实测）：run 记录被篡改后只许外科式改回
    锚定字段并全程留痕；整文件回滚会抹掉 voided_by 等只追加
    记（终局校验可检出），且作废处置不因修复撤销。
11. 恢复顺序约束（演示实测）：--retry-of 只接已终止未对账的
    尝试（completed/failed/deviated），reconciled 终态不可作
    恢复源——替代 run 必须在原 run 对账前建好。
12. 有偏估计自动警告可能过度触发（演示实测）：警告按「只换
    种子 + 冻结其余」机械生成，无调参成分的锚臂行（演示中
    R-FIX/R-ORA）也会中招；警告只作标记，逐行裁定靠人并记入
    报告，不改登记事实。
13. 真实链路未走通：Design 定版冻结 → 真实四件套 → 本技能
    承接，待多模型环境补完 Design 侧异家族评审；演示输入为
    合成设计（身份已明示），承接校验口径未为演示降低。
