# light-journal-select

Light-Science 子技能（Write 前置扩展位）：帮用户选刊 → 用户定刊 →
从目标刊官网下载模板与作者指南到本地项目 → 现场生成 Write
九组检查记录 → Write 开工。不建期刊信息库。

## 状态

**v1.0 已封版（2026-10-20）**。全链实现：指纹与约束 → 先例路
引擎（OpenAlex 实时统计 + 按刊发文量归一化）→ 逐刊核验纪律
→ 风险门（E3 分级硬度）→ 分档证据卡 → decide 定刊（定刊门：
被排除/未放行刊不许定刊）→ handoff（`journal/target/` 单刊
目录 + download-manifest 逐文件哈希与 pending 诚实登记 +
check-record 按 Write 九组字段现场生成、本地结构校验 + 可选
Write 校验器子进程自检、语言与指纹一致、handoff.md 交接
清单、指南修订新子目录并存）。端到端真实联网演示已跑通
（`examples/demo-fullrun/`，注入自备 OpenAlex Key）：先例路
3/3 式成功、21 刊入池、风险门排除虚构靶子、分档 target 5 刊、
定刊 Smart Agricultural Technology、check-record 双自检
pass、终点 handed_off、validate ok。演示结论与实测问题见
demo-report.md 第四节。

## 纪律速览

- **指标零记忆（JS-01）**：每个落字数值带来源 + 年份 + 查询日期；
- **未确认不加分（JS-02）**：未确认指标不参与分档，来源状态四态如实；
- **先例路为主（JS-04）**：近 5 年同题论文去向统计（OpenAlex，
  CC0），归一化防大刊霸榜，入门门槛防单篇偶合；
- **风险门分级硬度（E3）**：预警/停刊/scope 不符硬排除不可放行；
  掠夺/劫持名单默认排除，用户书面知情确认可放行且永久留痕；
- **审稿周期双路（E4）**：官方优先，众包强制三标注且不单独决定分档。

## 用法

见 SKILL.md §8（CLI）。全部命令输出 JSON，纪律错误逐项点名。

## 已知局限

- **学习文档 6 条约束原文佚失**：学习文档曾于落盘时截断，
  2026-10-20 已补全对齐：LEARNING 的 JS-05 末句、JS-07 /
  JS-11 / JS-14 与 REDESIGN-DRAFT §五–§七已回填并逐段标注
  来源类别；JS-06 / JS-08 / JS-09 / JS-10 / JS-12 / JS-13
  原文佚失、全域无从考据，只留占位，待学习期重做（本实现
  未锚定这 6 条，未凭空补写；对应表见 SKILL §11）。
- **OpenAlex 匿名 429 与 Key 路线**：匿名调用走共享免费日
  预算，出口 IP 预算耗尽时返回 429（先例路如实落 `failed`、
  不编造）；可用自备免费 Key 经环境变量 `OPENALEX_API_KEY`
  注入，Key 永不落盘（evidence 与日志中的 `api_key` 参数
  脱敏为 `REDACTED`）。
- **分档排序的小分母效应（演示实测）**：证据卡按
  rate_per_10k 单键排序取前 5，微型刊 1 篇先例即可率值
  冲高（实测 270/万篇居首），领域旗舰刊（7 篇先例、3 式
  全覆盖）反被挤出卡外。读卡须连同先例篇数与覆盖式数；
  复合排序列入 v1.1 评估。
- **候选官网 URL 恒缺（演示实测）**：OpenAlex works 的源
  记录为脱水形态、不含 homepage_url，候选 homepage_url /
  guide_url 恒为 None——官网 scope 核对无从触发（落
  unconfirmed）、check-record 的 H.source_url 须由执行者
  经 `--fields` 注入。v1.1 拟补 `/sources/{id}` 回填。
- **仓库型来源入池（演示实测）**：OpenAlex 中 type 为
  repository 的来源（如 Zenodo）会以候选身份入池；未做
  类型过滤，靠分档与人工读卡兜底，v1.1 评估过滤或标注。
- **verify 联网抓取的覆盖边界**：出版商官网页面抓取受限，
  专有指标（IF / 分区 / 自引率）无开放渠道，审稿周期无
  官方可抓统计——这些指标在本类环境下多为 unconfirmed
  （如实落痕）；当前开放数据条件下分档实际由先例证据 +
  收录/发文量驱动，challenge 档常为空（不凑数）。
- 先例路每刊多一次发文量查询（归一化分母）；OpenAlex 限流时
  分母取不到则 rate 留空（volume_status=attempted），不猜数。
- 中文刊在 OpenAlex 覆盖薄，主要靠检索补充路与目录核验（设计内口径）。
