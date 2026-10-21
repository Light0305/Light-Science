# light-crawler

Light-Science 的项目数据采集通道层（LD-02 通道层扩展位）：为科研项目从外部来源**合规地**批量取数——目标登记、合规预检、通道优先级、速率公式、轻量留存与 provenance 一条链。生态里的爬虫框架普遍「有合规件、无合规门」，本包把每一件都定成默认开的代码硬门。

## 核心纪律（速览）

- **无登记不抓取**：fetch 前 guard 逐项点名校验，本包不设任何绕过旗标。
- **robots 失败关闭**：5xx 或网络不可达即全面禁止（RFC 9309 第 2.3.1.4 节 MUST）；4xx 才放行（第 2.3.1.3 节）。
- **预检分级生效**：官方 API/开放数据自动生效；网页/浏览器须具名人工确认（S4）。浏览器默认关（S1）；具名者可把目标列入项目级预授权名单（D1，2026-10-21 批准）免逐个确认，名单增删与命中全部留痕，名单外手续原样。登录态经凭据访问通道开放（S2 口径沿革见 SKILL 第 4 节）：逐目标声明权限依据、凭据只经 vault 引用注入、会话只由浏览器通道承载，人工导出 + 登记导入仍是正当替代。
- **robots 缓存复用（D8）**：预检取回的 robots 原文按哈希缓存 24 小时，执行期比对哈希复用、不重复请求；哈希不符即作废重取并留痕。
- **速率只按公式**：max（登记值， robots crawl-delay， 模板下限， 项目锁下限），并发固定 1；crawl-delay 不是 RFC 内容，依据是站点公示意愿与本包自律。
- **被拒即停、全程留痕**：403/429 即停，连续两 run 被拒熔断；一切拒绝进可查询的留痕清单。
- **provenance 不可关**：原始响应内容寻址留存 + 哈希，版本链 supersedes 指针，validate 重算点名。

## 快速上手

```bash
cd <项目>/data-sources        # 工作区目录（项目根 data-sources/）
light-crawler --root . init --project <项目名>
light-crawler --root . register --file <登记.yaml>     # 模板见 examples/templates/
light-crawler --root . precheck --target <target_id>   # 低危自动生效 / 高危待确认
light-crawler --root . confirm --target <target_id> --by <姓名> --note <依据>
light-crawler --root . browser-preauth add --target <target_id> --by <姓名> --reason <理由>   # D1 名单（list/remove 同理）
light-crawler --root . fetch --target <target_id> [--url <url> ...]
light-crawler --root . discover --target <target_id>   # 发现 pass：端点/链接/sitemap 入发现账
light-crawler --root . crawl --target <target_id>      # frontier 任务：策略链 + 发现扩展 + 断点续跑
light-crawler --root . sources --target <target_id>    # 发现账（可枚举数据源）
light-crawler --root . validate                        # 登记自洽 + 哈希重算
light-crawler --root . refusals [--type <拒绝类>]     # 拒绝留痕清单（可按类计数）
```

依赖只有 PyYAML（传输与渲染编排走标准库；浏览器通道另需系统 Chromium，经 CDP 驱动）；在共享 venv 中从包根运行测试：`../.venv-lit/bin/python -m pytest`（116 项，含强化夹具对照、决策落地验收、深档抽取回归与第五批 simhash 近重 / WARC 档验收）。

## 演示

examples/demo-fullrun/：本地夹具站点上的全链演示（登记 → 预检 → 确认 → 采集 → 留存 → 校验），含 robots Disallow 与 robots 不可达（失败关闭）两例被拒留痕，另以同一全链试跑一次真实官方 API（OpenAlex）并如实记录结果。见该目录 demo-report.md。

## 已知局限

定时调度不在包内、回环/内网目标的浏览器渲染走传输桥接模式（Chrome 的 Local Network Access 检查所致，engine 字段如实标注）——详见 SKILL.md 第 12 节。留存两档：默认轻量档（原始字节 + 哈希）与 warc_full 全记录档（ISO 28500，纯标准库实现，逐记录摘要可回读复算，第五批落地）；另有 simhash 跨 run 近重检测（指纹库持久化、命中只标记不删除，阈值登记可配）。清洗现为两档：html_text_v1 轻档与 trafilatura_v1 深档（v1.2 增，深档为可选依赖，缺席/失败如实降级回轻档并留痕；带标注页面回归集见 eval/，双档要点召回同为 29/29、噪声泄漏轻档 20/20 对深档 1/20）。

## 许可

MIT，Copyright (c) 2026 light-crawler contributors。
