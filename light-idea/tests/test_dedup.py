"""去重：构造样本的检出与不误报；报告口径。"""

from light_idea.dedup import (
    DEFAULT_THRESHOLD,
    card_text,
    clusters_from_pairs,
    dedup_report,
    find_pairs,
)


def _card(idea_id, title, one_liner, purpose, mechanism, steps):
    return {
        "idea_id": idea_id,
        "title": title,
        "one_liner": one_liner,
        "facets": {
            "purpose": {"phrase": purpose, "detail": purpose},
            "mechanism": {"phrase": mechanism, "detail": mechanism},
            "evaluation": {"phrase": "macro-F1 小样本评估", "detail": ""},
        },
        "body": {"hypothesis": one_liner, "method_steps": steps},
    }


CARD_A = _card(
    "idea_a_000001", "Masked pretraining for tomato leaf disease",
    "用掩码自监督预训练缓解番茄病害小样本分类",
    "缓解小样本病害分类标注不足", "叶片掩码重建预训练",
    ["收集无标注叶片图", "掩码重建预训练", "小样本微调"])

CARD_A_TWIN = _card(  # 与 A 近乎同文，仅个别词不同 → 应被检出
    "idea_a_000002", "Masked pretraining for tomato leaf disease classification",
    "用掩码自监督预训练缓解番茄病害小样本分类问题",
    "缓解小样本病害分类标注不足", "叶片掩码重建预训练",
    ["收集无标注叶片图", "掩码重建预训练", "小样本微调分类头"])

CARD_B = _card(  # 完全不同领域 → 不应与 A 配对
    "idea_b_000003", "Quantum error mitigation for variational algorithms",
    "用零噪声外推降低变分量子算法的误差",
    "降低近期量子设备的门噪声误差", "零噪声外推与概率误差消除",
    ["噪声标定", "缩放电路噪声", "外推零噪声极限"])


def test_near_duplicate_detected():
    pairs = find_pairs([CARD_A, CARD_A_TWIN, CARD_B])
    hit = [p for p in pairs
           if {p["a"], p["b"]} == {"idea_a_000001", "idea_a_000002"}]
    assert hit and hit[0]["similarity"] >= DEFAULT_THRESHOLD


def test_unrelated_not_flagged():
    pairs = find_pairs([CARD_A, CARD_B])
    assert pairs == []


def test_identical_text_similarity_one():
    pairs = find_pairs([CARD_A, dict(CARD_A, idea_id="idea_a_000009")])
    assert pairs and abs(pairs[0]["similarity"] - 1.0) < 1e-6


def test_report_accounting():
    cards = [CARD_A, CARD_A_TWIN, CARD_B]
    pairs = find_pairs(cards)
    rep = dedup_report(cards, pairs, DEFAULT_THRESHOLD)
    assert rep["total_generated"] == 3
    assert rep["suspected_pairs"] == 1
    assert rep["clusters"] == [["idea_a_000001", "idea_a_000002"]]
    assert rep["redundant_if_all_confirmed"] == 1
    assert rep["survivors_if_all_confirmed"] == 2
    assert abs(rep["dedup_rate_if_all_confirmed"] - 1 / 3) < 1e-3


def test_empty_card_named_in_report():
    empty = {"idea_id": "idea_empty", "title": "", "one_liner": "",
             "facets": {}, "body": {}}
    rep = dedup_report([CARD_A, empty], [], DEFAULT_THRESHOLD)
    assert rep["empty_text_cards"] == ["idea_empty"]
    assert card_text(empty) == ""


def test_clusters_transitive():
    pairs = [{"a": "x", "b": "y", "similarity": 0.9},
             {"a": "y", "b": "z", "similarity": 0.8}]
    assert clusters_from_pairs(pairs) == [["x", "y", "z"]]
