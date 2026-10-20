# demo-fullrun：light-journal-select v1 端到端演示

真实联网演示（非 fixture）：以「火鸡异常行为检测」稿件指纹
（主题承 light-literature / light-write 演示的 CEA 2025
火鸡论文）走完整选刊链——指纹 → OpenAlex 实时先例路 →
逐刊联网核验 → 风险门 → 三档证据卡 → 定刊 CEA 优先 →
`journal/target/` 交接（check-record 过 Write 校验器自检）。

## 运行

前置：本包已 `pip install -e .`（在 light-journal-select
目录、目标 venv 中执行一次）；出站代理环境（https_proxy）
已设置。先例路需 OpenAlex 额度：匿名共享预算耗尽（429）
时注入用户自备的免费 Key（Key 值不经聊天明文、不落盘）：

```bash
cd ~/workspace/light-science/light-journal-select
OPENALEX_API_KEY=<主线经连接器注入> \
  ~/workspace/light-science/.venv-lit/bin/python \
  examples/demo-fullrun/run_demo.py
```

每次运行会清空并重建 `selection-pkg/`、`inputs/`、
`evidence/` 与 `demo-report.md`（骨架，叙述结论由主线回填）。

## 演示替身披露

- 风险名单为 demo fixture：predatory 靶子是虚构刊
  「Journal of Fictional Turkey Studies」，不命中任何真实
  期刊；软警告（volume_surge）为演示注入、非真实核查结论。
- handoff 指南字段集为演示种子值（照 elsarticle 常规与
  CEA 作者指南公开形态），正式使用须逐项对官网复核。
- 指南/模板文件不真下载：manifest 中如实落
  pending_download 并点名。
- 专有指标（IF/分区/自引率）无开放渠道：一律
  unconfirmed，不凭记忆报数。
