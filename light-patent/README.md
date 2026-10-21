# light-patent

Light-Science 子技能：科研成果的**权利固化出口**——把已成型的技术
方案（论文、代码仓、实验记录、口头交底）转成可审查、可答辩、可
管理的中国发明专利申请资产。位于 light-review 之后并列的出口层
扩展位（拍板 LD-02），不进十阶段主流水线。

**版本：v1.1（2026-10-21）**。v1 只做发明专利、只做中国（拍板
Q1/Q2）；法律结论只给草案级，全案固定「草案，需专利代理师复核」，
初筛产物再加「只作初筛底稿、不作法律意见」（Q4）。v1.1 增补：
检索执行通道（search-exec：CNIPA epub 经 light-crawler 驱动、
EPO OPS 官方 API 适配器）与申报副本 DOCX 渲染（render-docx），
逐渠道实测状态见 SKILL §6/§7。

## 流程坐标 P0–P7

公开审计（P0）→ 交底挖掘（P1）→ 检索查新（P2）→ 撰写（P3）→
审核（P4）→ 答复（P5）→ 静态台账（P6），政策雷达 lite 为旁路
（P7）。规范锚点：专利法（2020 年修正）、实施细则（2023 年
修订）、审查指南含局令第 84 号修改（2026-01-01 施行，SKILL
§10 逐字引用关键条文）。

## 快速上手

```bash
pip install -e .            # 核心依赖仅 pyyaml；DOCX 渲染另装 .[render]
light-patent init <案件目录> --title "一种……" [--ai-related]
light-patent audit <案件目录> --payload audit.json
light-patent scan-code <案件目录> --repo <代码仓>
light-patent mine <案件目录> --payload candidates.json
light-patent search <案件目录> --payload search.json
light-patent search-exec <案件目录> --payload exec.json
light-patent d1 <案件目录> --payload d1.json
light-patent claims <案件目录> --payload claims.json
light-patent text <案件目录> --kind specification --from spec.md
light-patent strip <案件目录>
light-patent render-docx <案件目录>
light-patent redteam <案件目录> --payload redteam.json
light-patent check <案件目录>
light-patent validate <案件目录>
light-patent status <案件目录>
```

全部命令输出 JSON，纪律错误逐项点名。查新渠道层见
`light-patent channels`（官方人工辅助为默认；自动化默认关，
开启须登记 light-crawler 预检引用）。

## 目录

- `SKILL.md`：规程本体（坐标、LP-01–LP-12 硬约束、84 号令引文）。
- `light_patent/`：实现（intake/novelty/draft/check/oa/ledger/
  radar/channels/validate/cli）。
- `tests/`：69 项（审计决策表、渠道与最小披露、查新纪律、撰写
  与检查咬合、答复第 33 条、台账期限、校验兜底、评测集、
  DOCX 渲染核验、检索执行通道含假 runner/假 transport 钉测）。
- `examples/demo-fullrun/`：端到端演示（火鸡主线脱敏自造案例，
  `run_demo.py` 离线可重跑，报告见其 demo-report.md）。
- `eval/`：12 个封闭评测案例 + 参考答案 + 确定性评分器（Q10）。

## 已知局限

1. 检索执行已落地两个渠道（search-exec）：epub 经
   light-crawler 全链驱动（门归 crawler，本包不代行）、EPO
   OPS 经官方 API 适配器。实测边界如实记：epub 的预检门已实
   连验通，但 2026-10-21 本机出口网络下该站 robots 不可达、
   预检失败关闭，检索结果页端点与解析器未经真实页面验证
   （仅自造 fixture 钉测）；OPS 待用户提供注册凭据后实连
   （当前 credential_gap）。两轮召回的第二轮由第一轮结果的
   IPC 高频号建议驱动、仍逐轮显式执行，不自动连发。
2. 先行基础检查为启发式（WARN 级），须人工复核。
3. 答复期按通知书登记月数机械算，不臆定具体程序的法定细则。
4. FTO/对照表、专利地图、布局围栏、解读为后置项（v1.1 登记），
   v1 只出查新与 worth-it 的初筛底稿形态。
5. 演示中的递交与审查意见均为模拟件，已逐项标注「演示模拟」。
