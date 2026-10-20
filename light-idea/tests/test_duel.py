"""三期 duel/rank 测试：对决双向落卡、镜像去重还原、胜率矩阵、
Elo 结算方向、循环胜负检测、非法 winner 拒绝、CLI 全流。"""

from __future__ import annotations

import pytest

from light_idea import duel
from light_idea.cli import main
from light_idea.project import init_project, load_card, save_card
from conftest import full_card


def _card(idea_id: str) -> dict:
    c = full_card()
    c["idea_id"] = idea_id
    c["aux"] = {}
    return c


def test_record_duel_writes_both_cards():
    a, b = _card("alpha_111111"), _card("beta_222222")
    rec = duel.record_duel(a, b, "alpha_111111", by="judge-x", note="机制更清晰")
    assert rec["winner"] == "alpha_111111"
    ra = a["aux"]["pairwise_record"]
    rb = b["aux"]["pairwise_record"]
    assert len(ra) == len(rb) == 1
    assert ra[0]["opponent"] == "beta_222222" and ra[0]["result"] == "win"
    assert rb[0]["opponent"] == "alpha_111111" and rb[0]["result"] == "loss"
    assert ra[0]["by"] == "judge-x"


def test_record_duel_draw_and_rejections():
    a, b = _card("alpha_111111"), _card("beta_222222")
    duel.record_duel(a, b, "draw", by="judge-x")
    assert a["aux"]["pairwise_record"][0]["result"] == "draw"
    assert b["aux"]["pairwise_record"][0]["result"] == "draw"
    with pytest.raises(duel.DuelError):
        duel.record_duel(a, b, "gamma_333333", by="judge-x")  # 非参赛者
    with pytest.raises(duel.DuelError):
        duel.record_duel(a, a, "alpha_111111", by="judge-x")  # 自己打自己


def test_collect_matches_dedupes_mirror():
    a, b = _card("alpha_111111"), _card("beta_222222")
    duel.record_duel(a, b, "beta_222222", by="j", date="2026-10-20")
    matches = duel.collect_matches([a, b])
    assert len(matches) == 1  # 双方各存一份镜像，只还原一场
    assert matches[0]["a"] == "alpha_111111"
    assert matches[0]["result_a"] == "loss"


def test_win_matrix_and_elo_direction():
    a, b, c = _card("a_000001"), _card("b_000002"), _card("c_000003")
    duel.record_duel(a, b, "a_000001", by="j", date="2026-10-20")
    duel.record_duel(a, c, "a_000001", by="j", date="2026-10-20")
    duel.record_duel(b, c, "draw", by="j", date="2026-10-20")
    cards = [a, b, c]
    rank = duel.rank_project(None, cards)
    m = rank["matrix"]
    assert m["a_000001"]["b_000002"] == {"win": 1, "loss": 0, "draw": 0}
    assert m["b_000002"]["a_000001"] == {"win": 0, "loss": 1, "draw": 0}
    assert m["b_000002"]["c_000003"]["draw"] == 1
    elo = rank["elo"]
    assert elo["a_000001"] > 1500 > elo["b_000002"]
    assert elo["c_000003"] > elo["b_000002"]  # c 与 a 负、与 b 平，仍高于全负的 b
    standings = rank["standings"]
    assert standings[0]["idea_id"] == "a_000001"
    assert standings[0]["win"] == 2 and standings[0]["win_rate"] == 1.0
    assert rank["cycles"] == []


def test_cycles_detected_and_reported():
    a, b, c = _card("a_000001"), _card("b_000002"), _card("c_000003")
    duel.record_duel(a, b, "a_000001", by="j", date="2026-10-20")
    duel.record_duel(b, c, "b_000002", by="j", date="2026-10-20")
    duel.record_duel(c, a, "c_000003", by="j", date="2026-10-20")
    rank = duel.rank_project(None, [a, b, c])
    assert rank["cycles"] == [["a_000001", "b_000002", "c_000003"]]


def test_rank_no_matches():
    rank = duel.rank_project(None, [_card("a_000001")])
    assert rank["matches"] == [] and rank["standings"] == []


def test_cli_duel_and_rank(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "对决方向")
    a, b = _card("alpha_111111"), _card("beta_222222")
    save_card(root, a)
    save_card(root, b)
    assert main(["duel", str(root), "--a", "alpha_111111",
                 "--b", "beta_222222", "--winner", "alpha_111111",
                 "--by", "judge-gpt"]) == 0
    la = load_card(root, "alpha_111111")
    assert la["aux"]["pairwise_record"][0]["result"] == "win"
    # 非法 winner（命令层 winner 校验在 record_duel，须走 CLI 返回 1）
    assert main(["duel", str(root), "--a", "alpha_111111",
                 "--b", "beta_222222", "--winner", "nobody"]) == 1
    # 不存在的卡
    assert main(["duel", str(root), "--a", "alpha_111111",
                 "--b", "ghost_999999", "--winner", "alpha_111111"]) == 1
    assert main(["rank", str(root)]) == 0
    la = load_card(root, "alpha_111111")
    assert la["aux"]["elo"] > 1500  # rank 已回写参考分
    assert main(["rank", str(root), "--no-write"]) == 0
