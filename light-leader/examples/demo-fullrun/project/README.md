# 火鸡异常行为检测：零调参跟踪阈值预测（总控演示拼装）

Light-Science 科研项目（总控 light-leader 登记）。

## 目录

| 目录 | 阶段 | 说明 |
|---|---|---|
| literature/ | light-literature | Literature/文献索引.csv（逐篇 status 列） |
| idea/ | light-idea | cards/<idea_id>/idea.yaml 的 status 字段 |
| design/ | light-design | designs/<design_id>/design.yaml 的 status 字段 |
| experiment/ | light-experiment | executions/<exec_id>/execution.yaml 的 status 字段 |
| analysis/ | light-analysis | analysis.yaml 的 status 字段 |
| journal-select/ | light-journal-select | selection.yaml 的 status 字段 |
| write/ | light-write | manuscript.yaml 的 status 字段 |
| figure/ | light-figure | figure.yaml 的 status 字段 |
| review/ | light-review | review.yaml 的 status 字段 |
| journal/target/ | 选刊交接落点 | light-journal-select 定刊 handoff 的模板与作者指南（仅本地使用） |
| memory/ | light-memory | 跨阶段沉淀（四账 + Obsidian 投影），由 light-memory 在此建包 |

## 用法

- 看全项目状态：`light-leader status .`
- 问下一步：`light-leader route .`
- 看对象注册统一视图：`light-leader registry .`
- 每阶段的内部规程见对应技能的 SKILL.md；总控规程见 light-leader SKILL.md。
