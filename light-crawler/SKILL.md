---
name: light-crawler
description: Use when 需要为 Light-Science 科研项目从外部来源批量获取数据（数据集、文献线索批、整刊 OA 全文批、基准或排行榜页面快照），或登记新数据源、查询某目标的合规预检结论与熔断状态时。
version: "1.1"
author: light-crawler contributors
license: MIT
---

# light-crawler SKILL（v1.1）

> 定位：Light-Science 的项目数据采集**通道层**（LD-02 通道层扩展位，不进十阶段主流水线）。给 light-literature 供文献线索批与批量全文获取批、给 light-experiment 供数据集获取批与基准页面快照。生态现状是「有合规件、无合规门」（Scrapy 的 ROBOTSTXT_OBEY 默认 False 为缩影），本包的差异化就是把合规件全部反着定成默认开的**代码硬门**：无登记不抓取、robots 失败关闭、预检分级生效、速率只按公式、被拒即停、一切拒绝留痕。
> 位置：工作区落项目根 `data-sources/`（LD-02 目录规范）；接入模型在任何取数动作前先读本文件并跑 guard 链，不许绕开 CLI 直接发请求。
> v1.0 定版（2026-10-21）：坐标 C0–C6 + 硬约束 HC-1 至 HC-8 + S1–S7 拍板落点；演示见 examples/demo-fullrun/demo-report.md（本地夹具站点全链 + 两例被拒留痕 + 一次真实官方 API 试跑如实记录）。
> v1.1 能力强化（2026-10-21，用户点名「爬虫太弱、遇到点啥就撞」后立项）：传输 v2、浏览器执行器随包、接口发现、frontier 断点续爬、回退策略链、自适应限速、凭据访问通道，详见第 14 节；S2 口径沿革见第 4 节，默认口径清单在工作区 20-build/crawler-decision-list.md。
> 决策落地（2026-10-21，用户对决策清单 D1–D10 全按推荐批准后施工）：D1 浏览器预授权名单、D8 robots 预检缓存复用已落码；D3/D6 以计数查询与示例措辞落地；其余各条按批准维持现状。施工记录见 20-build/crawler-decisions-impl.md。

---

## §1 定位与边界

- **只做批量与非文献数据**（S5）：单篇文献全文获取归 light-literature 的 Doc2X 与模型直读双轨，不进本包目标类型（登记层即拒 single_fulltext）。
- **不做通用爬虫教程、不做平台运营数据生意**：目标只能是为具体科研项目登记的数据源，产物只供已登记的消费方（consumer 字段点名到包与环节）。
- **登录态走凭据访问通道**（S2，口径沿革见第 4 节）：以用户本人账号或机构授予的权限访问的，逐目标登记 login_state（user_account / institutional）+ entitlement_basis + credential_ref（只许 vault 引用），会话由浏览器通道承载；凭据本体只经接入运行环境注入，永不落盘。正当出口另有：官方 API、机构授权通道、人工导出后用 import 登记导入。
- **权限外不绕**（HC-7，构建方边界）：不提供以技术手段突破付费墙、登录墙、验证码去获取**无权限**内容的规程与配置；隐身、指纹模拟、代理轮换、验证码代解、假账号、凭据共享、盗版镜像一律不进本包工具箱。此界是构建方（Muse）的线、非用户口径（用户 2026-10-21 表态为可以绕、沿革见第 4 节 S2 行与决策清单），落字时不许混淆。平台技术措施一旦针对抓取设置（令牌、签名、指纹校验），即视为访问控制信号：命中即停，转人工或官方通道，不做适配对抗（yt-dlp 与平台对抗史的合规定性，见 14-crawler 深读单元 B8）。
- **合规是代码门不是文档提醒**：MediaCrawler 式「声明免责、机制不设防」是无效合规，本包不学；预检不过，执行层在发出第一个请求之前就拒绝。

## §2 坐标（C0–C6）

| 坐标 | 名称 | 内容与纪律 |
|---|---|---|
| C0 | 目标登记 | 每个数据源先登记再抓取：源名、base_url、URL 模式、所属项目、用途（purpose_kind）、消费方（consumer）、通道类型、条款依据指针。无登记的目标执行层拒绝访问（形态学 reverse-skill 的 scope 硬门） |
| C1 | 合规预检 | 对登记目标逐项产出预检记录：robots 结论（失败关闭口径）、条款依据、通道合法性、速率裁决、个人数据标记、登录态。ready_to_fetch 是代码计算值，不靠任何人声明 |
| C2 | 获取 | 按 C1 裁决执行（通道优先级在登记/预检层已定，见 §4）：节流按 §6 公式加自适应（只加严或回落裁决值）；断点与增量靠已见集与 frontier 任务（crawl：策略链播种 + 发现扩展 + job 落盘续跑），被拒即停 |
| C3 | 清洗 | 原始响应留存 + 清洗件双存；清洗规则按目标登记的 clean_profile 选档，不散装在代码里；近重复只标记不删除 |
| C4 | 落盘与 provenance | 每条产物带 provenance：源 URL、获取时间、通道、run 配置哈希、原始响应哈希、预检记录指针、留存档位；版本链以 supersedes 指针管理，旧版保留 |
| C5 | 增量更新 | 已见集（请求指纹）+ 条件请求（ETag/Last-Modified，304 不落新版）；节奏按登记 rhythm（manual/daily/weekly），变更只产新版本与事件，不自动改写下游已消费的数据 |
| C6 | 回供与回流 | 供数形态见 §9；失败与被拒（robots 禁、条款禁、HTTP 回绝、熔断、越域、量上限）一律落 events.jsonl 并可成清单查询，不许静默换姿势重试 |

## §3 硬约束（HC-1 至 HC-8，代码落点逐条对应）

1. **HC-1 无登记不抓取**：fetch 前 guard 逐项校验（登记存在、预检生效且未过期、未熔断、通道可执行），缺项逐项点名退出。**本包不设任何绕过旗标**——reverse-skill 的 case-guard 原则「force 不绕硬门」在本包的形态是干脆不给 force。
2. **HC-2 robots 与条款必检**：robots 按 §5 判据（失败关闭锚 RFC 9309 第 2.3.1.4 节 MUST 原文）；条款依据指针 terms_basis 未登记，预检落 incomplete 不生效。
3. **HC-3 官方通道优先**：通道优先级 官方 API > 开放数据 > 公开网页 > 浏览器自动化。登记已声明存在官方替代通道时，web_page/browser 预检直接 blocked 并点名官方通道。优先的理由是通道**可治理性**（身份、计额、条款在服务端齐备，pyalex 实读结论），登记官方通道时连同身份方式与计额方式一并登记，不许只写一个名目。
4. **HC-4 速率与总量成文**：速率只按 §6 公式，总量上限（单 run、单目标单日）入登记并由执行层硬停。
5. **HC-5 个人数据禁区**：personal_data_risk=high 登记即拒；low 须 scope_note 写明最小必要范围（只限已公开的学术元数据类）。禁区实证：案件集三类案由——非法获取计算机信息系统数据、破坏技术措施、侵犯公民个人信息（刑法第 285、286、253 条之一；案件集汇编止于 2021 年前，只作案由实证，条文以现行法为准）。速率失控本身独立成罪（快鸽案），与抓什么无关。
6. **HC-6 provenance 不可关**：provenance 是产物的一部分，不是可选日志；validate 重算原始哈希，缺失或不符逐项点名；缺 provenance 的产物下游有权拒收。
7. **HC-7 权限外不绕（构建方边界）**：见 §1；凭据通道内的会话访问按 §4 S2 现行口径执行；重定向跳出登记域名即停、响应不落盘并落事件。
8. **HC-8 被拒即停**：收到 401/403/429 即停本 run 并落事件（429 的 Retry-After 只记录供后续参考，不当场重试绕过）；同一目标连续 2 个 run 被拒即熔断，guard 拒绝一切 fetch，须具名 unblock 并给理由、留痕后才恢复。不许换 IP/换 UA/换姿势继续。

## §4 拍板口径落点（S1–S7）

| 拍板 | 落点 |
|---|---|
| S1 浏览器默认关 | 登记 channel=browser 时，预检须 browser_enabled=true 且 browser_reason 非空才继续裁决；且项目锁 allow_browser=false 时直接 blocked；浏览器属高危通道另须人工确认。**D1 预授权名单（2026-10-21 批准）**：具名者可把已登记目标列入项目锁 lock.browser_preauthorized（条目含 target_id / listed_by / reason / listed_at，增删各落一条事件），名单内目标以名单层理由替代逐目标开启手续、预检免逐个 confirm 直接 effective（豁免依据落预检记录 confirmation_waiver + browser_preauthorization_applied 事件）；名单外目标维持三段手续原样，allow_browser=false 对名单内同样 blocked（锁只紧不松）。这不是全局默认开：名单之外默认关不变。执行器随包提供（v1.1）：Chromium CDP 渲染器经 CLI fetch 与 crawl 注入；库层 fetch_run 仍走 browser_fetcher 注入契约，未注入时如实拒绝并留痕（不假装能跑） |
| S2 登录态（口径沿革） | v1 全关出自第二轮 S1–S7 整批批准；用户 2026-10-21 指出该条款其本人从未单独注意、现立场为可以绕。现行口径 = 凭据访问通道：login_state 可取 user_account / institutional，逐目标必填 entitlement_basis（权限依据）与 credential_ref（只许 vault: 引用、凭据本体永不落盘）、channel 须为 browser（会话由浏览器承载）；预检落 credentials 检查行（不验真实有效性）；执行须由接入运行环境注入 credential_provider，会话失效落 credential_session_invalid 并按 HC-8 熔断记账；provenance 只记权限依据、引用与脱敏账号标识。替代通道 import 保留（来源说明 + 经手人必填）。无权限绕越不建——此为构建方（Muse）边界，非用户口径 |
| S3 轻量留存 | v1 只做原始响应文件 + 哈希，provenance 明示 retention_tier=lightweight_raw_plus_hash；WARC 全记录档（WARC 为 ISO 28500 标准，非 W3C）登记即拒并指向 v1.1 |
| S4 预检分级 | 低危通道（official_api、open_data）预检全过自动生效；高危通道（web_page、browser）须具名 confirm 才生效，确认动作落预检账留痕；唯一豁免 = D1 预授权名单内的 browser 目标（名单层具名登记即确认依据，豁免逐条落账，见 S1 行） |
| S5 文献边界 | purpose_kind 词表只有批量与非文献五类；single_fulltext 登记即拒 |
| S6 速率公式 | 见 §6 定版表；并发固定 1，登记其他值即拒 |
| S7 产物公开性 | 随包发布的只有空白登记模板与脱敏范例（本地夹具演示），不预置任何真实抓取目标清单 |

## §5 robots 判据（锚 RFC 9309 节号）

| 情形 | 判据 | 出处 |
|---|---|---|
| robots 2xx 取到 | 逐行尽力解析、坏行跳过并记警告；UA 组不区分大小写，我们的组与通配组合并；路径最长匹配、allow/disallow 等长时 allow 优先 | 第 2.2、2.3.1.5 节 |
| robots 4xx | 视为不可用，即无 robots 限制，可以访问 | 第 2.3.1.3 节（MAY） |
| robots 5xx 或网络不可达 | 视为未定义，**必须假定全面禁止**（失败关闭），预检 blocked、fetch 期复核同样整 run 停 | 第 2.3.1.4 节（MUST） |
| 重定向 | 至少跟随 5 次（传输层默认行为满足下限） | 第 2.3.1.2 节 |
| 缓存 | robots 结论缓存不超过 24 小时：预检记录以 robots 取回时刻 +24h 为 expires_at，过期即失效、须重跑预检。**D8 复用（2026-10-21 批准）**：预检把 robots 原文按哈希落 prechecks/robots-cache/，fetch/crawl/discover 执行期经 robots.resolve_robots 先查缓存——24h 内且重算哈希与预检记录 body_sha256 相符即复用（零额外 robots 请求，落 robots_cache_reused 事件）；哈希不符或本体缺失即作废回落实时取（落 robots_cache_invalidated 事件点名原因）；4xx 结论无原文，凭记录状态直接复用 | 第 2.4 节口径 |
| 解析体积 | 至少解析 500 KiB | 第 2.5 节 |

注意两条不可混引：其一，robots 规则不是访问授权体系（RFC 第 1 节），遵守 robots 不等于获得抓取授权，授权回到条款与法律；其二，crawl-delay 与 request-rate **不在 RFC 9309 内**，是 Protego/Google 谱系的常见扩展——本包只把 crawl-delay 作为站点公示意愿的事实参与速率取严，依据写条款与本包自律，绝不冒充标准要求。另：Disallow 路径本身公开可发现，预检记录（含目标清单）是项目内部文件，不对外发布（RFC 第 3 节安全考虑的同构提醒）。

## §6 速率定版（S6，只拍公式 + 模板数值）

**公式**：有效间隔 = max（登记值 registered_interval_sec，robots crawl-delay（若公示），模板下限，项目锁下限，包级硬下限）；请求现场再与 Retry-After 取最严（等到可发才发，不并行抢跑）。并发固定 1。

| 通道 | 模板下限（秒/请求） |
|---|---|
| official_api | 1 |
| open_data | 2 |
| web_page | 5 |
| browser | 10 |

包级硬下限 0.5 秒：任何登记与依据都不许更快。登记值低于模板下限须填 rate_basis（许可该速率的条款依据指针，如官方 API 条款明示的速率上限），无依据的放松被模板下限挡住（构建判断 J2，见 phase5-crawler.md）。总量上限默认：单 run 200 请求、单目标单日 1000 请求，登记可调小，调高同样须 rate_basis（校验在登记层，执行层硬停并落 volume_cap_hit 事件）。

**rate_basis 用法示例（D6，2026-10-21 批准落字；流程说明、非口径变更）**：模板下限是缺省档，不是天花板——确有条款依据时，在登记层一次写清即可，不必另设机制。例一：某官方 API 条款明示「每 API key 每秒至多 2 次请求」，登记写 registered_interval_sec: 0.5 并在 rate_basis 填该条款的指针（文档 URL 或条款编号），预检按公式取严后即以 0.5 秒生效；例二：自有站点或已签授权的合作站点，rate_basis 填授权文件指针，web_page 的 5 秒模板下限同样可据此下调；例三：总量上限要从默认 200/1000 上调，同样在 rate_basis 写明依据（如官方配额页）。反面：拿不出指针的「应该没问题」不构成 rate_basis，登记层直接拒收回到模板下限；rate_basis 只认条款/授权文本，不认口头判断。

## §7 预检三件与项目锁

1. **目标级检查**：登记自洽、通道合法性（含官方替代点名、浏览器开启与理由）、个人数据与项目锁上限、条款依据、robots 逐 URL 结论、速率裁决分解——每一项的结论与依据都落进预检记录（prechecks/<target_id>.jsonl，只增不改），不是只落一个总分。
2. **项目锁**：(a) 合规档位锁——登记头 lock 段（min_interval_sec、allow_browser、max_personal_data_risk、browser_preauthorized 预授权名单），单目标预检只能比锁更严，放松尝试被锁值覆盖并落 lock_applied 事件（形态学 firecrawl 的组织级 Safe Mode：档位可锁定、单次请求参数不得降档）；预授权名单是锁内唯一的「放行登记」：它不放松任何档位数值，只把 browser 目标的逐个确认改为名单层一次具名登记，增删与命中全部落事件（见 §4 S1 行）；(b) 目标运行锁——同一目标同时只许一个在飞 run，残锁只点名不自动夺锁，人工核对删锁的动作应另行留痕于项目记录。
3. **拒绝留痕**：预检 blocked、guard 拒绝、HTTP 被拒、熔断、越域重定向、量上限全部落 events.jsonl，refusals 命令成清单（含原因与规则出处）——学 firecrawl 的 robotsBlocked 清单形态：被拒要可见、可查，不是日志里的一行字。

预检状态机：blocked（硬不通过，解决点名项后重跑）/ incomplete（缺项，补齐后重跑）/ pending_confirmation（高危待具名确认）/ effective（生效）/ expired（超 24h 自动失效）。guard 只认 effective。

## §8 落盘形态与 provenance 字段

工作区（项目根 data-sources/）布局：crawler.yaml 登记头（顶层 status 由代码维护：任一目标熔断即 attention）、targets/<id>/（target.yaml 登记 + state.yaml 运行状态）、prechecks/<id>.jsonl、events.jsonl、seen.jsonl、provenance.jsonl、store/（原始响应内容寻址，同一哈希只存一份）、runs/<run_id>/（run.yaml + cleaned/ 清洗件）、locks/。

每条 fetch 类 provenance 必含字段：prov_id、at、kind、target_id、run_id、url、final_url、channel、http_status、bytes、sha256、raw_path、cleaned_path、precheck_ref、run_config_hash、retention_tier、etag、last_modified、fingerprint、supersedes。人工导入行 kind=manual_import，另含 source_file_name、source_note、imported_by，且 channel 落 manual_import 与抓取产物分开读。run 配置哈希由登记 + 速率裁决合成，同一目标的登记或裁决一变，哈希即变，产物可回溯到当时的确切配置。

## §9 回供接口

- **给 light-literature**：文献线索批（题录/DOI/链接，经官方 API 通道）与全文获取批（整刊 OA 批量等；OA 副本定位优先于抓出版商页面），产物带 provenance 与通道标记，直接对接四件套的来源登记。literature 的 Find 线已有源（Crossref/Europe PMC 等）本包不重复造，只做其未覆盖的源。
- **给 light-experiment**：数据集获取批（数据文件 + 版本 + 校验哈希 + 来源登记，对接执行包 data 入口与 identity_hash 的数据版本维）；基准/排行榜页面走 page_snapshot 目标 + rhythm 增量，变更以新版本 + 事件回流，不自动改写 experiment 已消费的数据。
- **给 light-patent 的预检门接口（只登记形态，本包定版）**：patent 的 CNIPA 公布站自动化默认关；开启路径唯一：在本包登记该目标并过预检，然后经 gate-check 接口查询——`gate_check(root, target_id)`（CLI：gate-check --target <id> --json）返回 ready、status、reasons（逐项点名）、channel、effective_interval_sec、precheck_id。ready 为假即不许开抓；消费方只读本接口，不绕开它自判。
- **给 light-memory（承接形态，集成步落适配器）**：抓取批次、预检记录、变更事件为一等事件源，按 provenance 字段在阶段定版点收编；数据版本链的 supersede 关系由 memory 的取代链接管，本包只产版本与指针。
- **给 light-leader（LD-02 纳管，集成步落）**：登记头顶层 status 进 status 只读汇总；route 只点名预检未过与熔断状态，不代跑本包命令。

## §10 命令面

init / register（--file，--update）/ targets / precheck / confirm（--by 具名 + --note）/ gate-check（--json）/ fetch（--target，--url 可重复，--refetch-seen 只影响增量跳过、不绕任何合规门）/ discover（--target：发现 pass，端点/链接/sitemap 登记进发现账）/ crawl（--target，--max-pages，--no-discover，--fresh：frontier 任务，断点自动续跑）/ sources（--target：发现账清单）/ import（--note 与 --by 必填）/ unblock（--by + --reason）/ browser-preauth（list / add --target --by --reason / remove --target --by --reason：D1 预授权名单维护，增删均具名留痕）/ refusals（--type 可按拒绝类过滤并给出该类计数，如 render_escalation_blocked）/ events / status / validate / render。全部命令从工作区根以 --root 指定 data-sources/ 运行。fetch 的错误输出即点名清单：缺什么、被哪条规则挡、合法替代是什么，一次说清（学 rea 工具契约「错误消息指回合法操作面」的写法）。

## §11 失败模式（接入模型自查）

| 失败 | 处置 |
|---|---|
| 目标未登记就想抓 | 先登记（C0），不许先抓后补登记 |
| 预检 blocked 却想换个姿势绕 | blocked 原因逐项解决或换官方通道；换 UA/IP/姿势继续属 HC-8 明禁 |
| 条款读不到或读不懂 | terms_basis 落「无据」并按最保守档（公开网页、低频、只取事实性数据）登记，预检记录里明示无据状态，不许假装已核 |
| 目标站 5xx 或连不上 | robots 与目标同口径失败关闭：停、落事件、等恢复后重跑预检，不许趁「站方异常」放行 |
| 被 403/429 后想立刻重试 | 即停本 run；连续两 run 被拒自动熔断，恢复走具名 unblock |
| 数据在登录墙后 | 三个合法出口之外无路：官方 API、机构授权、人工导出后 import |
| 下游嫌 provenance 麻烦想关 | HC-6 不可关；缺 provenance 的产物下游有权拒收，问题在本包一侧 |

## §12 已知局限（v1.1）

1. 浏览器执行器已随包（CDP 主通道），但环境依赖真实存在：本机无 Chromium 时如实拒绝并指路；回环/内网目标在 Chrome 152 的 Local Network Access 检查下走传输桥接渲染（engine 标注 cdp+fetch-bridge，渲染的是目标站真实响应字节）；dump-dom 降级在个别 Chromium 构建上无输出（实测本机 build 对 about:blank 亦无输出），此时以 RenderError 如实呈现、不冒充渲染成功。
2. 清洗层内置 html_text_v1 一档（标题/meta/可见文本 + JSON 透传），trafilatura 谱系的深度抽取未接适配器；clean_profile 接口形态已留。
3. WARC 全记录档（ISO 28500）未做（S3 定版）；高价值易变源的现场级留存在当前只有原始字节 + 哈希。
4. 增量靠已见集 + 条件请求 + crawl 任务续跑，rhythm 字段只登记节奏口径，定时调度不在本包（由项目侧调度或 leader 编排）。
5. crawl 任务内失败条目（5xx/传输错误）不自动重试：状态落 failed 并留痕，续跑只处理 pending；恢复靠 fresh 新任务或人工处置——防重试风暴与速率失控，是有意口径不是缺失。
6. 凭据通道的 CLI 形态不持有凭据：credential_provider 只能由接入运行环境（Secure Vault）注入，CLI 直跑凭据目标会如实拒绝并点名注入路径；预检不验证凭据真实有效性，有效性由执行期会话成败与熔断记账兜底。
7. 条款阅读是模型工作：预检只校验 terms_basis 指针在册与确认留痕，不自动判定条款语义；条款结论的对错由登记与确认的具名者负责。

## §13 交付收尾格式（全套通用，v1.1 X-10）

全套任何交付报告（各包 demo-report、封版记录、阶段交付说明与一切对用户的交付汇报）结尾必须带以下四行，逐行落字，不许合并、不许省略；没有内容的行写「无」并说明原因，不许整行消失：

- **完成项**：本次实际做完并已验证的事项，逐项带证据指针（文件、测试结果、清单条目）。
- **跳过项**：本次明确没有做的事项及原因（范围外、依赖未到、用户裁决缓行等），逐项点名，不许静默略过。
- **未验项**：做了但没有验证到位的事项（缺环境、缺原文、只达登记级等），逐项点名并注明验证缺口，不许与完成项混写。
- **风险**：用户须知的残余风险与后续触发条件（什么情况下需要回头处理、由谁裁决）。

口径：四行是全套交付的最低披露线。把跳过项写进完成项、把未验项写成已验证，均按造假论。

## §14 能力强化批（v1.1，2026-10-21）

用户点名「目前爬虫太弱、遇到点啥就撞」后施工。验收口径 = 本地夹具站点集逐场景强化前后对照（tests/fixture_sites.py + tests/test_strengthen.py，22 项），全量 77 项全绿（55 基线零变红）。

- **传输 v2**（transport.py）：重定向逐跳手动跟随（链进 provenance、成环/超限显式报错，不再把 3xx 空 body 当内容）；gzip/deflate 解压（含误标魔数兜底）；charset 判定链解码（响应头 -> meta -> utf-8 -> gb18030 兜底，GBK 站不再花屏）；大文件流式断点续传（.part + sidecar，Range 续传、服务器不支持时整件重下并如实记录，登记 large_files=true 启用）；慢站超时按 TransportError 分类点名（timeout/network/http_stream）。
- **浏览器渲染通道**（browser.py）：随包 Chromium 执行器正式入列——CDP 导航 + 网络事件采集（真实状态码、资源清单、重定向链）+ 滚动收割（无限滚动逐屏滚至 DOM 稳定）；以本包声明 UA 覆盖默认串（身份一致、不伪装真人）；渲染命中人机校验强标记返回 blocked 并按回绝熔断留痕（render_blocked），不代解验证码；回环/内网目标走传输桥接模式（见 §12.1）。
- **前端接口发现**（discover.py）：链接/分页（rel=next）抽取、内嵌数据岛（__NEXT_DATA__/__NUXT__/JSON-LD）抽取、同源脚本端点挖掘（fetch/axios/XHR/url 字段五形态，含模板占位单列）、sitemap 解析（urlset/sitemapindex 两形态）；发现结果登记进 targets/<id>/discovered.jsonl 发现账（去重、只增），sources 命令可查。
- **frontier 任务与回退链**（crawl.py）：job 落盘（targets/<id>/job.json，原子写、逐条目检查点），中断自动续跑（inflight 回滚、done/skipped 不重抓、已见集增量）；策略链逐级留痕：登记 api_endpoints（strategy_selected: api）-> sitemap -> 静态抓取 + 发现扩展 -> 逐页渲染升级；渲染升级须登记 allow_render_escalation=true 且预检确认，未授权落 render_escalation_blocked 并存壳标注（js_shell 信号在清洗件与事件双落）。
- **自适应限速**（throttle.py）：在预检裁决间隔之上自适应——5xx/网络错误乘性加严（上限 300s），连续成功 3 次逐步回落，永不低于裁决值；每次调整落 adaptive_backoff 事件。Retry-After 口径与 §6 公式不变。
- **凭据访问通道**：见 §4 S2 现行口径。会话由浏览器通道承载（cookie 经 CDP 在导航前注入），provenance 记 entitlement（basis / credential_ref / 脱敏 account_label）与 cookie 名，凭据值全程不落盘（测试以全工作区扫描断言）。
- **未动的默认**：浏览器默认关（S1）、通道优先级（HC-3）、并发 1、429 即停不重试、模板间隔下限、robots 失败关闭——均照旧；认为它们限制能力的条目连同风险与建议写入工作区 20-build/crawler-decision-list.md 交用户拍板，本批未自行放开任何一条。
- **决策落地批（同日续批，用户全按推荐批准）**：D1 浏览器预授权名单落码（project 名单管理 + precheck 豁免合成 + CLI browser-preauth，名单外三段手续原样）；D8 robots 缓存对齐落码（预检落原文哈希缓存、执行期 resolve_robots 统一复用，清偿 phase5 遗留问题 (1)）；D3 维持逐目标确认，render_escalation_blocked 计数以 refusals --type 钉死可查；D6 维持公式与下限，rate_basis 用法示例已写入 §6。其余 D2/D4/D5/D7/D9/D10 按批准维持现状，无代码变更。验收 = tests/test_decisions_impl.py 11 项，全量 88 项全绿。
