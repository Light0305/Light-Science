"""程式化核查层（WRT-D01，advisory 先行）：只报不改、不阻断定版。

位置在审计四门之后、submission_ready 之前，与措辞门分开记账：
措辞门管强度诚实（硬门），本层管成稿的程式化与 AI 味（建议层，
积累自家数据后再议硬度）。纪律：
- 规则只收可定位触发标记（schema.TONE_RULES，逐条带正反例）；
  不改表（schema.TONE_NOT_CHANGE）所列特征永不作报警依据。
- 信息守恒：本层只产报告与改写建议，建议不许删限定词；工具永不
  自动改稿（与约束 14 no-overreach 一致）。
- 不设 AI 检测器分数（约束 10）：报告只有触发标记的定位与计数。
- 产物落 audit/tone_report.json + audit/gate-tone.md，绑稿件哈希；
  稿改后报告内哈希与当前稿不一致即为过期（stale 字段自检）。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .project import load_package, manuscript_hash, section_files
from .util import dump_json, today, utcnow
from .validate import CITE_RE, CLAIM_MARK_RE, NUM_MARK_RE

TONE_REPORT_NAME = "tone_report.json"
TONE_MD_NAME = "gate-tone.md"

# 中文句末标点后通常无空格：CJK 标点按零宽断句，ASCII 标点仍要求空白/换行
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？])\s*|(?<=[.!?])\s+|\n+")
_EN_ORDINALS = ["first", "firstly", "second", "secondly", "third",
                "thirdly", "finally"]
_ZH_ORDINALS = ["首先", "其次", "再次", "最后", "第一", "第二", "第三"]


class ToneError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _plain(sentence: str) -> str:
    s = CLAIM_MARK_RE.sub("", sentence)
    s = NUM_MARK_RE.sub("", s)
    s = CITE_RE.sub("", s)
    return s.strip()


def _sentences(text: str) -> list:
    return [c.strip() for c in _SENTENCE_SPLIT_RE.split(text) if c.strip()]


def _finding(rule, fname, excerpt):
    return {
        "rule_id": rule["rule_id"], "rule_name": rule["name"],
        "file": fname, "excerpt": excerpt[:120],
        "suggestion": rule["suggestion"],
    }


def _check_pattern_rule(rule, fname, sentences, findings):
    pats = [re.compile(p, re.IGNORECASE) for p in rule["patterns"]]
    for s in sentences:
        plain = _plain(s)
        if any(p.search(plain) for p in pats):
            findings.append(_finding(rule, fname, plain))


def _check_ordinal_rule(rule, fname, sentences, findings):
    tokens = _ZH_ORDINALS if rule["language"] == "zh" else _EN_ORDINALS
    seen = []
    for s in sentences:
        plain = _plain(s)
        if rule["language"] == "zh":
            head = plain[:2]
            if head in tokens and head not in seen:
                seen.append(head)
        else:
            m = re.match(r"([A-Za-z]+)\b", plain)
            if m and m.group(1).lower() in tokens \
                    and m.group(1).lower() not in seen:
                seen.append(m.group(1).lower())
    if len(seen) >= 3:
        findings.append(_finding(
            rule, fname,
            f"序数脚手架成串：{'/'.join(seen)}（{len(seen)} 个序数开篇）"))


# 英文学术正文的默认主语（功能词）开篇不携带同构信号（WRT-D02 语料
# 对照实测：已发表论文中 The/We/This 开篇连排是常态而非模板痕迹）
_EN_FUNCTION_OPENERS = {"the", "we", "this", "it", "these", "those",
                        "there", "a", "an", "in", "on", "for", "with",
                        "by", "as", "our", "their", "its"}


def _opener_key(rule, sentence: str):
    """同构检出的开篇键；非正文行与功能词开篇 → None（断路，不计）。

    非正文行 = markdown 结构行（引用块/标题/列表/表格）与以年份起首
    的参考文献条目——语料形态而非行文（D02 对照实测的伪命中来源）。
    """
    plain = _plain(sentence)
    if not plain or plain[0] in ">#*|-" \
            or re.match(r"(19|20)\d{2}\b", plain):
        return None
    if rule["language"] == "zh":
        return plain[:2]
    m = re.match(r"([A-Za-z]+)\b", plain)
    if not m:
        return None
    word = m.group(1).lower()
    return None if word in _EN_FUNCTION_OPENERS else word


def _check_structure_rule(rule, fname, sentences, findings):
    keys = [_opener_key(rule, s) for s in sentences]
    runs = []
    i = 0
    while i < len(keys):
        if not keys[i]:
            i += 1
            continue
        j = i
        while j < len(keys) and keys[j] == keys[i]:
            j += 1
        if j - i >= 3:
            runs.append((i, j - i, keys[i]))
        i = j
    for start, length, key in runs:
        findings.append(_finding(
            rule, fname,
            f"连续 {length} 句以「{key}」开篇同构推进"
            f"（起句：{_plain(sentences[start])[:60]}）"))


_CHECKERS = {"pattern": _check_pattern_rule, "ordinal": _check_ordinal_rule,
             "structure": _check_structure_rule}


def check_tone_texts(language, texts: dict) -> list:
    """对 {文件名: 文本} 跑程式化核查（稿件包与外部语料共用同一实现）。"""
    rules = [r for r in schema.TONE_RULES if r["language"] == language]
    findings = []
    for fname, text in texts.items():
        sentences = _sentences(text)
        for rule in rules:
            _CHECKERS[rule["kind"]](rule, fname, sentences, findings)
    return findings


def check_tone(pkg) -> list:
    """对稿件包全部节文件跑程式化核查，返回 findings（不落盘）。"""
    language = (pkg["manuscript"] or {}).get("language")
    return check_tone_texts(language, section_files(pkg["root"]))


def run_tone_check(root) -> dict:
    """生成 tone_report 产物（audit/tone_report.json + gate-tone.md）。"""
    root = Path(root)
    pkg = load_package(root)
    if pkg["manuscript"] is None:
        raise ToneError(["稿件包不存在（先 init）"])
    findings = check_tone(pkg)
    current_hash = manuscript_hash(root)
    by_rule = {}
    for f in findings:
        by_rule[f["rule_id"]] = by_rule.get(f["rule_id"], 0) + 1
    report = {
        "kind": "light-write/tone-report",
        "version": "1.1",
        "advisory": True,
        "blocking": False,
        "manuscript_id": pkg["manuscript"].get("manuscript_id"),
        "manuscript_hash": current_hash,
        "generated_at": utcnow(),
        "generated_date": today(),
        "language": pkg["manuscript"].get("language"),
        "rules_applied": [r["rule_id"] for r in schema.TONE_RULES
                          if r["language"]
                          == pkg["manuscript"].get("language")],
        "not_change_table": schema.TONE_NOT_CHANGE,
        "findings": findings,
        "counts": {"total": len(findings), "by_rule": by_rule},
        "note": "程式化核查为建议层（advisory）：只报不改、不阻断定版；"
                "改写须守信息守恒（不许删限定词）；不改表所列特征永不"
                "作报警依据；本报告不含任何 AI 检测器分数（约束 10）",
    }
    audit_dir = root / "audit"
    audit_dir.mkdir(exist_ok=True)
    dump_json(audit_dir / TONE_REPORT_NAME, report)
    (audit_dir / TONE_MD_NAME).write_text(
        _render_tone_md(report), encoding="utf-8")
    return report


def _render_tone_md(report) -> str:
    lines = ["# 程式化核查（advisory · 只报不改）", "",
             f"- 稿件哈希：`{report['manuscript_hash'][:16]}…`",
             f"- 判定性质：建议层，不阻断定版；findings 共 "
             f"{report['counts']['total']} 处",
             f"- 时间：{report['generated_at']}", "",
             "## Findings", ""]
    if not report["findings"]:
        lines.append("（无触发标记命中）")
    for f in report["findings"]:
        lines.append(f"- `{f['rule_id']}` {f['file']}：{f['excerpt']}")
        lines.append(f"  建议：{f['suggestion']}")
    lines += ["", "## 不改表（永不作报警依据）", ""]
    for row in report["not_change_table"]:
        lines.append(f"- {row['feature']}：{row['note']}")
    lines.append("")
    return "\n".join(lines)


def tone_status(root) -> dict:
    """tone 报告状态：{exists, stale, findings}（stale = 哈希漂移）。"""
    from .util import load_structured

    path = Path(root) / "audit" / TONE_REPORT_NAME
    if not path.exists():
        return {"exists": False, "stale": None, "findings": None}
    report = load_structured(path)
    return {
        "exists": True,
        "stale": report.get("manuscript_hash") != manuscript_hash(root),
        "findings": (report.get("counts") or {}).get("total"),
        "advisory": True,
    }
