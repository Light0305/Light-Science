# light-crawler

Light-Science 的项目数据采集通道层（LD-02 通道层扩展位）：为科研项目从外部来源**合规地**批量取数——目标登记、合规预检、通道优先级、速率公式、轻量留存与 provenance 一条链。生态里的爬虫框架普遍「有合规件、无合规门」，本包把每一件都定成默认开的代码硬门。

## 核心纪律（速览）

- **无登记不抓取**：fetch 前 guard 逐项点名校验，本包不设任何绕过旗标。
- **robots 失败关闭**：5xx 或网络不可达即全面禁止（RFC 9309 第 2.3.1.4 节 MUST）；4xx 才放行（第 2.3.1.3 节）。
- **预检分级生效**：官方 API/开放数据自动生效；网页/浏览器须具名人工确认（S4）。浏览器默认关（S1），登录态全关（S2，正当替代 = 人工导出 + 登记导入）。
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
light-crawler --root . fetch --target <target_id> [--url <url> ...]
light-crawler --root . validate                        # 登记自洽 + 哈希重算
light-crawler --root . refusals                        # 拒绝留痕清单
```

依赖只有 PyYAML（抓取传输走标准库 urllib）；在共享 venv 中从包根运行测试：`../.venv-lit/bin/python -m pytest`。

## 演示

examples/demo-fullrun/：本地夹具站点上的全链演示（登记 → 预检 → 确认 → 采集 → 留存 → 校验），含 robots Disallow 与 robots 不可达（失败关闭）两例被拒留痕，另以同一全链试跑一次真实官方 API（OpenAlex）并如实记录结果。见该目录 demo-report.md。

## 已知局限

浏览器执行器不随包（只有预检门与接入契约）、WARC 全记录档未做（ISO 28500，v1.1）、清洗只有 html_text_v1 一档、定时调度不在包内——详见 SKILL.md 第 12 节。

## 许可

MIT，Copyright (c) 2026 light-crawler contributors。
