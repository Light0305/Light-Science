"""校验器：分析包全部纪律的确定性核查（只拦不赦，约束 13）。

每条纪律对应 REDESIGN-DRAFT / LEARNING 的一条硬约束，逐条有正反例测试。
本模块只做结构与纪律校验——不计算任何统计量、不产生任何判定。
"""

from __future__ import annotations

from . import schema
from .project import current_verdicts, load_package
from .specs import verify_ledger_hash

_EPS = 1e-12


def _scan_text_fields(errors, where, obj, fields):
    for f in fields:
        hits = schema.scan_forbidden(obj.get(f))
        if hits:
            errors.append(
                f"{where} 的 {f} 出现禁用词 {'/'.join(hits)}："
                "强度措辞词表已冻结（禁显著/不显著二分标签与证明了/无影响式"
                "表述，改用象限与强度档位落字）")


def _validate_verdict_row(errors, row, snap_line, families_by_id, spec_ids):
    lid = row.get("registry_line_id")
    verdict = row.get("verdict")
    where = f"判定行 {row.get('row_ref') or lid}"

    if verdict not in schema.VERDICTS:
        errors.append(f"{where}：verdict {verdict!r} 不在受控词表")
        return
    quadrant = row.get("quadrant")
    if quadrant is not None and quadrant not in schema.QUADRANTS:
        errors.append(f"{where}：quadrant {quadrant!r} 不在四象限词表")

    # ---- 承接事实门（约束 10）：作废 / fundamental 行只许 untested
    if snap_line:
        if snap_line.get("void_supported") and verdict != "untested":
            errors.append(
                f"{where}：支撑 run 已全部作废，只许落 untested，"
                f"现落 {verdict}（作废 run 的分布不许进判定）")
        if snap_line.get("fundamental_failure") and verdict != "untested":
            errors.append(
                f"{where}：支撑 run 有 fundamental 失败，主张属未检验，"
                f"只许落 untested，现落 {verdict}（未检验 ≠ 不成立）")

    # ---- 终态行纪律：一等终态须有注、永不入强度档
    if verdict in ("undetermined", "untested"):
        if not (row.get("note") or "").strip():
            errors.append(f"{where}：{verdict} 行必须在 note 注明原因（落字纪律）")
        if row.get("strength_grade") is not None:
            errors.append(
                f"{where}：{verdict} 是判定状态不是强度，不许入强度档")
    if verdict == "undetermined" and quadrant not in (None, "undetermined"):
        errors.append(f"{where}：undetermined 行的 quadrant 只许 undetermined")

    # ---- 强度组：入档须在 4 档词表内
    grade = row.get("strength_grade")
    if grade is not None and grade not in schema.GRADES:
        errors.append(f"{where}：strength_grade {grade!r} 不在 4 档词表")

    # ---- 三向判定行的字段完备
    if verdict in schema.DIRECTIONAL_VERDICTS:
        if not row.get("basis_spec_id"):
            errors.append(f"{where}：{verdict} 行缺 basis_spec_id（判定依据规格）")
        elif spec_ids is not None and row["basis_spec_id"] not in spec_ids:
            errors.append(
                f"{where}：basis_spec_id {row['basis_spec_id']} 不在规格集账本内")
        if not row.get("effect_size") or row["effect_size"].get("value") is None:
            errors.append(f"{where}：{verdict} 行缺 effect_size")
        iv = row.get("interval")
        if not iv or iv.get("lo") is None or iv.get("hi") is None:
            errors.append(f"{where}：{verdict} 行缺 interval（lo/hi）")
        elif iv.get("kind") not in schema.INTERVAL_KINDS:
            errors.append(f"{where}：interval.kind {iv.get('kind')!r} 不在词表")

    if verdict in ("positive", "negative"):
        if quadrant not in ("significant_not_equivalent",
                             "significant_but_equivalent"):
            errors.append(
                f"{where}：{verdict} 行 quadrant 须为 "
                "significant_not_equivalent 或 significant_but_equivalent")
        if verdict == "positive" and row.get("p_ab") is None:
            errors.append(f"{where}：positive 行缺 p_ab（P(A>B) 分布判据值）")

    # ---- positive 校准门（约束 2/11）：Type S/M 三元组 + D 只许外部代入
    if verdict == "positive":
        tsm = row.get("type_sm")
        if not tsm:
            errors.append(f"{where}：positive 行缺 Type S/M 三元组（校准组必填）")
        else:
            for key in ("power", "type_s", "type_m"):
                if tsm.get(key) is None:
                    errors.append(f"{where}：type_sm 缺 {key}")
            assumed = tsm.get("assumed_D") or {}
            basis = str(assumed.get("basis") or "")
            if basis not in schema.POWER_BASIS_OK:
                errors.append(
                    f"{where}：type_sm.assumed_D.basis={basis!r} 不合法，"
                    f"只许 {'/'.join(schema.POWER_BASIS_OK)}"
                    "（D 只许外部代入：冻结 SESOI 或外部先验）")
            from .util import canonical_json
            blob = canonical_json(tsm).lower()
            banned = [b for b in schema.POWER_BASIS_BANNED if b in blob]
            if banned:
                errors.append(
                    f"{where}：type_sm 出现事后功效字样 {'/'.join(banned)}"
                    "（约束 11：禁止用本批数据回代算 observed power）")

    # ---- null 等价门（约束 3）：必须靠 TOST 挣来，bounds 只许冻结 SESOI
    if verdict == "null":
        if quadrant != "equivalent_only":
            errors.append(f"{where}：null 行 quadrant 须为 equivalent_only")
        tost = row.get("tost")
        if not tost:
            errors.append(f"{where}：null 行缺 TOST 组——不显著 ≠ 等价，"
                          "null 必须靠等价检验挣来")
        else:
            bounds = tost.get("bounds") or {}
            if bounds.get("source") not in schema.TOST_BOUNDS_SOURCES_OK:
                errors.append(
                    f"{where}：tost.bounds.source={bounds.get('source')!r} 不合法，"
                    "bounds 只许用 Design 冻结 SESOI（design_sesoi）")
            if tost.get("result") != "pass":
                errors.append(f"{where}：TOST 未通过（result≠pass），不许落 null")
            if tost.get("ci90_in_bounds") is not True:
                errors.append(f"{where}：90% CI 未全落 bounds 内，不许落 null")

    # ---- 贝叶斯诊断门（约束 4）：硬字段先过门才许落判定
    is_bayes = bool(row.get("bayes")) or (
        (row.get("interval") or {}).get("kind") in schema.BAYES_INTERVAL_KINDS)
    diag = row.get("diagnostics")
    if is_bayes and verdict in schema.DIRECTIONAL_VERDICTS + ["undetermined"]:
        if not diag:
            if verdict != "undetermined":
                errors.append(
                    f"{where}：贝叶斯行缺诊断硬字段（r_hat/ess_bulk/ess_tail/mcse），"
                    "不许落判定")
            elif row.get("diagnostics_status") != "missing" \
                    or "诊断" not in (row.get("note") or ""):
                # D-ANA-1：诊断缺失 + undetermined 是合法终态，但必须
                # 机器可读地登记缺失现状且 note 点名，否则无处落脚即死锁
                errors.append(
                    f"{where}：贝叶斯行落 undetermined 也须登记诊断字段现状"
                    "（diagnostics_status=missing 且 note 点名诊断缺失）")
        else:
            missing_keys = [key for key in
                            ("r_hat", "ess_bulk", "ess_tail", "mcse")
                            if diag.get(key) is None]
            if missing_keys and verdict != "undetermined":
                for key in missing_keys:
                    errors.append(f"{where}：diagnostics 缺 {key}")
            if missing_keys and verdict == "undetermined" \
                    and "诊断" not in (row.get("note") or ""):
                errors.append(
                    f"{where}：diagnostics 残缺（缺 "
                    f"{'/'.join(missing_keys)}）落 undetermined 须在 note "
                    "点名诊断现状")
            gate_fail = (
                (diag.get("r_hat") is not None and diag["r_hat"] >= schema.R_HAT_MAX)
                or (diag.get("ess_bulk") is not None and diag["ess_bulk"] <= schema.ESS_MIN)
                or (diag.get("ess_tail") is not None and diag["ess_tail"] <= schema.ESS_MIN))
            if gate_fail and verdict != "undetermined":
                errors.append(
                    f"{where}：诊断未过门（须 rank-normalized R̂<1.01、"
                    "ESS_bulk/ESS_tail 均 >400），只许落 undetermined 并注明")
            if gate_fail and verdict == "undetermined" and \
                    "诊断" not in (row.get("note") or ""):
                errors.append(f"{where}：诊断未过落 undetermined 须在 note 注明诊断未过")

    # ---- 校正组（约束 6）：族须已声明、方法须与族声明一致、p_adj ≥ p_raw
    if verdict in schema.DIRECTIONAL_VERDICTS:
        corr = row.get("correction")
        if not corr:
            errors.append(f"{where}：{verdict} 行缺校正组（family/p_raw/p_adj）")
        else:
            fam = families_by_id.get(corr.get("family_id"))
            if fam is None:
                errors.append(
                    f"{where}：correction.family_id {corr.get('family_id')!r} "
                    "未在登记头校正族声明中")
            elif corr.get("method") != fam.get("method"):
                errors.append(
                    f"{where}：correction.method {corr.get('method')!r} 与族声明 "
                    f"{fam.get('method')!r} 不一致")
            for key in ("p_raw", "p_adj"):
                v = corr.get(key)
                if v is None or not (0.0 <= v <= 1.0):
                    errors.append(f"{where}：correction.{key} 缺失或不在 [0,1]")
            if corr.get("p_raw") is not None and corr.get("p_adj") is not None \
                    and corr["p_adj"] < corr["p_raw"] - _EPS:
                errors.append(f"{where}：p_adj 不应小于 p_raw（校正只许收紧）")

    # ---- 双 n（约束 12）
    if verdict in schema.DIRECTIONAL_VERDICTS:
        if row.get("n_effective") is None or row.get("n_registered") is None:
            errors.append(f"{where}：{verdict} 行须并存 n_effective 与 n_registered"
                          "（按独立重复层级计）")

    _scan_text_fields(errors, where, row,
                      ["note", "strength_cap_reason", "criteria_ref"])


def validate_package(root) -> list[str]:
    """返回错误清单（空 = 合格）。逐条纪律见各段注释。"""
    errors: list[str] = []
    pkg = load_package(root)
    analysis = pkg["analysis"]

    # ---- 文件群齐全
    for key in ("analysis", "verdicts", "spec_ledger", "spec_results",
                "conclusions", "exploratory"):
        if pkg[key] is None:
            errors.append(f"分析包缺文件：{key}")
    if analysis is None:
        return errors

    if analysis.get("status") not in schema.PKG_STATES:
        errors.append(f"登记头 status {analysis.get('status')!r} 不在状态词表")

    # ---- 校正族声明（约束 6）
    families = analysis.get("correction_families") or []
    if analysis.get("execution_ref") and not families:
        errors.append("校正族未声明：承接后 correction_families 不许为空"
                      "（family 是字段，不是调用者的自觉）")
    families_by_id = {}
    for fam in families:
        fid = fam.get("family_id")
        if not fid:
            errors.append("校正族缺 family_id")
            continue
        if fam.get("method") not in schema.CORRECTION_METHODS:
            errors.append(f"校正族 {fid} 的 method {fam.get('method')!r} 不在谱系词表")
        families_by_id[fid] = fam

    # ---- 规格集账本冻结哈希（约束 7）
    ledger = pkg["spec_ledger"]
    spec_ids = None
    if ledger is not None:
        if ledger.get("frozen_hash"):
            ok, detail = verify_ledger_hash(ledger)
            if not ok:
                errors.append(detail)
        spec_ids = {s.get("spec_id") for s in ledger.get("specs") or []
                    if s.get("status") == "included"}

    # ---- 判定回写表
    rows = pkg["verdicts"] or []
    snap_lines = {
        l["registry_line_id"]: l
        for l in (analysis.get("registry_snapshot") or {}).get("lines") or []
    }
    line_ids = set((analysis.get("registry_snapshot") or {}).get("line_ids") or [])

    # row_ref / supersedes 链完整性（改判只增不改）
    seen: dict[str, int] = {}
    last_ref: dict[str, str] = {}
    for row in rows:
        lid = row.get("registry_line_id")
        if line_ids and lid not in line_ids:
            errors.append(
                f"判定行 {lid}：不在登记行集内——判定只认登记行，"
                "分析期新立的行不许进判定（改判据回 Design 走 amendment）")
            continue
        seen[lid] = seen.get(lid, 0) + 1
        expect_ref = f"{lid}#v{seen[lid]}"
        if row.get("row_ref") != expect_ref:
            errors.append(f"判定行 {lid}：row_ref 应为 {expect_ref}，"
                          f"现为 {row.get('row_ref')!r}（只增链被破坏）")
        if seen[lid] > 1 and row.get("supersedes") != last_ref.get(lid):
            errors.append(f"判定行 {expect_ref}：改判行须以 supersedes 指向 "
                          f"{last_ref.get(lid)}")
        if seen[lid] == 1 and row.get("supersedes"):
            errors.append(f"判定行 {expect_ref}：首行不许带 supersedes")
        last_ref[lid] = expect_ref

    current = current_verdicts(rows)
    for lid, row in current.items():
        if lid in line_ids or not line_ids:
            _validate_verdict_row(errors, row, snap_lines.get(lid),
                                  families_by_id, spec_ids)

    # ---- 汇总计数机械复核（不许手填）
    from .project import refresh_counts
    probe = {"registry_snapshot": analysis.get("registry_snapshot") or {}}
    expect = refresh_counts(probe, rows)
    if analysis.get("counts") != expect:
        errors.append(
            f"登记头 counts 与 verdicts 机械汇总不一致："
            f"登记 {analysis.get('counts')} vs 复算 {expect}（汇总区不许手填）")

    # ---- 探索区词表拦截（约束 9 / §2.4）
    exploratory = pkg["exploratory"] or {}
    for entry in exploratory.get("entries") or []:
        eid = entry.get("id")
        if entry.get("exploratory") is not True:
            errors.append(f"探索条目 {eid}：缺 exploratory: true 标记")
        blob = " ".join(str(v) for v in entry.values()
                        if isinstance(v, (str, int, float)))
        hits = schema.scan_banned_words(blob)
        if hits:
            errors.append(
                f"探索条目 {eid}：出现判定/强度词表 {'/'.join(hits)}——"
                "探索区只许叙述性 finding，升格唯一路径是回 Design 走 amendment")

    # ---- 结论包 schema（Phase 1 先定结构与词表纪律）
    conclusions = pkg["conclusions"] or {}
    claim_ids = set(analysis.get("claim_ids") or [])
    for cv in conclusions.get("claims_verdict") or []:
        if not isinstance(cv, dict):
            errors.append("结论包 claims_verdict 条目须为结构化对象"
                          "（{claim_id, support, line_verdicts, …}）")
            continue
        cid = cv.get("claim_id")
        if claim_ids and cid not in claim_ids:
            errors.append(f"结论包 claims_verdict 引用未知主张 {cid}")
        if cv.get("support") not in schema.SUPPORT_VALUES:
            errors.append(
                f"结论包主张 {cid}：support {cv.get('support')!r} 不在词表")
        _scan_text_fields(errors, f"结论包主张 {cid}", cv, ["aggregation_note"])
    for st in conclusions.get("strength") or []:
        if not isinstance(st, dict):
            errors.append("结论包 strength 条目须为结构化对象"
                          "（{claim_id, grade, inputs, cap_reason}）")
            continue
        if st.get("grade") not in schema.GRADES:
            errors.append(
                f"结论包强度 {st.get('claim_id')}：grade {st.get('grade')!r} "
                "不在 4 档词表")
        _scan_text_fields(errors, f"结论包强度 {st.get('claim_id')}", st,
                          ["cap_reason"])
    for b in conclusions.get("boundaries") or []:
        if not isinstance(b, dict):
            errors.append("结论包 boundaries 条目须为结构化对象"
                          "（{claim_id, conditions, not_extrapolatable, "
                          "would_change_if}），不许用自由字符串充数")
            continue
        _scan_text_fields(errors, f"结论包边界 {b.get('claim_id')}", b,
                          ["conditions", "not_extrapolatable", "would_change_if"])
    for prov in conclusions.get("number_provenance") or []:
        if not isinstance(prov, dict):
            errors.append("数字溯源行须为结构化对象"
                          "（{value, verdict_line, registry_line_id, …}）")
            continue
        lid = prov.get("registry_line_id")
        if line_ids and lid not in line_ids:
            errors.append(f"数字溯源行引用未知登记行 {lid}（溯不到源的数字不许进结论包）")

    return errors
