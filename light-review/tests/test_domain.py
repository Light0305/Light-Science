"""Phase 2 · 领域门三层（R4 / RV-16 / RV-17）。

通用轴地板（恒加载）+ 按刊事实层（同一事实源指针 + 时效 UNVERIFIED
纪律）+ 蒸馏覆盖层（格式/加载校验/冲突优先序）。正反面各一。
"""
import pytest

from conftest import make_target_record
from light_review.domain import DomainError, run_domain
from light_review.intake import run_intake
from light_review.project import init_package, load_package
from light_review.util import dump_yaml, today
from light_review.validate import validate_package

SECTIONS_BOTH = {
    "02-methods.md": "# Methods\n\nWe tracked birds with a model.\n",
    "03-results.md": "# Results\n\nThe oracle arm differed by "
                     "[num:N001] 5.25 points [@dong2025].\n",
}


def _pkg_with_sections(world, tmp_path):
    """用带方法节+结果节的稿件包建评审包（通用轴基线全未命中）。"""
    from conftest import make_analysis, make_figure, make_manuscript
    ms = make_manuscript(tmp_path / "ms", sections=SECTIONS_BOTH)
    an = make_analysis(tmp_path / "an")
    fg = make_figure(tmp_path / "fg")
    root = tmp_path / "review"
    init_package(root, "review-pkg")
    run_intake(root, ms, an, figure_path=fg, intensity="standard")
    return root


def _rows(root):
    return load_package(root)["domain_gate"]


def _by_id(root):
    return {r["item_id"]: r for r in _rows(root)
            if r.get("type") == "domain_check"}


# ------------------------------------------------------------ 通用轴地板

def test_universal_floor_all_miss_on_complete_world(world, tmp_path):
    root = _pkg_with_sections(world, tmp_path)
    info = run_domain(root)
    rows = _by_id(root)
    for uid in ("DG-U01", "DG-U02", "DG-U03", "DG-U04", "DG-U05"):
        assert rows[uid]["result"] == "miss", uid
        assert rows[uid]["layer"] == "universal"
        for key in ("source_kind", "severity_if_hit", "evidence_pointer"):
            assert rows[uid].get(key), (uid, key)
    # 条目卡五元数据在定义层在场（稳定 ID/出处轴/严重度/范围/执行层，RV-16）
    from light_review.domain import UNIVERSAL_ITEMS
    for item in UNIVERSAL_ITEMS:
        for key in ("item_id", "axis", "severity_if_hit", "scope", "tier"):
            assert item.get(key), (item.get("item_id"), key)
    assert info["summary"]["checked"] == len(rows)
    assert validate_package(root) == []


def test_universal_hit_claim_without_evidence(world, tmp_path):
    from conftest import make_analysis, make_figure, make_manuscript
    claims = [{"claim_id": "C1", "statement": "s", "writable_form": "full",
               "evidence_refs": [], "strength_grade": "insufficient"}]
    ms = make_manuscript(tmp_path / "ms", sections=SECTIONS_BOTH,
                         claims=claims)
    an = make_analysis(tmp_path / "an")
    fg = make_figure(tmp_path / "fg")
    root = tmp_path / "review"
    init_package(root, "review-pkg")
    run_intake(root, ms, an, figure_path=fg, intensity="standard")
    run_domain(root)
    assert _by_id(root)["DG-U01"]["result"] == "hit"


def test_universal_hit_missing_method_section(review_pkg):
    # 基线世界只有结果节：DG-U05 必须命中（地板不是摆设）
    run_domain(review_pkg)
    assert _by_id(review_pkg)["DG-U05"]["result"] == "hit"


# ------------------------------------------------------------ 按刊事实层

def _pkg_with_record(world, tmp_path, *, groups=None, verified_at=None):
    from conftest import make_analysis, make_figure, make_manuscript
    ms = make_manuscript(tmp_path / "ms", sections=SECTIONS_BOTH)
    an = make_analysis(tmp_path / "an")
    fg = make_figure(tmp_path / "fg")
    record = make_target_record(tmp_path, groups=groups,
                                verified_at=verified_at)
    root = tmp_path / "review"
    init_package(root, "review-pkg")
    run_intake(root, ms, an, figure_path=fg, intensity="standard", journal_name="Demo Journal",
               target_record=record)
    return root


def test_journal_fact_hit_and_miss_fresh_record(world, tmp_path):
    root = _pkg_with_record(world, tmp_path, groups={
        "D": {"word_limit_total": 5, "figure_limit": 10}})
    info = run_domain(root)
    rows = _by_id(root)
    assert rows["DG-J01"]["result"] == "hit"      # 词数远超 5
    assert rows["DG-J01"]["fact"]["fact_status"] == "verified"
    assert rows["DG-J01"]["fact"]["value"] == 5
    assert rows["DG-J03"]["result"] == "miss"     # 1 图 ≤ 10
    assert info["fact_source"]["fact_status"] == "verified"
    assert validate_package(root) == []


def test_journal_fact_stale_record_all_not_applicable(world, tmp_path):
    """事实过期 → UNVERIFIED：那怕限额必然被超，也不许驱动判定。"""
    root = _pkg_with_record(world, tmp_path,
                            groups={"D": {"word_limit_total": 1}},
                            verified_at="2000-01-01")
    info = run_domain(root)
    rows = _by_id(root)
    assert info["fact_source"]["fact_status"] == "unverified"
    for jid in ("DG-J01", "DG-J02", "DG-J03", "DG-J04", "DG-J05", "DG-J06"):
        assert rows[jid]["result"] == "not_applicable", jid
        assert rows[jid]["fact"]["fact_status"] == "unverified"
    assert validate_package(root) == []


def test_journal_fact_tampered_stale_row_rejected(world, tmp_path):
    """把过期事实的行手改成 verified + hit → 校验器双咬（RV-17）。"""
    from light_review.project import save_domain_gate
    root = _pkg_with_record(world, tmp_path,
                            groups={"D": {"word_limit_total": 1}},
                            verified_at="2000-01-01")
    run_domain(root)
    rows = _rows(root)
    for r in rows:
        if r.get("item_id") == "DG-J01":
            r["result"] = "hit"
            r["fact"]["fact_status"] = "verified"
    save_domain_gate(root, rows)
    errors = validate_package(root)
    assert any("UNVERIFIED" in e for e in errors)
    assert any("过期事实" in e for e in errors)


def test_journal_fact_no_record_not_applicable(review_pkg):
    run_domain(review_pkg)
    rows = _by_id(review_pkg)
    assert rows["DG-J01"]["result"] == "not_applicable"
    assert "未登记目标刊" in rows["DG-J01"]["detail"]
    assert validate_package(review_pkg) == []


def test_journal_fact_ai_disclosure_hit(world, tmp_path):
    root = _pkg_with_record(world, tmp_path, groups={
        "G": {"ai_policy": {"has_guideline": True,
                            "disclosure_required": True}}})
    run_domain(root)
    # 稿件正文无 AI 使用披露声明 → 命中
    assert _by_id(root)["DG-J05"]["result"] == "hit"


# ------------------------------------------------------------ 蒸馏覆盖层

def _overlay(tmp_path, *, precedence="overlay_wins", **item_over):
    item = {"item_id": "DG-X01", "statement": "须含伦理声明",
            "source_kind": "historical_calibration",
            "explicit_or_inferred": "explicit",
            "confidence": 0.9, "severity_if_hit": "major",
            "scope": "本学科实验类稿件", "executor": "code",
            "overrides": "DG-U04",
            "check": {"kind": "keyword_present",
                      "keywords": ["ethics statement"]}}
    item.update(item_over)
    overlay = {"overlay_id": "demo-overlay", "version": "0.1",
               "source": {"kind": "historical_calibration",
                          "ref": "demo 校准集", "checked_at": today()},
               "dual_store_pointer": "light-memory://overlays/demo",
               "precedence": {"on_conflict": precedence},
               "items": [item]}
    path = tmp_path / "overlay.yaml"
    dump_yaml(path, overlay)
    return path


def test_overlay_overlay_wins_supersedes_core(world, tmp_path):
    root = _pkg_with_sections(world, tmp_path)
    run_domain(root, overlay_path=_overlay(tmp_path))
    rows = _by_id(root)
    assert rows["DG-X01"]["result"] == "hit"          # 正文无伦理声明
    assert rows["DG-U04"]["effective"] is False
    assert rows["DG-U04"]["superseded_by"] == "DG-X01"
    assert rows["DG-X01"]["effective"] is True
    assert validate_package(root) == []


def test_overlay_core_wins_supersedes_overlay(world, tmp_path):
    root = _pkg_with_sections(world, tmp_path)
    run_domain(root, overlay_path=_overlay(tmp_path,
                                           precedence="core_wins"))
    rows = _by_id(root)
    assert rows["DG-X01"]["effective"] is False
    assert rows["DG-X01"]["superseded_by"] == "DG-U04"
    assert rows["DG-U04"]["effective"] is True
    assert validate_package(root) == []


@pytest.mark.parametrize("mutate", [
    lambda o: o.pop("dual_store_pointer"),
    lambda o: o["precedence"].update(on_conflict="coin_flip"),
    lambda o: o["source"].update(kind="made_up"),
    lambda o: o["items"][0].update(confidence=1.5),
    lambda o: o["items"][0].update(check={"kind": "vibes"}),
    lambda o: o["items"][0].pop("statement"),
    lambda o: o["items"][0].update(source_kind="made_up"),
])
def test_overlay_format_rejected(world, tmp_path, mutate):
    root = _pkg_with_sections(world, tmp_path)
    path = _overlay(tmp_path)
    from light_review.util import load_structured
    overlay = load_structured(path)
    mutate(overlay)
    dump_yaml(path, overlay)
    with pytest.raises(DomainError):
        run_domain(root, overlay_path=path)


def test_overlay_resolution_tamper_rejected(world, tmp_path):
    """手改冲突解析结果（把被 supersede 的核心行改回 effective）→ 校验咬。"""
    from light_review.project import save_domain_gate
    root = _pkg_with_sections(world, tmp_path)
    run_domain(root, overlay_path=_overlay(tmp_path))
    rows = _rows(root)
    for r in rows:
        if r.get("item_id") == "DG-U04":
            r["effective"] = True
            r["superseded_by"] = None
    save_domain_gate(root, rows)
    errors = validate_package(root)
    assert any("supersede" in e for e in errors)


# ------------------------------------------------------------ 入门序

def test_reported_gate_requires_domain_file_when_registered(review_pkg):
    """登记了领域门但 domain_gate.jsonl 缺失 → reported 门阻断。"""
    from light_review.gates import GateError, advance_package
    from light_review.project import FILES
    run_domain(review_pkg)
    (review_pkg / FILES["domain_gate"]).unlink()
    from light_review.forensic import run_forensic
    from light_review.panel import build_consensus, freeze_reports
    from conftest import DEFAULT_CONCERNS, drive_panel
    run_forensic(review_pkg)
    advance_package(review_pkg)
    drive_panel(review_pkg)
    advance_package(review_pkg)
    freeze_reports(review_pkg)
    build_consensus(review_pkg, DEFAULT_CONCERNS)
    with pytest.raises(GateError) as exc:
        advance_package(review_pkg)
    assert any("领域门" in g for g in exc.value.gaps)


def test_reported_gate_passes_with_domain_present(review_pkg):
    from conftest import drive_to_reported
    run_domain(review_pkg)
    drive_to_reported(review_pkg)
    pkg = load_package(review_pkg)
    assert pkg["review"]["status"] == "reported"
    assert "domain_gate" not in pkg["review"]["phase2_pending"]
