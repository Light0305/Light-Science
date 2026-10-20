# 采集工作区报告（demo-poultry-research）

- 工作区状态：active（熔断目标：无）
- provenance 总账：4 条（抓取 3、人工导入 1）

## 目标

| 目标 | 通道 | 用途 | 预检 | 熔断 |
|---|---|---|---|---|
| demo-api | official_api | dataset_batch | effective | 否 |
| demo-down | official_api | dataset_batch | blocked | 否 |
| demo-private | official_api | dataset_batch | blocked | 否 |
| demo-web | web_page | dataset_batch | effective | 否 |

## 拒绝留痕（共 3 条）

- [2026-10-20T20:18:34+00:00] precheck_blocked 目标 demo-private：预检结论 blocked：robots 结论禁止 http://127.0.0.1:44309/private/secret.json：命中规则 disallow: /private（RFC 9309 2.2）
- [2026-10-20T20:18:34+00:00] precheck_blocked 目标 demo-down：预检结论 blocked：robots 结论禁止 http://127.0.0.1:56677：robots.txt 不可达（5xx 或网络错误），视为未定义，必须假定全面禁止（失败关闭）；错误：URLError: <urlopen error [Errno 111] Connection refused>（RFC 9309 2.3.1.4）
- [2026-10-20T20:18:34+00:00] fetch_refused 目标 demo-private：guard 拒绝：robots 结论禁止 http://127.0.0.1:44309/private/secret.json：命中规则 disallow: /private（RFC 9309 2.2）；合法替代：改走官方 API 通道重新登记，或人工获取后用 import 登记导入（预检门不设绕过旗标）
