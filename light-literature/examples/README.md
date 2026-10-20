# examples 说明

本目录只放**结构示意**，不放真实论文产物：没有 PDF 原件、没有全文
译文/笔记成品、没有 Doc2X 运行记录（uid / run_record / 原始结果）。
版权与隐私从严——想看真实跑通的形态，请用自己的一篇论文按
[../README.md](../README.md) 的命令走一遍。

## demo-cea：一篇论文走完双轨演示后的目录形态

演示篇（公开发表的 OA 论文，此处仅借其书目信息示意结构）：
Zhang et al., *Abnormal turkey behaviour detection using self-supervised
video anomaly detection and multiple object tracking*, Computers and
Electronics in Agriculture 239 (2025) 110856，
DOI 10.1016/j.compag.2025.110856。

```text
demo-cea/                                # 一个「项目目录」（init 的产物）
├── Literature/
│   ├── 00-文献总览.md / 文献索引.csv / 证据表.jsonl / 术语账本.md
│   ├── 候选池.jsonl / 检索报告.md        # find 线产物
│   ├── 粗筛表.csv / 粗筛说明.md          # screen 产物
│   ├── 研究证据矩阵.md / 参考文献.bib    # matrix 等产物
│   └── abnormal-turkey-behaviour-detection-usin_f65598/   # 单篇目录
│       ├── paper.yaml          # ← 本目录附脱敏版实样（字段同构）
│       ├── 原文.pdf             # ingest 复制入内（不随仓库发布）
│       ├── 原文.md              # parse 锚点化产物（S/C/F/T/E 锚点）
│       ├── 原文_中文翻译.md      # translate-scaffold 脚手架 + agent 逐块回填
│       ├── 阅读笔记.md           # notes 骨架（速读检查点 + 精读 16 节）
│       ├── source_map.json     # 全部块与溯源（锚点契约的机器可读形态）
│       ├── content_list.json   # export-content-list 导出
│       ├── verify_report.json  # verify 报告
│       ├── doc2x/              # Doc2X 轨运行区：doc2x_result.json、
│       │                       # 导出 MD + images/、run_record.json
│       └── assets/figures/     # 图资产（Doc2X 导出图 / PDF 裁片，逐块标来源）
└── （项目自己的其他目录，与 Literature 平级）
```

演示实测口径（供参考，非承诺）：该篇 12 页、出版社版 PDF；
Doc2X 轨锚点 S 161 / C 20 / F 8 / T 12 / E 11，费用约 ¥0.12–0.24；
模型直读轨独立产出 196 个锚点，两轨的 12 张表数据与关键数值抽查
全部一致。两轨互校能发现单轨自检的盲区——这正是双轨制的价值之一，
规程见 [../SKILL.md](../SKILL.md) §5。
