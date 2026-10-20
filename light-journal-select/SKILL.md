# Light-Journal-Select

> Light-Science 子技能：Light-Write 前置扩展位（拍板 E1，进主仓与
> 十件套并列，不改号）。位于 Light-Analysis 出结论包之后、
> Light-Write 开工之前。设计依据：`08-journal-select/LEARNING.md`
> （硬约束 JS-01 起）与 `REDESIGN-DRAFT.md` v0.1（含拍板附录 E1–E5）。
>
> **版本：v1.0（2026-10-20 封版）**。§1–§9 为已实现规程
> （Phase 1 承接/先例/核验/风险门/报告 + Phase 2 的 decide /
> handoff），§10 为诚实边界，§11 为与 LEARNING-14 的对应表。
> 端到端真实联网演示见 `examples/demo-fullrun/`（终点
> handed_off，结论与实测问题见其 demo-report.md 第四节）。

## §1 定位与边界

1. 每次投稿（一篇稿 / 一轮投递）运行一次，产物落本地项目目录；
   **不建常驻期刊数据库**——每次运行实时查询，证据随报告落盘即
   为该次选刊的全部留痕。
2. 只做四件事：解析稿件指纹、生成并核验候选、过风险门出证据卡、
   定刊后备齐 Write 的开工交接物（Phase 2）。
3. 不做：不判稿件质量、不预测录用、不给唯一最优解；不代用户投稿；
   档位是投稿策略分层（challenge / target / safety），不是质量判定。

## §2 文件群

| 文件 | 内容 |
|---|---|
| `selection.yaml` | 登记头（权威）：指纹、约束、候选池、风险门结果、excluded[] 留痕、状态机 |
| `evidence/` | 先例路原始响应留痕（OpenAlex JSON，逐查询一份） |
| `SELECTION_REPORT.md` | 选刊报告：约束清单 + 三档证据卡 + 已排除清单 + 时效声明 + finder 手工区 + 附录 |
| `selection.json` | 机器可读全集导出（report 生成，供衔接段与追踪消费） |
| `journal/target/` | 定刊后单刊目录（Phase 2，E5：guideline/ + templates/ + download-manifest.json + check-record.json） |

状态机：`draft → candidates_ready → verified → gated → decided
→ handed_off`，跃迁由工具逐项点名缺口，不许跳段。

报告文件名以实现为准定版为 `SELECTION_REPORT.md`（草案 §五曾用
名 `journal-selection-report.md`，已弃用，不再使用）。

## §3 指纹与约束规程（S1：指纹段）

1. 从题摘抽结构化指纹七区：领域、专长、研究对象、核心问题、
   贡献类型、受众、方法角色。**方法不许冒充领域**，除非贡献
   本身是方法学（methods_role 落字区分）。
2. 由指纹构造 2–3 条判别性检索式（precedent 消费）。
3. 约束八键必须在场（`tier_expectation / apc_budget /
   review_cycle_limit / excluded_journals / excluded_publishers /
   excluded_modes / journal_language_pref / recognized_catalogs`）；
   缺项不许静默默认——值可为「未设」（None），报告逐项点名。
   约束未与用户对齐前先给投稿策略初判请用户校正（规程层），
   用户明说「默认推荐」才按默认集继续（冲稳保都要、无 IF 下限、
   APC 未知可接受但须披露）。
4. 专有排名（EasyScholar 等）只许用户自备 Key 时实时查询，
   Key 不落盘不入报告（JS-11 口径）；IF / 分区等专有数值只许
   实时查询后带源落卡，**永不落任何常驻存储**。

## §4 候选生成规程（S2：先例路为主，E2）

1. **先例路（主路）**：`precedent` 命令按检索式查 OpenAlex 近
   5 年同题论文（每式约 50 篇，剔撤稿与非研究类），按刊聚合，
   **按刊同期发文量归一化**（rate_per_10k），过入门门槛
   （相似 ≥2 篇 / 覆盖 ≥2 式 / 单式名次 ≤3）入池；每刊留
   ≤5 篇真实先例。原始响应落 `evidence/`，失败如实落
   `failed`——不编造、不静默跳过。可选 API Key 的注入与
   脱敏纪律见 §10。
2. **检索补充路**：新刊 / 小刊 / 中文刊（OpenAlex 覆盖薄）经
   联网检索后用 `add-candidate --source search` 入池，指标层
   允许留空（未确认），靠 scope 与国内目录命中核验支撑。
3. **finder 路（E2）**：出版商 finder 不进自动流程（只推自家
   刊）；报告尾附人工复核清单（链接 + 可粘贴文本 + 偏倚
   提示）；用户带回的结果用 `--source finder_manual` 入池，
   过同一核验与风险门。
4. Jane 局限内化（JS-05）：先例统计的语料是 OpenAlex 全学科
   （不是 PubMed-only）、窗口近 5 年、不用相似度和裸排序
   （已归一化），先例刊仍须全数过风险门（先例里会有掠夺刊）。

## §5 逐刊核验纪律（S3，JS-01/02/03）

1. **指标零记忆（JS-01）**：IF、分区、APC、审稿周期、收录、
   预警、自引率、年发文量一律不许凭记忆报数；verified 的值
   必须带「来源 URL + 指标年份/版本 + 查询日期」三元组，
   裸数值被校验器直接拒绝。
2. **未确认如实（JS-02）**：查不到写 `unconfirmed`（value 必须
   为空），并带 source_status 四态（succeeded / attempted /
   partial / skipped）说明；未确认指标不加分、**不参与分档**。
   风险源不可用时明写「名单核查未完成」，不许宣称某刊安全。
3. **来源优先级（JS-03）**：scope / APC / 政策以官网为权威；
   收录以 MJL / Scopus 官方名单为权威；聚合站只作回退与经验
   信号。冲突时官方优先，冲突与取舍必须落字
   （conflict_resolution），不许静默取一。防混淆：ESCI 有
   IF ≠ SCIE 收录；SJR 分区 ≠ JCR 分区。
4. **审稿周期双路（E4）**：官方统计优先；LetPub 等众包可入卡
   但强制三标注（众包口径 + 样本量，未知写「未披露」+ 查询
   日期），且**不单独决定分档**；皆无写「未确认」。

## §6 风险门（S4，E3 分级硬度）

1. **硬排除（不可放行）**：中科院预警名单命中 / 已停刊或被
   Scopus·WoS 剔除 / 官网 scope 明显不符 / 命中用户排除项。
   命中即出局，用户确认也不许放行；只进报告「已排除」清单
   与 `excluded[]` 留痕（只增不改）。
2. **准硬门（默认排除，可知情放行）**：掠夺 / 劫持社区名单
   命中、官网域名与登记不一致（劫持嫌疑同级）。放行须用户
   书面知情确认记录字段齐全（确认人 + 确认文本 + 日期），
   命中理由与放行一并永久留痕，证据卡上必须显形。
3. **软警告**：APC 不透明、周期只有众包数据、自称 OA 不在
   DOAJ、自引率 >20%、年发文量异常膨胀、ESCI-only、指标
   过期未复核、finder 来源偏倚——保留推荐，卡上显形。
4. 数据源只用合法开放源：本地可注入名单文件（stop-predatory
   风格 CSV，随 skill 分发须注版本）+ 预警/停刊联网核查登记。
   命中记录必须带来源，无源不许落命中。

## §7 分档与证据卡（S5）

1. 证据序：先例 > scope > 主题 > 指标。只有刊名/指标支撑、
   无先例无 scope 核验的候选标「暂定」，至多落 safety。
2. 三档共 3–5 张卡；challenge 无合格者如实留空，不许凑数。
   约束冲突（APC 超预算、官方周期超上限）只据 verified
   指标判定并在卡上落标记。
3. 每卡字段缺一不可（取不到写「未确认」）：刊名 / ISSN /
   出版商 / 官网与指南链接、档位、匹配理由（由证据机械
   生成）、先例样例 2–3 篇（题名+年份+DOI）、指标表
   （值+来源+年份+查询日期）、风险提示。
4. 报告含：策略与约束清单、三档卡、未入卡备选、已排除
   清单、数据时效声明、finder 人工复核清单、附录（指纹 +
   检索式 + 先例运行留痕 + 近失刊）。

## §8 CLI（Phase 1 + Phase 2）

```
light-journal-select init <root> --title <题> --language en|zh [--type research|review|methods]
light-journal-select fingerprint <root> --file <指纹.json>
light-journal-select precedent <root>
light-journal-select add-candidate <root> --name <刊名> --source search|finder_manual [--detail <出处>]
light-journal-select verify <root> --file <核验.json>
light-journal-select gate <root> [--name-list <名单.csv>] [--checks <核查.json>] [--override <放行.json>]
light-journal-select report <root>
light-journal-select decide <root> --candidate <id|刊名> --by <定刊人> --reason <理由> [--date <日期>]
light-journal-select handoff <root> --fields <指南字段.json> [--files <下载登记.json>] [--write-root <light-write 路径>] [--guideline-version <版本>] [--date <日期>]
light-journal-select validate <root>     # 0 errors 才 exit 0
light-journal-select status <root>
```

## §9 定刊与交接（Phase 2，decide / handoff）

1. **decide**：仅 gated 可定刊。decision 四项 {刊、日期、
   定刊人、理由} 缺一不可（理由是决策痕）。定刊口不许绕门：
   已被风险门排除的刊（excluded 留痕在册，含未放行的
   quasi_hard）报错并点名排除级别与理由；池内 hard_exclude
   同样拒绝；quasi_hard 只有带有效书面放行记录才许定刊。
   跃迁 gated → decided。
2. **handoff**：在项目 `journal/target/` 建单刊目录
   （guideline/<日期或版本>/ + templates/ +
   download-manifest.json + check-record.json + handoff.md，
   E5）。下载逐条登记：真拿到文件并入库的标 `downloaded`
   （逐文件 SHA-256 按入库字节算、来源 URL、下载日期）；
   拿不到的外站文件只许 `pending_download` 待下载条目
   （sha256 为空）——**不许伪造已下载**；未给下载登记时至少
   把作者指南以官网 URL 列入待下载清单。
3. **check-record 生成**：按 Write 九组字段（A–I，口径以
   light-write 的 `template_reg.py` / `schema.TEMPLATE_GROUPS`
   为准）现场生成：A 组身份字段由选刊包机械回填，
   `journal_language` 强制 = 稿件指纹语言（字段文件报的
   语言与指纹不符 = 拿错指南，报错拦截）；B–I 指南派生
   字段由执行者读官网作者指南后经 `--fields` 提供，工具
   不许凭空编造指南事实；H 组 verified_at 按交接当日落字。
4. **自检闭环**：记录先在内存组装，过本包本地结构校验
   （镜像 Write `check_template_record` 的 error 级规则，
   错误码同名）；配 `--write-root`（或环境变量
   `LIGHT_JOURNAL_SELECT_WRITE_ROOT`）时再以子进程调用
   真正的 Write 校验器自检。任一 error → 整批拒绝、不写
   交接物、不进 handed_off（产品代码不 import light_write，
   不形成跨包运行时依赖）。自检结论写入 handoff.md 与
   selection 的 handoff 登记块。
5. **交接清单 handoff.md**：列目标刊、target/ 路径、
   check-record 路径与自检结论、下载状态计数（待下载文件
   逐个点名），并给出 Write `register-template` 的确切
   调用行。模板与指南仅本地使用、不分发、不入公开仓。
6. **指南修订纪律**：handed_off 后重跑 handoff = 指南刷新：
   新指南进新版本子目录并存（旧版不删），manifest 新条目
   以 `supersedes` 指向被取代的旧指南条目、旧条目回填
   `superseded_by`，check-record 按新 verified_at 重新
   生成并重新自检，状态保持 handed_off，刷新留痕进
   handoff_history。
7. 未定刊则流程止于报告（报告即终产物）；decide / handoff
   的每一步缺口都逐项点名，不许半落盘。

## §10 诚实边界

- 校验器绿灯只表示「未发现自动可判的失败」，不表示某刊
  安全、适合或能中；报告中不存在「绝对安全」表述（JS-02）。
- 先例统计是去向证据不是质量证据；先例刊同样过风险门。
- 学习文档截断已补全对齐（2026-10-20）：LEARNING 的
  JS-05 末句据构建实现回填、JS-07 / JS-11 / JS-14 据存世
  交叉引用还原，REDESIGN-DRAFT §五–§七已回填，补全段落
  均在原文逐段标注来源类别；**JS-06 / JS-08 / JS-09 /
  JS-10 / JS-12 / JS-13 原文佚失**（全域无从考据，只留
  占位），待学习期重做。本实现的锚点为 JS-01–JS-05、
  JS-07、JS-11、JS-14、草案回填部分与拍板 E1–E5；
  不锚定佚失的 6 条，不许凭空补写约束条文。
- OpenAlex 匿名请求走共享免费日预算，耗尽时 429 如实
  落 `failed`、不编造。用户可自备免费 API Key，经运行
  进程的环境变量 `OPENALEX_API_KEY` 注入（JS-11）：
  Key 只活在进程内存与请求线，永不落盘——evidence、
  precedent_runs、日志与异常消息中的 `api_key` 参数
  一律脱敏为 `REDACTED`（tests/test_api_key.py 钉死）。
- 分档的卡位排序以归一化率（rate_per_10k）为单键：小刊
  分母小、单篇先例即可率值冲高（演示实测微型刊率
  270/万篇居首、领域旗舰刊 7 篇先例反被挤出卡外）。
  读报告时须连同先例篇数与覆盖式数看卡，不许只看档位
  与率；此排序口径的复合化列入 v1.1 评估，v1.0 不改。

## §11 与 LEARNING-14 的对应

| 约束 | 内容 | 落点 |
|---|---|---|
| JS-01 | 指标零记忆 | §5.1；verify 三元组强制、裸数值被校验器拒绝 |
| JS-02 | 核验失败如实标记，不许补猜 | §5.2；unconfirmed 四态、未确认不参与分档 |
| JS-03 | 来源优先级与冲突处置 | §5.3；官网权威、冲突落 conflict_resolution |
| JS-04 | 先例路为主路 | §4.1；OpenAlex 近 5 年同题去向统计、归一化、入门门槛 |
| JS-05 | Jane 的做法与局限必须内化 | §4.4；全学科语料（末句据构建实现回填） |
| JS-06 | **原文佚失** | **本实现不锚定**（无从考据，只留占位，待学习期重做） |
| JS-07 | finder 偏倚必须披露 | §4.3；finder 不进自动流程、报告尾人工区带偏倚提示 |
| JS-08 | **原文佚失** | **本实现不锚定** |
| JS-09 | **原文佚失** | **本实现不锚定** |
| JS-10 | **原文佚失** | **本实现不锚定** |
| JS-11 | 专有通道与 Key 纪律 | §3.4 + §10；Key 只经环境注入、永不落盘、落痕全程脱敏 |
| JS-12 | **原文佚失** | **本实现不锚定** |
| JS-13 | **原文佚失** | **本实现不锚定** |
| JS-14 | 中文刊口径 | §4.2；检索补充路入池、指标层允许留空、靠目录命中核验 |

另：风险门分级硬度（E3）、审稿周期双路（E4）、单刊目录
落盘（E5）与定名/定位（E1）、路线取舍（E2）来自拍板附录
E1–E5，不在 JS 编号内。
