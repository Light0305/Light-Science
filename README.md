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
| Light-Figure | 作图：方法/机制图与数据图 | 规划中 |
| Light-Review | 评审：成稿自审与投稿前检查 | 规划中 |
| Light-Memory | 记忆：跨阶段沉淀、检索与 Obsidian 轻量图谱视图（贯穿全部阶段，最后建设） | 规划中 |

建设顺序按科研实际流程推进：Literature 已定版，其后依次为 Idea → Design → Experiment → Analysis → Write → Figure → Review，Memory 与图谱视图放最后——等各阶段产物形态都定型后再做沉淀与连接，返工最少。

## Light-Literature（已发布）

把一篇外部论文加工成「四件套」——原文 PDF、带 S/C/F/T/E 锚点的原文 MD、块级对齐的中文翻译 MD、图文并茂的精读笔记——并配套证据行、术语账本与 Find 线（多源检索 → 身份核实与撤稿检查 → 粗筛 → 研究证据矩阵）。

解析采用**双轨制**：使用者自配 Doc2X Key 时走 `parse` 命令锚点化（按页计费约 ¥0.01–0.02/页）；未配置时由接入模型按规范逐页直读 PDF 亲自撰写带锚点的四件套，不依赖其他解析工具。两轨的锚点契约、校验与证据纪律完全一致。详见 [light-literature/README.md](light-literature/README.md) 与 [light-literature/SKILL.md](light-literature/SKILL.md)。

## 许可证

各子技能的许可证见其目录内的 `LICENSE` 文件（如 [light-literature/LICENSE](light-literature/LICENSE)）。
