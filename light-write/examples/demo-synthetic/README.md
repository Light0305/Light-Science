# 演示：承接 Analysis 合成演示结论包（Phase 1 实跑记录）

本目录是一个真实跑出的稿件包骨架，承接对象是上游演示产物（均为合成演示口径，不构成对真实数据的结论）：

- **Analysis 侧**：`light-analysis/examples/demo-synthetic/analysis-pkg/conclusion_card.json`——状态 `blocked`（非 delivered）、复核 `REVIEW_UNAVAILABLE`、唯一主张 C1 为 `untested × insufficient`（含未检验行 R-NEG）。
- **Literature 侧**：`light-literature/examples/demo-find/Literature/候选池.jsonl`——9 条候选中 4 条 `identity_status=verified`。

## 实跑结果（2026-10-20，light-write 0.1.0）

```
init    → manuscript_id zero-tuning-tracker-thresholds-synthetic_7e1290, status intake, language en
intake  → claims_registered [C1]; writable_forms {C1: limitations_only};
          literature_entries_locked 4; gaps 1 条（见下）
validate → 0 errors, 6 warnings（全部点名，见下）
advance → 被拦，gaps 恰为 2 项真实缺口（见下）
```

### 承接纪律的实测落点

1. **untested 主张按规则降级**：C1（untested）writable_form 由规则表导出为 `limitations_only`——只许进局限节；若人工改登记为 `full`，validate 以 `claims.form_exceeds_ceiling` 拒绝（有测试）。
2. **上游状态原样落字**：登记头 `upstream_flags` 记 `analysis_not_delivered: 上游结论包状态为 blocked（非 delivered），主张按降级口径登记` 与 `analysis_review_status: REVIEW_UNAVAILABLE（原样落字）`；结论卡文件哈希、卡内主张集哈希、数字溯源表哈希（19 条 number_provenance 中本卡为演示子集口径，以 intake 快照为准）、verified 集哈希均已落快照，任一侧变动 validate 即报承接失效。
3. **verified 过滤实测**：候选池 9 条中仅 4 条 verified 入锁（ST 系列演示条目），未核实条目不进锁——成稿层「未核实文献一律不用」的机械落点。
4. **如实记录的缺口**（不掩盖、不临场编造）：
   - 主张 C1 上游未给规范文本（conclusion_card 无 text 字段）→ `claims.text_pending` 警告，text_hash 留空待补；
   - 声明四项（data_availability / ethics / conflict / funding）为骨架缺省 `absent` → 4 条 `declarations.absent` 警告；
   - 目标期刊模板记录未登记 → `template.not_registered` 警告，且是 advance 的拦项之一；
   - 验收合同未冻结 → advance 的另一拦项（拍板⑥硬门）。
5. **advance 被拦是预期行为**：gaps 逐项点名（模板未登记、合同未冻结），补齐两项并冻结合同后即可进 outlined（全路径有测试覆盖，含 contested 降级变体）。
