# 定刊交接清单（light-journal-select → light-write）

- 目标刊：Computers and Electronics in Agriculture（ISSN 0168-1699，出版商 Elsevier BV）
- 定刊：2026-10-20 由 demo-author（演示代行） 定刊，理由：演示定刊：先例 7 篇（归一化 13.16 篇/万篇）、风险等级 clear、报告档位 target；scope_fit 未确认（官网未取得，正式投稿前须人工核对该刊 scope），证据见 SELECTION_REPORT.md。由演示脚本代用户执行 CEA 优先口径的选择，正式投稿前请用户复核。
- 交接目录：journal/target/（本机绝对路径 ../../../../../../light-journal-select/examples/demo-rerun-v11/selection-pkg/journal/target）
- 核查记录：journal/target/check-record.json（record_id TR-2026-2c0d2d，内容哈希 facd964b1b505827e3900ac0171b2056c345ebb3de2fa058cd1eb07347ee9564）
- 自检结论：本地结构校验 pass；Write 校验器自检 pass
- 下载清单：journal/target/download-manifest.json（已下载 0 件 / 待下载 2 件：guide-for-authors.html, elsarticle-template.zip）

## 政策核读（JS-13：定刊时点逐刊现行页面）

- 本轮交接未带回逐刊政策核读条目（见下方缺项）。
- **政策必查项未覆盖**：ai_use_disclosure、data_code_availability——投稿前必须逐刊核读补齐，不许以通行惯例代替该刊现行政策（JS-13）。

## Write 开工提示

在 Write 稿件包目录执行（--record 指向本清单同目录的 check-record.json）：

```bash
light-write register-template <稿件包目录> --record ../../../../../../light-journal-select/examples/demo-rerun-v11/selection-pkg/journal/target/check-record.json
```

- 待下载条目请按 manifest 的 source_url 从官网取回后回填登记（状态与哈希不许手改冒充）；
- 本目录的模板与作者指南仅本地投稿使用，不分发、不入任何公开仓库（E5）；
- 生成日期：2026-10-20（light-journal-select handoff）
