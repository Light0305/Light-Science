# 分册：披露、复核门、W7 返修与 W5 图表对账细则

> light-write SKILL 分册（WRT-D06 分册化）。来源 = v1.0 SKILL §12–§15 verbatim 下沉；主文件只留 submission_ready 门卡，细则以本册为准。

## §12 按刊披露规程（W4/W6）

1. `disclose` 以 use_log × 模板记录 G 组 `ai_policy` 生成披露：规定措辞模板在场时按模板回填占位符（{tool}/{model}/{version}/{purpose}/{section}/{date} 从 use_log 聚合），占位符无从回填 → 点名拦停；无模板时以留痕逐项渲染（数据呈现）。规定声明标题在场时作小标题。
2. **缺字段不许编造**：政策缺标题与模板两者 → 拦停点名，须先按期刊官方原文补全模板记录；use_log 为空 → 拦停（无留痕不编披露）；披露位置在稿件节登记中无对应节 → 点名。
3. `output_validity_evaluation` 子项在场（PLOS 口径）→ 须作者在 `manuscript.output_validity_note` 落字，工具只检查在场不代写，披露文本附该说明。
4. 披露落到 `disclosure_positions` 的**每个**位置（节内锚点块 `<!-- light-write:disclosure:<position> -->`，重跑替换不叠加）；生成记录落 `manuscript.disclosures[]`（含 policy/use_log 双哈希），政策或留痕变动 → STALE，投稿就绪门检出须重跑。
5. 披露靠留痕生成，全程不设 AI 检测器分数（约束 10）；该刊不要求披露时 disclose 返回说明即止，不生成文本。

## §13 复核门与 submission_ready（W6）

1. `review prepare` 生成自包含复核包 `review_packet.md`：成稿口径宪法 + 审计总判定 + 主张摘要 + **边界主张**全字段（正文在场且强度档 ≤ suggestive，或 writable_form 被降格者）+ 门一相关性待核清单 + 回填 JSON 形态。复核只判边界情形的落字属实性，不重开冻结口径。
2. `review record` 落收据 `RV-<sha256[:10]>`：复核者身份与家族必填；与执行者（`manuscript.executor`）同族拒、同一人拒；带异议（非 agree/agree_with_notes）不落收据，须先改稿/改登记后重审。`review import --from-json` 回填外部判定：schema 外字段拒、边界主张须逐条回填、任一 disagree 拒收。`review unavailable --reason` 显式落 REVIEW_UNAVAILABLE。
3. **submission_ready 门** = 审计四门新鲜全过 + 落点**底线层**全 addressed + 声明无 absent + 披露齐备且新鲜 + 合同非 contested + 复核 approved 收据且其稿件哈希与当前稿一致。REVIEW_UNAVAILABLE 时 advance 停在 audited 并把 blocked 原因落字（`submission_blocked_reason`），与 Idea/Design/Analysis 同构——降级是落字停等，不是放行。
4. 置真后稿件任何内容变动 → 审计/复核/披露连环 STALE，validate 报错；要改稿先回退状态重走对应段。

## §14 W7 返修规程（revision 子包）

1. **意见登记**：`revision add-comment` 逐条登记审稿意见**原文**（不许转述替代）、来源审稿人、分类（major/minor/editorial）、关联主张/节、轮次。意见到了先全登记再逐条处置，不许边回边漏。
2. **逐条回复**：`revision respond` 每条意见恰一回复——决策 accept/partial/reject + 理由必填（reject 也要说清依据）；accept/partial 必须登记改动锚点 change_anchors（{file, marker}），正文改动处落 `[rev:<comment_id>]` 标记。
3. **双向对账**（`revision check`）：正向——意见全覆盖、回复锚点实位存在；反向——正文每个 `[rev:]` 标记都被对应回复锚点回指，无无主改动。对账不过不许 bind。
4. **回复信绑定**（`revision bind`）：对账全过后渲染 `revision/response_letter.md` 并绑当前稿件哈希；此后稿改而信未更新 → check 报 STALE，须更新回复后重绑。resubmit 前必查：`revision check` ok 且 stale=False。

## §15 W5 图表回填对账与编号冻结

1. **登记与回填**：图表先 `figures add` 登记（F###/T###、kind）；正文以 `[fig:F###]` 标记占位/引用；`figures sync` 从正文回填 intext_refs 账（唯一回填口，check 只判不改）；Figure 交付后 `figures delivered` 记 source_ref + 文件哈希，图注以 `figures caption` 登记（落 caption_text_hash），回填完成标 `--backfill`。
2. **三方对账**（`figures check`）：清单行 ↔ 正文标记实位 ↔ 图注文本——intext_refs 账实一致；backfilled 行图注在场、哈希对齐、图注原文出现在放置节文件中；display_number 同 kind 内不重复。
3. **编号冻结**：时点在 audited 段前（投稿就绪前编号不再动），且**必须排在终审审计之前**——冻结改动图表清单的 `numbering_freeze` 字段（在稿件哈希覆盖范围内），冻结后先前的审计产物即 STALE 须重跑（demo-fullrun 实测教训）。`figures freeze` 按正文首次出现次序（节登记序 × 行号）分 kind 派号并落冻结日志。冻结后新增图表**只许追加编号**（add 自动派尾号 + 落 `append_after_freeze` 日志）或**全量重编**（`freeze --renumber`，落 `renumber_all` 日志）——不许静默插队改号。

