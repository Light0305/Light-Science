"""simhash 跨 run 近重检测（第五批，PLAN §13 P1）。

口径钉：命中只标记不处置——内容照常落盘、provenance 照常落账、
事件点名来源 run 与实际距离与生效阈值；精确层（请求指纹
duplicate_skipped / 内容寻址）与本层互不替代。
距离数字为算法标定值（sha256 特征哈希、无随机源，跨平台恒定）：
多样化词汇 126 词文本改 2 词距离 3、无关文本距离 28。
"""

import json

import pytest
from conftest import make_reg

from light_crawler import fetch as fetch_mod
from light_crawler import precheck as pc
from light_crawler import project, schema, simhash, storage

NO_SLEEP = lambda s: None  # noqa: E731

TEXT_A = (
    "the trial measured feed intake growth performance and body weight "
    "gain across twelve pens during winter automated video tracking "
    "recorded posture changes feeding visits drinking events and "
    "locomotion scores hourly statistical analysis used mixed models "
    "with pen as random effect and treatment diet as fixed factor "
    "levels results showed significant improvements in average daily "
    "gain for the supplemented group compared with control animals "
    "farm staff validated sensor readings manually each morning "
    "before the first feeding round began in the barn weather data "
    "including temperature humidity and ventilation rates were logged "
    "by the building management system the ethics committee approved "
    "the protocol under institutional guidelines for livestock "
    "research conducted on site samples of blood and faeces were "
    "collected fortnightly and analysed for metabolic markers and "
    "parasite burden")
TEXT_B = TEXT_A.replace("winter", "summer").replace("hourly", "nightly")
TEXT_FAR = (
    "quantum entanglement experiments require cryogenic isolation "
    "chambers superconducting magnets photon detectors and extremely "
    "stable laser sources calibrated against atomic clocks in "
    "underground laboratories shielded from seismic noise and "
    "electromagnetic interference fields")


# ---------------------------------------------------------------- 单元层

def test_simhash_deterministic_and_local():
    a, b, far = (simhash.simhash64(t) for t in (TEXT_A, TEXT_B, TEXT_FAR))
    assert simhash.hamming(a, a) == 0
    assert 0 < simhash.hamming(a, b) <= 3          # 改 2 词：近
    assert simhash.hamming(a, far) >= 20           # 无关：远（误报反例）
    assert simhash.simhash64("") == 0
    assert simhash.simhash64("   ") == 0


def test_find_match_threshold_and_exact_exclusion(tmp_path):
    simhash.record_fingerprint(
        tmp_path, text=TEXT_A, prov_id="pv-1", target_id="t1",
        run_id="run-1", url="http://x/a")
    # 与库中文本全同：归精确层，本层不报
    assert simhash.find_match(tmp_path, TEXT_A, 64) is None
    # 距离 3：阈值 2 不命中、阈值 3 命中且逐项点名
    assert simhash.find_match(tmp_path, TEXT_B, 2) is None
    hit = simhash.find_match(tmp_path, TEXT_B, 3)
    assert hit["hamming_distance"] == 3
    assert hit["row"]["prov_id"] == "pv-1"
    assert hit["row"]["run_id"] == "run-1"
    assert hit["matches_within_threshold"] == 1
    # 无关文本在默认阈值下不命中（误报反例）
    assert simhash.find_match(tmp_path, TEXT_FAR, 3) is None
    # 空文本永不参与判定
    assert simhash.find_match(tmp_path, "", 64) is None


def test_fingerprint_store_roundtrip(tmp_path):
    row = simhash.record_fingerprint(
        tmp_path, text=TEXT_A, prov_id="pv-9", target_id="t2",
        run_id="run-9", url="http://x/b", kind="manual_import")
    rows = simhash.load_fingerprints(tmp_path)
    assert rows == [row]
    assert len(row["simhash"]) == 16
    assert row["text_sha256"] == storage.sha256_bytes(
        TEXT_A.encode("utf-8"))


# ---------------------------------------------------------------- 集成层

def _ready(ws, base, **kw):
    reg = make_reg(base, **kw)
    project.register_target(ws, reg)
    rec = pc.run_precheck(ws, reg["target_id"])
    assert rec["status"] == "effective"
    return reg["target_id"]


def _transport(bodies):
    def t(url, headers=None):
        body = bodies[url]
        return fetch_mod.Response(
            200, {"Content-Type": "text/plain; charset=utf-8"},
            body.encode("utf-8"), url)
    return t


def test_cross_run_near_duplicate_detected_and_content_kept(ws, site):
    _, base = site
    tid = _ready(ws, base)
    url = base + "/data.json"  # 路径只作已见集键，内容由注入传输给
    r1 = fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_A}),
        sleep=NO_SLEEP)
    assert r1["stored"] == 1 and r1["near_duplicates"] == 0
    assert len(simhash.load_fingerprints(ws)) == 1

    # 站方小改后重取（refetch_seen 只放增量跳过，不绕任何合规门）
    r2 = fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_B}),
        sleep=NO_SLEEP, refetch_seen=True)
    # 只标记不处置：内容照常落盘、计数如实
    assert r2["stored"] == 1 and r2["near_duplicates"] == 1
    prov = [r for r in storage.read_provenance(ws) if r["kind"] == "fetch"]
    assert len(prov) == 2

    ev = [e for e in project.read_events(ws)
          if e["type"] == "near_duplicate_detected"]
    assert len(ev) == 1
    data = ev[0]["data"]
    assert data["matched_run_id"] == r1["run_id"]       # 点名来源 run
    assert data["matched_prov_id"] == prov[0]["prov_id"]
    assert data["hamming_distance"] == 3
    assert data["hamming_threshold"] == 3               # 生效阈值留痕
    assert data["prov_id"] == prov[1]["prov_id"]

    cleaned = json.loads(
        (ws / prov[1]["cleaned_path"]).read_text("utf-8"))
    note = cleaned["near_duplicate_cross_run"]
    assert note["matched_run_id"] == r1["run_id"]
    assert note["hamming_threshold"] == 3
    assert len(simhash.load_fingerprints(ws)) == 2


def test_unrelated_content_no_false_positive(ws, site):
    _, base = site
    tid = _ready(ws, base)
    url = base + "/data.json"
    fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_A}),
        sleep=NO_SLEEP)
    r2 = fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_FAR}),
        sleep=NO_SLEEP, refetch_seen=True)
    assert r2["near_duplicates"] == 0
    assert not [e for e in project.read_events(ws)
                if e["type"] == "near_duplicate_detected"]


def test_threshold_override_widens_detection(ws, site):
    _, base = site
    tid = _ready(ws, base,
                 near_duplicate={"hamming_threshold": 1})
    url = base + "/data.json"
    fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_A}),
        sleep=NO_SLEEP)
    r2 = fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_B}),
        sleep=NO_SLEEP, refetch_seen=True)
    # 距离 3 > 登记阈值 1：不命中（阈值确实由登记裁决，不是写死）
    assert r2["near_duplicates"] == 0


def test_near_duplicate_disabled_target_opts_out(ws, site):
    _, base = site
    tid = _ready(ws, base, near_duplicate={"enabled": False})
    url = base + "/data.json"
    fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_A}),
        sleep=NO_SLEEP)
    fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_B}),
        sleep=NO_SLEEP, refetch_seen=True)
    assert simhash.load_fingerprints(ws) == []   # 不比对也不入库
    assert not [e for e in project.read_events(ws)
                if e["type"] == "near_duplicate_detected"]


def test_import_participates_in_fingerprint_library(ws, site, tmp_path):
    _, base = site
    tid = _ready(ws, base)
    url = base + "/data.json"
    fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_A}),
        sleep=NO_SLEEP)
    f = tmp_path / "export.txt"
    f.write_text(TEXT_B, encoding="utf-8")
    prov = fetch_mod.import_file(ws, tid, str(f), "合法导出", "测试员")
    assert prov["kind"] == "manual_import"
    rows = simhash.load_fingerprints(ws)
    assert len(rows) == 2 and rows[1]["kind"] == "manual_import"
    ev = [e for e in project.read_events(ws)
          if e["type"] == "near_duplicate_detected"]
    assert len(ev) == 1 and ev[0]["data"]["prov_id"] == prov["prov_id"]


def test_cli_fingerprints_lists_library(ws, site, capsys):
    from light_crawler import cli
    _, base = site
    tid = _ready(ws, base)
    url = base + "/data.json"
    fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_A}),
        sleep=NO_SLEEP)
    assert cli.main(["--root", str(ws), "fingerprints"]) == 0
    out = capsys.readouterr().out
    assert "共 1 条指纹" in out
    assert cli.main(
        ["--root", str(ws), "fingerprints", "--target", "ghost"]) == 0
    out = capsys.readouterr().out
    assert "共 0 条指纹" in out


def test_exact_duplicate_request_still_skips(ws, site):
    # 精确层口径不被本层动摇：同 URL 未要求重取时仍 duplicate_skipped
    _, base = site
    tid = _ready(ws, base)
    url = base + "/data.json"
    fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_A}),
        sleep=NO_SLEEP)
    r2 = fetch_mod.fetch_run(
        ws, tid, urls=[url], transport=_transport({url: TEXT_B}),
        sleep=NO_SLEEP)
    assert r2["duplicates"] == 1 and r2["stored"] == 0
    assert schema.DEFAULT_NEAR_DUP_HAMMING_THRESHOLD == 3
    assert not [e for e in project.read_events(ws)
                if e["type"] == "near_duplicate_detected"]
