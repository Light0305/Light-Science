"""LD-02 扩展位纳管（v1.1 集成步）：三包状态词登记、status 汇总
读到三包、route 点名符合定位（爬虫熔断/blocked、专利时间窗与门、
软著补正与出口提示）；扩展位不进主流水线的下一步与收官判定。
"""

from datetime import date, timedelta

from light_leader import cli, route as route_mod, scan as scan_mod
from light_leader import scaffold, statusmap
from light_leader.layout import EXTENSIONS, SCAFFOLD_DIRS

from conftest import (make_copyright, make_crawler, make_literature,
                      make_patent, make_review)


def _scan(root):
    return scan_mod.scan_project(root)


def _route(root):
    return route_mod.route(_scan(root))


# ---------------------------------------------------------------- 状态词

def test_statusmap_extensions_coverage():
    for stage in ("patent", "software-copyright", "crawler"):
        assert set(statusmap.KNOWN_STATES[stage]) == \
            set(statusmap.STATUS_MAP[stage]), stage
    assert statusmap.canonical("patent", "granted") == "已达终态"
    assert statusmap.canonical("patent", "responded") == "进行中"
    assert statusmap.canonical("patent", "abandoned") == "旁路"
    assert statusmap.canonical("software-copyright", "packaged") == "已达终态"
    assert statusmap.canonical("software-copyright", "correcting") == "旁路"
    assert statusmap.canonical("crawler", "active") == "进行中"
    assert statusmap.canonical("crawler", "attention") == "被门拦"
    for stage, spec in EXTENSIONS.items():
        for term in spec["terminal"]:
            assert statusmap.canonical(stage, term) == "已达终态", \
                (stage, term)


# ---------------------------------------------------------------- 骨架

def test_init_creates_extension_slots(tmp_path):
    root = tmp_path / "proj"
    head = scaffold.init_project(root, "demo-proj")
    for d in ("data-sources", "patent/cases", "软件著作权申请资料"):
        assert d in SCAFFOLD_DIRS
        assert (root / d).is_dir(), d
    from light_leader.util import load_yaml
    data = load_yaml(head)
    exts = {e["extension"]: e for e in data["extensions"]}
    assert set(exts) == {"patent", "software-copyright", "crawler"}
    assert exts["patent"]["slot"] == "出口层扩展位"
    assert exts["crawler"]["slot"] == "通道层扩展位"
    # stages 十项不被扩展位污染（既有断言口径不变）
    assert len(data["stages"]) == 10


# ---------------------------------------------------------------- status

def test_scan_reads_all_three_extensions(tmp_path):
    make_patent(tmp_path, status="responded", deadlines=[
        {"kind": "office_action_response", "label": "审查意见答复期",
         "due": "2027-07-01", "basis": "通知书"}])
    make_copyright(tmp_path, status="packaged")
    make_crawler(tmp_path, targets=[
        {"target_id": "t-ok", "precheck_status": "effective"},
        {"target_id": "t-bad", "precheck_status": "blocked",
         "blocked_reasons": ["robots 结论禁止"]}])
    rep = _scan(tmp_path)
    pat = rep["extensions"]["patent"]
    assert pat["found"] and pat["items"][0]["status"] == "responded"
    assert pat["items"][0]["canonical"] == "进行中"
    assert pat["items"][0]["deadlines"][0]["due"] == "2027-07-01"
    cr = rep["extensions"]["software-copyright"]
    assert cr["found"] and cr["items"][0]["status"] == "packaged"
    assert cr["items"][0]["canonical"] == "已达终态"
    cw = rep["extensions"]["crawler"]
    assert cw["found"] and cw["items"][0]["status"] == "active"
    targets = {t["target_id"]: t for t in cw["items"][0]["targets"]}
    assert targets["t-ok"]["precheck_status"] == "effective"
    assert targets["t-bad"]["precheck_status"] == "blocked"
    assert targets["t-bad"]["circuit_broken"] is False


def test_scan_patent_ignores_foreign_case_yaml(tmp_path):
    # 同名 case.yaml 但 kind 不是 light-patent/case：不冒认
    from conftest import write_yaml
    write_yaml(tmp_path / "misc" / "case.yaml",
               {"kind": "other/case", "status": "whatever"})
    rep = _scan(tmp_path)
    assert rep["extensions"]["patent"]["found"] is False


def test_cli_status_prints_extensions(tmp_path, capsys):
    make_patent(tmp_path)
    make_copyright(tmp_path)
    make_crawler(tmp_path, targets=[{"target_id": "t1",
                                      "precheck_status": "effective"}])
    assert cli.main(["status", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "light-patent" in out and "出口层扩展位" in out
    assert "light-software-copyright" in out
    assert "light-crawler" in out and "通道层扩展位" in out
    assert "预检 effective" in out


# ---------------------------------------------------------------- route

def test_route_crawler_circuit_broken_named(tmp_path):
    make_crawler(tmp_path, workspace_status="attention", targets=[
        {"target_id": "t-hot", "circuit_broken": True,
         "circuit_reason": "连续两 run 被拒", "precheck_status": "effective"}])
    r = _route(tmp_path)
    named = [n for n in r["notes"] if "t-hot" in n and "熔断" in n]
    assert len(named) == 1
    assert "unblock" in named[0]


def test_scan_crawler_precheck_fold_semantics(tmp_path):
    # prechecks 是混合种类追加日志：当前态按 crawler 自家折叠语义——
    # 末条 precheck 为准，确认行把 pending_confirmation 翻 effective，
    # 但确认行不解 blocked
    from conftest import write_jsonl, write_yaml
    ds = tmp_path / "data-sources"
    write_yaml(ds / "crawler.yaml",
               {"kind": "light-crawler/workspace", "version": 1,
                "workspace_id": "ws-x", "status": "active",
                "circuit_broken_targets": []})
    for tid, rows in (
        ("t-conf", [{"kind": "precheck", "precheck_id": "pc-1",
                     "target_id": "t-conf",
                     "status": "pending_confirmation"},
                    {"kind": "confirmation", "precheck_id": "pc-1",
                     "target_id": "t-conf", "confirmer": "演示用户"}]),
        ("t-blk", [{"kind": "precheck", "precheck_id": "pc-2",
                    "target_id": "t-blk", "status": "blocked",
                    "blocked_reasons": ["禁止"]},
                   {"kind": "confirmation", "precheck_id": "pc-2",
                    "target_id": "t-blk", "confirmer": "演示用户"}]),
    ):
        write_yaml(ds / "targets" / tid / "target.yaml",
                   {"target_id": tid, "channel": "web_page"})
        write_yaml(ds / "targets" / tid / "state.yaml",
                   {"target_id": tid, "circuit_broken": False})
        write_jsonl(ds / "prechecks" / f"{tid}.jsonl", rows)
    rep = _scan(tmp_path)
    targets = {t["target_id"]: t
               for t in rep["extensions"]["crawler"]["items"][0]["targets"]}
    assert targets["t-conf"]["precheck_status"] == "effective"
    assert targets["t-blk"]["precheck_status"] == "blocked"


def test_route_crawler_blocked_and_unprechecked_named(tmp_path):
    make_crawler(tmp_path, targets=[
        {"target_id": "t-blocked", "precheck_status": "blocked",
         "blocked_reasons": ["robots 结论禁止 /private"]},
        {"target_id": "t-new"},
        {"target_id": "t-pending",
         "precheck_status": "pending_confirmation"},
        {"target_id": "t-ok", "precheck_status": "effective"}])
    r = _route(tmp_path)
    notes = "\n".join(r["notes"])
    assert "t-blocked" in notes and "robots 结论禁止 /private" in notes
    assert "t-new" in notes and "未预检" in notes
    assert "t-pending" in notes and "待具名确认" in notes
    assert "t-ok" not in notes


def test_route_patent_deadline_window_named(tmp_path):
    soon = (date.today() + timedelta(days=30)).isoformat()
    far = (date.today() + timedelta(days=300)).isoformat()
    make_patent(tmp_path, deadlines=[
        {"kind": "office_action_response", "label": "审查意见答复期",
         "due": soon, "basis": "通知书"},
        {"kind": "request_examination", "label": "请求实质审查期限",
         "due": far, "basis": "专利法第 35 条"}])
    r = _route(tmp_path)
    notes = "\n".join(r["notes"])
    assert "审查意见答复期" in notes and "剩 30 天" in notes
    assert "请求实质审查期限" not in notes


def test_route_patent_overdue_deadline_named(tmp_path):
    past = (date.today() - timedelta(days=5)).isoformat()
    make_patent(tmp_path, deadlines=[
        {"kind": "priority", "label": "优先权窗", "due": past,
         "basis": "申请日"}])
    r = _route(tmp_path)
    assert any("已逾期" in n and "逾期 5 天" in n for n in r["notes"])


def test_route_patent_blocked_gate_named(tmp_path):
    make_patent(tmp_path, status="intake", blocked={
        "gate_id": "public_disclosure_block",
        "detail": "已公开非宽限", "fix_pointer": "见 light-patent P0"})
    r = _route(tmp_path)
    gates = [g for g in r["gates"] if g["stage"] == "patent"]
    assert len(gates) == 1
    assert gates[0]["family"] == "blocked_gate"
    assert "public_disclosure_block" in gates[0]["gate"]
    assert gates[0]["pointer"] == "见 light-patent P0"


def test_route_copyright_correcting_named(tmp_path):
    make_copyright(tmp_path, status="correcting", correction={
        "notice_date": "2026-10-15", "deadline": "2026-11-14",
        "items": ["补交签章页", "修正版本号"]})
    r = _route(tmp_path)
    named = [n for n in r["notes"] if "补正" in n]
    assert len(named) == 1
    assert "2026-11-14" in named[0] and "视为撤回" in named[0]


def test_route_exit_hints_after_review_delivered(tmp_path):
    make_literature(tmp_path)
    make_review(tmp_path, status="delivered")
    r = _route(tmp_path)
    notes = "\n".join(r["notes"])
    assert "light-patent" in notes and "出口层扩展位" in notes
    assert "light-software-copyright" in notes
    # 有案件时不再给「可启动」提示
    make_patent(tmp_path)
    make_copyright(tmp_path)
    r2 = _route(tmp_path)
    notes2 = "\n".join(r2["notes"])
    assert "可启动 light-patent" not in notes2
    assert "可启动 light-software-copyright" not in notes2


def test_extensions_do_not_change_mainline_route(tmp_path):
    # 扩展位在场（含熔断与专利门）不改变主线下一步与收官判定
    make_crawler(tmp_path, workspace_status="attention", targets=[
        {"target_id": "t-hot", "circuit_broken": True,
         "circuit_reason": "连续被拒", "precheck_status": "effective"}])
    r = _route(tmp_path)
    assert r["next"]["stage"] == "literature"
    assert r["done"] is False
