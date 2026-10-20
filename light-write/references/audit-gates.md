# 分册：引用核查口径与审计四门细则

> light-write SKILL 分册（WRT-D06 分册化）。来源 = v1.0 SKILL §8/§11 verbatim 下沉；主文件只留四门规程卡，细则以本册为准。

## §8 引用核查口径（两段核对门的命名与容差，两门消费见 §11）

- 两套幻觉口径分名，不得混用阈值（纠错 11(a)）：
  - `field_level_hallucination_screen`（Chelli）：题名/第一作者/年份任二错 → 字段级筛阳性；
  - `identity_level_fabrication`（refchecker LIKELY）：作品不存在或作者名单实质不符（不含年份/venue 漂移），落字须第二路阴性证据（约束 1）。
- 容差与定级表在 `schema.FIELD_TOLERANCES`：年份 ±1 只 warning、venue 变体 warning、DOI 可解析降级/不可解析才 error、题名容差以身份已确认为前提——零容差执行会与 no-false-positive（约束 14）冲突。
- 语境核对（约束 4）处置词表 KEEP/FIX/REPLACE/REMOVE（REPLACE/REMOVE 永须人类批准）；与三元组蕴含三值（entailment/neutral/contradiction + abstain）是不同粒度，不可混用（纠错 11(d)）。


## §11 审计四门规程（W3/W6，audited 段）

`audit` 逐门出报告（`audit/gate-*.md` + `audit_report.json` + `AUDIT_SUMMARY.md`），产物绑稿件哈希；**稿改即 STALE**，validate 与段门都检出，须重跑。审计只出判定，阻断权在 gates（审计与把门分离）。

1. **门一 引用两段核对**：范围 = 正文实际被引条目。第一段身份核：在线权威记录（经 `--online-records` 注入，形态为 {entry_id: 权威记录}）查无此条 → 只有第一路+第二路**双阴性证据**齐备才许落 `identity_level_fabrication`，缺第二路落未决拦门（不许单路定罪）。第二段字段核：执行 `schema.FIELD_TOLERANCES` 容差层——年份 ±1 只 warning、venue 变体只 warning、DOI 不一致时能解析降 warning/不能解析才 error、题名容差以身份已确认前提；题名/一作/年份任二错 → `field_level_hallucination_screen` 阳性整门 fail（两口径分名，不混用阈值）。**离线或记录未覆盖全部被引条目 → 整门 honest-unverified，不许 PASS、不许声称查过**。相关性轴：判定以蕴含四值（entailment/neutral/contradiction/abstain）登记，存疑只进 `relevance_pending` 待人工/复核，**不自动定罪**；已登记处置中 REPLACE/REMOVE 无人类批准拦门、FIX 无落字说明拦门。
2. **门二 数字对账**：正文每个 `[num:]` 呈现串三方逐串比对——呈现串 ↔ 账内 value_as_printed ↔ 溯源表数值按呈现小数位半上舍入。正文出现任何未登记数字串（披露生成块、列表序号除外）逐个点名 fail。溯源表不可得或承接哈希漂移 → 门 fail 并写明未核查（honest-unverified 的数字版）。
3. **门三 强度措辞门**：逐 `[claim:]` 锚点取其句子，按**稿件语言**词表比对该主张 wording_ceiling：全档禁用词出现 → 拒；术语的最低可用档高于主张强度档 → 拒；两种都给出降格建议（本档 allowed_terms）。主张 text_hash 漂移 → 先执行重验贴合度规程并 `reverify-claim` 落字，未重验不许过门（哈希只证明文本未变，贴合度靠人/规程重验）。
4. **门四 落点映射复核**：submission_checklist 全条目机械复核——status 合法、落点存在（section 落点：节文件在场且锚点字符串实位存在；declarations 落点：对应声明三态非 absent；file 落点：文件存在）。报告规范条目**只复核落点**，不做声明式自查（本地检查过 ≠ 声称遵循规范）。
5. 四门全 pass 才许 advance 到 audited；任一门 fail/unverified → 停在 drafted，逐项点名。

