"""四方对账的逐项检查函数（纯函数：输入结构化数据，输出检查行 + 发现）。

纪律（RV-06/RV-07/RV-08）：
- 检查器是代码，模型只做抽取且保留 raw；本模块不调任何模型；
- 两层分类：数值/指针不一致（error）是第一层门，结论翻转
  （decision_error）只在第一层已成立、且不一致改变了结论强度/支持度/
  符号时才许标——不许无不一致而谈翻转；
- 覆盖自报：每条边返回逐项行，边级分母由 forensic 汇总；
- 判定口径参数化：舍入一律走 grim.rounding_interval（由报告小数位
  导出真值区间），不设拍脑袋阈值。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from . import schema
from .grim import consistent_with_rounding

_RANK = {"pass": 0, "not_assessable": 1, "error": 2, "decision_error": 3}


def _worst(results) -> str:
    return max(results, key=lambda r: _RANK[r]) if results else "pass"


def _finding(check_id, edge, category, layer, detail, claim_pointer=None,
             evidence_pointer=None, raw=None, flag_only=False):
    return {
        "check_id": check_id,
        "edge": edge, "category": category, "layer": layer,
        "detail": detail, "claim_pointer": claim_pointer,
        "evidence_pointer": evidence_pointer, "raw": raw,
        "flag_only": flag_only,
    }


# ================================================================ 边 (a) 主张↔证据

def check_claims_evidence(write_claims, conclusions) -> tuple[list, list]:
    """Write claims_register.writable_form/grade vs Analysis 结论卡上限复核。

    复核而非重做（草案 §五）：Write 的措辞门已管正文句子，Review 只验
    跨包一致性——结论行存在否、grade 与 support 是否被登记侧改写、
    writable_form 是否越过登记的 writable_ceiling。
    """
    checks, findings = [], []
    verdicts = {c.get("claim_id"): c
                for c in (conclusions or {}).get("claims_verdict") or []}
    grades = {s.get("claim_id"): s.get("grade")
              for s in (conclusions or {}).get("strength") or []}
    for i, claim in enumerate(write_claims or []):
        cid = claim.get("claim_id")
        check_id = f"F-CE-{i + 1:03d}"
        ref = claim.get("analysis_claim_ref") or cid
        results, details = [], []
        concl = verdicts.get(ref)
        if concl is None:
            checks.append(schema.check_row(
                check_id, "claims_evidence", cid, "error",
                detail=f"主张 {cid} 回指的结论行 {ref} 在 Analysis 结论卡中不存在",
                claim_pointer=f"claims_register:{cid}",
                evidence_pointer=f"conclusions:{ref}"))
            findings.append(_finding(
                    check_id, "claims_evidence", "unresolved_input", "inconsistency",
                f"主张 {cid} 的证据指针 {ref} 无着落",
                claim_pointer=f"claims_register:{cid}",
                evidence_pointer=f"conclusions:{ref}"))
            continue
        # grade 一致性（登记侧不许改写结论卡强度档）
        w_grade = claim.get("strength_grade")
        a_grade = grades.get(ref)
        if w_grade is not None and a_grade is not None and w_grade != a_grade:
            results.append("decision_error")
            details.append(f"强度档不一致：登记 {w_grade} vs 结论卡 {a_grade}")
            findings.append(_finding(
                    check_id, "claims_evidence", "confirmed_error", "conclusion_flip",
                f"主张 {cid} 强度档被登记侧改写：{w_grade} ≠ 结论卡 {a_grade}",
                claim_pointer=f"claims_register:{cid}",
                evidence_pointer=f"conclusions.strength:{ref}",
                raw=f"writable grade={w_grade}, analysis grade={a_grade}"))
        # support 一致性（upstream_status 是登记侧对结论 support 的转述）
        support = concl.get("support")
        upstream = claim.get("upstream_status")
        if upstream is not None and support is not None and upstream != support:
            results.append("decision_error")
            details.append(f"支持度不一致：登记 {upstream} vs 结论卡 {support}")
            findings.append(_finding(
                    check_id, "claims_evidence", "confirmed_error", "conclusion_flip",
                f"主张 {cid} 支持度转述失真：{upstream} ≠ 结论卡 {support}",
                claim_pointer=f"claims_register:{cid}",
                evidence_pointer=f"conclusions.claims_verdict:{ref}",
                raw=f"upstream_status={upstream}, support={support}"))
        # 逐行判定一致性
        w_lines = claim.get("line_verdicts") or {}
        a_lines = concl.get("line_verdicts") or {}
        for lid, wv in w_lines.items():
            av = a_lines.get(lid)
            if av is not None and av != wv:
                results.append("error")
                details.append(f"登记行 {lid} 判定不一致：{wv} vs {av}")
                findings.append(_finding(
                        check_id, "claims_evidence", "confirmed_error", "inconsistency",
                    f"主张 {cid} 的登记行 {lid} 判定被改写：{wv} ≠ {av}",
                    claim_pointer=f"claims_register:{cid}",
                    evidence_pointer=f"conclusions.claims_verdict:{ref}#{lid}",
                    raw=f"{lid}: write={wv}, analysis={av}"))
        # writable_form 不许越过登记上限（形态序：full 最强）
        form = claim.get("writable_form")
        ceiling = claim.get("writable_ceiling")
        if form in schema.WRITABLE_FORMS and ceiling in schema.WRITABLE_FORMS:
            if schema.form_rank(form) < schema.form_rank(ceiling):
                results.append("decision_error")
                details.append(
                    f"writable_form={form} 越过上限 writable_ceiling={ceiling}")
                findings.append(_finding(
                        check_id, "claims_evidence", "confirmed_error", "conclusion_flip",
                    f"主张 {cid} 呈现形态 {form} 越过结论强度上限 {ceiling}",
                    claim_pointer=f"claims_register:{cid}",
                    evidence_pointer=f"conclusions.strength:{ref}",
                    raw=f"form={form}, ceiling={ceiling}"))
        result = _worst(results) if results else "pass"
        checks.append(schema.check_row(
            check_id, "claims_evidence", cid, result,
            detail="；".join(details) if details else
                   "结论行存在，grade/support/逐行判定/形态上限一致",
            claim_pointer=f"claims_register:{cid}",
            evidence_pointer=f"conclusions:{ref}"))
    return checks, findings


# ================================================================ 边 (b) 数字↔数字

_NUM_MARKER = r"\[num:(?:{})\]\s*(\S+)"


def _spec_value(spec_results, spec_id, line_id):
    for row in spec_results or []:
        if row.get("spec_id") == spec_id and \
                row.get("registry_line_id") == line_id and \
                row.get("status") == "computed":
            es = row.get("effect_size") or {}
            if es.get("value") is not None:
                return es["value"], f"spec_results:{spec_id}@{line_id}"
    return None, None


def _provenance_value(provenance, spec_id, line_id):
    for row in provenance or []:
        if row.get("registry_line_id") == line_id and \
                (spec_id is None or row.get("spec_id") == spec_id) and \
                row.get("value") is not None:
            return row["value"], f"number_provenance:{line_id}"
    return None, None


def _sign_flip(printed, recomputed) -> bool:
    try:
        p = Decimal(str(printed))
        r = Decimal(str(recomputed))
    except InvalidOperation:
        return False
    if (p == 0) != (r == 0):
        return True
    return p * r < 0


def check_numbers_numbers(numbers, sections_text, spec_results,
                          provenance) -> tuple[list, list]:
    """numbers_ledger 登记值 vs 正文呈现值 vs Analysis 登记派生量复算。

    复算对象是登记过的派生数（statcheck 方法的正确投影）：呈现值由
    其小数位导出真值区间，复算值落区间内才一致（RV-08）。
    """
    checks, findings = [], []
    joined = "\n".join((sections_text or {}).values())
    for i, num in enumerate(numbers or []):
        nid = num.get("num_id")
        check_id = f"F-NN-{i + 1:03d}"
        printed = num.get("value_as_printed")
        results, details = [], []
        # ---- 呈现值对账：正文 [num:N###] 标记后的实印值
        occurrences = re.findall(_NUM_MARKER.format(re.escape(nid)), joined)
        locations = num.get("locations") or []
        if not occurrences:
            if locations:
                results.append("error")
                details.append("登记了出现位置但正文未见 [num:] 标记实印值")
                findings.append(_finding(
                        check_id, "numbers_numbers", "provenance_gap", "inconsistency",
                    f"数字 {nid} 登记位置与正文实印对不上（无标记出现）",
                    evidence_pointer=f"numbers_ledger:{nid}"))
            else:
                results.append("not_assessable")
                details.append("登记数字未被正文引用，无呈现值可对账")
        else:
            bad = [o for o in occurrences if o != str(printed)]
            if bad:
                results.append("error")
                details.append(
                    f"正文实印值 {bad} ≠ 登记值 {printed}")
                findings.append(_finding(
                        check_id, "numbers_numbers", "confirmed_error", "inconsistency",
                    f"数字 {nid} 正文实印 {bad[0]} ≠ 登记 {printed}",
                    evidence_pointer=f"numbers_ledger:{nid}",
                    raw=f"[num:{nid}] {bad[0]}"))
            else:
                details.append(f"呈现值 {printed} 与正文 {len(occurrences)} 处一致")
        # ---- 复算对账：登记派生量经舍入区间判定
        spec_id = num.get("spec_ref")
        line_id = num.get("verdict_ref")
        true_val, src = _spec_value(spec_results, spec_id, line_id)
        if true_val is None:
            true_val, src = _provenance_value(provenance, spec_id, line_id)
        if true_val is None:
            results.append("not_assessable")
            details.append("无登记复算源（spec_results/number_provenance 均无）")
            if line_id:
                findings.append(_finding(
                        check_id, "numbers_numbers", "provenance_gap", "inconsistency",
                    f"数字 {nid} 回指 {line_id} 但 Analysis 无对应溯源/规格结果",
                    evidence_pointer=f"numbers_ledger:{nid}"))
        else:
            ok = consistent_with_rounding(printed, true_val)
            if ok is None:
                results.append("not_assessable")
                details.append("登记值非数值，无法导出舍入区间")
            elif not ok:
                flip = _sign_flip(printed, true_val)
                results.append("decision_error" if flip else "error")
                details.append(
                    f"复算值 {true_val}（{src}）落在呈现值 {printed} 的"
                    "舍入区间外" + ("，且符号翻转" if flip else ""))
                findings.append(_finding(
                        check_id, "numbers_numbers", "confirmed_error",
                    "conclusion_flip" if flip else "inconsistency",
                    f"数字 {nid} 呈现值 {printed} 与复算值 {true_val} 不一致",
                    evidence_pointer=src,
                    raw=f"printed={printed}, recomputed={true_val}"))
            else:
                details.append(f"复算值 {true_val}（{src}）与呈现值舍入相容")
        checks.append(schema.check_row(
            check_id, "numbers_numbers", nid, _worst(results),
            detail="；".join(details),
            evidence_pointer=f"numbers_ledger:{nid}"))
    return checks, findings


# ================================================================ 边 (c) 数字↔图

def _fig_key(fig_id, display_number=None):
    if display_number is not None:
        return int(display_number)
    m = re.search(r"(\d+)\s*$", str(fig_id or ""))
    return int(m.group(1)) if m else None


def _correspondence_parts(fig_row) -> dict | None:
    """提取 delivery 图行的对应件清单（v1.1 REV-D09 消费侧）。

    契约（figure 侧构建单 F9）：correspondence = 源资产清单（路径 +
    SHA-256）到交付文件的映射 + 内容级哈希（数据图 = 量测面板结构
    哈希；方法图 = 反抽形状清单哈希），缺件落 null + note。键名按
    语义多形兼容读取，读不到清单即返回 None（维持 not_assessable，
    不冒充已检）；确切键名留全套第 6 步跨包总核按实物复核。
    """
    corr = (fig_row or {}).get("correspondence")
    if not isinstance(corr, dict):
        return None
    sources = (corr.get("source_assets") or corr.get("sources")
               or corr.get("assets") or [])
    deliverables = (corr.get("deliverables")
                    or corr.get("delivered_files")
                    or corr.get("mapping") or [])
    # 内容级哈希：单值 content_hash，或分项字典 content_hashes
    # （figure 封版实物形态：{面板名: 结构哈希}）——统一收成集合，
    # 稿件侧登记值命中集合任一即视为内容级一致。
    content_hashes = set()
    if isinstance(corr.get("content_hash"), str):
        content_hashes.add(corr["content_hash"])
    ch = corr.get("content_hashes")
    if isinstance(ch, dict):
        content_hashes |= {v for v in ch.values() if isinstance(v, str)}
    elif isinstance(ch, list):
        content_hashes |= {v for v in ch if isinstance(v, str)}
    if isinstance(deliverables, list):
        for d in deliverables:
            if isinstance(d, dict) and isinstance(d.get("content_hash"),
                                                  str):
                content_hashes.add(d["content_hash"])
    source_shas = set()
    for s in sources if isinstance(sources, list) else []:
        if isinstance(s, dict):
            h = s.get("sha256") or s.get("hash")
            if h:
                source_shas.add(h)
    return {"source_shas": source_shas,
            "deliverables": deliverables if isinstance(deliverables, list)
            else [],
            "content_hashes": content_hashes,
            "note": corr.get("note")}


def check_numbers_figures(manifest_figures, delivery, ledger_values
                          ) -> tuple[list, list]:
    """Figure delivery ↔ 稿件引用侧（figures_manifest）。

    Figure 审计已做图内侧，Review 补引用侧（草案 §五）：对应存在性、
    文件哈希对应（同名文件）、图注未登记数字。
    """
    checks, findings = [], []
    if delivery is None:
        for i, fig in enumerate(manifest_figures or []):
            checks.append(schema.check_row(
                f"F-NF-{i + 1:03d}", "numbers_figures",
                fig.get("figure_id"), "not_assessable",
                detail="图包未承接，本边无对账物料",
                evidence_pointer="figures_manifest:"
                                 + str(fig.get("figure_id"))))
        return checks, findings
    dfigs = {}
    for df in delivery.get("figures") or []:
        key = _fig_key(df.get("fig_id"))
        if key is not None:
            dfigs[key] = df
    for i, fig in enumerate(manifest_figures or []):
        fid = fig.get("figure_id")
        check_id = f"F-NF-{i + 1:03d}"
        key = _fig_key(fid, fig.get("display_number"))
        results, details = [], []
        df = dfigs.get(key)
        if df is None:
            checks.append(schema.check_row(
                check_id, "numbers_figures", fid, "error",
                detail=f"稿件图 {fid} 在 Figure delivery 中无对应图",
                evidence_pointer=f"figures_manifest:{fid}"))
            findings.append(_finding(
                    check_id, "numbers_figures", "unresolved_input", "inconsistency",
                f"稿件图 {fid} 的图包对应缺失",
                evidence_pointer=f"figures_manifest:{fid}"))
            continue
        # 文件哈希对应（同名文件）
        src_hash = fig.get("source_hash")
        src_base = (fig.get("source_ref") or "").rsplit("/", 1)[-1]
        matched = None
        for f in df.get("files") or []:
            if (f.get("path") or "").rsplit("/", 1)[-1] == src_base and src_base:
                matched = f
        hash_done = False
        if src_hash and matched:
            hash_done = True
            if matched.get("sha256") != src_hash:
                results.append("error")
                details.append(
                    f"文件 {src_base} 哈希不一致：稿件侧 {src_hash[:12]}… "
                    f"vs 图包 {str(matched.get('sha256'))[:12]}…")
                findings.append(_finding(
                        check_id, "numbers_figures", "confirmed_error", "inconsistency",
                    f"图 {fid} 的文件 {src_base} 两侧哈希不一致",
                    evidence_pointer=f"delivery:{df.get('fig_id')}",
                    raw=f"manifest={src_hash}, delivery={matched.get('sha256')}"))
            else:
                details.append(f"文件 {src_base} 哈希两侧一致")
        if not hash_done:
            # 对应件清单消费（REV-D09）：源资产与交付件异名异格式时，
            # 字节哈希无从比对——改走清单：稿件侧 source_hash 命中
            # 图包源资产清单 = 源链真检；清单自相矛盾 / 内容级哈希
            # 与稿件登记不符 = error；清单未覆盖 = 维持未检并落字。
            parts = _correspondence_parts(df)
            if parts is None:
                results.append("not_assessable")
                details.append("无同名文件或稿件侧未登记 source_hash，"
                               "哈希对应未检")
            else:
                if src_hash and src_hash in parts["source_shas"]:
                    details.append(
                        "对应件清单源链真检通过：稿件侧源资产哈希命中"
                        "图包源资产清单（异名异格式经清单闭合）")
                    hash_done = True
                elif src_hash and parts["source_shas"]:
                    results.append("not_assessable")
                    details.append(
                        "对应件清单未覆盖稿件侧登记源资产"
                        "（source_hash 不在源资产清单内）：清单未覆盖"
                        "不等于不符，哈希对应维持未检")
                elif src_hash:
                    results.append("not_assessable")
                    details.append(
                        "对应件清单在册但源资产缺件"
                        f"（note：{parts['note'] or '图包未登记'}）"
                        "：哈希对应维持未检")
                # 清单内部一致性：交付映射哈希须与 files 清单对得上
                files_by_base = {
                    (f.get("path") or "").rsplit("/", 1)[-1]: f
                    for f in df.get("files") or []}
                for d in parts["deliverables"]:
                    if not isinstance(d, dict):
                        continue
                    base = (d.get("path") or "").rsplit("/", 1)[-1]
                    f = files_by_base.get(base)
                    d_hash = d.get("sha256") or d.get("hash")
                    if f is not None and d_hash \
                            and f.get("sha256") != d_hash:
                        results.append("error")
                        details.append(
                            f"对应件清单称交付文件 {base} 哈希 "
                            f"{str(d_hash)[:12]}… 与 delivery files 清单 "
                            f"{str(f.get('sha256'))[:12]}… 自相矛盾")
                        findings.append(_finding(
                                check_id, "numbers_figures",
                                "provenance_gap", "inconsistency",
                            f"图 {fid} 的对应件清单与交付文件清单哈希"
                            "自相矛盾",
                            evidence_pointer=f"delivery:{df.get('fig_id')}",
                            raw=f"correspondence={d_hash}, "
                                f"files={f.get('sha256')}"))
                # 内容级哈希：稿件侧有登记才许比对，无登记只留痕
                m_hash = fig.get("content_hash")
                if parts["content_hashes"] and m_hash:
                    if m_hash not in parts["content_hashes"]:
                        results.append("error")
                        details.append(
                            "内容级哈希不一致：稿件侧登记 "
                            f"{str(m_hash)[:12]}… 不在图包对应件清单的"
                            "内容级哈希集内")
                        findings.append(_finding(
                                check_id, "numbers_figures",
                                "confirmed_error", "inconsistency",
                            f"图 {fid} 内容级哈希两侧不一致",
                            evidence_pointer=f"delivery:{df.get('fig_id')}",
                            raw=f"manifest={m_hash}, "
                                f"correspondence="
                                f"{sorted(parts['content_hashes'])}"))
                    else:
                        details.append("内容级哈希两侧一致"
                                       "（量测面板/形状清单结构哈希）")
                        hash_done = True
                elif parts["content_hashes"]:
                    details.append(
                        "内容级哈希由图包在对应件清单声明（稿件侧无"
                        "对应登记，仅留痕不作比对）")
                if not hash_done and "not_assessable" not in results:
                    results.append("not_assessable")
                    details.append("对应件清单未提供可比对锚点，"
                                   "哈希对应维持未检")
        # 图注未登记数字（只查小数形态，整数多为编号/年份不硬判）
        caption = fig.get("caption") or ""
        decimals = re.findall(r"\d+\.\d+", caption)
        unregistered = [t for t in decimals
                        if t not in (ledger_values or set())]
        if unregistered:
            results.append("error")
            details.append(f"图注出现未登记数字：{unregistered}")
            for t in unregistered:
                findings.append(_finding(
                        check_id, "numbers_figures", "provenance_gap", "inconsistency",
                    f"图 {fid} 图注数字 {t} 未在 numbers_ledger 登记",
                    evidence_pointer=f"figures_manifest:{fid}",
                    raw=f"caption token {t}"))
        elif decimals:
            details.append("图注数字均已登记")
        checks.append(schema.check_row(
            check_id, "numbers_figures", fid, _worst(results),
            detail="；".join(details) if details else "对应存在",
            evidence_pointer=f"figures_manifest:{fid}"))
    return checks, findings


# ================================================================ 边 (d) 引用↔主张

_CITE_KEY = re.compile(r"\[@([^\]]+)\]")


def check_citations_claims(sections_text, lock_entries, write_claims,
                           conclusion_line_ids, audit_archive_present
                           ) -> tuple[list, list]:
    """只验 Write 已归档的核对指针存在性，不重做引用核对（草案 §五）。

    三组指针：正文 [@key] → references.lock 条目（含归档 entry_hash）；
    主张 evidence_refs → Analysis 登记行；Write 审计归档件存在性。
    """
    checks, findings = [], []
    lock = {e.get("key"): e for e in lock_entries or []}
    joined = "\n".join((sections_text or {}).values())
    cited = sorted(set(_CITE_KEY.findall(joined)))
    for i, key in enumerate(cited):
        check_id = f"F-CC-{i + 1:03d}"
        entry = lock.get(key)
        if entry is None:
            checks.append(schema.check_row(
                check_id, "citations_claims", f"[@{key}]", "error",
                detail=f"正文引用键 {key} 在 references.lock 中无条目",
                evidence_pointer=f"sections:[@{key}]"))
            findings.append(_finding(
                    check_id, "citations_claims", "unresolved_input", "inconsistency",
                f"引用指针 [@{key}] 无着落（lock 无此键）",
                evidence_pointer=f"sections:[@{key}]"))
        elif not entry.get("entry_hash"):
            checks.append(schema.check_row(
                check_id, "citations_claims", f"[@{key}]", "not_assessable",
                detail=f"lock 条目 {key} 缺 entry_hash：归档核对指针不完整",
                evidence_pointer=f"references.lock:{key}"))
            findings.append(_finding(
                    check_id, "citations_claims", "provenance_gap", "inconsistency",
                f"引用 {key} 的归档核对指针（entry_hash）缺失",
                evidence_pointer=f"references.lock:{key}"))
        else:
            checks.append(schema.check_row(
                check_id, "citations_claims", f"[@{key}]", "pass",
                detail="lock 条目与归档哈希指针齐",
                evidence_pointer=f"references.lock:{key}"))
    base = len(cited)
    for j, claim in enumerate(write_claims or []):
        cid = claim.get("claim_id")
        check_id = f"F-CC-{base + j + 1:03d}"
        refs = []
        for er in claim.get("evidence_refs") or []:
            refs += list(er.get("refs") or [])
        missing = [r for r in refs if r not in (conclusion_line_ids or set())]
        if missing:
            checks.append(schema.check_row(
                check_id, "citations_claims", cid, "error",
                detail=f"主张 {cid} 的 evidence_refs 指向不存在的登记行：{missing}",
                claim_pointer=f"claims_register:{cid}"))
            findings.append(_finding(
                    check_id, "citations_claims", "unresolved_input", "inconsistency",
                f"主张 {cid} 证据指针 {missing} 在结论卡登记行中不存在",
                claim_pointer=f"claims_register:{cid}"))
        else:
            checks.append(schema.check_row(
                check_id, "citations_claims", cid, "pass",
                detail="evidence_refs 全部指向现存登记行" if refs
                       else "无 evidence_refs 登记（按登记现状记 pass-through）",
                claim_pointer=f"claims_register:{cid}"))
    audit_id = f"F-CC-{base + len(write_claims or []) + 1:03d}"
    checks.append(schema.check_row(
        audit_id,
        "citations_claims", "write_audit_archive",
        "pass" if audit_archive_present else "not_assessable",
        detail="Write 审计归档件存在，核对指针可回溯"
               if audit_archive_present else
               "Write 审计归档件（audit/audit_report.json）缺失，"
               "已归档核对无从指认",
        evidence_pointer="manuscript:audit/"))
    if not audit_archive_present:
        findings.append(_finding(
                audit_id, "citations_claims", "not_assessable", "inconsistency",
            "Write 审计归档件缺失，引用核对指针链不完整",
            evidence_pointer="manuscript:audit/"))
    return checks, findings
