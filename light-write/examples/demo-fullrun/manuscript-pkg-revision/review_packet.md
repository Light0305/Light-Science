# 成稿复核包 — zero-tuning-tracker-thresholds-predicted_c8d0fc

- 生成日期：2026-10-20
- 稿件语言：en
- 稿件哈希：`447ab38f6890f42dd3f973dee8dada7f99c6a365115f8aba4d30fe06c63e2794`
- 审计总判定：pass
- 执行者：Claude (light-write demo operator)（家族 claude）

## 成稿口径宪法（复核者须知，判据不重开）

- 引用只许来自 Light-Literature verified 集快照（references.lock）；
  数字只许来自 Analysis 溯源表；正文措辞强度永不超过 Analysis 强度档。
- writable_form 与 wording_ceiling 由上游状态 × 强度档规则表机械导出，
  不许临场升格；untested 主张只许 limitations_only / omit。
- 审计四门（引用两段核对 / 数字对账 / 强度措辞 / 落点映射）的判定
  形态与容差层已冻结，复核不重开门规则本身，只判边界情形的落字属实性。
- 引用语境处置 REPLACE / REMOVE 永须人类批准；相关性存疑只标记不定制。
- 验收合同 contested 的稿件不许 submission_ready，复核不得推翻。
- 复核结论形态：逐边界主张 agree / disagree + 一句理由；有 disagree 的
  回填不被接受——须先改稿或改登记后重新备包复核。


## 主张摘要

| 主张 | 上游状态 | 强度档 | 可写形态 | 措辞上限 |
|---|---|---|---|---|
| C1 | untested | insufficient | limitations_only | minimal |

## 边界主张（共 1 条，逐条全字段）

### C1

入选理由：低强度档主张在正文在场：措辞贴合待核；被降格形态主张在正文在场：降格落字待核

```json
{
  "claim_id": "C1",
  "analysis_claim_ref": "C1",
  "upstream_status": "untested",
  "strength_grade": "insufficient",
  "cap_reason": "主张含未检验行，强度封顶 insufficient；Type M 最差值 4.35 > 2.0，封顶 suggestive",
  "line_verdicts": {
    "R-FIX": "undetermined",
    "R-ORA": "undetermined",
    "R-PRED": "undetermined",
    "R-NEG": "untested",
    "R-LONG": "undetermined"
  },
  "writable_ceiling": "limitations_only",
  "writable_form": "limitations_only",
  "form_choice_note": "intake 按规则表导出上限形态（untested×insufficient）",
  "wording_ceiling": {
    "language": "en",
    "grade": "insufficient",
    "ceiling_label": "minimal",
    "allowed_terms": [
      "was observed",
      "is reported descriptively"
    ],
    "banned_terms": [
      "proves",
      "proved",
      "proof that",
      "no effect",
      "not significant",
      "highly significant"
    ]
  },
  "claim_text": null,
  "text_hash": null,
  "manuscript_locations": [],
  "evidence_refs": [
    {
      "kind": "analysis_verdict_lines",
      "refs": [
        "R-FIX",
        "R-LONG",
        "R-NEG",
        "R-ORA",
        "R-PRED"
      ]
    }
  ]
}
```

## 相关性待核条目（门一标记，复核时一并看）

ST001, ST002, ST005

## 回填形态（review import --from-json 的 JSON schema）

```json
{
  "reviewer": "<复核者名>",
  "family": "<模型家族，须与执行者不同族>",
  "decisions": [
    {
      "claim_id": "<边界主张 id>",
      "agree": true,
      "comment": "<一句理由>"
    }
  ],
  "notes": "<可选总评>"
}
```
