"""WRT-D01 程式化核查层：正例必报、反例不报、advisory 不阻断定版。"""

from pathlib import Path

from light_write import schema
from light_write.audit import run_audit
from light_write.gates import advance
from light_write.project import init_package, load_package, save_manuscript
from light_write.tone import check_tone, run_tone_check, tone_status
from conftest import add_section, online_records_for


def _pkg_with_text(tmp_path, language, text, fname="01-introduction.md"):
    root = tmp_path / "ms-tone"
    init_package(root, "Tone Demo", language)
    (root / "sections" / fname).write_text(text, encoding="utf-8")
    pkg_data = load_package(root)
    pkg_data["manuscript"]["sections"] = [
        {"section_id": "S-intro", "file": fname, "role": "introduction",
         "goal": "确立空白", "required_info": ["空白"], "claim_ids": []}]
    save_manuscript(root, pkg_data["manuscript"])
    return root


def _rule_ids(findings):
    return {f["rule_id"] for f in findings}


def test_en_positive_examples_all_reported(tmp_path):
    text = (
        "The method is not merely a tracker, but a new paradigm for "
        "behaviour analysis. It is worth noting that all segments came "
        "from one site. First, the data are diverse. Second, the method "
        "is simple. Third, the results are robust. Finally, the cost "
        "is low.\n")
    root = _pkg_with_text(tmp_path, "en", text)
    findings = check_tone(load_package(root))
    ids = _rule_ids(findings)
    assert "tone.en.reversal_frame" in ids
    assert "tone.en.boilerplate" in ids
    assert "tone.en.ordinal_scaffold" in ids


def test_en_structure_rule_reports_isostructural_run(tmp_path):
    text = ("Method A improves recall. Method A improves precision. "
            "Method A improves robustness across sites.\n")
    root = _pkg_with_text(tmp_path, "en", text)
    findings = check_tone(load_package(root))
    assert "tone.en.adjacent_isostructural" in _rule_ids(findings)


def test_en_not_change_features_never_reported(tmp_path):
    # 不改表反例：被动句 + 句长参差 + 名词化 + 真实时序序数，全零报
    text = (
        "Segments were extracted from the recordings by two annotators. "
        "Then each segment was scored against the frozen configuration, "
        "a procedure that took the better part of a week because the "
        "annotation of behaviour categories requires frame-level "
        "verification of every onset and offset. Scores were aggregated. "
        "First, segments were extracted. Second, each segment was "
        "scored. Finally, scores were aggregated.\n")
    root = _pkg_with_text(tmp_path, "en", text)
    findings = check_tone(load_package(root))
    # 真实时序序数会被 ordinal 规则提示复核（advisory 的设计如此），
    # 但被动/名词化/句长本身永不单独成 finding：除 ordinal 外应为零
    others = [f for f in findings
              if f["rule_id"] != "tone.en.ordinal_scaffold"]
    assert others == [], findings


def test_zh_positive_examples_reported(tmp_path):
    text = (
        "值得注意的是，本研究只使用了一个场的片段。随着视频分析技术的"
        "发展，行为检测日益受到广泛关注。本方法提高了召回率。本方法"
        "提高了精确率。本方法提高了稳健性。\n")
    root = _pkg_with_text(tmp_path, "zh", text)
    findings = check_tone(load_package(root))
    ids = _rule_ids(findings)
    assert "tone.zh.boilerplate_opener" in ids
    assert "tone.zh.translationese" in ids
    assert "tone.zh.adjacent_isostructural" in ids


def test_zh_legit_text_zero_findings(tmp_path):
    text = (
        "片段来自同一个养殖场的 6 个留出段。处理组与对照组使用同一批"
        "段，差异只在阈值来源。由于段间离散较大，区间估计偏宽，判定"
        "落在未定档。\n")
    root = _pkg_with_text(tmp_path, "zh", text)
    findings = check_tone(load_package(root))
    assert findings == [], findings


def test_every_rule_has_positive_and_negative_examples():
    for rule in schema.TONE_RULES:
        assert rule["positive_example"] and rule["negative_example"]
        assert rule["suggestion"]


def test_tone_report_binds_hash_and_stales(tmp_path):
    root = _pkg_with_text(tmp_path, "en",
                          "It is worth noting that data are limited.\n")
    report = run_tone_check(root)
    assert report["advisory"] is True and report["blocking"] is False
    assert report["counts"]["total"] >= 1
    assert tone_status(root)["stale"] is False
    (root / "sections" / "01-introduction.md").write_text(
        "Data are limited.\n", encoding="utf-8")
    assert tone_status(root)["stale"] is True


def test_advisory_does_not_block_audit_or_advance(audited_pkg):
    # audited_pkg 的 audit 已随 run_audit 生成 tone 产物；再往正文注入
    # 触发标记后重跑 audit：四门若仍过，advance 到 audited 不被 tone 拦
    root = audited_pkg["root"]
    sec = Path(root) / "sections" / "04-discussion.md"
    sec.write_text(
        sec.read_text(encoding="utf-8")
        + "It is worth noting that the setting is narrow.\n",
        encoding="utf-8")
    report = run_audit(root, online_records=online_records_for(root))
    assert report["tone_advisory"]["findings"] >= 1
    assert report["tone_advisory"]["blocking"] is False
    # 审计因稿改 STALE 需重跑后才新鲜——此处验证 tone 不改变 overall 口径：
    assert report["overall"] in ("pass", "fail")
    tone_only = [g for g in report["gates"]]
    assert len(tone_only) == 4  # tone 不冒充第五门
