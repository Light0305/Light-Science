"""校验器：稿件包全部纪律的确定性核查（只出判定，不改文件）。

分级口径：error = 成稿纪律被破（fail-closed，约束 15）；warning = 须落字
说明或复核的风险（如手写作者-年份串、模板记录过期）。检查者三纪律
（约束 14）：honest-unverified（没查的写没查）、no-false-positive
（容差层在 schema.FIELD_TOLERANCES，Phase 2 执行）、no-overreach
（本校验器只判登记与形态，不评研究设计）。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import schema
from .project import (
    FILES, contract_content_hash, load_package, manuscript_hash,
    section_files,
)
from .render import lock_entries_hash, render_bib
from .util import (
    claim_text_hash, component_hash, load_structured, sha256_file,
)

CITE_RE = re.compile(r"\[@([^\]]+)\]")
CLAIM_MARK_RE = re.compile(r"\[claim:([A-Za-z0-9_-]+)\]")
NUM_MARK_RE = re.compile(r"\[num:([A-Za-z0-9_-]+)\]")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\])}>\"']+")
ETAL_YEAR_RE = re.compile(r"et al\.,?\s*\(?\s*(?:19|20)\d{2}\s*\)?")
AUTHYEAR_RE = re.compile(
    r"\b[A-Z][A-Za-z-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z-]+)?\s*\((?:19|20)\d{2}\)")


def _issue(level, code, message, where=None):
    return {"level": level, "code": code, "message": message, "where": where}


class Report:
    def __init__(self):
        self.issues = []

    def error(self, code, message, where=None):
        self.issues.append(_issue("error", code, message, where))

    def warning(self, code, message, where=None):
        self.issues.append(_issue("warning", code, message, where))

    @property
    def errors(self):
        return [i for i in self.issues if i["level"] == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i["level"] == "warning"]

    @property
    def ok(self):
        return not self.errors


# ------------------------------------------------------------ 模板记录

def check_template_record(record, rep: Report, today_date=None):
    """模板核查记录九组完整性校验（草案 §四 + 纠错 11(e)(f)）。"""
    today_date = today_date or date.today()
    if not isinstance(record, dict):
        rep.error("template.not_object", "模板核查记录须为 {A..I 分组} 对象")
        return
    for group_id, spec in schema.TEMPLATE_GROUPS.items():
        group = record.get(group_id)
        if not isinstance(group, dict):
            rep.error("template.group_missing",
                      f"模板记录缺 {group_id} 组（{spec['name']}）",
                      where=f"template.{group_id}")
            continue
        for field in spec["required"]:
            if group.get(field) in (None, "", []):
                rep.error("template.field_missing",
                          f"模板记录 {group_id} 组缺必填字段 {field}",
                          where=f"template.{group_id}.{field}")
        if spec.get("at_least_one"):
            present = [f for f in spec["fields"] if group.get(f) is not None]
            if not present:
                rep.error("template.limits_empty",
                          f"模板记录 {group_id} 组（限额）无任何限额字段",
                          where=f"template.{group_id}")
            for f in present:
                if not isinstance(group[f], (int, float)) or isinstance(group[f], bool):
                    rep.error("template.limit_not_numeric",
                              f"模板记录限额字段 {f} 须为数值，实为 {group[f]!r}",
                              where=f"template.D.{f}")
    group_b = record.get("B") or {}
    if group_b.get("format_track") and \
            group_b["format_track"] not in schema.FORMAT_TRACKS:
        rep.error("template.format_track",
                  f"format_track {group_b['format_track']!r} 不在 {schema.FORMAT_TRACKS}")
    group_a = record.get("A") or {}
    if group_a.get("journal_language") and \
            group_a["journal_language"] not in schema.LANGUAGES:
        rep.error("template.language",
                  f"journal_language {group_a['journal_language']!r} 不在 {schema.LANGUAGES}")
    group_g = record.get("G") or {}
    ai = group_g.get("ai_policy")
    if isinstance(ai, dict):
        for field in schema.TEMPLATE_GROUPS["G"]["ai_policy_required"]:
            if ai.get(field) is None:
                rep.error("template.ai_policy_field",
                          f"AI 政策组缺子字段 {field}", where="template.G.ai_policy")
        if ai.get("disclosure_required"):
            positions = ai.get("disclosure_positions")
            if not positions or not isinstance(positions, list):
                rep.error("template.ai_disclosure_positions",
                          "AI 政策要求披露但 disclosure_positions 为空"
                          "（披露位置须多值落字，如 Methods/Acknowledgments/图注）",
                          where="template.G.ai_policy")
            if not ai.get("disclosure_title") and not ai.get("disclosure_wording_template"):
                rep.warning("template.ai_disclosure_wording",
                            "AI 政策要求披露但无规定声明标题与措辞模板字段"
                            "（Elsevier/MDPI 型期刊有规定口径，宜补）",
                            where="template.G.ai_policy")
        decls = group_g.get("declarations")
        if isinstance(decls, list):
            for d in decls:
                if not isinstance(d, dict) or not d.get("type") or "position" not in d:
                    rep.error("template.declaration_shape",
                              "声明清单条目须含 {type, required, position, field_name}",
                              where="template.G.declarations")
    group_h = record.get("H") or {}
    verified_at = group_h.get("verified_at")
    if verified_at:
        try:
            vdate = date.fromisoformat(str(verified_at)[:10])
            cycle = group_h.get("review_cycle_days") or schema.TEMPLATE_EXPIRY_DEFAULT_DAYS
            age = (today_date - vdate).days
            if age > cycle:
                rep.warning("template.expired",
                            f"模板记录已过期：核查日期 {vdate}，距今 {age} 天 "
                            f"> 复核周期 {cycle} 天，消费前须重新核查",
                            where="template.H.verified_at")
        except ValueError:
            rep.error("template.verified_at_format",
                      f"verified_at {verified_at!r} 不是 ISO 日期")
    group_i = record.get("I") or {}
    if group_i.get("redistribution") and \
            group_i["redistribution"] not in schema.REDISTRIBUTION_VALUES:
        rep.error("template.redistribution",
                  f"redistribution {group_i['redistribution']!r} 不在词表")
    if group_h.get("bundled") and group_h["bundled"] not in schema.BUNDLED_VALUES:
        rep.error("template.bundled",
                  f"bundled {group_h['bundled']!r} 不在 {schema.BUNDLED_VALUES}（库存诚实）")


def template_record_expired(record, today_date=None) -> bool:
    today_date = today_date or date.today()
    group_h = (record or {}).get("H") or {}
    verified_at = group_h.get("verified_at")
    if not verified_at:
        return True
    try:
        vdate = date.fromisoformat(str(verified_at)[:10])
    except ValueError:
        return True
    cycle = group_h.get("review_cycle_days") or schema.TEMPLATE_EXPIRY_DEFAULT_DAYS
    return (today_date - vdate).days > cycle


# ------------------------------------------------------------ 主校验

def validate_package(root) -> dict:
    root = Path(root)
    rep = Report()
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        rep.error("package.missing", "稿件包不存在（manuscript.yaml 缺失）")
        return _finish(rep)

    language = manuscript.get("language")
    if language not in schema.LANGUAGES:
        rep.error("manuscript.language",
                  f"manuscript.language {language!r} 必填且须 ∈ {schema.LANGUAGES}"
                  "（语言按目标期刊定，一篇稿一个语言）")

    _check_intake(root, pkg, rep)
    _check_claims(pkg, rep, language)
    _check_lock_and_bib(root, pkg, rep)
    _check_sections(pkg, rep)
    _check_numbers_figures_checklist(pkg, rep)
    _check_declarations_uselog(manuscript, rep)
    _check_template(pkg, rep)
    _check_contract(pkg, rep)
    _check_audit_freshness(root, pkg, rep)
    _check_supplement(pkg, rep)
    return _finish(rep)


def _check_supplement(pkg, rep: Report):
    """补课 D 采纳项的校验面（deep-read-D-supplement）。

    D-W02 术语账 / D-W01 正文分配 / D-W13 标记纯度（经 ledger 模块）、
    D-W04 use_log 风险分级、D-W07 作者完整性门、D-W08 数据集映射、
    D-W09 清单 stage/适用性词表、D-W11 承重陈述保护。
    """
    from .ledger import allocation_check, scan_markers, terminology_check

    for issue in terminology_check(pkg) + allocation_check(pkg):
        (rep.error if issue["level"] == "error" else rep.warning)(
            issue["code"], issue["message"], issue.get("where"))
    markers = scan_markers(pkg)
    for u in markers["unknown"]:
        rep.error("markers.unregistered",
                  f"节 {u['section']} 出现未注册标记 {u['marker']}："
                  "草稿标记分工见 schema.DRAFT_MARKERS（D-W13）",
                  u["section"])
    manuscript = pkg["manuscript"]
    # D-W04：风险分级——prohibited 直接禁（不是披露能洗的）；
    # evaluative_interpretive 须强人类核验落字
    for i, entry in enumerate(manuscript.get("use_log") or []):
        tier = entry.get("risk_tier")
        if tier is None:
            continue
        where = f"use_log[{i}]"
        if tier not in schema.RISK_TIERS:
            rep.error("use_log.risk_tier_vocab",
                      f"risk_tier {tier!r} 不在 {schema.RISK_TIERS}", where)
        elif tier == "prohibited":
            rep.error("use_log.prohibited",
                      "该 AI 使用属 prohibited 级（代写核心论证/未核查引用"
                      "数据入稿/未发表材料上传公共模型等）：流程上直接禁，"
                      "披露不能洗（D-W04）", where)
        elif tier == "evaluative_interpretive" and not entry.get("human_verified"):
            rep.error("use_log.evaluative_unverified",
                      "evaluative_interpretive 级使用（解释结果/回复框架/"
                      "统计解释）须有强人类核验落字 human_verified（D-W04）",
                      where)
    # D-W07：作者完整性门——禁从 et al. 显示串推导，缺名停生成（可留痕覆盖）
    for e in (pkg["lock"] or {}).get("entries") or []:
        if e.get("authors_complete") is False and not e.get("author_override"):
            rep.error("lock.authors_incomplete",
                      f"lock 条目 {e.get('entry_id')} 作者名单不完整"
                      "（authors_complete=false）：必须取结构化源的完整有序"
                      "名单，禁从 et al. 推导；紧急覆盖须落 author_override"
                      "并把警告写进记录（D-W07）", e.get("entry_id"))
    # D-W08：数据可用性声明的 dataset→location 映射与访问路径分类
    decls = manuscript.get("declarations") or {}
    da = decls.get("data_availability") or {}
    datasets = manuscript.get("datasets") or []
    if da.get("state") == "present" and not datasets:
        rep.warning("datasets.mapping_missing",
                    "数据可用性声明已 present 但 manuscript.datasets 为空："
                    "声明须按 dataset→location 显式映射写（D-W08）")
    for i, d in enumerate(datasets):
        where = f"datasets[{i}]"
        if d.get("access_path") not in schema.ACCESS_PATHS:
            rep.error("datasets.access_path_vocab",
                      f"access_path {d.get('access_path')!r} 不在七路分类 "
                      f"{schema.ACCESS_PATHS}", where)
        if not d.get("location"):
            rep.warning("datasets.no_location",
                        "数据集缺 location：声明映射须显式（D-W08）", where)
        if d.get("access_path") == "justified_request" and not d.get("restriction"):
            rep.warning("datasets.weak_request",
                        "justified_request（available upon request）无具体法律/"
                        "伦理/商业限制落字：弱声明待改（D-W08）", where)
    # D-W09：清单 stage / applicability 词表
    for item in (pkg["checklist"] or {}).get("items") or []:
        if item.get("stage") is not None and \
                item["stage"] not in schema.CHECKLIST_STAGES:
            rep.error("checklist.stage_vocab",
                      f"清单条目 {item.get('item_id')} stage {item['stage']!r} "
                      f"不在 {schema.CHECKLIST_STAGES}（规则不许跨阶段套用）",
                      item.get("item_id"))
        if item.get("applicability") is not None and \
                item["applicability"] not in schema.APPLICABILITY:
            rep.error("checklist.applicability_vocab",
                      f"清单条目 {item.get('item_id')} applicability "
                      f"{item['applicability']!r} 不在 {schema.APPLICABILITY}",
                      item.get("item_id"))
    # D-W11：承重陈述保护——登记的承重句须在登记节中实存（删/移即报错）
    from .project import section_files
    files = section_files(pkg["root"])
    by_id = {s.get("section_id"): files.get(s.get("file"), "")
             for s in manuscript.get("sections") or []}
    for i, ps in enumerate(manuscript.get("protected_statements") or []):
        where = f"protected_statements[{i}]"
        if ps.get("kind") not in schema.PROTECTED_KINDS:
            rep.error("protected.kind_vocab",
                      f"承重陈述 kind {ps.get('kind')!r} 不在保护清单词表",
                      where)
        snippet = ps.get("snippet") or ""
        if not snippet or snippet not in by_id.get(ps.get("section"), ""):
            rep.error("protected.missing",
                      "承重陈述在登记节中找不到：已被删除或移位——姿态/压缩/"
                      "返修编辑只许移位、只述一次、改写为正向 scope，不许删"
                      "（D-W11 承重保护）", where)


def _finish(rep: Report) -> dict:
    return {
        "ok": rep.ok,
        "errors": rep.errors,
        "warnings": rep.warnings,
        "error_count": len(rep.errors),
        "warning_count": len(rep.warnings),
    }


def _check_intake(root, pkg, rep: Report):
    manuscript = pkg["manuscript"]
    intake = manuscript.get("intake")
    if not intake:
        rep.warning("intake.missing", "尚未 intake：承接快照为空（承接规程见 SKILL §2）")
        return
    card_info = (intake.get("conclusion_card") or {})
    card_path = card_info.get("path")
    if card_path:
        if not Path(card_path).exists():
            rep.error("intake.card_missing",
                      f"承接的 conclusion_card 已不存在：{card_path}")
        elif sha256_file(card_path) != card_info.get("sha256"):
            rep.error("intake.card_hash_drift",
                      "conclusion_card 文件哈希与承接快照不符：上游变动后"
                      "承接失效，须重新 intake（不许静默沿用旧快照）")
    lit = intake.get("literature") or {}
    lit_path = lit.get("source_path")
    if lit_path and Path(lit_path).exists():
        from .intake import verified_snapshot

        try:
            _, fresh_hash = verified_snapshot(lit_path)
            if fresh_hash != lit.get("set_hash"):
                rep.error("intake.literature_stale",
                          "Literature verified 集已变动（集哈希与快照不符）："
                          "承接失效，须重新 intake")
        except Exception as e:  # 读不出即点名，不假装核过（honest-unverified）
            rep.warning("intake.literature_unreadable",
                        f"verified 集源文件无法复算哈希（未核查）：{e}")
    elif lit_path:
        rep.warning("intake.literature_missing",
                    f"verified 集源文件已不存在，集哈希未复核（未核查）：{lit_path}")


def _check_claims(pkg, rep: Report, language):
    manuscript = pkg["manuscript"]
    rows = (pkg["claims"] or {}).get("claims") or []
    intake = manuscript.get("intake") or {}
    expected_ids = intake.get("claim_ids")
    if expected_ids is not None:
        got_ids = [r.get("analysis_claim_ref") for r in rows]
        missing = [c for c in expected_ids if c not in got_ids]
        extra = [c for c in got_ids if c not in expected_ids]
        if missing:
            rep.error("claims.coverage_missing",
                      f"主张登记不全：上游主张 {missing} 无登记行")
        if extra:
            rep.error("claims.coverage_extra",
                      f"主张登记含无上游来源的行 {extra}（稿内主张不许无上游来源）")
    seen = set()
    for row in rows:
        cid = row.get("claim_id")
        if cid in seen:
            rep.error("claims.duplicate", f"主张 {cid} 重复登记")
        seen.add(cid)
        status = row.get("upstream_status")
        grade = row.get("strength_grade")
        if status not in schema.UPSTREAM_STATUSES:
            rep.error("claims.status_vocab",
                      f"主张 {cid} upstream_status {status!r} 不在词表")
            continue
        if grade not in schema.STRENGTH_GRADES:
            rep.error("claims.grade_vocab",
                      f"主张 {cid} strength_grade {grade!r} 不在词表")
            continue
        ceiling = schema.writable_ceiling(status, grade)
        if row.get("writable_ceiling") != ceiling:
            rep.error("claims.ceiling_mismatch",
                      f"主张 {cid} writable_ceiling 登记值 "
                      f"{row.get('writable_ceiling')!r} 与规则导出 {ceiling!r} 不符")
        form = row.get("writable_form")
        if form not in schema.WRITABLE_FORMS:
            rep.error("claims.form_vocab",
                      f"主张 {cid} writable_form {form!r} 不在词表（须落字）")
        elif schema.form_rank(form) > schema.form_rank(ceiling):
            rep.error("claims.form_exceeds_ceiling",
                      f"主张 {cid}（{status}×{grade}）writable_form={form} "
                      f"超过规则上限 {ceiling}"
                      + ("（untested 主张只许 limitations_only/omit）"
                         if status == "untested" else ""))
        wc = row.get("wording_ceiling") or {}
        if wc.get("language") != language:
            rep.error("claims.wording_language",
                      f"主张 {cid} wording_ceiling 语言 {wc.get('language')!r} "
                      f"与稿件语言 {language!r} 不符（措辞词表按稿件语言取）")
        text, thash = row.get("claim_text"), row.get("text_hash")
        if text and thash:
            if claim_text_hash(text) != thash:
                rep.error("claims.text_hash_drift",
                          f"主张 {cid} 文本哈希漂移：登记文本已改而哈希未更新，"
                          "须重验证据贴合度后才许更新哈希（约束 11）",
                          where=f"claims.{cid}")
        elif thash and not text:
            rep.error("claims.hash_without_text",
                      f"主张 {cid} 有 text_hash 而无 claim_text，哈希无所绑")
        elif text and not thash:
            rep.error("claims.text_without_hash",
                      f"主张 {cid} 有 claim_text 而无 text_hash，绑定缺失")
        else:
            rep.warning("claims.text_pending",
                        f"主张 {cid} 规范文本未登记（text_hash 待补）")


def _cited_keys(pkg):
    """sections 中实际引用的 key 集：{key 或 lit:<entry_id>} → 出现节文件。"""
    cited = {}
    for fname, text in section_files(pkg["root"]).items():
        for m in CITE_RE.finditer(text):
            cited.setdefault(m.group(1).strip(), set()).add(fname)
    return cited


def _check_lock_and_bib(root, pkg, rep: Report):
    lock = pkg["lock"] or {}
    entries = lock.get("entries") or []
    keys, ids = set(), set()
    for e in entries:
        if e.get("key") in keys:
            rep.error("lock.key_duplicate", f"lock 中 key {e.get('key')} 重复")
        keys.add(e.get("key"))
        if e.get("entry_id") in ids:
            rep.error("lock.entry_duplicate",
                      f"lock 中条目 {e.get('entry_id')} 重复（去重按条目 ID 归一）")
        ids.add(e.get("entry_id"))
        if e.get("retraction_state") not in schema.RETRACTION_STATES:
            rep.error("lock.retraction_vocab",
                      f"条目 {e.get('entry_id')} retraction_state "
                      f"{e.get('retraction_state')!r} 不在四态词表 {schema.RETRACTION_STATES}")
    cited = _cited_keys(pkg)
    by_key = {e.get("key"): e for e in entries}
    by_id = {e.get("entry_id"): e for e in entries}
    for token in cited:
        entry = None
        if token.startswith("lit:"):
            entry = by_id.get(token[4:])
            if entry is None:
                rep.error("cite.unknown_entry",
                          f"引用占位符 [@{token}] 的条目 ID 不在 references.lock 中")
        else:
            entry = by_key.get(token)
            if entry is None:
                rep.error("cite.unknown_key",
                          f"引用占位符 [@{token}] 不在 references.lock 中"
                          "（引用只许来自 verified 集快照）")
        if entry is not None:
            state = entry.get("retraction_state")
            if state == "retracted":
                rep.error("cite.retracted",
                          f"被引条目 {entry.get('entry_id')} 撤稿状态为 retracted，"
                          "不许进入成稿（约束：撤稿条目引用即拒）")
            elif state == "unknown" and not entry.get("retraction_note"):
                rep.error("cite.retraction_unknown_no_note",
                          f"被引条目 {entry.get('entry_id')} 撤稿状态 unknown "
                          "且无落字说明（retraction_note），须先复核并落字")
            elif state == "no_doi":
                rep.warning("cite.no_doi",
                            f"被引条目 {entry.get('entry_id')} 无 DOI（no_doi 态），"
                            "成稿时点须复核其身份")
    bib_path = root / FILES["bib"]
    if bib_path.exists():
        actual = bib_path.read_text(encoding="utf-8")
        if actual != render_bib(entries):
            rep.error("bib.hand_edited",
                      "references.bib 与 lock 重渲染不一致：bib 是生成物、禁手改，"
                      "须整条回退重渲染（约束 3/15）")
    elif entries:
        rep.error("bib.missing", "references.bib 缺失而 lock 非空")


def _check_sections(pkg, rep: Report):
    manuscript = pkg["manuscript"]
    files = section_files(pkg["root"])
    registered = {s.get("file"): s for s in manuscript.get("sections") or []}
    for fname, s in registered.items():
        if fname not in files:
            rep.error("section.file_missing",
                      f"登记的节文件 sections/{fname} 不存在")
        if not s.get("section_id"):
            rep.error("section.no_id", f"节登记 {fname} 缺 section_id")
    for fname in files:
        if fname not in registered:
            rep.warning("section.unregistered",
                        f"节文件 sections/{fname} 未在 manuscript.yaml 登记")
    claim_ids = {r.get("claim_id") for r in (pkg["claims"] or {}).get("claims") or []}
    num_ids = {n.get("num_id") for n in (pkg["numbers"] or {}).get("numbers") or []}
    for fname, text in files.items():
        stripped = CITE_RE.sub(" ", text)
        for m in DOI_RE.finditer(stripped):
            rep.error("section.bare_doi",
                      f"{fname} 正文出现占位符之外的 DOI 形态字符串 {m.group(0)!r}："
                      "书目信息只许由 verified 集回填（约束 2/3）",
                      where=f"sections/{fname}")
        for m in ETAL_YEAR_RE.finditer(stripped):
            rep.warning("section.handwritten_cite",
                        f"{fname} 出现疑似手写引用串 {m.group(0)!r}（et al.+年份），"
                        "引用应改用占位符 [@key]",
                        where=f"sections/{fname}")
        for m in AUTHYEAR_RE.finditer(stripped):
            rep.warning("section.handwritten_cite",
                        f"{fname} 出现疑似手写作者-年份串 {m.group(0)!r}，"
                        "引用应改用占位符 [@key]",
                        where=f"sections/{fname}")
        for m in CLAIM_MARK_RE.finditer(text):
            if m.group(1) not in claim_ids:
                rep.error("section.unknown_claim_mark",
                          f"{fname} 的 [claim:{m.group(1)}] 不在主张登记中")
        for m in NUM_MARK_RE.finditer(text):
            if m.group(1) not in num_ids:
                rep.error("section.unknown_num_mark",
                          f"{fname} 的 [num:{m.group(1)}] 不在数字溯源账中"
                          "（数字只许来自溯源表，约束 5）")


def _check_numbers_figures_checklist(pkg, rep: Report):
    numbers = (pkg["numbers"] or {}).get("numbers") or []
    seen = set()
    for n in numbers:
        nid = n.get("num_id")
        if nid in seen:
            rep.error("numbers.duplicate", f"数字 {nid} 重复登记")
        seen.add(nid)
        if not n.get("trace_ref"):
            rep.error("numbers.no_trace",
                      f"数字 {nid} 缺溯源表条目指针 trace_ref（无溯源数字不许进成稿）")
    figures = (pkg["figures"] or {}).get("figures") or []
    seen = set()
    for f in figures:
        fid = f.get("figure_id")
        if fid in seen:
            rep.error("figures.duplicate", f"图表 {fid} 重复登记")
        seen.add(fid)
        if f.get("status") not in schema.FIGURE_STATUSES:
            rep.error("figures.status_vocab",
                      f"图表 {fid} status {f.get('status')!r} 不在 {schema.FIGURE_STATUSES}")
        if f.get("status") == "backfilled" and \
                (not f.get("source_ref") or not f.get("source_hash")):
            rep.error("figures.backfill_no_source",
                      f"图表 {fid} 已标 backfilled 但缺交付物指针/文件哈希")
        caption, chash = f.get("caption"), f.get("caption_text_hash")
        if caption and chash:
            from .util import sha256_text

            if sha256_text(caption.strip()) != chash:
                rep.error("figures.caption_hash_drift",
                          f"图表 {fid} caption_text_hash 与图注文本不符")
    seen_numbers = {}
    for f in figures:
        n = f.get("display_number")
        if n is not None:
            kind = f.get("kind") or (
                "table" if str(f.get("figure_id", "")).startswith("T")
                else "figure")
            key = (kind, n)
            if key in seen_numbers:
                rep.error("figures.display_number_dup",
                          f"{kind} 编号 {n} 重复（{seen_numbers[key]} 与 "
                          f"{f.get('figure_id')}）")
            seen_numbers[key] = f.get("figure_id")
    items = (pkg["checklist"] or {}).get("items") or []
    seen = set()
    for it in items:
        iid = it.get("item_id")
        if iid in seen:
            rep.error("checklist.duplicate", f"检查条目 {iid} 重复登记")
        seen.add(iid)
        for field in ("source", "requirement", "status"):
            if not it.get(field):
                rep.error("checklist.field_missing",
                          f"检查条目 {iid} 缺字段 {field}")
        if it.get("status") == "not_applicable" and not it.get("note"):
            rep.error("checklist.na_no_reason",
                      f"检查条目 {iid} 标 not_applicable 但无理由落字")


def _check_declarations_uselog(manuscript, rep: Report):
    decls = manuscript.get("declarations") or {}
    for key in schema.DECLARATION_KEYS:
        entry = decls.get(key)
        if entry is None:
            rep.error("declarations.missing",
                      f"声明区缺 {key}（三态须登记齐备，不许样板话顶替）")
            continue
        state = entry.get("state")
        if state not in schema.DECLARATION_STATES:
            rep.error("declarations.state_vocab",
                      f"声明 {key} state {state!r} 不在 {schema.DECLARATION_STATES}")
        elif state == "na" and not entry.get("note"):
            rep.error("declarations.na_no_reason",
                      f"声明 {key} 标 na 但无理由落字")
        elif state == "absent":
            rep.warning("declarations.absent",
                        f"声明 {key} 尚缺失（absent 已登记，投稿前须补齐或改 na 并落理由）")
    for i, entry in enumerate(manuscript.get("use_log") or []):
        where = f"use_log[{i}]"
        if not entry.get("model_version"):
            rep.error("use_log.no_model_version",
                      "AI 使用留痕缺模型版本（model_version）：披露须含版本号"
                      "（Science 口径），缺失即拒", where=where)
        for field in ("tool", "purpose", "section", "date"):
            if not entry.get(field):
                rep.warning("use_log.field_missing",
                            f"AI 使用留痕缺字段 {field}", where=where)


def _check_audit_freshness(root, pkg, rep: Report):
    """audited / submission_ready 态：审计产物必须在场且未 STALE（Phase 2）。"""
    manuscript = pkg["manuscript"]
    if manuscript.get("status") not in ("audited", "submission_ready"):
        return
    report_path = root / "audit" / "audit_report.json"
    if not report_path.exists():
        rep.error("audit.missing",
                  "稿件已达 audited/submission_ready 但审计产物缺失")
        return
    try:
        report = load_structured(report_path)
    except Exception as e:
        rep.error("audit.unreadable", f"审计产物不可读（未核查）：{e}")
        return
    if (report or {}).get("manuscript_hash") != manuscript_hash(root):
        rep.error("audit.stale",
                  "审计产物 STALE：稿件在审计后已变动（哈希漂移），"
                  "须重跑 audit（稿改即 STALE，约束 13）")
    elif report.get("overall") != "pass":
        rep.error("audit.not_pass",
                  "审计总判定非 pass 但稿件状态已过 audited：状态与产物矛盾")


def _check_template(pkg, rep: Report):
    manuscript = pkg["manuscript"]
    target = manuscript.get("target_journal")
    record = pkg["template_record"]
    if target is None:
        rep.warning("template.not_registered",
                    "目标期刊模板记录未登记（register-template）")
        return
    if record is None:
        rep.error("template.record_missing",
                  "manuscript.yaml 已登记目标期刊但 template_record.json 快照缺失")
        return
    check_template_record(record, rep)
    if component_hash(record) != target.get("record_hash"):
        rep.error("template.record_hash_drift",
                  "template_record.json 与登记头记录的核查记录哈希不符"
                  "（快照被改或登记过期，须重新 register-template）")
    group_a = record.get("A") or {}
    if group_a.get("journal_language") and \
            group_a["journal_language"] != manuscript.get("language"):
        rep.error("template.language_mismatch",
                  f"模板记录期刊语言 {group_a['journal_language']} 与稿件语言 "
                  f"{manuscript.get('language')} 不一致（一篇稿一个语言）")


def _check_contract(pkg, rep: Report):
    manuscript = pkg["manuscript"]
    contract = pkg["contract"] or {}
    assertions = contract.get("assertions") or []
    for a in assertions:
        aid = a.get("assertion_id")
        for field in ("text", "checkable_via"):
            if not a.get(field):
                rep.error("contract.assertion_field",
                          f"验收断言 {aid} 缺字段 {field}"
                          "（断言须只读终稿+上游产物即可判定）")
        if a.get("status") not in schema.ASSERTION_STATUSES:
            rep.error("contract.assertion_status",
                      f"验收断言 {aid} status {a.get('status')!r} 不在词表")
    if assertions and not (schema.CONTRACT_MIN_ASSERTIONS
                           <= len(assertions) <= schema.CONTRACT_MAX_ASSERTIONS):
        rep.warning("contract.assertion_count",
                    f"验收断言 {len(assertions)} 条，ARIS 口径为 "
                    f"{schema.CONTRACT_MIN_ASSERTIONS}–{schema.CONTRACT_MAX_ASSERTIONS} 条")
    contested = [a for a in assertions if a.get("status") == "contested"]
    if contested and contract.get("status") != "contested":
        rep.error("contract.status_inconsistent",
                  "存在 contested 断言但合同状态未落 contested")
    if contract.get("frozen"):
        if contract_content_hash(contract) != contract.get("content_hash"):
            rep.error("contract.frozen_hash_drift",
                      "验收合同已冻结但内容哈希不符：冻结后改动被检出，"
                      "须解冻重议（不许静默改冻结合同）")
    head = manuscript.get("acceptance_contract") or {}
    if head.get("status") not in (None, "unset") and \
            head.get("status") != contract.get("status"):
        rep.warning("contract.head_drift",
                    "登记头 acceptance_contract.status 与合同文件状态不一致")
