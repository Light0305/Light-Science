---
light_memory_view: relations-guide.md
---

<!-- light-memory:machine:start -->
# 关系类型说明

Obsidian 图谱只渲染链接存在性，不区分边类型与方向语义；语义以本页图例与各笔记关系行的类型词为准。

- supersedes：修订/取代（强）：新版对旧版的取代，只由上游事件与取代链机械生成（方向 directed，生成 mechanical）
- refutes：否定（强）：如撤稿事件对关联结论的否定边（方向 directed，生成 mechanical）
- supports：证实（强）：证据对主张的支持（方向 directed，生成 mechanical）
- depends-on：依赖（强）：结论包对执行包/设计包的承接依赖（方向 directed，生成 mechanical）
- derived-from：出处包含（强）：派生条目回指其源头（方向 directed，生成 mechanical）
- same-object-as：跨项目同源（中）：同一上游对象在不同项目的登记映射（方向 undirected，生成 mechanical）
- backtracks-to：折返（中）：死胡同/返工路线连回其种子与定版产物（方向 directed，生成 mechanical）
- inspires：启发（弱）：只许候选 + 判定两段式生成，落账带判定标记（方向 directed，生成 judged）
<!-- light-memory:machine:end -->

<!-- light-memory:annotations:start -->
（用户标注区：在这里写下的内容不会被投影覆盖；用 light-memory readback 回读为候选）
<!-- light-memory:annotations:end -->
