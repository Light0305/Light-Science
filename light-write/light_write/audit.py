"""审计四门（Phase 2，audited 段）：fail-closed，产物绑稿件哈希。

四门（草案 §三 + LEARNING 约束 1/2/4/5/8/12/13/14）：
  门一 引用两段核对：存在性/身份核（identity_level_fabrication 口径，
       疑似编造须第二路阴性证据才许落字）+ 字段级核
       （field_level_hallucination_screen 口径 + FIELD_TOLERANCES 容差层）。
       在线权威记录经「复核接口」注入（online_records）；离线时整门落
       honest-unverified——不许声称查过，门不许 PASS（约束 14）。
       相关性轴（引对但撑不住主张）只标记待人工/复核，不自动定罪；
       已登记的处置（KEEP/FIX/REPLACE/REMOVE）中 REPLACE/REMOVE
       无人类批准则拦门（约束 4 + ARIS 形态）。
  门二 数字对账：正文 [num:] 锚定的呈现串 ↔ numbers_ledger
       value_as_printed ↔ Analysis 溯源表数值逐串比对（舍入规则：
       呈现值须等于溯源值按呈现小数位标准舍入）；正文出现未登记
       数字串 → 逐个点名（约束 5）。
  门三 强度措辞门：逐 [claim:] 锚点取其句子，比对该主张 wording_ceiling
       （按稿件语言词表）：禁用词 → 拒；高于本档的术语 → 拒；两类都给
       降格建议（本档 allowed_terms）。text_hash 漂移的主张先重验
       贴合度（reverify-claim）才许过门（约束 11/12）。
  门四 落点映射复核：submission_checklist 全条目落点存在性机械复核
       （节文件锚点 / 声明三态 / 包内文件）；报告规范条目只复核落点
       不做声明式自查（约束 7/8）。

审计产物落 audit/（audit_report.json + 逐门 MD + AUDIT_SUMMARY.md），
绑 manuscript_hash；稿改 → 哈希漂移 → 产物 STALE（validate/gates 检出）。
审计与把门分离（约束 13）：本模块只出判定与产物，推进状态机的阻断权
在 gates；审计的绿灯只表示「未发现自动可判的失败」，不表示内容为真。
"""

from __future__ import annotations

import json
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from . import schema
from .project import FILES, load_package, manuscript_hash, section_files
from .util import (
    claim_text_hash, component_hash, dump_json, load_structured, sha256_file,
    today, utcnow,
)
from .validate import CITE_RE, CLAIM_MARK_RE, NUM_MARK_RE

AUDIT_DIR = "audit"
REPORT_NAME = "audit_report.json"

# [num:N001] 5.2 / [num:N001] 5.2 points / [num:N001] 37%
NUM_VALUE_RE = re.compile(
    r"\[num:([A-Za-z0-9_-]+)\]\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([A-Za-z%μ°/]*)")
FIG_MARK_RE = re.compile(r"\[fig:([A-Za-z0-9_-]+)\]")
REV_MARK_RE = re.compile(r"\[rev:([A-Za-z0-9_-]+)\]")
BARE_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.])\d+(?:,\d{3})*(?:\.\d+)?%?(?![A-Za-z0-9_])")
DISCLOSURE_BLOCK_RE = re.compile(
    r"<!--\s*light-write:disclosure:.*?-->.*?<!--\s*/light-write:disclosure:"
    r".*?-->", re.DOTALL)


class AuditError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _finding(level, code, message, where=None):
    return {"level": level, "code": code, "message": message, "where": where}


class GateResult:
    def __init__(self, gate_id):
        self.gate_id = gate_id
        self.status = "pass"  # pass | fail | unverified
        self.findings = []
        self.details = {}

    def error(self, code, message, where=None):
        self.findings.append(_finding("error", code, message, where))
        self.status = "fail"

    def warning(self, code, message, where=None):
        self.findings.append(_finding("warning", code, message, where))

    @property
    def errors(self):
        return [f for f in self.findings if f["level"] == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f["level"] == "warning"]

    def to_dict(self):
        return {"gate": self.gate_id,
                "title": schema.AUDIT_GATE_TITLES[self.gate_id],
                "status": self.status,
                "findings": self.findings,
                "details": self.details}


# ================================================================ 门一

def _norm_text(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _levenshtein(a: str, b: str, cap=4) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (0 if ca == cb else 1))
            best = min(best, cur[j])
        if best > cap:
            return cap + 1
        prev = cur
    return prev[len(b)]


def _surname(name) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    parts = [p for p in re.split(r"[^a-z]+", text) if p]
    return parts[-1] if parts else ""


def _title_verdict(lock_title, rec_title):
    """题名核查（FIELD_TOLERANCES.title）：返回 (ok, wrong, warning|None)。"""
    lt, rt = _norm_text(lock_title), _norm_text(rec_title)
    if lt == rt:
        return True, False, None
    # 副标题容差：一侧是另一侧在冒号处的前缀
    for full, part in ((str(lock_title or ""), str(rec_title or "")),
                       (str(rec_title or ""), str(lock_title or ""))):
        head = full.split(":")[0].strip()
        if head and _norm_text(head) == _norm_text(part):
            return True, False, "题名仅副标题差异（容差内）"
    if _levenshtein(lt, rt, cap=3) <= 3:
        return True, False, "题名编辑距离 ≤3（typo 容差内）"
    return False, True, None


def _doi_norm(doi) -> str:
    s = str(doi or "").strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    return s.rstrip(".,;)")


def _page_start(pages):
    m = re.match(r"\s*(\d+)", str(pages or ""))
    return int(m.group(1)) if m else None


_CONFUSABLES = str.maketrans({"T": "7", "l": "1", "I": "1", "O": "0", "S": "5"})


def _confusable_eq(a, b):
    return a != b and a.translate(_CONFUSABLES) == b.translate(_CONFUSABLES)


def _check_one_entry(entry, record):
    """对一条被引条目做两段核对。record = 在线权威记录（dict）。"""
    out = {"entry_id": entry.get("entry_id"), "key": entry.get("key"),
           "identity": None, "field_screen": None, "findings": []}
    finds = out["findings"]

    def err(code, msg):
        finds.append(_finding("error", code, msg, entry.get("entry_id")))

    def warn(code, msg):
        finds.append(_finding("warning", code, msg, entry.get("entry_id")))

    if record.get("exists") is False:
        # 身份级：落「编造」须第二路阴性证据（约束 1）；只有一路 → 未决拦门
        if record.get("second_source_checked") and \
                record.get("second_source_found") is False:
            out["identity"] = "fabrication"
            err("cite.identity_fabrication",
                "identity_level_fabrication：第一路查无此条 + 第二路阴性证据"
                "齐备，判定编造（口径见 schema.CITATION_FABRICATION_LEVELS）")
        else:
            out["identity"] = "suspected_unresolved"
            err("cite.identity_unresolved",
                "第一路查无此条，但缺第二路阴性证据：只许落「疑似未决」拦门，"
                "不许直接定罪编造（约束 1）")
        out["field_screen"] = "not_applicable"
        out["verification_status"] = (
            "needs_fix" if out["identity"] == "fabrication"
            else "unverifiable")
        return out
    out["identity"] = "verified_online"

    wrong = []
    # 题名
    ok, is_wrong, warn_msg = _title_verdict(entry.get("title"),
                                            record.get("title"))
    if warn_msg:
        warn("cite.title_tolerance", warn_msg)
    if is_wrong:
        wrong.append("title")
    # 第一作者
    lock_authors = entry.get("authors") or []
    rec_authors = record.get("authors") or []
    if lock_authors and rec_authors:
        if _surname(lock_authors[0]) != _surname(rec_authors[0]):
            wrong.append("first_author")
    elif bool(lock_authors) != bool(rec_authors):
        wrong.append("first_author")
    if len(lock_authors) != len(rec_authors):
        err("cite.authors_count",
            f"作者人数不符：lock {len(lock_authors)} 人 vs 权威记录 "
            f"{len(rec_authors)} 人（FIELD_TOLERANCES.authors：人数不符报错）")
    # 年份（±1 只 warning，超差才计错）；Early Access 漂移单列（D-W05）
    ly, ry = entry.get("year"), record.get("year")
    if ly is not None and ry is not None:
        if int(ly) != int(ry) and record.get("early_access"):
            warn("cite.early_access_drift",
                 f"Early Access 元数据漂移：lock 年 {ly} vs 权威现值 {ry}，"
                 "以权威现值为准（D-W05），只警告")
        elif int(ly) != int(ry):
            if abs(int(ly) - int(ry)) <= 1:
                warn("cite.year_drift",
                     f"年份差 1（lock {ly} vs 权威 {ry}）：在线年/正式年漂移，"
                     "容差内只警告")
            else:
                wrong.append("year")
    elif (ly is None) != (ry is None):
        wrong.append("year")
    # venue（只 warning）
    if _norm_text(entry.get("venue")) != _norm_text(record.get("venue")):
        warn("cite.venue_variant",
             f"venue 变体差异：lock {entry.get('venue')!r} vs 权威 "
             f"{record.get('venue')!r}（缩写/全称等价口径，只警告）")
    # DOI（归一化全等；不一致时能解析降 warning、不能解析才 error）
    ld, rd = _doi_norm(entry.get("doi")), _doi_norm(record.get("doi"))
    if ld and rd and ld != rd:
        if record.get("doi_resolves"):
            warn("cite.doi_resolvable",
                 "DOI 与权威记录不一致但可解析：降为警告，成稿前应回填权威 DOI")
        else:
            err("cite.doi_unresolvable",
                "DOI 与权威记录不一致且不可解析（Chelli 实测：模型给出 DOI "
                "约八成不可信，标识符必须反查回填）")
    elif ld and not rd:
        warn("cite.doi_absent_in_record", "权威记录无 DOI，lock 侧 DOI 未获印证")
    # 页码/文章号（D-W05 实测矩阵）：差 ≤4 Warning、≥5 Critical；
    # 仅形近字符之差（T/7、l/1、O/0）= 文章号字母误判 Critical
    lp, rp = str(entry.get("pages") or ""), str(record.get("pages") or "")
    if lp and rp and lp != rp:
        ls, rs = _page_start(lp), _page_start(rp)
        if _confusable_eq(lp, rp):
            err("cite.article_number_confusable",
                f"文章号形近误判：lock {lp!r} vs 权威 {rp!r} 仅差形近字符"
                "（T/7、l/1、O/0）——Critical，须按权威记录回填")
        elif ls is not None and rs is not None:
            diff = abs(ls - rs)
            if diff >= 5:
                err("cite.pages_critical",
                    f"页码差 {diff}（lock {lp!r} vs 权威 {rp!r}）≥5：Critical")
            elif diff >= 1:
                warn("cite.pages_drift",
                     f"页码差 {diff}（lock {lp!r} vs 权威 {rp!r}）≤4：Warning")
    # 撤稿态以在线为准复核
    rec_retr = record.get("retraction_state")
    if rec_retr == "retracted" and entry.get("retraction_state") != "retracted":
        err("cite.retraction_online",
            "在线复核显示该条目已撤稿（retracted），lock 快照状态滞后："
            "不许进入成稿，须回 Literature 更新快照")
    # 字段级筛（Chelli 口径）：题名/一作/年份任二错 → 阳性，整门 fail
    if len(wrong) >= 2:
        out["field_screen"] = "positive"
        err("cite.field_screen_positive",
            f"field_level_hallucination_screen 阳性：{wrong} 中 ≥2 项与权威"
            "记录不符（题名/一作/年份任二错口径），整条须回 Literature 复核")
    else:
        out["field_screen"] = "negative"
        if wrong:
            warn("cite.field_single_mismatch",
                 f"字段级筛阴性但有单项不符：{wrong}（逐项回填修正）")
    # 核查状态四级（D-W06）：Unverifiable 是合法终态，查不到 ≠ 编造
    if any(f["level"] == "error" for f in finds):
        out["verification_status"] = "needs_fix"
    elif finds:
        out["verification_status"] = "check_suggested"
    else:
        out["verification_status"] = "verified"
    return out


def _check_support_assessments(g, pkg, support):
    """支撑五级量表 + 双角色对抗协议的机械面（D-W07/D-W12）。

    support: {(entry_id 或 key): {claim_id, level, verbatim_quote,
    rejection_reason}}。协议本体（proposer/skeptic 分离、默认拒绝）是规程
    （SKILL §6），此处只验：量表词表、strong/partial 须逐字支撑句、
    失败原因分类学词表、metadata_only 不许作支撑。
    """
    if support is None:
        support = {}
        path = pkg["root"] / "audit" / "support_assessments.yaml"
        if path.exists():
            from .util import load_structured
            data = load_structured(path) or {}
            for row in data.get("assessments") or []:
                support[row.get("entry_id") or row.get("key")] = row
    checked = []
    for token, a in sorted(support.items()):
        level = a.get("level")
        if level not in schema.SUPPORT_LEVELS:
            g.error("cite.support_vocab",
                    f"支撑判定 {level!r} 不在五级量表 {schema.SUPPORT_LEVELS}",
                    str(token))
            continue
        if level in ("strong", "partial") and not a.get("verbatim_quote"):
            g.error("cite.support_no_quote",
                    f"条目 {token} 支撑判定为 {level} 但无逐字支撑句："
                    "无逐字句不确认（双角色对抗协议，D-W12）", str(token))
        reason = a.get("rejection_reason")
        if reason is not None and reason not in schema.REJECTION_REASONS:
            g.error("cite.rejection_vocab",
                    f"失败原因 {reason!r} 不在分类学 {schema.REJECTION_REASONS}",
                    str(token))
        if level == "metadata_only":
            g.warning("cite.support_metadata_only",
                      f"条目 {token} 支撑仅 metadata-only：未查摘要/出版商页"
                      "不许作支撑，须人工裁决换源或降主张", str(token))
        if level == "contradictory_limiting":
            g.warning("cite.support_contradictory",
                      f"条目 {token} 支撑判定 contradictory-limiting："
                      "引用须同时呈现限定，不许只引支持面", str(token))
        checked.append({"token": token, "level": level,
                        "claim_id": a.get("claim_id"),
                        "rejection_reason": reason})
    g.details["support_assessments"] = checked
    return g


def gate_citations(pkg, online_records=None, relevance=None,
                   support=None) -> GateResult:
    g = GateResult("citations")
    from .validate import _cited_keys

    cited = _cited_keys(pkg)
    entries = (pkg["lock"] or {}).get("entries") or []
    by_key = {e.get("key"): e for e in entries}
    by_id = {e.get("entry_id"): e for e in entries}
    cited_entries = {}
    for token in cited:
        entry = by_id.get(token[4:]) if token.startswith("lit:") \
            else by_key.get(token)
        if entry is None:
            g.error("cite.unknown", f"引用占位符 [@{token}] 不在 lock 中",
                    token)
        else:
            cited_entries[entry.get("entry_id")] = entry
    g.details["cited_count"] = len(cited_entries)

    relevance = relevance or {}
    relevance_pending = []
    for eid, entry in sorted(cited_entries.items()):
        row = {"entry_id": eid, "key": entry.get("key")}
        if online_records is None or eid not in online_records:
            row["identity"] = "honest-unverified"
            row["verification_status"] = "unverifiable"
            row["note"] = ("无在线权威记录注入：本条未做在线核查"
                           "（honest-unverified，不许声称查过）")
            g.details.setdefault("entries", []).append(row)
            continue
        row.update(_check_one_entry(entry, online_records[eid]))
        for f in row["findings"]:
            g.findings.append(f)
            if f["level"] == "error":
                g.status = "fail"
        g.details.setdefault("entries", []).append(row)
        # 相关性轴：只标记不自动定罪；已登记处置按纪律执行
        rel = relevance.get(eid) or relevance.get(entry.get("key"))
        if rel is None:
            relevance_pending.append(eid)
        else:
            row["relevance"] = rel
            verdict = rel.get("verdict")
            disposition = rel.get("disposition")
            if verdict not in schema.ENTAILMENT_VERDICTS:
                g.error("cite.relevance_vocab",
                        f"条目 {eid} 相关性判定 {verdict!r} 不在蕴含四值词表",
                        eid)
            if disposition is not None and \
                    disposition not in schema.CONTEXT_DISPOSITIONS:
                g.error("cite.disposition_vocab",
                        f"条目 {eid} 处置 {disposition!r} 不在 "
                        "KEEP/FIX/REPLACE/REMOVE 词表", eid)
            if disposition in schema.CONTEXT_DISPOSITIONS_NEED_HUMAN and \
                    not rel.get("human_approved"):
                g.error("cite.disposition_needs_human",
                        f"条目 {eid} 处置为 {disposition}：REPLACE/REMOVE "
                        "永须人类批准，未批不许过门", eid)
            if disposition == "FIX" and not rel.get("note"):
                g.error("cite.fix_needs_note",
                        f"条目 {eid} 处置为 FIX 但无落字说明", eid)
            if verdict == "contradiction" and disposition in (None, "KEEP"):
                g.warning("cite.relevance_contradiction",
                          f"条目 {eid} 相关性判定为 contradiction 但处置为 "
                          f"{disposition}：已标记待复核，不自动定罪", eid)
    _check_support_assessments(g, pkg, support)
    g.details["relevance_pending"] = sorted(relevance_pending)
    if relevance_pending:
        g.warning("cite.relevance_pending",
                  f"相关性轴待人工/复核（不自动定罪）：{sorted(relevance_pending)}")
    if online_records is None:
        g.status = "unverified"
        g.warning("cite.offline",
                  "未注入在线权威记录：门一整门 honest-unverified——"
                  "引用两段核对未执行，不许声称查过（约束 14）")
    elif cited_entries and not online_records:
        g.status = "unverified"
    elif any(eid not in online_records for eid in cited_entries):
        g.status = "unverified"
        g.warning("cite.partial_online",
                  "在线记录未覆盖全部被引条目：未覆盖者 honest-unverified，"
                  "整门不得 PASS")
    return g


# ================================================================ 门二

def _num_normalize(token: str, unit: str):
    """呈现串规范化：去千分逗号；返回 (数值, 小数位, 规范串)。"""
    raw = token.replace(",", "")
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    return float(raw), decimals, (raw + (unit or "")).strip()


def _load_provenance(pkg):
    """从承接快照读 Analysis 数字溯源表；不可得 → (None, 原因)。"""
    manuscript = pkg["manuscript"]
    intake = manuscript.get("intake") or {}
    card_info = intake.get("conclusion_card") or {}
    path = card_info.get("path")
    if not path or not Path(path).exists():
        return None, "承接的 conclusion_card 不可得：溯源表无法复核（未核查）"
    if sha256_file(path) != card_info.get("sha256"):
        return None, "conclusion_card 哈希与承接快照不符：承接已失效，须重新 intake"
    card = load_structured(path)
    rows = {}
    for row in card.get("number_provenance") or []:
        for key in (row.get("verdict_line"), row.get("registry_line_id")):
            if key:
                rows.setdefault(key, row)
    return rows, None


def gate_numbers(pkg) -> GateResult:
    g = GateResult("numbers")
    ledger = {(n.get("num_id")): n
              for n in (pkg["numbers"] or {}).get("numbers") or []}
    provenance, prov_err = _load_provenance(pkg)
    if prov_err:
        g.error("numbers.provenance_unavailable", prov_err)
    occurrences = {}  # num_id -> [(file, printed_token, unit)]
    for fname, text in section_files(pkg["root"]).items():
        stripped = CITE_RE.sub(" ", text)
        for m in NUM_VALUE_RE.finditer(stripped):
            occurrences.setdefault(m.group(1), []).append(
                (fname, m.group(2), m.group(3) or ""))
        # 未登记数字串：剥掉标记锚与其值、披露生成块、标题/列表结构后扫描
        scan = NUM_VALUE_RE.sub(" ", stripped)
        scan = DISCLOSURE_BLOCK_RE.sub(" ", scan)
        scan = CLAIM_MARK_RE.sub(" ", scan)
        scan = FIG_MARK_RE.sub(" ", scan)
        scan = REV_MARK_RE.sub(" ", scan)
        for line in scan.splitlines():
            line = re.sub(r"^\s*#{1,6}\s*", "", line)
            line = re.sub(r"^\s*\d+[.)]\s+", "", line)  # 有序列表序号
            for m in BARE_NUMBER_RE.finditer(line):
                g.error("numbers.unregistered_in_text",
                        f"{fname} 正文出现未登记数字串 {m.group(0)!r}："
                        "正文每个数字必须以 [num:N###] 锚定并在账内有行"
                        "（约束 5）", fname)
    for nid, occs in sorted(occurrences.items()):
        row = ledger.get(nid)
        if row is None:
            g.error("numbers.unknown_mark",
                    f"[num:{nid}] 无账行（validate 应已拦，此为门内复核）", nid)
            continue
        if not row.get("value_as_printed"):
            g.error("numbers.no_printed_value",
                    f"数字 {nid} 账行缺 value_as_printed，无从逐串比对", nid)
            continue
        mval = re.match(r"\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(.*)$",
                        str(row["value_as_printed"]))
        if not mval:
            g.error("numbers.printed_not_numeric",
                    f"数字 {nid} value_as_printed {row['value_as_printed']!r} "
                    "不以数值开头，无从逐串比对", nid)
            continue
        ledger_val, _, _ = _num_normalize(mval.group(1), mval.group(2))
        trace_row = (provenance or {}).get(row.get("trace_ref"))
        if provenance is not None and trace_row is None:
            g.error("numbers.trace_ref_unresolved",
                    f"数字 {nid} trace_ref {row.get('trace_ref')!r} 在 "
                    "Analysis 溯源表中无对应行", nid)
        trace_val = trace_row.get("value") if trace_row else None
        for fname, token, unit in occs:
            printed, decimals, _ = _num_normalize(token, unit)
            if abs(printed - ledger_val) > 1e-12:
                g.error("numbers.printed_vs_ledger",
                        f"{fname} 的 [num:{nid}] 呈现值 {token}{unit} 与账内 "
                        f"value_as_printed {row['value_as_printed']!r} 不一致："
                        "润色改数未同步账本 → fail（约束 5）", nid)
            if trace_val is not None:
                # 标准舍入 = 半上舍入（Decimal），不用 Python 银行家舍入冒充
                expected = float(
                    Decimal(str(trace_val)).quantize(
                        Decimal("1e-%d" % decimals),
                        rounding=ROUND_HALF_UP))
                if abs(printed - expected) > 1e-9:
                    g.error("numbers.printed_vs_trace",
                            f"{fname} 的 [num:{nid}] 呈现值 {printed} 与溯源表"
                            f"数值 {trace_val} 按呈现精度（{decimals} 位）舍入"
                            f"应为 {expected}：逐串比对不过", nid)
    for nid in sorted(ledger):
        if nid not in occurrences:
            g.error("numbers.ledger_not_in_text",
                    f"数字 {nid} 已登记但正文无 [num:{nid}] 出现：账实不符", nid)
    # 一致性清扫（D-W03，consistency sweep 的机械面）：只报警告不自动改
    by_trace: dict[str, list] = {}
    for row in ledger.values():
        if row.get("trace_ref"):
            by_trace.setdefault(row["trace_ref"], []).append(row)
    for tref, rows in sorted(by_trace.items()):
        decimals_seen, units_seen = set(), set()
        for row in rows:
            m = re.match(r"\s*[0-9][0-9,]*(?:\.([0-9]+))?\s*(.*)$",
                         str(row.get("value_as_printed") or ""))
            if m:
                decimals_seen.add(len(m.group(1) or ""))
                units_seen.add((m.group(2) or "").strip())
        if len(decimals_seen) > 1:
            g.warning("numbers.precision_drift",
                      f"同一量 {tref} 多处呈现精度不一（小数位 {sorted(decimals_seen)}）"
                      "：同量异精度，逐处读语境裁决，本门只警告不自动改", tref)
        units_seen.discard("")
        if len(units_seen) > 1:
            g.warning("numbers.unit_variant",
                      f"同一量 {tref} 单位表述不一：{sorted(units_seen)}"
                      "（同量异单位，警告）", tref)
    all_text = "\n".join(section_files(pkg["root"]).values())
    sd_forms = [f for f in ("SD", "Std.", "std. dev.", "s.d.")
                if re.search(r"(?<![A-Za-z])" + re.escape(f), all_text)]
    if len(sd_forms) > 1:
        g.warning("numbers.sd_variant",
                  f"离散量表述混用 {sd_forms}：全稿统一一种（警告）")
    g.details["numbers_checked"] = len(ledger)
    return g


# ================================================================ 门三

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")


def _sentences(text):
    out = []
    for chunk in _SENTENCE_SPLIT_RE.split(text):
        chunk = chunk.strip()
        if chunk:
            out.append(chunk)
    return out


def gate_wording(pkg) -> GateResult:
    g = GateResult("wording")
    manuscript = pkg["manuscript"]
    language = manuscript.get("language")
    claims = {r.get("claim_id"): r
              for r in (pkg["claims"] or {}).get("claims") or []}
    all_terms = schema.all_wording_terms(language)
    checked = 0
    for fname, text in section_files(pkg["root"]).items():
        for sentence in _sentences(text):
            marks = CLAIM_MARK_RE.findall(sentence)
            if not marks:
                continue
            plain = CLAIM_MARK_RE.sub("", sentence)
            plain = NUM_MARK_RE.sub("", plain)
            plain = CITE_RE.sub("", plain)
            for cid in marks:
                row = claims.get(cid)
                if row is None:
                    g.error("wording.unknown_claim",
                            f"{fname} 的 [claim:{cid}] 不在主张登记中", fname)
                    continue
                checked += 1
                # text_hash 漂移 → 先重验贴合度，不许过门
                text_val, thash = row.get("claim_text"), row.get("text_hash")
                if text_val and thash and \
                        claim_text_hash(text_val) != thash and \
                        not row.get("fit_reverified_at"):
                    g.error("wording.hash_drift_unreverified",
                            f"主张 {cid} text_hash 已漂移且未重验贴合度："
                            "先 reverify-claim 重验后才许过措辞门（约束 11）",
                            cid)
                ceiling = row.get("wording_ceiling") or {}
                grade = row.get("strength_grade")
                rank = schema.GRADE_RANK.get(grade, 0)
                suggestions = ceiling.get("allowed_terms") or []
                for banned in ceiling.get("banned_terms") or []:
                    hit = banned.lower() in plain.lower() \
                        if language == "en" else banned in plain
                    if hit:
                        g.error("wording.banned_term",
                                f"{fname} 主张 {cid} 句中出现全档禁用词 "
                                f"{banned!r}：降格建议句式（本档可用）"
                                f"：{suggestions}", cid)
                for term in all_terms:
                    hit = term.lower() in plain.lower() \
                        if language == "en" else term in plain
                    if not hit:
                        continue
                    required = schema.term_required_rank(language, term)
                    if required is not None and required > rank:
                        g.error("wording.exceeds_ceiling",
                                f"{fname} 主张 {cid}（{grade} 档）句中术语 "
                                f"{term!r} 须 {required} 档以上可用，超过该主张"
                                f"措辞上限：降格建议句式：{suggestions}", cid)
    g.details["claim_sentences_checked"] = checked
    return g


# ================================================================ 门四

def gate_landing(pkg) -> GateResult:
    g = GateResult("landing")
    manuscript = pkg["manuscript"]
    files = section_files(pkg["root"])
    items = (pkg["checklist"] or {}).get("items") or []
    declarations = manuscript.get("declarations") or {}
    baseline_missing = []
    for item in items:
        iid = item.get("item_id")
        status = item.get("status")
        if status not in schema.CHECKLIST_STATUSES:
            g.error("landing.status_vocab",
                    f"条目 {iid} status {status!r} 不在词表", iid)
            continue
        if status == "missing":
            g.error("landing.item_missing",
                    f"条目 {iid} 状态为 missing：落点未落实", iid)
            if item.get("tier") == "baseline":
                baseline_missing.append(iid)
            continue
        location = item.get("location")
        if not location:
            g.error("landing.no_location",
                    f"条目 {iid} 无落点登记：检查产物 = 条目→位置映射表，"
                    "无落点即未过门（约束 8）", iid)
            continue
        kind = location.get("kind")
        if kind == "section":
            f = location.get("file")
            anchor = location.get("anchor")
            if f not in files:
                g.error("landing.section_missing",
                        f"条目 {iid} 落点节文件 sections/{f} 不存在", iid)
            elif anchor and anchor not in files[f]:
                g.error("landing.anchor_missing",
                        f"条目 {iid} 落点锚点 {anchor!r} 在 sections/{f} "
                        "中不存在（落点须实位存在）", iid)
        elif kind == "declarations":
            key = location.get("key")
            state = (declarations.get(key) or {}).get("state")
            if state is None:
                g.error("landing.declaration_unknown",
                        f"条目 {iid} 落点声明 {key} 未登记", iid)
            elif state == "absent":
                g.error("landing.declaration_absent",
                        f"条目 {iid} 落点声明 {key} 状态为 absent：落点为空", iid)
        elif kind == "file":
            p = pkg["root"] / str(location.get("path") or "")
            if not p.exists():
                g.error("landing.file_missing",
                        f"条目 {iid} 落点文件 {location.get('path')} 不存在", iid)
        else:
            g.error("landing.kind_vocab",
                    f"条目 {iid} 落点 kind {kind!r} 不在 "
                    "section/declarations/file", iid)
    g.details["items_checked"] = len(items)
    g.details["baseline_missing"] = baseline_missing
    return g


# ================================================================ 主流程

def run_audit(root, online_records=None, relevance=None,
              support=None) -> dict:
    root = Path(root)
    pkg = load_package(root)
    if pkg["manuscript"] is None:
        raise AuditError(["稿件包不存在（先 init）"])
    gates = [
        gate_citations(pkg, online_records=online_records,
                       relevance=relevance, support=support),
        gate_numbers(pkg),
        gate_wording(pkg),
        gate_landing(pkg),
    ]
    report = {
        "kind": "light-write/audit-report",
        "version": "1.0",
        "manuscript_id": pkg["manuscript"].get("manuscript_id"),
        "manuscript_hash": manuscript_hash(root),
        "audited_at": utcnow(),
        "audited_date": today(),
        "online_mode": "injected" if online_records is not None else "offline",
        "overall": "pass" if all(g.status == "pass" for g in gates) else "fail",
        "gates": [g.to_dict() for g in gates],
    }
    audit_dir = root / AUDIT_DIR
    audit_dir.mkdir(exist_ok=True)
    dump_json(audit_dir / REPORT_NAME, report)
    for g in gates:
        (audit_dir / f"gate-{g.gate_id}.md").write_text(
            _render_gate_md(report, g), encoding="utf-8")
    (audit_dir / "AUDIT_SUMMARY.md").write_text(
        _render_summary_md(report), encoding="utf-8")
    return report


def _render_gate_md(report, gate: GateResult) -> str:
    lines = [f"# {schema.AUDIT_GATE_TITLES[gate.gate_id]}", "",
             f"- 稿件哈希：`{report['manuscript_hash'][:16]}…`",
             f"- 判定：**{gate.status}**",
             f"- 时间：{report['audited_at']}", ""]
    if gate.details:
        lines += ["## 明细", "", "```json",
                  json.dumps(gate.details, ensure_ascii=False, indent=2),
                  "```", ""]
    lines.append("## Findings")
    lines.append("")
    if not gate.findings:
        lines.append("（无）")
    for f in gate.findings:
        lines.append(f"- [{f['level']}] `{f['code']}` {f['message']}")
    lines.append("")
    return "\n".join(lines)


def _render_summary_md(report) -> str:
    lines = ["# 审计总判定", "",
             f"- 稿件：{report['manuscript_id']}",
             f"- 稿件哈希：`{report['manuscript_hash']}`",
             f"- 总判定：**{report['overall']}**",
             f"- 在线模式：{report['online_mode']}",
             f"- 时间：{report['audited_at']}", "",
             "| 门 | 判定 | errors | warnings |",
             "|---|---|---|---|"]
    for g in report["gates"]:
        errs = sum(1 for f in g["findings"] if f["level"] == "error")
        warns = sum(1 for f in g["findings"] if f["level"] == "warning")
        lines.append(f"| {g['title']} | {g['status']} | {errs} | {warns} |")
    lines += ["",
              "说明：绿灯只表示未发现自动可判的失败，不表示内容为真"
              "（non-scoring 立场）；稿件任何内容变动后本产物即 STALE。", ""]
    return "\n".join(lines)


def load_audit_report(root):
    path = Path(root) / AUDIT_DIR / REPORT_NAME
    if not path.exists():
        return None
    return load_structured(path)


def audit_status(root) -> dict:
    """审计产物状态：{exists, stale, overall, manuscript_hash, report_hash}。"""
    root = Path(root)
    report = load_audit_report(root)
    if report is None:
        return {"exists": False, "stale": None, "overall": None}
    current = manuscript_hash(root)
    return {
        "exists": True,
        "stale": report.get("manuscript_hash") != current,
        "overall": report.get("overall"),
        "manuscript_hash": report.get("manuscript_hash"),
        "current_hash": current,
        "audited_at": report.get("audited_at"),
    }


def reverify_claim(root, claim_id, by=None) -> dict:
    """主张文本改词后重验贴合度的落字口：更新 text_hash + 落重验记录。

    前提是执行者已实际重验该主张与上游证据的贴合度（规程动作）；
    本命令只落字，不代替重验本身（约束 11 的诚实边界）。
    """
    root = Path(root)
    pkg = load_package(root)
    rows = (pkg["claims"] or {}).get("claims") or []
    for row in rows:
        if row.get("claim_id") == claim_id:
            if not row.get("claim_text"):
                raise AuditError([f"主张 {claim_id} 无 claim_text，无从重验"])
            row["text_hash"] = claim_text_hash(row["claim_text"])
            row["fit_reverified_at"] = today()
            row["fit_reverified_by"] = by or "light-write reverify-claim"
            from .project import save_claims

            save_claims(root, pkg["claims"])
            return {"claim_id": claim_id, "text_hash": row["text_hash"],
                    "fit_reverified_at": row["fit_reverified_at"]}
    raise AuditError([f"主张 {claim_id} 不在主张登记中"])
