# demo-fullrun：端到端完整链演示（light-write v1 Phase 3）

与 `demo-synthetic/`（Phase 1 承接骨架演示：只走到 intake 并如实暴露缺口）区分，
本目录是一次**从承接到终点的完整运行**：承 Analysis 演示结论卡走完
intake → 模板登记 → 合同冻结 → outlined → 起草 → 披露 → 审计四门 →
图件冻结 → audited → 跨模型复核（REVIEW_UNAVAILABLE 拦停）的全链，
并另以副本包演示一段 W7 返修（意见登记 → 改稿 → 逐条回复 → 双向对账 → 回复信绑定）。

## 身份声明（必读）

- **合成链身份**：上游结论卡来自 light-analysis 的合成演示包
  （`light-analysis/examples/demo-synthetic/`），其数据为合成自签执行包的产物；
  本演示稿件是合成演示稿，不是真实研究投稿。
- 模板核查记录（`fixtures/journal_record.json`）是**演示自备 fixture**：
  期刊名明写 "Journal of Synthetic Demonstrations (demo fixture, not a real journal)"，
  字段形态严格对齐模板记录 schema（A–I 九组），不是任何真实期刊的核查结果。
- 在线权威记录（`fixtures/online_records.json`）是演示操作者在构建时
  **真实调用 Crossref API 现拉**的三条已引文献记录（原始响应存 `evidence/crossref/`），
  按工具的注入接口喂入审计——工具本身不内嵌网络调用（v1 口径）。
- 跨模型复核在本环境不可得（单一模型家族），如实落 REVIEW_UNAVAILABLE，
  稿件停在 audited——与 Idea/Design/Analysis 演示同构，不伪造收据。

## 目录

| 路径 | 内容 |
|---|---|
| `manuscript-pkg/` | 主演示稿件包（终点：audited，四门全过，复核拦停） |
| `manuscript-pkg-revision/` | W7 返修副本包（自 manuscript-pkg 复制后独立返修，与主包状态互不影响） |
| `fixtures/journal_record.json` | 演示期刊模板核查记录（fixture） |
| `fixtures/online_records.json` | Crossref 现拉的在线权威记录（注入用） |
| `evidence/run-log.txt` | 全程 CLI 运行日志（每步命令的真实输出） |
| `evidence/crossref/` | Crossref 原始响应（works 记录 + 撤稿更新查询，共 6 份） |
| `evidence/audit-01-offline/` | 第 1 次审计产物（离线：门一 honest-unverified） |
| `evidence/audit-04-online/` | 第 4 次审计产物（在线注入后四门全过） |
| `evidence/audit-05-online-final/` | 第 5 次审计产物（图件冻结后重审，终审版） |
| `evidence/main-pkg-final-audit_report.json` | 主包终审报告副本 |
| `demo-report.md` | 演示报告：逐段状态、四门逐门结果、STALE 演示、三账本触发记录、数字对账、接口观察 |

复现：`light-write` CLI 按 `evidence/run-log.txt` 的顺序对 `manuscript-pkg/` 逐步执行即可
（在线记录注入需 `fixtures/online_records.json`；其内容可按 `evidence/crossref/` 原始响应重建）。
