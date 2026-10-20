"""门三强度措辞门：英文超限/禁用、中文超限/禁用、哈希漂移重验口。"""

from pathlib import Path

from light_write.audit import gate_wording, reverify_claim
from light_write.intake import run_intake
from light_write.project import (
    init_package, load_package, save_manuscript,
)
from light_write.template_reg import register_template
from light_write.util import claim_text_hash, dump_json, dump_yaml
from conftest import make_record


def _codes(gate):
    return {f["code"] for f in gate.findings}


def _edit_section(root, fname, old, new):
    path = Path(root) / "sections" / fname
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_wording_en_exceeds_ceiling_with_suggestion(drafted_pkg):
    # C2 是 suggestive 档，"demonstrates" 须 strong 以上 → 超限并给出降格建议
    _edit_section(drafted_pkg["root"], "03-results.md",
                  "suggests a possible gain", "demonstrates a possible gain")
    pkg = load_package(drafted_pkg["root"])
    gate = gate_wording(pkg)
    assert gate.status == "fail"
    assert "wording.exceeds_ceiling" in _codes(gate)
    msg = next(f["message"] for f in gate.findings
               if f["code"] == "wording.exceeds_ceiling")
    assert "suggests" in msg  # 降格建议句式来自本档 allowed_terms


def test_wording_en_banned_term_rejected(drafted_pkg):
    _edit_section(drafted_pkg["root"], "01-introduction.md",
                  "Method A shows a clear improvement",
                  "Method A proves a clear improvement")
    pkg = load_package(drafted_pkg["root"])
    gate = gate_wording(pkg)
    assert gate.status == "fail"
    assert "wording.banned_term" in _codes(gate)


def test_wording_passes_on_fixture(drafted_pkg):
    pkg = load_package(drafted_pkg["root"])
    gate = gate_wording(pkg)
    assert gate.status == "pass", gate.findings
    assert gate.details["claim_sentences_checked"] == 2


# ---------------------------------------------------------------- 中文稿

def _zh_pkg(tmp_path, upstreams):
    root = tmp_path / "ms-zh"
    init_package(root, "中文测试稿", "zh")
    run_intake(root, upstreams["card"], upstreams["literature"])
    record_path = tmp_path / "record-zh.json"
    dump_json(record_path, make_record(language="zh"))
    register_template(root, record_path)
    return root


def _zh_section(root, text):
    (Path(root) / "sections" / "01-introduction.md").write_text(
        text, encoding="utf-8")
    pkg_data = load_package(root)
    pkg_data["manuscript"]["sections"] = [
        {"section_id": "S-introduction", "file": "01-introduction.md",
         "role": "introduction", "goal": "确立空白",
         "required_info": ["空白"], "claim_ids": []}]
    save_manuscript(root, pkg_data["manuscript"])


def test_wording_zh_banned_term(tmp_path, upstreams):
    root = _zh_pkg(tmp_path, upstreams)
    _zh_section(root, "本方法证明了处理流程的优越性 [claim:C1]。\n")
    gate = gate_wording(load_package(root))
    assert gate.status == "fail"
    assert "wording.banned_term" in _codes(gate)


def test_wording_zh_exceeds_and_passes(tmp_path, upstreams):
    root = _zh_pkg(tmp_path, upstreams)
    # C2 为 suggestive 档：「证实」须 strong 以上 → 超限
    _zh_section(root, "结果证实流程存在增益 [claim:C2]。\n")
    gate = gate_wording(load_package(root))
    assert gate.status == "fail"
    assert "wording.exceeds_ceiling" in _codes(gate)
    # 降格为本档词「提示」→ 过门
    _zh_section(root, "结果提示可能存在增益 [claim:C2]。\n")
    gate = gate_wording(load_package(root))
    assert gate.status == "pass", gate.findings


# ---------------------------------------------------------------- 哈希漂移

def test_wording_hash_drift_blocks_until_reverified(drafted_pkg):
    root = drafted_pkg["root"]
    pkg_data = load_package(root)
    claims = pkg_data["claims"]
    row = next(r for r in claims["claims"] if r["claim_id"] == "C1")
    row["claim_text"] = "Method A outperforms the baseline by a wide margin."
    # 只改文本不更新哈希 → 漂移（validate 也会报，此处测门三的重验口）
    dump_yaml(root / "claims_register.yaml", claims)
    gate = gate_wording(load_package(root))
    assert gate.status == "fail"
    assert "wording.hash_drift_unreverified" in _codes(gate)
    result = reverify_claim(root, "C1", by="tester")
    assert result["text_hash"] == claim_text_hash(row["claim_text"])
    gate = gate_wording(load_package(root))
    assert "wording.hash_drift_unreverified" not in _codes(gate)
