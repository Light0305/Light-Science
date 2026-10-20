# Light-Science

面向科研全流程的智能体技能包：把「找文献 → 读文献 → 出想法 → 做设计 → 跑实验 → 分析 → 写作 → 作图 → 评审」每一步沉淀为可执行、可核查的技能规范与工具，让接入的智能体按统一纪律产出可复用的研究材料。

## 技能版图

| 技能 | 职责 | 状态 |
|---|---|---|
| Light-Science | 总控：调度各阶段技能、维护项目状态 | 规划中 |
| [Light-Literature](light-literature/) | 文献：检索核实、双轨解析、四件套、精读卡与证据行 | **v1.0 已发布** |
| Light-Idea | 想法：基于证据矩阵与笔记生成、查新并筛选研究想法 | **v1.0 已发布**（light-idea/） |
| Light-Design | 设计：把想法落成可执行的研究/实验设计 | **v1.0 已发布**（light-design/） |
| Light-Experiment | 实验：执行设计、记录过程与原始产物 | **v1.0 已发布**（light-experiment/） |
| [Light-Analysis](light-analysis/) | 分析：按冻结登记行逐行回写正式判定，产出可审计的分析结论包 | **v1.0 已发布** |
| [Light-Write](light-write/) | 写作：基于证据行成稿，引用只走核实过的文献 | **v1.0 已发布** |
| [Light-Journal-Select](light-journal-select/) | 选刊（**Write 前置扩展位**，不占十件套编号）：Analysis 出结论后先选刊——先例路统计 + 逐刊核验 + 风险门出三档证据卡，用户定刊后备齐模板与九组检查记录再交 Write 开工 | **v1.0 已发布** |
| [Light-Figure](light-figure/) | 作图：图合同先行、双线生成（数据图代码线 / 方法图提示词→Visio 重绘线）、七门实测审计与交付 | **v1.0 已发布** |
| [Light-Review](light-review/) | 评审：投稿前内部评审（法医式四方对账 + GRIM 族、模拟审稿人组与共识门、校准门决定建议、自审门、concern 回填清单） | **v1.0 已发布** |
| Light-Memory | 记忆：跨阶段沉淀、检索与 Obsidian 轻量图谱视图（贯穿全部阶段，最后建设） | 规划中 |

建设顺序按科研实际流程推进：Literature 已定版，其后依次为 Idea → Design → Experiment → Analysis → Write → Figure → Review，Memory 与图谱视图放最后——等各阶段产物形态都定型后再做沉淀与连接，返工最少。

## Light-Literature（已发布）

把一篇外部论文加工成「四件套」——原文 PDF、带 S/C/F/T/E 锚点的原文 MD、块级对齐的中文翻译 MD、图文并茂的精读笔记——并配套证据行、术语账本与 Find 线（多源检索 → 身份核实与撤稿检查 → 粗筛 → 研究证据矩阵）。

解析采用**双轨制**：使用者自配 Doc2X Key 时走 `parse` 命令锚点化（按页计费约 ¥0.01–0.02/页）；未配置时由接入模型按规范逐页直读 PDF 亲自撰写带锚点的四件套，不依赖其他解析工具。两轨的锚点契约、校验与证据纪律完全一致。详见 [light-literature/README.md](light-literature/README.md) 与 [light-literature/SKILL.md](light-literature/SKILL.md)。

## 许可证

各子技能的许可证见其目录内的 `LICENSE` 文件（如 [light-literature/LICENSE](light-literature/LICENSE)）。
