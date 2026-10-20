# Light-Memory Phase 3 真实演示报告（demo-fullrun）

> 驱动：`run_demo.py`，全链经 CLI 子进程真跑（可整删 `world/` 重复执行，结果确定性复现）。输入全部为全项目各包的真实演示产物；唯一的构造物是第二代结论包（§3 明确标注）。证据在 `evidence/`（逐条 CLI 日志 + `summary.json` + `bench_report.json`）。

## 终点状态

**演示走完至封版就绪**：三包（proj-a 主项目 / proj-b 跨项目对照 / global 全局层）终局 `validate` 全部零错误；Obsidian 投影、标注回读、画像、晋升、bench 首测均有实物产物。记忆项目终局计数（proj-a）：**对象 26、事件 88、事实 30（current 29 / superseded 1）、关系 16、争议 0**。

## 1. 逐包 ingest → 四账成形

| 包 | 输入（真实演示产物） | 新增对象 | 新增事件 | 新增事实 | 新增关系 | 备注 |
|---|---|---|---|---|---|---|
| Literature | demo-cea 证据表.jsonl（14 行） | 1 | 0 | 14 | 0 | 同一篇 CEA 论文的 14 条证据事实，锚点原样保留 |
| Design | 主设计 design.yaml（979ee7） | 1 | 2 | 2 | 0 | 两条设计主张 + 状态里程碑事件 |
| Experiment | 执行包 b2（execution_card + events + failures + deviations） | 9 | 60 | 2 | 8 | 60 条事件直通（含失败/偏离），2 条失败事实，run→执行包 derived-from 边 |
| Analysis | conclusion_card.json | 3 | 1 | 1 | 2 | C1 判定事实（第一代）；depends-on 边指向执行包（已收编，转正）与自签设计（未收编，保持 referenced） |
| Write | manuscript.yaml（demo-fullrun） | 1 | 6 | 0 | 0 | use_log 2 条均有 model_version 入事件账；状态里程碑 4 条；claim:C1 对象与 Analysis 同一派生 ID 自动合并 |
| Figure | provenance.yaml + exports/delivery.yaml | 2 | 7 | 2 | 0 | 两图出处事实 + 6 条修订事件 + delivery 里程碑 |
| Journal-Select | selection.json | 1 | 0 | 0 | 0 | 只登记选刊对象；两处缺口逐项点名（见 §8），零编造 |
| Review | handoff_to_write.json | 8 | 0 | 6 | 5 | 6 条 concern 事实 + 回指 claim 的 derived-from 边；关闭史缺口点名 |
| Idea | demo-poultry（整目录） | 0 | 0 | 0 | 0 | **exit 1 点名失败**：缺 memory_export.jsonl（演示卡未定版），水位线不动、一行不入账；改走 dossier（§2） |

proj-b（MOT17 极简项目）：ingest mot17 design.yaml → 对象 1、事件 1、事实 1（设计主张 M1），供跨项目对照与 bench 跨项目题。

收编后 proj-a 计数：对象 26、事件 76、事实 27（全 current）、关系 15。

## 2. Idea 死胡同 dossier 收编

Idea 演示 6 张卡全部未定版（C1 止步 pre_mortem_passed、跨模型硬门 REVIEW_UNAVAILABLE 拦停；4 张 screened；CUSUM 1 张留 draft），无官方导出。按 REDESIGN 第四节定版口径，从真实卡面（title/one_liner/operator/status/种子 DOI）生成 6 篇 dossier 折返笔记入 `notes/idea-dossier/`：5 篇死胡同以 `backtracks-to` 关系行连回入选主路线卡，C1 留痕篇以 `derived-from` 连回种子文献。笔记经索引收编、可召回（bench 与 recall 语料含笔记块）。

## 3. 取代演示（构造第二代结论包，明确标注）

真实 Analysis 演示只有一代结论包。按一期冒烟已验证的形态**构造**第二代（提名文件 `inputs/nominations-gen2.json`，nominator 与 rationale 均明写「构造演示，非真实上游产物」，provenance 的 source_artifact 为 `conclusion_card.gen2-CONSTRUCTED.json`）：

- 先以 verdict store 登记一条真实派生事实（Write 对 C1 的表述口径，derived_from 指向第一代判定事实）；
- supersede 落账：第一代判定事实 → status=superseded、invalid_at=2026-10-21、superseded_by 指针与 supersedes 关系边同步落账（关系总数 15→16）；
- **派生失效传播实测命中**：派生事实被标 `stale=true` 并写明 stale_reason（源事实已被取代、待按新版再生），propagation 事件入账；
- as-of 分界实测：`facts --as-of 2026-10-20` 含第一代口径（「Type M 最差值 4.35」命中 1 次）、不含第二代；当前事实集只含第二代（第一代片段命中 0 次）。

**撤稿传播**：真实撤稿数据无结构化源（Literature 适配器已点名缺口，见 §8），本轮未实测撤稿事件本身；钩子已备——refutes 边类型在词表内、失效传播与本次实测同一路径（事实失效 → 派生 stale），待 Literature 事件 schema 回填后接入。

## 4. settle 候选流

- **accept 生效**：由 F-0001 提炼的判断性候选「承接执行前必须核验登记数据版本的完整交付（逐段清单对账）……」经 `candidate propose → accept --by demo-user` 入事实层（fact_type=lesson，derived_from 指向 F-0001 失败事实——运行时注入真实 fact_id，模板在 `inputs/candidate-lesson.json`，生效件为 `candidate-lesson.effective.json`）。
- **reject 留痕**：推测性候选「CUSUM 累积监测可直接迁移其他畜种、无需重新验证」被 reject（理由：跨域迁移无任何证据、来源卡本身未验证），候选账留痕不删、事实层无此条。

## 5. 跨包 recall 实测（输出存 evidence/）

- **q1 跨阶段追溯**「主张 C1 的判定 support 与 grade 是什么，承接自哪个执行包」（default，depth 1）：命中 20 条（封顶），前列含 Review concern（RV-C001 复述 C1 未检验状态）、F-0001 失败事实、设计主张两条——跨 Literature/Design/Experiment/Analysis/Review 五包材料同屏。因该次 recall 发生在取代落账后、索引重建前，结果头如实带**降级声明**（索引与真相不一致、基于旧索引），MM 降级契约实测生效；其后驱动重建索引再继续。
- **q2 失败经验复用**「数据版本交付不完整造成过什么失败，承接新执行前要核验什么」（failure-lookup）：输出存 `evidence/recall-q2-failure-reuse.log`。
- **q3 as-of 历史口径**：`facts --as-of 2026-10-20` 与当前事实集对照（§3 的分界数字），另有 `recall --as-of 2026-10-20` 输出存档。
- **q4 英文释义**「predicting tracker thresholds from video-level statistics」（paraphrase 配方）：输出存 `evidence/recall-q4-paraphrase-en.log`；在确定性测试嵌入下主要靠共享拉丁 token 命中，语义质量不作数（见 §9 折扣）。

## 6. Obsidian 投影实物

`project-obsidian` 生成 vault（`world/proj-a/obsidian/`）：**13 篇对象笔记 + 索引页 + 关系说明页 = 15 个 MD**，wikilink 共 21 处。精选规则命中情况：30 条事实中 29 条入选（evidence 14、design_claim 2、conclusion_verdict 两代 2、figure_provenance 2、review_concern 6、failure_record 2、lesson 1）；唯一未入选的是 generic 型「稿件表述口径」事实（不在成文的入选类型表内，按规则不落笔记）。两代结论同入 claim-c1 笔记，取代关系正是图谱看点。

标注全链：在 claim-c1.md 标注区手写一条标注（第二代口径确认）→ `readback` 产 annotation 候选 cand_a2d6377faafd → `accept` 生效 → events.jsonl 落 1 条 annotation 事件，标注原文留视图内（回读是复制不是剪切）。

## 7. 跨项目晋升

已生效的教训事实经 `promote propose（全局层）→ confirm --by demo-user` 复制入 global 包：全局层事实 1 条（副本）、promotions.jsonl 记账 1 行（promoted），项目原件不动。

## 8. 上游回填缺口（两处，如实点名）

1. **Literature 撤稿/Find 线无结构化事件源**：证据收编时适配器逐项点名「撤稿事件未收编（事件 schema 待 Literature 侧回填后接入）」；撤稿 stale 传播钩子已备未实测（§3）。
2. **Idea 未定版卡与死胡同无官方导出**：memory_export 只含定版卡；本演示卡未定版 → idea 适配器点名失败、零入账，死胡同改走 dossier 笔记形态收编（§2），relations.jsonl 的机械 backtracks-to 边待 Idea 侧 dossier 结构化导出回填后生成。

另有两处接口形态差（非缺口、已在 SKILL §10 登记）：选刊 selection.json 导出停在 gated 态、decision 为空（定刊权威记录在 selection.yaml），且已核验指标形态（metrics 状态字符串）与适配器约定形态不符 → 选刊只登记对象、定刊决策与期刊事实未落值，缺口逐项点名、未编造；Review concern 关闭史不在 handoff 源内（以 Write 回填为准），未收编。

演示中发现的接口小毛病一件：`candidate list` 的 `--kind` 默认值为 fact，annotation 候选不显式给 `--kind annotation` 就列不出来（API 层无此问题）——已在本报告登记，未改产品代码。

## 9. bench 首测（正式题集 50 题）

题集 `inputs/bench_set_fullrun.jsonl` 全部由本演示真实记忆构造（金标准片段逐字取自事实账/笔记，驱动内置锚点核验、跑前全过）。构成：知识更新 10（含 as-of 历史口径 3 题）、跨项目同名 8、失败复用 10、拒答 10、释义基线 12。配置：确定性测试嵌入（embedder=deterministic-test-v1，dim 64，未登记真实提供者）、当版配方与索引，报表 `evidence/bench_report.json`（verdict=not_judged，只报数不判线）。

| 类别 | 命中 | 备注 |
|---|---|---|
| 知识更新 | 5/10 | **旧答案误答率 0**：当前口径题无一例把第一代当现行答案召回（效力过滤生效）；失分全在目标事实未进 top-5（其中 as-of 题 3 题失分 3） |
| 跨项目同名 | 7/8 | 分组归属无一混答；失分 1 题为目标事实未进 top-5 |
| 失败复用 | 6/10 | 失分均为教训/失败事实未进 top-5（排序稀释），无召回错项目 |
| 拒答 | 7/10 | 按运行器操作化判据（top-5 内无共享 ≥2 实义 token 的词法/关系命中），3 题各有 1 条弱证据命中被判编造（见折扣） |
| 释义基线 | 9/12 | 含纯英文查询 2 题中 1 题命中（靠 AUROC 等共享拉丁 token）；纯英文语义查询 pp-09 未命中 |
| **总计** | **34/50（0.68）** | |

构造修正披露：首轮跑分（v1）后发现被 accept 的教训候选未带 derived_from 出处指针，补正后重跑（v2）——**两轮逐题结果完全一致（34/50）**，证明失分不在关系缺失而在 top-5 排序稀释；本报告数字即 v2（与 v1 相同）。

### 建议通过线（供用户定版，本报告不写入 SKILL）

按 REDESIGN §七纪律（以旧实现基线 + 首测实绩为据），建议以**首测实绩为回归地板**定版如下（当前确定性测试嵌入配置下）：

- 知识更新：旧答案误答率 **= 0**（硬线，安全面不许 regress）；当前口径命中率 ≥ 0.50；
- 跨项目同名：命中率 ≥ 0.80，且分组混答 = 0；
- 失败复用：命中率 ≥ 0.60；
- 拒答：编造率（操作化判据）≤ 0.30；
- 释义基线：top-5 命中率 ≥ 0.70（单列；与 v2.2 的 Recall@1 0.220 非同一口径，不直接比较）；
- 总线：总命中率 ≥ 0.65。

依据：首测是在确定性测试嵌入（无语义质量）下的管线基线，定线于实绩地板可使「配置变更不许 regress」立即可执行；真实本地/API 嵌入接入后必须重跑全集、另行提线（尤其释义类），不在本线覆盖内。通过线本身留空待用户定版（SKILL §8 第 5 条已留占位）。

## 10. 已知折扣

- **确定性测试嵌入下，释义类分数只代表管线基线**：嵌入是哈希分桶词袋、无语义，释义命中主要来自共享 token 与词法/关系两路；接入真实嵌入后须全量重建索引并重测。
- 拒答的「编造」是操作化判据：中文单字 token 使任意两字词（如「火鸡」）即构成 ≥2 共享 token，3 道失分题各有 1 条此类弱命中——判据口径已在报表注明，不等同于端到端答案真的编造。
- 小语料（30 条事实 + 6 篇笔记）下 top-5 排序竞争激烈，多类失分属排序稀释；语料规模增长后应复测再议提线。
- 第二代结论包为构造演示（§3），其「补跑后重判」情节不对应任何真实执行；取代/传播/as-of 的机制实测结果不受影响。
