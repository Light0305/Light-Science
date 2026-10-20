---
name: light-journal-select
description: Use when 需要为待投稿稿件选定期刊：按同主题先例证据推荐候选刊、过风险门、定刊后备齐该刊模板与作者指南并生成检查记录时。
version: "1.1"
author: light-journal-select contributors
license: MIT
---

# light-journal-select

> Light-Science 子技能：light-write 前置扩展位（拍板 E1，进主仓与
> 十件套并列，不改号）。位于 light-analysis 出结论包之后、
> light-write 开工之前。设计依据：`08-journal-select/LEARNING.md`
> （硬约束 JS-01 起）与 `REDESIGN-DRAFT.md` v0.1（含拍板附录 E1–E5）。
>
> **版本：v1.0（2026-10-20 封版）+ v1.1 增补（2026-10-21）**。
> §1–§9 为已实现规程（Phase 1 承接/先例/核验/风险门/报告 +
> Phase 2 的 decide / handoff），§10 为诚实边界，§11 为与
> LEARNING-14 的对应表。端到端真实联网演示见
> `examples/demo-fullrun/`（终点 handed_off，结论与实测问题
> 见其 demo-report.md 第四节）。
> v1.1 增补（第二轮拍板 JS-D01/D02/D03/D06 + JS-D04 重做六条
> 锚定）：取卡改证据量门槛 + 复合排序（§7）、官网 URL 回填
> （§4.1）、来源类型过滤（§4.1）、报告增证据构成段（§7）、
> scope 三项核验（§5.5）、声称回源头核验（§5.6）、录用率与
> 派生周期口径（§5.7）、费用组与许可组（§5.8）、名单版本
> 年份字段（§6.4）、政策必查项（§9.8）。

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
   - **来源类型过滤（JS-D03）**：聚合时 OpenAlex source 的
     type 明确非 journal 者（repository 如 Zenodo、conference
     等）不以期刊身份入池，逐条落 `source_type_exclusions`
     附记（刊名/类型/先例篇数/日期/理由）并进报告附录——
     留痕不静默丢弃；type 缺失（脱水记录不全）按 journal
     处置，不误杀。
   - **官网回填（JS-D02）**：works 的脱水源记录不含
     homepage_url，入池后自动对缺官网的候选回填——通道序
     为 OpenAlex `/sources/{id}` 全量记录、再 DOAJ 按 ISSN
     查登记页 homepage 链接（只认登记源，不跟随期刊自家
     「验证页」，JS-09）；结果落 `homepage_backfill` 块
     （状态/取值/通道/证据 URL/查询日期/逐通道尝试留痕，
     证据 URL 过 api_key 脱敏）；全通道失败落 unconfirmed
     不猜。回填成功后官网 scope 核对（§5）自动可触发、
     check-record 的 H 组 source_url 由候选 homepage 兜底
     （§9.3 既有链）。聚合同时落 `source_facts` 源事实快照
     （type / is_in_doaj / is_oa / listed_in / 查询日期），
     作白名单在册证据（JS-09）。
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
5. **scope 三项核验（JS-06）**：Aims & Scope 文案只是自述，
   不构成匹配证据。scope_fit 之外可经 verify 登记
   `scope_checks` 三项——近 2 年实发文章对应、最近 3 期
   目录、文章类型/邀请制官网核读——逐项与指标同口径校验
   （verified 带来源与查询日期）。匹配理由据此区分
   「实发核验」（三项皆 verified）与「文案核对」（只有
   scope_fit），卡面落字，不许把文案核对说成实发匹配；
   三类落差点名：scope 随主编更替漂移、文案宽泛而实发
   狭窄、类型名相同而内涵不同。
6. **声称回源头核验（JS-09）**：白名单优先——正面证据取
   在册事实（DOAJ 在册、MJL / Scopus Sources 源记录、
   COPE / OASPA 会员名录、OpenAlex listed_in 与源事实
   快照）；黑名单只作调查线索，不作排除唯一依据，更不许
   以「不在黑名单上」反推安全。一切身份与背书声称必须在
   声称所指的源头核验：收录查源记录、会员查组织名录、
   指标查出具方；**不许跟随期刊给出的「验证页」链接**
   （已有仿冒验证页），核验入口由核验者自行输入官方
   地址。收录（indexing）以聚合源落 verified 时校验器
   给警告，提示回源头复核。在册事实带查询日期，往期
   在册不等于当前在册。
7. **录用率与派生周期（JS-10）**：`acceptance_rate` 指标
   verified 只许期刊官方公布口径（provenance=official），
   其余来源校验层拒收；未官方公布一律写「未确认」，不许
   以个案经验、论坛帖子或先例样本量估算冒充。由实发文章
   收稿/录用日期倒推的周期属派生估计：条目带
   `derived: true` 与 `derivation` 方法落字（缺方法报错），
   卡面与官方统计分列并标「派生」，不参与约束判定；
   众包数字另有系统性偏差（自报样本非随机、与录用结果
   正相关、学科基线差异大），只作经验信号。
8. **费用组与许可组（JS-12）**：APC 的 verified 值应登记
   为结构化费用组——标价 + 币种 + 收费时点（投稿时/录用
   后/发表时，未披露写 None）+ 附加费清单（与主费用分开
   登记）+ 减免有无 + 本单位协议覆盖状态（未知写
   unknown）；标价不等于实付，卡面逐项显形。旧标量值
   兼容读取（迁移警告 + 卡面标「仅标价，费用组未
   结构化」）。费用时点未披露时校验器给 apc_opaque 衔接
   警告（与 §6.3 软警告口径衔接：投稿前不公开费用、录用
   后才揭示是掠夺行为标记）。OA 不是布尔值：经 verify
   登记 `oa_license` 许可组（OA 模型 / CC 许可类型 /
   作者保留权利 / 自存档政策 + 来源与查询日期），选刊
   约束中的 OA 要求落到许可层。

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
5. **名单证据纪律（JS-08）**：命中是信号，不是定罪，四类
   名单不许混用口径。预警名单是风险提示而非黑名单——官方
   说明明言预警不是论文评价，**不许回溯评价已发论文**；
   掠夺判定锚定行为（欺骗性收费、无真实同行评审、虚假
   收录声称、保证录用），新刊/区域刊/低收费/无 IF 本身
   不构成掠夺证据；**被劫持的正刊是受害者、非排除对象，
   排除的是克隆网址**，候选入池以官方登记网址为锚，网址
   不一致按劫持嫌疑处置。命中落字带名单名 + 版本/年份 +
   查询日期：名单 CSV 可带 `version` 与可选 `year` 列，
   名单生成的核查记录强制落 `list_version` / `list_year`
   结构化字段（显式 year 列优先，否则从 version 串解析
   四位年份）；校验器对名单源命中缺版本与年份者报错。
   名单未命中也不许宣称安全（JS-02）。

## §7 分档与证据卡（S5）

1. 证据序：先例 > scope > 主题 > 指标。只有刊名/指标支撑、
   无先例无 scope 核验的候选标「暂定」，至多落 safety。
2. 三档共 3–5 张卡；challenge 无合格者如实留空，不许凑数。
   约束冲突（APC 超预算、官方周期超上限）只据 verified
   指标判定并在卡上落标记；政策冲突（JS-13）同样计入
   标记并封 challenge。
3. **取卡两步（JS-D01）**：先过卡位证据量门槛——与入池
   门槛同构的三叉（先例不少于 3 篇，或覆盖不少于 2 式且
   篇数不少于 2 篇，或单式名次不大于 3；阈值以演示数据
   回放校准定版），无先例统计的候选走暂定路径不受此门；
   门槛内按复合键排序取卡：覆盖检索式数优先，其次复合权
   （先例篇数乘以 ln(1 + 归一化率)——篇数加权压住小分母
   率值膨胀），再篇数、率、刊名兜底。每刊落 `ranking`
   分解块（门槛判定与依据、各因子、声望、风险级），卡面
   渲染排序因子行，逐项可溯；未过门槛者留备选并在报告
   点名依据。风险级先行过滤（is_eligible）、费用与周期
   经约束标记参与分档、声望只读 verified 分区——排序
   因子全集即：先例强度（覆盖+加权率）、声望、风险、
   约束冲突。
4. 每卡字段缺一不可（取不到写「未确认」）：刊名 / ISSN /
   出版商 / 官网与指南链接、档位、排序因子行、匹配理由
   （由证据机械生成）、先例样例 2–3 篇（题名+年份+
   DOI）、指标表（值+来源+年份+查询日期）、许可组（已
   登记时）、政策核读（已登记时）、风险提示。
5. **证据构成段（JS-D06）**：报告含「本轮分档证据构成」
   段（同数据落 selection 的 `evidence_composition` 块
   进 selection.json）：逐档给刊数、先例总篇数、覆盖、
   verified 与未确认指标条数、白名单在册命中数、众包/
   派生周期条数、政策冲突数；空档逐档落字说明证据构成
   不足以支撑该档，不只留空档。读卡纪律：档位不是完备
   评估结论，须连同本段与卡面因子看。
6. 报告含：策略与约束清单、三档卡、证据构成段、未入卡
   备选、已排除清单、数据时效声明、finder 人工复核清单、
   附录（指纹 + 检索式 + 先例运行留痕 + 近失刊 + 来源
   类型排除附记）。

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
8. **政策必查项（JS-13）**：与投稿合规直接相关的期刊政策
   必须在定刊时点从该刊（或出版商）官网现行页面逐刊
   核读，不许以「通行惯例」代替。handoff 字段文件可带
   `policies` 逐刊核读条目（topic / status / finding /
   source_url / accessed_at），必查两项为 AI 使用与披露
   （ai_use_disclosure）、数据/代码可用性
   （data_code_availability），其余主题（预印本、利益
   冲突、作者资格等）按本稿情形带回；条目过三元组校验
   后落 `selection.policy_checks` 并渲染进 handoff.md
   点名带回，与 Write 的 use_log 和 G 组声明衔接。政策
   是活文本：快照带访问日期，定刊到投稿间隔过长或政策
   页更新时必须复核，过期快照不许当现行政策引用。条目
   报 conflict（本稿情形与该刊政策冲突）即阻断交接——
   政策不合规是阻断项不是提示项，须回报告处置后再
   交接；必查项未覆盖者落 `handoff.policy_gaps` 并在
   handoff.md 显形、校验器给警告，不静默。候选级核读
   可经 verify 登记 `policy_checks`，卡面显形，冲突
   计入约束标记并封 challenge（§7.2）。

## §10 诚实边界

- 校验器绿灯只表示「未发现自动可判的失败」，不表示某刊
  安全、适合或能中；报告中不存在「绝对安全」表述（JS-02）。
- 先例统计是去向证据不是质量证据；先例刊同样过风险门。
- 学习文档截断条文已重做并锚定（2026-10-21，JS-D04）：
  JS-06 / JS-08 / JS-09 / JS-10 / JS-12 / JS-13 六条原文
  佚失后已按全套普查规矩重新深读立起（LEARNING 逐条标注
  「v1.1 重做」与来源类别，非原文还原），并在本包逐条
  落地锚定（落点见 §11 对应表）。其余存世条文的补全
  对齐沿 v1.0 口径（JS-05 末句据构建实现回填、JS-07 /
  JS-11 / JS-14 据存世交叉引用还原，逐段标注来源类别）。
- OpenAlex 匿名请求走共享免费日预算，耗尽时 429 如实
  落 `failed`、不编造。用户可自备免费 API Key，经运行
  进程的环境变量 `OPENALEX_API_KEY` 注入（JS-11）：
  Key 只活在进程内存与请求线，永不落盘——evidence、
  precedent_runs、日志与异常消息中的 `api_key` 参数
  一律脱敏为 `REDACTED`（tests/test_api_key.py 钉死）。
- 分档取卡排序已复合化（v1.1，JS-D01）：v1.0 的
  rate_per_10k 单键曾使微型刊 1 篇先例率 270/万篇居首、
  旗舰刊 7 篇/3 式被挤出卡外；现行口径为证据量门槛 +
  复合键（§7.3），演示数据回放中旗舰刊居首、微型刊
  落选。复合键仍只是取卡顺序：率值本身不构成推荐理由，
  读卡须连同 ranking 分解、先例篇数与证据构成段看。
- 官网回填的覆盖边界（JS-D02）：回填只走 OpenAlex 源
  记录详情与 DOAJ 登记两条登记源通道；两路皆无官网的
  候选（不在 DOAJ 的混合刊居多）homepage 仍落
  unconfirmed、scope 核对随之未确认，不许以聚合站或
  搜索结果冒充官网回填。
- 政策必查项的硬度边界（JS-13）：必查项以「清单 + 缺项
  显形 + 已报冲突硬阻断」落地，未做成 handoff 前置硬门
  （G 组 ai_policy 与 declarations 已是既有必填政策面）；
  未覆盖的必查项在交接清单与校验警告中持续点名，投稿
  前必须补核，不得视为已核。

## §11 与 LEARNING-14 的对应

| 约束 | 内容 | 落点 |
|---|---|---|
| JS-01 | 指标零记忆 | §5.1；verify 三元组强制、裸数值被校验器拒绝 |
| JS-02 | 核验失败如实标记，不许补猜 | §5.2；unconfirmed 四态、未确认不参与分档 |
| JS-03 | 来源优先级与冲突处置 | §5.3；官网权威、冲突落 conflict_resolution |
| JS-04 | 先例路为主路 | §4.1；OpenAlex 近 5 年同题去向统计、归一化、入门门槛 |
| JS-05 | Jane 的做法与局限必须内化 | §4.4；全学科语料（末句据构建实现回填） |
| JS-06 | scope 匹配须以近期实发文章核验（v1.1 重做） | §5.5；scope_checks 三项（近 2 年实发/近 3 期目录/文章类型核读）逐项三元组校验，匹配理由区分实发核验与文案核对 |
| JS-07 | finder 偏倚必须披露 | §4.3；finder 不进自动流程、报告尾人工区带偏倚提示 |
| JS-08 | 风险名单的证据纪律：命中是信号不是定罪（v1.1 重做） | §6.5；名单记录落 list_version/list_year 结构化字段（校验器对名单源命中缺版本年份报错），预警不回溯、劫持排除克隆网址两句口径落字 |
| JS-09 | 白名单优先，声称须在源头核验（v1.1 重做） | §5.6 + §4.1；回源头核验清单与不许跟随验证页链接落字，source_facts 快照（is_in_doaj/listed_in）为可注入白名单证据，收录聚合源 verified 给警告 |
| JS-10 | 审稿周期与录用数据的口径（v1.1 重做） | §5.7；acceptance_rate verified 只许官方口径（校验拒收其余来源），派生周期带 derived + 方法落字、分列不参与约束判定，众包偏差口径落字 |
| JS-11 | 专有通道与 Key 纪律 | §3.4 + §10；Key 只经环境注入、永不落盘、落痕全程脱敏 |
| JS-12 | 费用与开放获取的全成本口径（v1.1 重做） | §5.8；APC 结构化费用组（标价/币种/时点/附加费/减免/协议覆盖）形态校验 + 标量兼容读，许可组 oa_license 登记校验渲染，费用时点未披露给 apc_opaque 衔接警告 |
| JS-13 | 期刊政策逐刊核读与时效（v1.1 重做） | §9.8；政策必查项（AI 披露、数据/代码可用性）逐刊核读条目带三元组落 policy_checks 并进 handoff.md 点名带回，冲突阻断交接，缺项落 policy_gaps 显形 |
| JS-14 | 中文刊口径 | §4.2；检索补充路入池、指标层允许留空、靠目录命中核验 |

另：风险门分级硬度（E3）、审稿周期双路（E4）、单刊目录
落盘（E5）与定名/定位（E1）、路线取舍（E2）来自拍板附录
E1–E5，不在 JS 编号内。
