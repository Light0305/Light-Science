# 分册：补课 D 采纳规程与约束对应表

> light-write SKILL 分册（WRT-D06 分册化）。来源 = v1.0 SKILL §18/§19 verbatim 下沉；主文件路由表指此。补课条文的处置全文另见 `06-write/SUPPLEMENT-D-DISPOSITION.md`。

## §18 补课 D 采纳规程（nature-skills 生态簇，deep-read-D-supplement）

补课 18 条（D-W01–D-W18）逐条处置见 `06-write/SUPPLEMENT-D-DISPOSITION.md`；本节只落已采纳的
规程与机制，未采纳项（D-W17 组织形态重构留 v1.1 评估；D-W18 五项：
Zotero 同步、CNS 白名单过滤、逐页生图翻译、行为宪法式写法、词表式去
AI 味）不进本 skill，理由在报告中逐条交代。

### 18.1 正文分配纪律（D-W01，`body_allocation.yaml` + `allocation` 命令）

现有约束管「能不能写、写多强」；本纪律管「写在哪、占多少、重复几处」：
结果先按功能八分类（core_discovery / necessary_support / qualification /
robustness / heterogeneity / provenance_detail / alternative_inference /
edge_case）再定目的地（正文/图注/Methods/SI），建最短充分证据链；每处
主张出现入位置图（introduce/demonstrate/interpret/synthesize/shorten/
delete）；结论改变型证据不许埋 SI（校验硬拦）；每次增补触发全段删除
检查（删除日志 + 字数增量留档）；返修时回复信答全、正文改动取最短
（与 W7 对齐）。`enforced=true` 时位置图未覆盖的出现处拦 audited→ready。

### 18.2 术语账（D-W02，`terminology.yaml` + `terms` 命令）

起草前建账（canonical / 首现全称 / 已见变体 / 裁决），W0 承接时从上游
材料首建；锁定后全稿强制：变体入正文 = 校验 error（只报不改）；改名 =
全稿替换 + 账本更新；不许自创术语，缺定义标旗问作者。

### 18.3 一致性清扫（D-W03，数字门子项）

数字门附带机械清扫：同量异精度、同量异单位、SD/Std 变体只报警告、
逐条读语境裁决，永不自动改（与约束 14 相容）。

### 18.4 AI 使用风险分级（D-W04，use_log.risk_tier）

逐条留痕加分级：assistive（留痕即可）；evaluative_interpretive（解释
结果/回复框架/统计解释——须 human_verified 强核验落字 + 按刊披露）；
prohibited（代写核心论证、未核查引用/数据入稿、未发表稿与评审材料上传
公共模型、AI 图像造假——流程直接禁，披露不能洗，校验硬拦）。

### 18.5 引用门补强（D-W05/D-W06/D-W07/D-W12）

- 容差矩阵校准：DOI 可解析性是最便宜的第一步；页码差 ≤4 warning /
  ≥5 Critical；文章号形近误判（T/7、l/1、O/0）Critical；Early Access
  漂移以权威现值为准记 warning；作者漏人 Critical（经作者人数核）。
- 核查状态四级：verified / check_suggested / needs_fix / unverifiable，
  逐条落审计报告；**Unverifiable 是合法终态**（内部报告、老旧学位论文
  查不到 ≠ 编造），与「判编造须第二路阴性证据」互证。
- 作者完整性门：lock 作者名单必须取结构化源完整有序名单，禁从 et al.
  显示串推导；authors_complete=false 停生成，紧急覆盖须 author_override
  落字并把警告写进记录。
- 支撑五级量表 + 双角色对抗协议：引用语境核查的组织方式——proposer
  给源 + **逐字支撑句**，skeptic 在新上下文默认拒绝、无逐字句不确认、
  不确定向拒绝侧裁决；判定分五级（strong / partial / background /
  contradictory-limiting / metadata-only，metadata-only 不许作支撑），
  与处置词表 KEEP/FIX/REPLACE/REMOVE 分层并用；失败原因用五类分类学
  （does_not_support_claim / metadata_wrong / wrong_site_or_population /
  not_primary_but_required / paywalled_unverifiable）。判定落
  `audit/support_assessments.yaml`（或 audit --support 注入），机械面由
  引用门校验。校准注脚：实测一篇 Review 中 139 个提议源被独立 skeptic
  拒 55、零编造——存在性核查会全数放行这 139 条，故语境核查不可省。

### 18.6 声明与清单补强（D-W08/D-W09/D-W14）

- 数据可用性：先盘点再起草——每数据集分类七路访问路径之一，声明按
  dataset→location 显式映射写（manuscript.datasets）；"available upon
  request" 无具体限制落字 = 弱声明待改（校验警告）。
- 清单条目带 stage（initial/revision/production，规则不许跨阶段套用）
  与 applicability 四态；status 输出 readiness 三态（ready /
  ready_with_author_checks / blocked）。
- 统计报告底稿：`checklist add-stats` 加入两条底线条目（独立单元 n
  定义与分层、主张→分析映射字段集）；缺项一律 AUTHOR_INPUT_NEEDED，
  不许编造样本量/检验/校正（与 Analysis 的 n 纪律同构互证）。

### 18.7 编辑组织（D-W10/D-W11/D-W13/D-W15/D-W16）

- 分层编辑顺序：结构 → 章节 prose → 段落逻辑 → **姿态** → 句子，只修
  有问题的层；姿态层查五种声音（audit / defensive / self-critical /
  developer / commitment，覆盖正文、SI、图注与声明）。两条停机规则：
  主张层级未稳不做姿态编辑；Review 稿先 drift audit 后润色。去 AI 味
  只采 information test（删无信息内容），不采词表替换（D-W18⑤）。
- 承重陈述保护（manuscript.protected_statements）：重复单元与 n、无 P
  值声明、盲法与排除、访问路径、决策背后的计数、估计量假设、阴性
  结果、Methods scope 条件、目标刊必查声明——登记后只许移位、只述
  一次、改写为正向 scope；校验逐条核对实存，删/移即报错。
- 草稿标记纪律：[todo-fact:] 只许事实/来源问题（开放计数 = 证据就绪
  度，status 输出）、[note-edit:] 编辑意见、[directive:] 必改指令
  （未结拦 drafted 门)、[superseded:] 冻结替换留痕；未注册标记 = 纯度
  违规；开放项按解决路径分诊；字数口径排除草稿装置。
- 经验值证据规则（D-W15）：逐节规程里任何数值型经验区间（摘要句数、
  引言段数、数字密度等）须附语料证据文件与采样框（库/年份/期刊/
  检索式/纳入排除 + 脚本复跑），不许凭印象写数；证据带「描述 ≠ 因果」
  边界。
- 蒸馏路线（D-W16）：范文/句式证据层采用「固定抽取 schema + verbatim
  ≤25 词 + grep 可回查 + 语料附录逐篇登记」的生产方法（转交模板库
  姊妹仓执行）；规律分三档（常见模式/子门类倾向/强约定）标注置信；
  **句级模板与 language bank 只许诊断对照、不许进生成侧**（与约束 6
  Sadallah 实证一致）；SyntaxSmith 的提交前 checklist 与 5-pass 自审
  只作成稿前事后诊断参照。

---

## §19 附录：LEARNING 16 条硬约束对应表

每条约束在 v1.0 的落点（规程节 → 工具实现）。补课 D 18 条（D-W01–D-W18）的处置摘要：采纳 16 条（D-W01–D-W16）落 §18（规程 + 工具），D-W17 组织形态重构未采纳（留 v1.1 评估），D-W18 五项（Zotero 同步 / CNS 白名单过滤 / 逐页生图翻译 / 行为宪法式写法 / 词表式去 AI 味）已评估不采——**逐条全文见 §18 与 `06-write/SUPPLEMENT-D-DISPOSITION.md`**。

| # | 约束（一行） | 规程落点 | 工具实现 |
|---|---|---|---|
| 1 | 引用核对两段式：存在性判定 + 逐字段核对 | §8、§11 门一 | `audit._check_one_entry`：双路阴性才落 fabrication、单路落 unresolved；字段容差层逐项定级 |
| 2 | 标识符默认不可信，只许权威源反查回填 | §2.3、§7 | lock 只收 Literature verified 集；validate 裸 DOI/疑似手写引用检出；标识符不许手填进正文 |
| 3 | 起草期占位符隔离，参考文献表只许回填生成 | §2.6、§7 | validate 占位符外引用报错；`references.bib` 由 lock 渲染 + 条目集哈希，未手改校验 |
| 4 | 相关性是独立于真实性的第二道核查 | §8、§11 门一、§18.5 | 支撑五级量表 + 双角色对抗（support_assessments）；相关性轴缺失只落 relevance_pending 不定罪 |
| 5 | 正文数字只许来自溯源表；改数字串触发复核 | §7、§10.3、§11 门二 | numbers_ledger 逐行 trace_ref 必填；门二三方逐串比对 + 裸数字扫描 |
| 6 | 逐节规程只写功能目标 + 必备信息元 + 禁令 | §4.2、§10.1 | 节登记 schema（goal/required_info/claim_ids）；规程卡四问，无模板句字段 |
| 7 | 报告规范条目前置拆入逐节规程 | §4.5 | 提纲期条目拆入 required_info；门四只复核落点 |
| 8 | 投稿前检查 = 条目 → 稿件位置映射，逐条实位判定 | §11 门四 | checklist location 三形态（section 锚点逐字 / declarations 三态 / file 在场）机械复核 |
| 9 | 披露按目标刊记录逐刊生成，规程不写死政策 | §6.3、§12 | disclose 以模板记录 G 组 × use_log 生成；期刊层优先、冲突留 resolution_note |
| 10 | 合规靠留痕 + 披露，不靠检测分数 | §7、§12.5 | use_log 逐条留痕（model_version 缺失即拒）；全包无检测器分数字段 |
| 11 | 主张-证据行内标记 + 文本哈希绑定，改词即漂移 | §7、§11 门三 | [claim:]/[num:] 行内标记；text_hash 漂移未 reverify 拦门三与 validate |
| 12 | 措辞强度永远 ≤ 上游强度档 | §3、§10.4、§11 门三 | writable_form 规则表 + wording_ceiling 双语词表；门三逐句比对 + 降格建议 |
| 13 | 审计与把门分离；审计产物必达且绑哈希 | §11、§13 | audit 只出判定、gates 持阻断权；产物绑 manuscript_hash，稿改即 STALE；阴性/未核查落字不 silent-skip |
| 14 | 检查者三纪律：honest-unverified / no-false-positive / no-overreach | §8、§11 | 离线整门 unverified 不许 PASS；容差层防零容差误杀；门只报判定不改稿 |
| 15 | fail-on-errors 写死为开，无可关口子 | §7 | validate/audit/各 check 命令 error 即 exit 1；绿灯语义在 §7 明示证明边界 |
| 16 | 核对强度与模型版本/自评脱钩 | §11、§13 | 核对走确定性代码与注入记录；放行只认状态机门 + 异家族复核收据，自评永不作依据 |
