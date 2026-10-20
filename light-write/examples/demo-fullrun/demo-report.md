# demo-report：light-write v1 端到端演示报告

> 身份：合成链演示。上游结论卡 = light-analysis 合成演示包的 `conclusion_card.json`
> （status=blocked、review=REVIEW_UNAVAILABLE、唯一主张 C1=untested/insufficient）。
> 本稿为合成演示稿；模板记录为演示 fixture；在线记录为构建时真实调用 Crossref 现拉。
> 全程命令与原始输出见 `evidence/run-log.txt`。

## 1. 逐段状态

| 段 | 动作 | 结果 |
|---|---|---|
| 承接 | `init` + `intake`（结论卡 + Literature 候选池） | C1 登记为 `limitations_only`；参考文献 lock 回填 4 条 verified；上游两条旗标原样落字（`analysis_not_delivered`、`analysis_review_status: REVIEW_UNAVAILABLE`）；缺口如实登记：C1 上游无规范文本，text_hash 留空待补 |
| 模板 | `register-template`（演示 fixture 记录 TPL-DEMO-FIXTURE-001） | 登记成功、零警告；栏目序列/披露口径（G 组）成为后续 drafted 门与 disclose 的依据 |
| 合同 | 12 条可核查验收断言（agreed）+ `freeze-contract` | 冻结哈希 `c3ba413a…`，contested=false |
| 大纲 | `advance` → outlined | validate 0 错误（唯一 warning：C1 text_pending，如实保留）；模板/合同/登记三门全过 |
| 起草 | 逐节稿 + 术语账 + 数字账 + 清单 + 图表 + 分配账 | 见 §4 三账本触发记录；`advance` → drafted，lock 收窄清单落字：被引 ST001/ST002/ST005、未引 ST003（只列不删） |
| 披露 | `disclose`（drafted 后、审计前，规程 §10.6） | 按记录 G 组模板逐刊生成，落 declarations 节；disclose-status：complete、非 stale；use_log 两条（assistive + evaluative_interpretive，后者带 human_verified 落字） |
| 审计 | 五次审计（见 §2） | 终审 overall=pass、四门全过、审计与稿件哈希对齐（`447ab38f…`） |
| 图件 | `figures freeze`（派号 F001）+ check | 冻结后 check ok；注意冻结动作本身使先前审计 STALE（见 §3 第 2 条） |
| 推进 | `advance` → audited | 成功 |
| 复核 | `review prepare` + `review unavailable` | REVIEW_UNAVAILABLE 落字（本环境单一模型家族 claude，无异家族复核者；与上游结论卡同因） |
| 终点 | `advance` → submission_ready | **被拦**：gaps 明示 REVIEW_UNAVAILABLE；`submission_blocked_reason` 落字；稿件停在 **audited**（演示终点，与任务书一致） |

## 2. 审计四门结果（逐门一行）

审计共跑 5 次：#1 离线、#2 离线（STALE 复审）、#3 离线（支撑账本缺陷注入）、
#4 在线注入、#5 在线注入（图件冻结后终审）。终审（#5）结果：

| 门 | 终审结果 | 说明 |
|---|---|---|
| 门一 引用两段核对 | **pass** | 在线注入 Crossref 现拉记录覆盖全部 3 条被引条目：ST001/ST002 `verified`；ST005 `check_suggested`（venue 变体：lock 作 "arXiv"、权威记录为 "IEEE Access"，门一只警告不判错——该 lock 条目源自候选池登记口径，如实保留）；撤稿态三条均 clean（Crossref updates 查询 total-results=0，原始响应存 evidence）；相关性轴三条 `relevance_pending` 警告（待人工/复核，不自动定罪）；支撑判定三条落账（见 §4） |
| 门二 数字对账 | **pass** | 3 个 [num:] 全部对账（呈现值 ↔ 数字账 ↔ 结论卡溯源，逐串舍入一致，见 §5）；正文无裸数字 |
| 门三 强度措辞门 | **pass** | C1 锚定句 1 句受检：insufficient 天花板下仅用 allowed 表述 "was observed"，无越档/禁用词 |
| 门四 落点映射复核 | **pass** | 清单 5 条全 addressed 且落点实位复核通过（含 add-stats 注入的 2 条统计底线条目，见 §6 第 2 条） |

**离线 honest-unverified 的如实呈现（#1）**：未注入在线记录时门一整门落
`unverified`、三条被引条目逐条落 `identity: honest-unverified` /
`verification_status: unverifiable`，附言"本条未做在线核查（honest-unverified，
不许声称查过）"；overall 因此为 fail——离线状态下审计**不能**给出全过结论，
这是设计而非缺陷（产物存 `evidence/audit-01-offline/`）。

## 3. STALE 演示（两条，均真实发生）

1. **改一字**：讨论节 "single-site" 改为 "single-barn"（一词）后，
   `audit-status` 立即报 `stale: true`（审计哈希 `467eb9db…` ≠ 当前 `62270e26…`）；
   复审（#2）后 stale=false、新哈希绑定。
2. **冻结动作**：图件编号冻结改动了图表清单的 `numbering_freeze` 字段（在稿件哈希
   覆盖范围内），使 #4 的全过审计在推进 audited 时被判 STALE 并拦下；
   按"冻结在前、终审在后"的顺序重跑 #5 后过门。教训已回写 SKILL §12：
   图件冻结须排在终审审计之前。

## 4. 补课三账本的实际触发记录

| 账本 | 触发 | 处置 |
|---|---|---|
| 术语账（terminology.yaml，locked） | 方法节初稿用变体 "prediction arm" → `terms` 报 error `terms.variant_in_text`（exit 1） | 改回 canonical "predicted-threshold arm" 后复查 ok；账本只报不改，改名走全稿替换 |
| 正文分配纪律（body_allocation.yaml，enforced） | 位置图为空时 `allocation` 报 error `allocation.unmapped_occurrence`：C1 @ S-discussion 未入图 | 补位置图（C1 → S-discussion，role=interpret）+ 结果功能行（qualification → main_text）+ 删除日志一条后复查 ok |
| 支撑判定（audit/support_assessments.yaml） | 初版给 ST005 判 partial 但无逐字支撑句 → 审计 #3 门一 error `cite.support_no_quote` | 按双角色对抗协议修正：ST005 改判 background 并附 Crossref 摘要逐字句（skeptic 拒绝 proposer 初提的 partial）；ST002 partial 附逐字句确认；ST001 background。终审三条判定落账（background / partial / background） |

## 5. C1 的 limitations_only 落法与数字对账

**C1 落法**：C1 全稿只出现一处——讨论节局限段，逐字如下（措辞经门三核验在
insufficient 天花板内）：

> "The comparison at the centre of this study is reported descriptively: across the
> held-out segments, a difference between the predicted-threshold arm and the
> fixed-threshold arm **was observed** [claim:C1]."

摘要不锚 C1、不用其数字；结果节只报数字不解释主张；返修副本中 RC001 进一步要求
在主张句旁明示"分析行未获检验、未出判定"，已落实。

**数字对账实况**（门二逐串比对）：

| 标记 | 正文呈现 | 数字账 | 溯源（结论卡 number_provenance） | 舍入 |
|---|---|---|---|---|
| N001 | 5.25 | 5.25 | R-ORA effect_size 5.249333… | 2 位小数半上 → 5.25 ✓ |
| N002 | 5.20 | 5.20 | R-PRED effect_size 5.197833… | 2 位小数半上 → 5.20 ✓ |
| N003 | 0.0 | 0.0 | R-FIX effect_size 0.0 | 1 位小数 → 0.0 ✓ |

起草纪律实况：全稿除 [num:] 呈现值外无裸数字（数量一律英文单词，
如 "three arms"、"the same set of held-out segments"），门二裸数字扫描零命中。

## 6. 接口观察（两条，供 v1.1 参考）

1. **溯源表共键遮蔽**：审计的溯源建表以 `(verdict_line, registry_line_id)` 为键
   先到先占——同一登记行的 effect_size 与 p_ab 共键，p_ab 行被先到的 effect 行
   遮蔽，无法被独立锚定入稿。本演示因此只锚三个 effect_size；
   若 v1.1 要锚 p 值，溯源键须细化到量名（如 `R-ORA#effect` / `R-ORA#p_ab`）。
2. **add-stats 条目形态**：`checklist add-stats` 注入的统计底线条目初始为
   `status=open` + AUTHOR_INPUT_NEEDED 占位锚，此形态下门四必然 fail——
   这是设计（强制作者补落点），演示中由作者改写为 addressed + 真实锚点后过门。
   使用者须知此一步不可跳过。

## 7. W7 返修演示（副本包 manuscript-pkg-revision/）

自终点状态的主包复制为副本后独立返修（主包不受影响）：

| 意见 | 来源/级别 | 处置 | 正文实位 |
|---|---|---|---|
| RC001 主张句旁须明示分析行未检验/未判定 | Reviewer 1 / major（关联 C1、S-discussion） | accept：主张句后新增明示句 | [rev:RC001] @ 04-discussion.md |
| RC002 独立实验单元须在首次出现处定义 | Reviewer 2 / minor（S-methods） | accept：首次出现处补定义从句 | [rev:RC002] @ 02-methods.md |
| RC003 图注须点名复制单元 | Reviewer 1 / minor（S-results） | partial：图注改写并经 figures caption 重登记（哈希更新、正文逐字一致）；逐段原始分数附表留待正式投稿轮次（理由落 rationale） | [rev:RC003] @ 03-results.md |

对账：`revision check` 双向全过（意见 3/3 有回复、改动标记 3/3 被锚点回指）；
`revision bind` 生成 `revision/response_letter.md` 并绑定稿件哈希 `182d1842…`，
bind 后复查 stale=false。副本改稿使主包的审计/复核包对副本不再适用（预期），
副本已用同一在线记录重跑审计：四门全过（overall=pass），副本状态仍为
audited + REVIEW_UNAVAILABLE（复核拦停与主包同口径）。

另：首次回复尝试时对账曾真实报警——回复未登记阶段 check 报 3 条
`revision.unanswered` + 3 条 `revision.unclaimed_change`，证明双向对账在
"只改稿未回复"与"只回复未回指"两种半成品状态下都会拦（日志见 run-log）。
