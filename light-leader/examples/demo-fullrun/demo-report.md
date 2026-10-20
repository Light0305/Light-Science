# light-leader 演示报告（demo-fullrun）

驱动：run_demo.py（经 CLI 子进程真跑，可整删 project/ 与 evidence/ 复现）。
终点：init → status → route → registry 全链跑通；route 点名四处
REVIEW_UNAVAILABLE 硬门，下一步落在推进 light-idea 定版。

## 1. 拼装口径（如实说明）

- 项目骨架由 `light-leader init` 真生成（project/，登记头 project.yaml）。
- 各阶段内容只复制各包真实 demo 的登记头与关键交接件——这正是
  status 的设计边界（只读登记头判状态）。逐项来源：
  - literature：light-literature/examples/demo-cea 的 文献索引.csv、
    证据表.jsonl、参考文献.bib；
  - idea：light-idea/examples/demo-poultry 的 C1 卡整目录
    （zero-tuning-tracker-thresholds-predicted_77cdb7）；
  - design：light-design/examples/demo-poultry-design 的主设计整目录
    （zero-tuning-tracker-thresholds_979ee7）；
  - experiment：light-experiment/examples/demo-synthetic 的两个
    execution.yaml（b1 与 b2，只复制登记头）；
  - analysis：light-analysis/examples/demo-synthetic 的 analysis-pkg 整目录；
  - journal-select：选刊 selection.yaml + journal/target 的
    check-record.json 与 handoff.md（落点按总控规范置于项目根 journal/）；
  - write：light-write/examples/demo-fullrun/manuscript-pkg 的
    manuscript.yaml 与 claims_register.yaml；
  - figure / review：各自 demo 图包与评审包的登记头 figure.yaml / review.yaml；
  - memory：发布版 light-memory 演示世界 proj-a 的 memory.yaml 与六账
    （objects/events/facts/relations/disputes/promotions），未复制 .index
    与 obsidian 投影（派生物，非状态读数所需）。
- 复制时把文件内的机器绝对路径前缀改写为仓库根相对路径；拼装后全树
  grep 机器绝对路径命中 0。
- 诚实注记：这不是一个真实走完的项目，而是同一条火鸡主线在各包演示
  中的真实终局拼图——下游包（选刊 handed_off、write audited、figure 与
  review delivered）是各自在上游降级口径下如实推进的结果，与上游四处
  硬门并存正是本演示要呈现的全链实况，总控照实报告、不调和。

## 2. status 实况（evidence/04-status.txt）

十个阶段全部读到真实状态：

| 阶段 | 读数 | 出处 |
|---|---|---|
| literature | 篇目 1（精读完成 x1），证据行 14 | 文献索引.csv + 证据表.jsonl |
| idea | status=pre_mortem_passed，硬门标记 review_status = REVIEW_UNAVAILABLE | C1 卡 idea.yaml |
| design | status=reviewed，硬门标记同上 | 主设计 design.yaml 的 freeze.review |
| experiment | b2 status=delivered（终态）；b1 status=intake | 两个 execution.yaml 逐个报告不合并 |
| analysis | status=blocked，门标记 + blocked 原因原文 | analysis.yaml |
| journal-select | status=handed_off（终态） | selection.yaml |
| write | status=audited，submission_blocked_reason 与 review_status 双标记 | manuscript.yaml |
| figure | status=delivered（终态） | figure.yaml |
| review | status=delivered（终态） | review.yaml |
| memory | 对象 26、事件 88、事实 30、关系 16；registry-view.json 已导出 | memory.yaml + 四账行数 |

## 3. route 实况（evidence/05-route.txt）

- 硬门点名四处，每处带登记头证据与统一解法指针（异家族复核 + 各包
  回填命令落账，不许伪造收据）：
  idea 定版硬门（跨模型判定）、design 冻结门（Stage-1 五条 + 跨家族
  复核）、analysis 交付门（判定复核）、write 定版复核门。
- 下一步：推进 light-idea——本阶段进行中（pre_mortem_passed），终态为
  finalized_executable / finalized_conceptual。判断依据：流水线第一个
  未达终态阶段即 idea；其余未终态阶段（design / analysis / write）
  均已被各自硬门点名，不另给含糊推进建议。
- 提示：memory 收编触发点——已达终态的 experiment、journal-select、
  figure、review 在各自定版点应已由 light-memory ingest 收编，以
  memory.yaml 的 watermarks 核对是否漏收（本拼装中 memory 计数与
  各包演示收编实况一致：对象 26 等）。

## 4. registry 实况（evidence/02、03、06）

- 未导出时（02）：`light-leader registry` exit 1，点名未找到
  registry-view.json 并给生成方式指针（在记忆项目目录运行
  light-memory registry export），总控不自行生成。
- 导出（03）：由 light-memory 自家命令对副本执行 registry export，
  刷新出 26 个对象（11 个类型：paper 1、design 2、execution 1、run 8、
  analysis_package 1、claim 2、concern 6、figure 2、journal_selection 1、
  manuscript 1、review_package 1）。
- 消费（06）：总控按类型分组渲染 26 个对象，逐个呈现上游 ID、状态
  （active / referenced）、当前版本指针（短哈希）与项目归属；其中
  claim F001 与 design video-threshold-predict_synth01 为 referenced
  （前向登记未转正），与 memory 侧口径一致。

## 5. 已知折扣

- status 演示只验证登记头读取与路由判断，不验证各包内部产物完整性
  （那是各包 validate 的职责，总控不越界）。
- experiment 只复制了登记头，run 级产物未拼装；write 只复制登记头与
  主张登记，章节正文未拼装——两者均不影响状态读数，口径已在 §1 落字。

## 6. v1.1 复跑增补（LD-03 / LD-04，2026-10-21）

本演示于 v1.1 第 3 步之十一复跑（run_demo.py 整删重拼）：四处
REVIEW_UNAVAILABLE 硬门仍逐一点名、下一步仍落推进 light-idea，
与上文实况一致。新增可见变化：status 逐登记头多一行「规范态」标注
（LD-03 映射表，如 analysis blocked → 被门拦、delivered → 已达终态），
route 的下一步理由同步带规范态标注。LD-04 的新门类点名（design
returned 携缺项清单、blocked_gate 统一字段）由包内测试覆盖
（tests/test_statusmap_gates.py），本演示登记头未携该类记录，故
route 输出无新增点名行——缺字段不点名、不猜，属预期行为。
