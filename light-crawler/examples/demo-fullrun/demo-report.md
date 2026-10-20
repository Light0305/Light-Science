# light-crawler 演示报告（demo-fullrun）

演示形态（构建判断 J1）：主链跑在本地自搭夹具站点上（确定、无真实目标风险），被拒案例按学习期纪律用本地夹具演示，不拿真实站点试拒；另在第 13 步以**同一条全链**试跑一次真实官方 API（OpenAlex），结果如实记录、不作通过判据。逐段证据在 evidence/（demo-transcript.txt、05-gate-check.json），工作区产物在 project/data-sources/。

## 全链结果（据 evidence/demo-transcript.txt 原文）

| 步 | 动作 | 结果 |
|---|---|---|
| 1–2 | init + 登记四目标 | 工作区建成；demo-api（official_api）、demo-web（web_page）、demo-private（URL 模式含 /private）、demo-down（主机不可达） |
| 3 | 预检 | demo-api effective（低危自动生效）；demo-web pending_confirmation（高危分级）；demo-private **blocked**（robots 命中 disallow: /private，RFC 9309 第 2.2 节）；demo-down **blocked**（robots 不可达、失败关闭，RFC 9309 第 2.3.1.4 节 MUST，原文附 URLError） |
| 4 | confirm | demo-web 经具名（演示用户）确认后生效（S4） |
| 5 | gate-check | demo-api ready=true，有效间隔 1.0s（模板下限裁决），precheck 号落证据 |
| 6–7 | fetch | demo-api 落盘 2（JSON + HTML，清洗件含标题与正文）；demo-web 落盘 1 |
| 8 | fetch demo-private | 被 guard 在发请求前拒绝，理由即预检 blocked 原文，拒绝落事件账 |
| 9 | 增量 | /data.json 带 ETag 条件请求回 304：未变更 1、不落新版（C5） |
| 10 | import | 人工导出 CSV 经 import 落盘（通道 manual_import，来源说明与经手人齐全，同 provenance 口径） |
| 11 | validate | ok（登记自洽 + provenance 哈希重算全对） |
| 12 | refusals | 拒绝留痕共 3 条（两次 precheck_blocked + 一次 fetch_refused），命令可查 |
| 13 | 真实试跑 | OpenAlex 目标登记 → 预检 effective（robots outcome ok）→ fetch 落盘 1（works/doi 10.1016/j.compag.2025.110856 的 JSON），无错误 |

## 演示证明了什么

- 预检三件齐全：目标级逐项检查（robots 结论带规则与 RFC 节号）、项目锁在位（本演示未触发抬升，单测覆盖）、拒绝留痕成清单。
- 分级生效真实运转：同站两个目标，一个自动生效、一个非确认不能抓，guard 在确认前对 CLI fetch 返回拒绝（tests/test_cli.py 钉住）。
- 失败关闭不是口号：主机不可达目标在预检期即 blocked，且 fetch 期还有第二道 robots 复核。
- 增量与版本纪律：304 不落新版；内容变化时新行以 supersedes 指向旧行（tests 钉住）。

- **完成项**：全链 13 步走完（证据 evidence/demo-transcript.txt）；本地夹具四目标的预检/确认/采集/增量/导入/校验全部按预期；真实 OpenAlex 试跑预检 effective 且落盘 1 条。
- **跳过项**：浏览器通道真实执行未演示——执行器按 S1 窄口径不随包提供，演示只走到预检门与如实拒绝（tests 以注入式假执行器验证了契约）；WARC 档未演示（S3 定版 v1.1）。
- **未验项**：真实站点上的 403/429 熔断链未在演示中触发（不拿真实站点试拒是纪律）；该链路由本地夹具单测覆盖（tests/test_fetch.py 的 403/429/熔断三例）。
- **风险**：OpenAlex 匿名调用在本机共享出口 IP 下曾有 429 前科，本次试跑成功不代表每次可达；被限流时本包按 HC-8 即停并留痕，属预期行为而非故障。
