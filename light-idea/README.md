# light-idea

Light-Science 的选题子技能：把领域缺口变成经得起查新的**定版想法卡**。
技能规范见 [SKILL.md](SKILL.md)。

**当前版本：v1.2（封版）**。七环全落地：I0 趋势与缺口感知 → I1 想法
生成（演进链 + 远域碰撞两算子）→ I2 想法结构化（想法卡 + 状态机）→
I3 facet 查新（七源实查取证 + 判定落卡）→ I4 两两对决排序 → I5 打磨
迭代（pre-mortem 独立关）→ I6 交接三件套导出。质量纪律三条写死：
查新结论只认实查证据（分数只作粗筛辅助，不进判定区）；判想法死刑
（ABANDON）必须点名一篇已发表的在先论文；定版必须过跨模型收据
硬门与「最接近工作全部经 light-literature 核实」门，缺一不可。

> 开发说明：设计草案、学习期深读文档与完整验收记录属开发档案，
> 不在本仓库；本仓库只有产品本体。

## 快速开始

```bash
python -m venv .venv && .venv/bin/pip install -e ".[test]"

.venv/bin/light-idea init ./my-direction --direction "番茄病害检测"
.venv/bin/light-idea new ./my-direction \
    --title "Self-supervised pretraining for tomato leaf disease" \
    --one-liner "用自监督预训练缓解小样本番茄病害分类" \
    --operator evolution_chain --provenance "演进链 LC-001 尾端外推"
# 填充 cards/<idea_id>/idea.yaml 后：
.venv/bin/light-idea validate ./my-direction <idea_id>
.venv/bin/light-idea dedup ./my-direction
.venv/bin/light-idea advance ./my-direction <idea_id> --to screened
# 查新：取证 → 把证据包交另一模型家族判定 → 落卡 → 过查新门
.venv/bin/light-idea novelty prepare ./my-direction <idea_id>
.venv/bin/light-idea novelty verdict ./my-direction <idea_id> \
    --verdict PROCEED --judge-model <判定模型> --judge-family <其家族> \
    --executor-model <执行模型> --executor-family <其家族> \
    --closest-file ./closest.json
.venv/bin/light-idea advance ./my-direction <idea_id> --to novelty_checked
```

## 想法卡字段总表（idea.yaml）

| 区 | 字段 | 说明 |
|---|---|---|
| 头部 | `idea_id` | `slug_hash6`（题名 slug 截断 40 + sha256(题名)[:6]） |
| | `title` / `one_liner` | 题名 / 一句话 |
| | `status` | 状态机当前状态 |
| | `operator` | 来源算子：evolution_chain / collider / graph_path（v2 预留）/ user_supplied / manual |
| | `provenance` | 生成出处 {chain_id, path_string, combo, note}，至少一项非空，无出处不许入池 |
| | `created` / `updated` | 日期 |
| 文献 | `seed_refs[]` | 种子文献，每条必须带 `paper_id` 或 `doi`（拒裸文本） |
| facet 区 | `facets.purpose` / `.mechanism` / `.evaluation` | 每面 {phrase 结构化短语, detail 展开, source{type, paper_id/doi…}}；source.type ∈ paper / chain_node / operator / user |
| 正文区 | `body.method_steps[]` | 平语方法描述（2–4 步） |
| | `body.hypothesis` | 一句话假设 |
| | `body.mechanism_rationale` | 机制说明（为什么应该有效） |
| | `body.unexpected_prediction` | 可证伪的意外预测 |
| | `body.contribution_type` | empirical / method / theory / diagnostic |
| 可行性 | `feasibility` | {compute_within_budget, compute_note, data_obtainable, data_note}——screened 门的两条客观事实 |
| 执行级规格区 | `exec_spec.datasets[]` | 指名数据集 {name, version, access} |
| | `exec_spec.strongest_baseline` | 指名最强基线 {name, paper_id/doi}，禁写「与 SOTA 比较」 |
| | `exec_spec.metrics[]` | {name, convention_source 领域惯例出处} |
| | `exec_spec.ablations[]` | 计划中的消融，逐项列 |
| | `exec_spec.resource_budget` | 算力/数据/工期，常量化 |
| | `exec_spec.key_details[]` | 关键实现细节（先写死） |
| | `exec_spec.discriminating_experiment` | 最小判别实验 {description, readout_positive, readout_negative, readout_null}（判读标准预先写死） |
| 负面字段区 | `negative.strongest_objection` | 最强反对意见（必填） |
| | `negative.risks[]` / `negative.why_not_selected_first` | 风险与局限 / 落选原因 |
| pre-mortem | `pre_mortem` | {date, checklist{item: {status: pass/na, note}}, open_items[]}；清单六项见门规则 |
| 定版级别 | `finalization_level` | 定版后写入 executable / conceptual；概念定版须事前显式标注才许过门 |
| 查新证据区 | `novelty.checked_at` | 判定落卡时间（verdict 写入） |
| | `novelty.search_scope` | {sources[], pool_size, known_blind_spots} 检索范围声明（防乐观偏差） |
| | `novelty.closest_works[]` | 最接近工作 {paper_id/doi, title, year, collided_facets, delta, verified} |
| | `novelty.verdict` | PROCEED / PROCEED_WITH_CAUTION / ABANDON / null |
| | `novelty.caution_reason` | CAUTION 时必填（delta 薄在哪） |
| | `novelty.receipt` | 判定收据 {verdict_id, judge_model, judge_family, executor_model, executor_family} |
| | `novelty.review_status` | ok / REVIEW_UNAVAILABLE（降级通道） |
| | `novelty.abandon_named_paper` | ABANDON 时点名的在先论文（verdict 写入，与 closest_works 交叉校验在池） |
| | `novelty.evidence_package` | 证据包指针 → novelty/<idea_id>/（prepare 落盘：evidence.jsonl / queries.json / pool_report.md / verdict.json） |
| 辅助字段区 | `aux` | 只许 neighbor_similarity / atypicality_z + conventionality_z（成对）/ source_disruption / pairwise_record / elo；**与判定区物理分离，分数不进判定**，一律标「暂定，未经执行验证」 |
| 试点 | `pilot` | {status: not_run / verified / negative, note}；未 verified 的定版卡渲染时带「未经试点验证」标注 |
| 谱系 | `lineage` | {changed_from, revision_operator, revision_log[], bad_case_refs[]} |
| 去重 | `dedup` | {checked, max_similarity, most_similar_to, adjudication}；adjudication 由人工裁决填写（duplicate 的卡不许推进） |
| 状态留痕 | `status_history[]` | {from, to, date, by, note} 每次成功推进自动追加 |
| 旁路 | `kill` | {reason, date, source, failure_class, root_cause, boundary_conditions, retry_guidance, countermeasures, named_paper} |
| | `park` | {reason, revival_condition, date} |

## 状态机门规则清单

主线：`draft → screened → novelty_checked → pre_mortem_passed →
finalized_executable / finalized_conceptual`；旁路 `killed / parked`
（parked 可复活回 draft）。一切跃迁先过结构校验，再过目标门；
不许跳级、不许逆行（parked 复活除外）、终态（两级定版、killed）不许再转出。

| 目标状态 | 门规则（逐项验，任一不过即拦并点名） |
|---|---|
| screened | ① provenance 有出处；② compute_within_budget=true 且 compute_note 有据；③ data_obtainable=true 且 data_note 有据；④ dedup.checked=true；⑤ dedup.adjudication ≠ duplicate |
| novelty_checked | ① novelty.checked_at 已落盘；② search_scope.sources 非空；③ closest_works 为列表（可空，须显式在场）且每条带 paper_id/doi；④ verdict ≠ ABANDON（ABANDON 应走 killed） |
| pre_mortem_passed | ① pre_mortem 记录存在且 date 落盘；② 清单六项（strongest_baseline_attack / metric_convention / ablations_complete / resources_realistic / null_result_learning / method_instantiable）逐项 status ∈ {pass, na}，na 须附理由；③ open_items 为空；④ negative.strongest_objection 非空；⑤ 最小判别实验齐全且三向判读标准（正/负/零）预先写死 |
| finalized_executable | ① 执行级规格六项齐全（datasets 指名 / strongest_baseline 点名 / metrics 带惯例出处 / ablations 非空 / resource_budget / key_details）；② verdict 合法（PROCEED，或 CAUTION 且 caution_reason 非空；ABANDON 拦）；③ 跨模型收据合法（verdict_id + 判定/执行模型齐全且不同家族）；④ review_status ≠ REVIEW_UNAVAILABLE；⑤ closest_works 全部 verified=true；⑥ pilot.status 已显式登记且 ≠ negative |
| finalized_conceptual | 同 finalized_executable 的 ②–⑥（查新/收据/核实门不降格）；⑦ 卡上已显式标注 finalization_level=conceptual；执行级规格允许未齐（缺项随定版备注留痕，卡面带「不得直接开工」横幅） |
| killed | ① kill.reason / kill.date 非空；② source ∈ {budget_gate, novelty_named_paper, pilot_negative, pre_mortem, manual}；③ failure_class 必填二分类：fundamental 须附 root_cause + boundary_conditions，implementation 须附 retry_guidance；④ source=novelty_named_paper 时 named_paper 必须带 paper_id 或 doi（点名在先论文） |
| parked | ① park.reason 非空；② park.revival_condition 非空（复活条件） |

## 去重口径

字符 n-gram（3–5）TF-IDF + 余弦相似度，纯标准库离线实现（选型理由：
卡文本短、中英混排、无需分词与外部服务、可复现）。默认阈值 0.55。
报告口径：生成总数 → 疑似重复对（降序）→ 并查集重复簇 →
若人工裁决全部成立的冗余数 / 存活数 / 去重率；空文本卡单独点名。
**只报告不删卡**，裁决写回各卡 dedup.adjudication。

## 开发记录（节略）

本项目分三期建成，完整验收记录属开发档案，不在本仓库。此处只记
结论口径：

- 一期：项目骨架 + 想法卡系统（facet 区 / 执行级规格区 / 查新证据区
  / 辅助字段区物理分离）+ 状态机定版门（确定性校验器，逐门正/反例
  测试）+ 离线字符级去重工具。63 个测试。
- 二期：I3 facet 查新子流程——`novelty prepare` 四源实查取证落
  证据包、`novelty verdict` 判定落卡（ARIS 宽松判定口径：ABANDON
  须点名在先论文；跨模型收据硬门 + REVIEW_UNAVAILABLE 降级
  通道）。80 个测试。真实联网冒烟中证据池 105 条，粗排首位即
  种子方向的真实在先工作，facet 构式召回成立；OpenAlex /
  Semantic Scholar 曾全程 429，盲区均如实落盘。
- 三期：I0/I1 生成算子规程 + `chain` 引文链取材、I4 `duel`/`rank`
  两两对决排序、I5 打磨与 pre-mortem 规程、I6 `export` 交接三件套
  与 `report` 项目报告。101 个测试。端到端演示（家禽行为监测
  方向，种子为一篇已发表论文）：6 张卡真实落卡，top 卡走完
  查新 → pre-mortem 到 pre_mortem_passed，定版被跨模型硬门如实
  拦下（单模型环境走 REVIEW_UNAVAILABLE，不伪造收据）；演示中
  发现的「closest 须先过 Literature 核实」已固化为定版门规则
  （见封版记录第 9 条），其三篇最接近工作其后已补核实通过。


- v1.1（第二轮）：IDEA-D02 查新扩源四源 → 七源（新增 dblp /
  CORE / OpenAIRE，记录模型与 literature 适配层对齐，失败源
  如实落盲区；dblp 对机房出口 IP 启用 Anubis 校验、本机不可用，
  未绕过，适配器由离线夹具钉住）；IDEA-D04 判例集冷启动
  （判定自动沉淀判例、脱敏、种子 4 条逐条标源）；IDEA-D03
  想法卡增能力匹配维度（blocking 只拦可执行级定版）。测试
  101 → 124 passed；演示 C1 回填能力匹配后终点仍
  pre_mortem_passed，只剩 REVIEW_UNAVAILABLE 一拦。
- v1.2（快修批）：D1 种子标识符订正——种子 CB-3c3e80c688 的
  MAE DOI 经 Crossref 逐条核验由 10.1109/CVPR52688.2022.01639
  （实为他文）订正为 10.1109/CVPR52688.2022.01553，原错值保留
  在 identifier_check 留痕中；种子全部 7 处 DOI 引用同批复核
  并逐条落 identifier_check。测试 124 → 125 passed。

## v1.0 封版记录（2026-10-20）

light-idea v1.0 至此封版：全部交付，SKILL.md 定版 v1.0，
pyproject 版本 1.0.0，全量测试 101 passed。已知局限总表：

1. 图谱路径算子未做（v2）：v1 只有演进链 + 远域碰撞两个算子。
2. I3 查新第二段重排未独立成命令（向量粗排 + 按面 LLM 重排在判
   定者阅读环节完成）；构式关键词式会混入 facet 细则的中文词
   （短语式干净，演示中实测观察）。
3. 查新判例集尚未冷启动：判定者依据 SKILL §10.2 守则与判定宪法
   工作，无已判案例库校准。
4. 试点环只落标注纪律（未试点定版卡标注「未经试点验证」），
   工具不代跑试点。
5. 跨周期记忆只做结构化留痕与 memory_export.jsonl 导出，未做检
   索与回流，等 light-memory 收编。
6. 去重仍为字符 n-gram 级：语义近重（同义改写）检不出，只报告
   不删卡的纪律不变。
7. chain 与 novelty 的源依赖公开 API 限流：三/四源中任一源 429
   时覆盖不全（工具自动落盲区声明，但结论须按盲区打折）。
8. duel 的跨家族判定靠规程（逐场 note 声明），代码不强制判定者
   家族；Elo 只给对决过卡的子集分，未对决的卡无分。
9. 定版要求 closest works 先过 light-literature 核实口径
   （verified=true）：演示证明该门真实存在——从题名级证据池直
   接定版会被拦，这是设计而非缺陷，但意味着定版流程必须安排
   核实环节。
