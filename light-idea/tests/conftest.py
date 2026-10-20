"""测试共用：构造一张各区齐全的想法卡（默认能过全部定版门）。"""

from __future__ import annotations

import copy

from light_idea.schema import PRE_MORTEM_ITEMS


def full_card(status: str = "draft") -> dict:
    card = {
        "idea_id": "self-supervised-pretraining-for-tomato_540d00",
        "title": "Self-supervised pretraining for tomato leaf disease",
        "one_liner": "用自监督预训练缓解小样本番茄病害分类的标注不足",
        "status": status,
        "operator": "evolution_chain",
        "provenance": {"chain_id": "LC-001", "path_string": None,
                       "combo": None, "note": None},
        "created": "2026-10-20",
        "updated": "2026-10-20",
        "seed_refs": [
            {"paper_id": "masked-autoencoder_abc123", "title": "MAE"},
        ],
        "facets": {
            "purpose": {
                "phrase": "缓解小样本病害分类标注不足",
                "detail": "田间番茄病害标注昂贵，公开集与田间域差距大。",
                "source": {"type": "paper", "paper_id": "survey_plant_disease_def456"},
            },
            "mechanism": {
                "phrase": "叶片自监督掩码预训练",
                "detail": "在无标注叶片图上做掩码重建预训练，再小样本微调。",
                "source": {"type": "chain_node", "chain_id": "LC-001", "node": 3},
            },
            "evaluation": {
                "phrase": "跨域小样本 macro-F1",
                "detail": "在田间集上以 10/50/200 shot 的 macro-F1 评估。",
                "source": {"type": "user"},
            },
        },
        "body": {
            "method_steps": ["收集无标注田间叶片图", "掩码重建预训练", "小样本微调分类头"],
            "hypothesis": "叶片纹理的自监督表征可把标注需求降一个数量级",
            "mechanism_rationale": "病害斑纹理是判别主信号，掩码重建强迫模型学纹理结构。",
            "unexpected_prediction": "预训练后对背景变化的鲁棒性提升大于对类内变化的提升",
            "contribution_type": "method",
        },
        "feasibility": {
            "compute_within_budget": True, "compute_note": "单卡 40 GPU 小时内可完成",
            "data_obtainable": True, "data_note": "无标注叶片图来自公开田间集，可下载",
        },
        "exec_spec": {
            "datasets": [{"name": "PlantVillage", "version": "v2",
                          "access": "公开下载"}],
            "strongest_baseline": {"name": "ResNet50 ImageNet 微调",
                                   "paper_id": "resnet_baseline_111aaa"},
            "metrics": [{"name": "macro-F1",
                         "convention_source": "本领域近三年 CEA 论文惯例"}],
            "ablations": ["去掉预训练", "冻结层数 0/2/4", "掩码率 0.5/0.75"],
            "resource_budget": {"gpu_hours": 40, "data": "公开集", "weeks": 3},
            "key_details": ["掩码率 0.75", "微调只解冻最后两层起步"],
            "discriminating_experiment": {
                "description": "50-shot 田间集上与最强基线对决",
                "readout_positive": "macro-F1 高 ≥3 点：机制成立，进 Design",
                "readout_negative": "低于基线：掩码预训练不适配叶片纹理，回炉 facet",
                "readout_null": "差距 <1 点：判别力不足，加大 shot 或换评估域",
            },
        },
        "negative": {
            "strongest_objection": "审稿人会说 MAE 在植物域已被试过，只是换作物",
            "risks": ["田间集与预训练域仍有差距"],
            "why_not_selected_first": "",
        },
        "pre_mortem": {
            "date": "2026-10-20",
            "checklist": {item: {"status": "pass", "note": "已查"}
                          for item in PRE_MORTEM_ITEMS},
            "open_items": [],
        },
        "finalization_level": None,
        "novelty": {
            "checked_at": "2026-10-20",
            "search_scope": {"sources": ["semantic_scholar", "openalex"],
                             "pool_size": 132,
                             "known_blind_spots": "中文期刊覆盖弱"},
            "closest_works": [
                {"paper_id": "mae-plant_999fff", "title": "MAE for plant phenotyping",
                 "year": 2024, "collided_facets": ["mechanism"],
                 "delta": "其预训练在温室受控图上，本想法针对田间域",
                 "verified": True},
            ],
            "verdict": "PROCEED",
            "caution_reason": "",
            "receipt": {"verdict_id": "V-2026-001",
                        "judge_model": "gpt-5", "judge_family": "openai",
                        "executor_model": "claude-opus", "executor_family": "anthropic"},
            "review_status": "ok",
            "evidence_package": "novelty/self-supervised-pretraining-for-tomato_540d00/",
        },
        "aux": {"neighbor_similarity": 0.42},
        "pilot": {"status": "not_run", "note": ""},
        "lineage": {"changed_from": None, "revision_operator": None,
                    "revision_log": [], "bad_case_refs": []},
        "dedup": {"checked": True, "max_similarity": 0.42,
                  "most_similar_to": "other_idea_000000", "adjudication": None},
        "status_history": [{"from": None, "to": "draft", "date": "2026-10-20",
                            "by": "test", "note": ""}],
        "kill": None,
        "park": None,
    }
    return copy.deepcopy(card)
