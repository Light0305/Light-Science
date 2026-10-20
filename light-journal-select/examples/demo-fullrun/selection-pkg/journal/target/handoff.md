# 定刊交接清单（light-journal-select → light-write）

- 目标刊：Smart Agricultural Technology（ISSN 2772-3755，出版商 Elsevier BV）
- 定刊：2026-10-20 由 demo-author（演示代行） 定刊，理由：演示定刊：先例 6 篇（归一化 23.34 篇/万篇）、风险等级 clear、报告档位 target；scope_fit 未确认（官网未取得，正式投稿前须人工核对该刊 scope），证据见 SELECTION_REPORT.md。由演示脚本代用户执行 CEA 优先口径的选择，正式投稿前请用户复核。
- 交接目录：journal/target/（本机绝对路径 ../../../../../../light-journal-select/examples/demo-fullrun/selection-pkg/journal/target）
- 核查记录：journal/target/check-record.json（record_id TR-2026-623ddd，内容哈希 2ea3531f34d92c9794a87d74635afe0992b5eb3b2879bef06ed15d8db257b80a）
- 自检结论：本地结构校验 pass；Write 校验器自检 pass
- 下载清单：journal/target/download-manifest.json（已下载 0 件 / 待下载 1 件：author-guide）

## Write 开工提示

在 Write 稿件包目录执行（--record 指向本清单同目录的 check-record.json）：

```bash
light-write register-template <稿件包目录> --record ../../../../../../light-journal-select/examples/demo-fullrun/selection-pkg/journal/target/check-record.json
```

- 待下载条目请按 manifest 的 source_url 从官网取回后回填登记（状态与哈希不许手改冒充）；
- 本目录的模板与作者指南仅本地投稿使用，不分发、不入任何公开仓库（E5）；
- 生成日期：2026-10-20（light-journal-select handoff）
