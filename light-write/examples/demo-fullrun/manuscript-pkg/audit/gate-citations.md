# 门一 · 引用两段核对

- 稿件哈希：`9544b862a48218c9…`
- 判定：**pass**
- 时间：2026-10-20T18:45:55+00:00

## 明细

```json
{
  "cited_count": 3,
  "entries": [
    {
      "entry_id": "ST001",
      "key": "dong2025-is",
      "identity": "verified_online",
      "field_screen": "negative",
      "findings": [],
      "verification_status": "verified"
    },
    {
      "entry_id": "ST002",
      "key": "bai2021-enet",
      "identity": "verified_online",
      "field_screen": "negative",
      "findings": [],
      "verification_status": "verified"
    },
    {
      "entry_id": "ST005",
      "key": "wang2022-attention",
      "identity": "verified_online",
      "field_screen": "negative",
      "findings": [
        {
          "level": "warning",
          "code": "cite.venue_variant",
          "message": "venue 变体差异：lock 'arXiv' vs 权威 'IEEE Access'（缩写/全称等价口径，只警告）",
          "where": "ST005"
        }
      ],
      "verification_status": "check_suggested"
    }
  ],
  "support_assessments": [
    {
      "token": "ST001",
      "level": "background",
      "claim_id": null,
      "rejection_reason": null
    },
    {
      "token": "ST002",
      "level": "partial",
      "claim_id": null,
      "rejection_reason": null
    },
    {
      "token": "ST005",
      "level": "background",
      "claim_id": null,
      "rejection_reason": null
    }
  ],
  "relevance_pending": [
    "ST001",
    "ST002",
    "ST005"
  ]
}
```

## Findings

- [warning] `cite.venue_variant` venue 变体差异：lock 'arXiv' vs 权威 'IEEE Access'（缩写/全称等价口径，只警告）
- [warning] `cite.relevance_pending` 相关性轴待人工/复核（不自动定罪）：['ST001', 'ST002', 'ST005']
