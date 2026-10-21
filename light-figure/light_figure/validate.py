"""校验器：图包全部纪律的确定性核查（只出判定，不改文件）。

分级口径：error = 纪律被破（fail-closed）；warning = 须落字说明或
在后续段门清零的风险。检查范围（Phase 1）：
- 图合同五点完整性（约束 1：缺项逐项点名）与词表（原型/面板角色/
  证据层级/密度取舍）；
- 后端排他（约束 2 / 拍板 D2：同图双后端冲突拦截、R 覆写须带
  条件依据、图行后端与登记不一致报错）；
- 期刊合同数值合法性（约束 14）与容差纪律（拍板 D3：放宽只许
  逐项豁免登记，私自放宽报错）；
- provenance 账（约束 10：method 图在 produced 段起缺参考图哈希
  或重绘源即报错；data 图缺脚本/源数据哈希同理）；
- 承接快照哈希对齐（上游变动即失效，不许静默沿用）；
- 姊妹仓接口引用完整性（条目引用须带 id + 版本，草案 §四）。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import schema
from .project import effective_backend, load_package, provenance_row
from .util import sha256_file

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


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


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _nonempty(x) -> bool:
    return x is not None and x != "" and x != []


# ------------------------------------------------------------ 期刊合同

def check_journal_contract(jc, rep: Report):
    """期刊图形合同登记校验（约束 14 数值合法性 + D3 容差纪律）。"""
    if not isinstance(jc, dict):
        rep.error("journal.not_object", "期刊合同须为对象")
        return
    if not jc.get("registered"):
        rep.warning("journal.not_registered",
                    "期刊合同未登记（骨架缺省值不许当登记值用，"
                    "contracted 门要求 registered=true）")
    if jc.get("registered"):
        for field in ("journal", "version", "checked_at", "source_url"):
            if not _nonempty(jc.get(field)):
                rep.error("journal.field_missing",
                          f"已登记的期刊合同缺字段 {field}",
                          where=f"journal_contract.{field}")

    columns = jc.get("columns_mm") or {}
    for key in ("single", "double"):
        value = columns.get(key)
        if not _is_number(value) or value <= 0:
            rep.error("journal.column_illegal",
                      f"栏宽 columns_mm.{key} 须为正数，实为 {value!r}",
                      where="journal_contract.columns_mm")
    if _is_number(columns.get("single")) and _is_number(columns.get("double")) \
            and columns["double"] <= columns["single"]:
        rep.error("journal.column_order",
                  "双栏宽须大于单栏宽",
                  where="journal_contract.columns_mm")
    max_h = jc.get("max_height_mm")
    if not _is_number(max_h) or max_h <= 0:
        rep.error("journal.max_height_illegal",
                  f"最大高度 max_height_mm 须为正数，实为 {max_h!r}",
                  where="journal_contract.max_height_mm")

    font = jc.get("font") or {}
    for key in ("min_pt", "max_pt", "glyph_floor_pt"):
        value = font.get(key)
        if not _is_number(value) or value <= 0:
            rep.error("journal.font_illegal",
                      f"字号 font.{key} 须为正数，实为 {value!r}",
                      where="journal_contract.font")
    if _is_number(font.get("min_pt")) and _is_number(font.get("max_pt")) \
            and font["min_pt"] > font["max_pt"]:
        rep.error("journal.font_order", "font.min_pt 须 ≤ font.max_pt",
                  where="journal_contract.font")

    formats = jc.get("formats_main")
    if not isinstance(formats, list) or not formats:
        rep.error("journal.formats_empty",
                  "主图格式白名单 formats_main 不许为空",
                  where="journal_contract.formats_main")
    else:
        for fmt in formats:
            if fmt not in schema.KNOWN_EXPORT_FORMATS:
                rep.error("journal.format_unknown",
                          f"主图格式 {fmt!r} 不在已知格式集 "
                          f"{schema.KNOWN_EXPORT_FORMATS}",
                          where="journal_contract.formats_main")

    preview = jc.get("preview") or {}
    if preview.get("tiff_dpi") is not None:
        dpi = preview["tiff_dpi"]
        if not _is_number(dpi) or dpi <= 0:
            rep.error("journal.preview_dpi_illegal",
                      f"预览 TIFF 分辨率须为正数，实为 {dpi!r}",
                      where="journal_contract.preview")

    palettes = jc.get("palettes") or {}
    for slot in ("categorical", "continuous"):
        ref = palettes.get(slot)
        if ref is None:
            continue
        if not isinstance(ref, dict) or not _nonempty(ref.get("entry_id")) \
                or not _nonempty(ref.get("version")):
            rep.error("palette.ref_incomplete",
                      f"色板登记指针 palettes.{slot} 须带 entry_id + version"
                      "（约束 4 登记表消费口径）",
                      where="journal_contract.palettes")

    # ---- 容差纪律（D3）：放宽只许逐项豁免登记
    tolerances = jc.get("tolerances") or {}
    exemptions = {}
    for ex in jc.get("tolerance_exemptions") or []:
        if not isinstance(ex, dict):
            rep.error("tolerance.exemption_malformed",
                      "容差豁免登记条目须为对象 {param, value, reason}")
            continue
        param = ex.get("param")
        if param not in schema.TOLERANCE_PARAMS:
            rep.error("tolerance.exemption_unknown_param",
                      f"豁免参数 {param!r} 不在容差参数集",
                      where="journal_contract.tolerance_exemptions")
            continue
        if not _nonempty(ex.get("reason")):
            rep.error("tolerance.exemption_no_reason",
                      f"容差豁免 {param} 缺理由（放宽只许逐项带理由登记，D3）",
                      where="journal_contract.tolerance_exemptions")
        exemptions[param] = ex
    for param, value in tolerances.items():
        if param not in schema.TOLERANCE_PARAMS:
            rep.error("tolerance.unknown_param",
                      f"容差参数 {param!r} 不在参数集 "
                      f"{sorted(schema.TOLERANCE_PARAMS)}",
                      where="journal_contract.tolerances")
            continue
        if not _is_number(value) or value <= 0:
            rep.error("tolerance.illegal_value",
                      f"容差 {param} 须为正数，实为 {value!r}",
                      where="journal_contract.tolerances")
            continue
        if schema.tolerance_relaxed(param, value):
            ex = exemptions.get(param)
            if ex is None or ex.get("value") != value:
                rep.error(
                    "tolerance.relaxed_without_exemption",
                    f"容差 {param}={value} 宽于全局默认 "
                    f"{schema.TOLERANCE_PARAMS[param]['default']}，"
                    "且无逐项豁免登记（D3：不许改全局默认放行，"
                    "放宽只许 tolerance_exemptions 逐项带理由落字）",
                    where="journal_contract.tolerances")
    font_floor = font.get("glyph_floor_pt")
    tol_floor = tolerances.get("glyph_floor_pt")
    if _is_number(font_floor) and _is_number(tol_floor) \
            and font_floor != tol_floor:
        rep.warning("journal.glyph_floor_mismatch",
                    f"font.glyph_floor_pt={font_floor} 与 "
                    f"tolerances.glyph_floor_pt={tol_floor} 不一致，"
                    "审计门（Phase 2）以 tolerances 值为准，登记时应统一",
                    where="journal_contract")


# ------------------------------------------------------------ 图合同

def check_contract(contract, rep: Report):
    """图合同五点完整性 + 词表（约束 1；草案 §1.2）。"""
    fig_id = contract.get("fig_id") or "?"
    where = f"contracts/{fig_id}.yaml"
    line = contract.get("line")
    if line not in schema.LINES:
        rep.error("contract.line_illegal",
                  f"图 {fig_id} 的 line {line!r} 不在 {schema.LINES}",
                  where=where)
    if not _nonempty(contract.get("core_conclusion")):
        rep.error("contract.five_point_missing",
                  f"图 {fig_id} 五点合同缺 ①核心结论 core_conclusion",
                  where=where)
    if not _nonempty(contract.get("results_question")):
        rep.error("contract.five_point_missing",
                  f"图 {fig_id} 五点合同缺 ①Results 级问题 results_question",
                  where=where)
    archetype = contract.get("archetype")
    if archetype is None:
        rep.error("contract.five_point_missing",
                  f"图 {fig_id} 五点合同缺 ③原型 archetype",
                  where=where)
    elif archetype not in schema.ARCHETYPES:
        rep.error("contract.archetype_vocab",
                  f"图 {fig_id} 的 archetype {archetype!r} 不在四分类 "
                  f"{schema.ARCHETYPES}",
                  where=where)

    panels = contract.get("panel_map")
    if not isinstance(panels, list) or not panels:
        rep.error("contract.five_point_missing",
                  f"图 {fig_id} 五点合同缺 ②证据链 panel_map（每面板一行）",
                  where=where)
    else:
        seen = set()
        for panel in panels:
            if not isinstance(panel, dict):
                rep.error("contract.panel_malformed",
                          f"图 {fig_id} 的 panel_map 条目须为对象",
                          where=where)
                continue
            pid = panel.get("panel_id")
            if not _nonempty(pid):
                rep.error("contract.panel_no_id",
                          f"图 {fig_id} 的 panel_map 条目缺 panel_id",
                          where=where)
            elif pid in seen:
                rep.error("contract.panel_duplicate",
                          f"图 {fig_id} 的 panel_id 重复：{pid}",
                          where=where)
            seen.add(pid)
            if panel.get("role") not in schema.PANEL_ROLES:
                rep.error("contract.panel_role_vocab",
                          f"图 {fig_id} 面板 {pid} 的 role "
                          f"{panel.get('role')!r} 不在十类推理角色词表",
                          where=where)
            if panel.get("evidence_tier") not in schema.EVIDENCE_TIERS:
                rep.error("contract.panel_tier_vocab",
                          f"图 {fig_id} 面板 {pid} 的 evidence_tier "
                          f"{panel.get('evidence_tier')!r} 不在三层级 "
                          f"{schema.EVIDENCE_TIERS}",
                          where=where)
            if not _nonempty(panel.get("content")):
                rep.error("contract.panel_no_content",
                          f"图 {fig_id} 面板 {pid} 缺内容摘要 content",
                          where=where)

    evidence = contract.get("evidence_requirements")
    if not isinstance(evidence, dict):
        rep.error("contract.five_point_missing",
                  f"图 {fig_id} 五点合同缺证据需求 evidence_requirements",
                  where=where)
    else:
        for key in ("statistics", "source_data", "image_integrity_notes"):
            if evidence.get(key) is None:
                rep.error("contract.evidence_missing",
                          f"图 {fig_id} 的 evidence_requirements.{key} 未登记"
                          "（无需求时显式记 \"none\"，不许留空）",
                          where=where)

    stance = contract.get("density_stance") or {}
    if stance.get("stance") not in schema.DENSITY_STANCES:
        rep.error("contract.density_stance",
                  f"图 {fig_id} 的密度取舍 density_stance.stance "
                  f"{stance.get('stance')!r} 不在 {schema.DENSITY_STANCES}"
                  "（约束 7：密度/简洁取舍须按图选边，不许默认）",
                  where=where)
    elif not _nonempty(stance.get("reason")):
        rep.error("contract.density_no_reason",
                  f"图 {fig_id} 的密度取舍缺理由 reason",
                  where=where)

    export_ref = contract.get("export_contract_ref")
    if not isinstance(export_ref, dict) \
            or not _nonempty(export_ref.get("journal_contract")):
        rep.error("contract.five_point_missing",
                  f"图 {fig_id} 五点合同缺 ⑤期刊/导出合同指针 "
                  "export_contract_ref.journal_contract",
                  where=where)
    else:
        for ov in export_ref.get("overrides") or []:
            if not isinstance(ov, dict) or not _nonempty(ov.get("key")) \
                    or not _nonempty(ov.get("reason")):
                rep.error("contract.override_no_reason",
                          f"图 {fig_id} 的导出合同覆写项须带 key + reason",
                          where=where)

    risks = contract.get("reviewer_risk")
    if not isinstance(risks, list) or not risks:
        rep.error("contract.reviewer_risk_missing",
                  f"图 {fig_id} 缺审稿风险自问 reviewer_risk（至少一条）",
                  where=where)
    else:
        for risk in risks:
            if isinstance(risk, dict):
                if not _nonempty(risk.get("risk")) \
                        or not _nonempty(risk.get("disposition")):
                    rep.error("contract.reviewer_risk_malformed",
                              f"图 {fig_id} 的 reviewer_risk 条目须带 "
                              "risk + disposition",
                              where=where)
            elif not _nonempty(risk):
                rep.error("contract.reviewer_risk_malformed",
                          f"图 {fig_id} 的 reviewer_risk 条目为空",
                          where=where)

    integrity = contract.get("data_integrity") or {}
    exclusions = integrity.get("exclusions")
    if exclusions is None:
        rep.error("contract.integrity_undeclared",
                  f"图 {fig_id} 的数据排除未登记（无排除显式记 \"none\"；"
                  "约束 1：不得为画图方便删数据，排除须记前后计数/规则/理由）",
                  where=where)
    elif isinstance(exclusions, list):
        for ex in exclusions:
            if not isinstance(ex, dict) or any(
                    ex.get(k) is None for k in
                    ("before_count", "after_count", "rule", "reason")):
                rep.error("contract.exclusion_malformed",
                          f"图 {fig_id} 的数据排除条目须带 "
                          "before_count/after_count/rule/reason",
                          where=where)

    # 姊妹仓接口引用（草案 §四）：引用在场即须带 id + 版本
    refs = contract.get("sister_library_refs") or {}
    for slot in ("method_gallery", "data_gallery"):
        ref = refs.get(slot)
        if ref is None:
            continue
        if not isinstance(ref, dict) or not _nonempty(ref.get("entry_id")) \
                or not _nonempty(ref.get("version")):
            rep.error("library.ref_incomplete",
                      f"图 {fig_id} 的姊妹仓引用 {slot} 须带 entry_id + "
                      "version（消费登记表不翻仓文件，版本须钉住）",
                      where=where)
    for comp in refs.get("visio_components") or []:
        if not isinstance(comp, dict) \
                or not _nonempty(comp.get("component_id")) \
                or not _nonempty(comp.get("version")):
            rep.error("library.ref_incomplete",
                      f"图 {fig_id} 的 Visio 组件引用须带 "
                      "component_id + version",
                      where=where)
    gallery = refs.get("method_gallery")
    if line == "schematic" and isinstance(gallery, dict):
        # 三元组（D5）：风格锚 ↔ 参考图 ↔ 绑定提示词版本，缺一不可用
        for key in ("style_anchor", "prompt_version"):
            if not _nonempty(gallery.get(key)):
                rep.error("library.triplet_incomplete",
                          f"图 {fig_id} 的图库条目三元组缺 {key}"
                          "（D5：风格锚/参考图/绑定提示词版本缺一不许登记为可用）",
                          where=where)
        # FIG-D09：参考图六维拆解必填（提示词风格段与重绘查表的输入）
        breakdown = gallery.get("reference_breakdown")
        if breakdown is not None or line == "schematic":
            if not isinstance(breakdown, dict):
                rep.error("library.breakdown_missing",
                          f"方法图 {fig_id} 的图库条目缺参考图六维拆解 "
                          "reference_breakdown（FIG-D09：配色/布局流向/"
                          "模块样式/标注方式/信息密度/特殊元素，缺维不许"
                          "登记为可用）",
                          where=where)
            else:
                for dim in schema.REFERENCE_BREAKDOWN_DIMS:
                    value = breakdown.get(dim)
                    if not _nonempty(value):
                        rep.error("library.breakdown_incomplete",
                                  f"图 {fig_id} 的六维拆解缺维度 {dim}"
                                  "（FIG-D09 六维必填）",
                                  where=where)
                    elif dim == "palette_hex":
                        hexes = value if isinstance(value, list) \
                            else [value]
                        for hx in hexes:
                            if not re.match(r"^#[0-9a-fA-F]{6}$",
                                            str(hx)):
                                rep.error(
                                    "library.breakdown_palette_hex",
                                    f"图 {fig_id} 的 palette_hex 条目 "
                                    f"{hx!r} 不是 #RRGGBB 色值",
                                    where=where)

    # FIG-D08：配色决定入合同（双线；缺失 warning，contracted 门清零）
    decision = contract.get("palette_decision")
    if decision is None:
        rep.warning("contract.palette_decision_missing",
                    f"图 {fig_id} 缺配色决定 palette_decision（FIG-D08："
                    "方案来源三选一 + 依据 + 确认记录，contracted 门要求"
                    "已落字）",
                    where=where)
    elif not isinstance(decision, dict):
        rep.error("contract.palette_decision_malformed",
                  f"图 {fig_id} 的 palette_decision 须为对象",
                  where=where)
    else:
        if decision.get("source") not in schema.PALETTE_DECISION_SOURCES:
            rep.error("contract.palette_decision_source",
                      f"图 {fig_id} 的配色决定来源 "
                      f"{decision.get('source')!r} 不在三选一 "
                      f"{schema.PALETTE_DECISION_SOURCES}（FIG-D08）",
                      where=where)
        if not _nonempty(decision.get("basis")):
            rep.error("contract.palette_decision_no_basis",
                      f"图 {fig_id} 的配色决定缺依据 basis（FIG-D08："
                      "决定须带依据，不许只有结论）",
                      where=where)
        conf = decision.get("confirmation") or {}
        if not _nonempty(conf.get("confirmed_by")) \
                or not _nonempty(conf.get("confirmed_at")):
            rep.warning("contract.palette_decision_unconfirmed",
                        f"图 {fig_id} 的配色决定确认记录未落字"
                        "（confirmation.confirmed_by/at，contracted "
                        "门清零）",
                        where=where)

    if line == "schematic":
        backend = contract.get("schematic_backend")
        if backend is not None \
                and backend not in schema.SCHEMATIC_BACKENDS:
            rep.error("contract.schematic_backend_vocab",
                      f"方法图 {fig_id} 的 schematic_backend "
                      f"{backend!r} 不在 {schema.SCHEMATIC_BACKENDS}"
                      "（三路平权：Visio / PowerPoint / Illustrator "
                      "三条原生复刻生产路线对等登记，FIG-D02 后端集 + "
                      "用户 2026-10-21 推翻 FIG-D03 精修定位）",
                      where=where)
        refine = contract.get("illustrator_refinement")
        if refine is not None:
            check_illustrator_refinement(fig_id, refine, rep, where)
    elif contract.get("schematic_backend") is not None:
        rep.error("contract.schematic_backend_on_data",
                  f"数据图 {fig_id} 不许登记 schematic_backend（数据图"
                  "不归 PPT/Visio 方法线后端，FIG-D02 定位）",
                  where=where)

    # 提示词多版变体（2026-10-21 补丁）：合同 prompt_variants 形态——
    # 变体 id 须在词表内、不重复、文件合命名规则、选定须在集合内。
    pv = contract.get("prompt_variants")
    if pv is not None:
        if line != "schematic":
            rep.error("prompt.variants_on_data",
                      f"数据图 {fig_id} 不许登记提示词变体 "
                      "prompt_variants（变体只服务方法图线）",
                      where=where)
        elif not isinstance(pv, dict) \
                or not isinstance(pv.get("variants"), list) \
                or not pv.get("variants"):
            rep.error("prompt.variants_malformed",
                      f"方法图 {fig_id} 的 prompt_variants 须为对象且 "
                      "variants 为非空列表（每版 {variant_id, file, "
                      "version}）",
                      where=where)
        else:
            seen_variants = set()
            for entry in pv.get("variants") or []:
                if not isinstance(entry, dict):
                    rep.error("prompt.variants_malformed",
                              f"方法图 {fig_id} 的变体条目须为对象",
                              where=where)
                    continue
                vid = entry.get("variant_id")
                if vid not in schema.PROMPT_VARIANTS:
                    rep.error("prompt.variant_vocab",
                              f"方法图 {fig_id} 的变体 {vid!r} 不在变体"
                              f"词表 {sorted(schema.PROMPT_VARIANTS)}"
                              "（变体只在构图/密度/布局流向三维上区分）",
                              where=where)
                    continue
                if vid in seen_variants:
                    rep.error("prompt.variant_duplicate",
                              f"方法图 {fig_id} 的变体 {vid} 重复登记",
                              where=where)
                seen_variants.add(vid)
                expected = f"schematic/prompts/{fig_id}.{vid}.md"
                if entry.get("file") != expected:
                    rep.error("prompt.variant_file_mismatch",
                              f"方法图 {fig_id} 变体 {vid} 的文件登记 "
                              f"{entry.get('file')!r} 与命名规则 "
                              f"{expected} 不符",
                              where=where)
            selected = pv.get("selected_variant")
            if selected is not None and selected not in seen_variants:
                rep.error("prompt.selected_variant_unknown",
                          f"方法图 {fig_id} 的 selected_variant "
                          f"{selected!r} 不在已登记变体集合 "
                          f"{sorted(seen_variants)} 内",
                          where=where)

    if line == "schematic":
        policy = contract.get("policy_check")
        if not isinstance(policy, dict):
            rep.error("contract.policy_check_missing",
                      f"方法图 {fig_id} 缺政策门登记 policy_check（约束 8）",
                      where=where)
        else:
            if policy.get("degradation_path") not in schema.DEGRADATION_PATHS:
                rep.error("contract.degradation_vocab",
                          f"方法图 {fig_id} 的 degradation_path "
                          f"{policy.get('degradation_path')!r} 不在 "
                          f"{schema.DEGRADATION_PATHS}",
                          where=where)
            if policy.get("reference_not_in_delivery") is False:
                rep.error("contract.policy_block_failed",
                          f"方法图 {fig_id} 的硬拦自检未过：参考图本体"
                          "不许进交付集（D1 全线唯一政策硬拦）",
                          where=where)
            elif policy.get("reference_not_in_delivery") is None:
                rep.warning("contract.policy_check_unfilled",
                            f"方法图 {fig_id} 的硬拦自检 "
                            "reference_not_in_delivery 未落字",
                            where=where)
            if not _nonempty(policy.get("policy_snapshot_ref")):
                rep.warning("contract.policy_snapshot_unset",
                            f"方法图 {fig_id} 的 policy_check 未指向 "
                            "AI 政策快照（contracted 门要求已落）",
                            where=where)
        palette_conf = contract.get("palette_confirmation") or {}
        if not _nonempty(palette_conf.get("confirmed_by")):
            rep.warning("contract.palette_unconfirmed",
                        f"方法图 {fig_id} 未过配色确认门（约束 7："
                        "角色色板未定不许出提示词，contracted 门清零）",
                        where=where)


def check_illustrator_refinement(fig_id, refine, rep: Report, where):
    """Illustrator 精修段（FIG-D03 遗留合同段）：形态校验（兼容保留）。

    FIG-D03 的精修定位已被用户 2026-10-21 推翻：Illustrator 现为
    第三条生产路线（aibuild 的 ai manifest + ExtendScript 构建 +
    DOM 回读对账，印前五项终检在该 manifest 的 preflight 段）。
    本段仅为 v1.0/v1.1 既有合同的兼容校验而保留，新图不许再以
    精修段代替生产路线登记。
    """
    if not isinstance(refine, dict):
        rep.error("contract.illustrator_malformed",
                  f"方法图 {fig_id} 的 illustrator_refinement 须为对象",
                  where=where)
        return
    if refine.get("planned") is True:
        if not _nonempty(refine.get("entry_svg_ref")):
            rep.error("contract.illustrator_no_entry",
                      f"方法图 {fig_id} 计划 Illustrator 精修但缺入口 "
                      "entry_svg_ref（SVG 桥入口，FIG-D03）",
                      where=where)
        status = refine.get("status") or "planned"
        if status not in schema.ILLUSTRATOR_REFINE_STATUSES:
            rep.error("contract.illustrator_status_vocab",
                      f"方法图 {fig_id} 的精修状态 {status!r} 不在 "
                      f"{schema.ILLUSTRATOR_REFINE_STATUSES}",
                      where=where)
        if status in ("readback_recorded", "done"):
            readback = refine.get("readback") or {}
            for key in ("object_count", "texts_verbatim_checked",
                        "anchor_bbox_checked"):
                if readback.get(key) is None:
                    rep.error("contract.illustrator_readback_incomplete",
                              f"方法图 {fig_id} 精修状态为 {status} 但 "
                              f"DOM 回读记录缺 {key}（FIG-D03 回读对账门"
                              "记录形态）",
                              where=where)
            preflight = readback.get("preflight") or {}
            for item in schema.ILLUSTRATOR_PREFLIGHT_ITEMS:
                if preflight.get(item) is None:
                    rep.error("contract.illustrator_preflight_incomplete",
                              f"方法图 {fig_id} 的印前检查项 {item} "
                              "未落记录（true=检出问题，须处置后才许 "
                              "done）",
                              where=where)
            if status == "done" and any(
                    preflight.get(item) is True
                    for item in schema.ILLUSTRATOR_PREFLIGHT_ITEMS):
                rep.error("contract.illustrator_preflight_open",
                          f"方法图 {fig_id} 印前检查仍有未处置项，"
                          "不许标 done（FIG-D03）",
                          where=where)


# ------------------------------------------------------------ 后端登记

def check_backend(pkg, rep: Report):
    """后端排他（约束 2）+ R 启用条件（拍板 D2）。"""
    reg = pkg["backend"] or {}
    head = pkg["head"] or {}
    rows = {r.get("fig_id"): r for r in head.get("figures") or []}
    package_backend = reg.get("backend")
    if package_backend is not None:
        if package_backend not in schema.BACKENDS:
            rep.error("backend.vocab",
                      f"包级后端 {package_backend!r} 不在 {schema.BACKENDS}",
                      where="backend.json")
        if reg.get("decided_via") not in schema.BACKEND_DECISION_SOURCES:
            rep.error("backend.decision_source",
                      "包级后端已定但 decided_via 不在解析顺序五级词表"
                      "（约束 2：选择须按序决定并落盘）",
                      where="backend.json")
        if package_backend == "r":
            code = reg.get("reason_code")
            if code not in schema.R_ENABLE_CONDITIONS:
                rep.error("backend.r_without_basis",
                          "包级后端为 R 但缺 D2 启用条件依据 reason_code"
                          f"（须为 {sorted(schema.R_ENABLE_CONDITIONS)} 之一）",
                          where="backend.json")
            elif code == "user_specified" \
                    and not _nonempty(reg.get("reason")):
                rep.error("backend.r_without_reason",
                          "包级后端为 R 且依据为 user_specified（用户指定）"
                          "但缺依据说明 reason（D2：用户指定也须落字，"
                          "无 reason 照样拦）",
                          where="backend.json")
    else:
        rep.warning("backend.undecided",
                    "数据图后端尚未决定（contracted 门要求已按解析顺序"
                    "决定并落盘 backend.json）",
                    where="backend.json")

    seen = {}
    for ov in reg.get("overrides") or []:
        if not isinstance(ov, dict):
            rep.error("backend.override_malformed",
                      "后端覆写条目须为对象", where="backend.json")
            continue
        fig_id = ov.get("fig_id")
        backend = ov.get("backend")
        if fig_id not in rows:
            rep.error("backend.override_unknown_figure",
                      f"后端覆写指向未承接的图：{fig_id}",
                      where="backend.json")
            continue
        if rows[fig_id].get("line") == "schematic":
            rep.error("backend.schematic_override",
                      f"方法图 {fig_id} 不许登记数据图后端覆写"
                      "（约束 3：定量图代码分流，方法图不走绘图后端）",
                      where="backend.json")
        if backend not in schema.BACKENDS:
            rep.error("backend.vocab",
                      f"图 {fig_id} 的覆写后端 {backend!r} 不在 "
                      f"{schema.BACKENDS}",
                      where="backend.json")
            continue
        if fig_id in seen:
            if seen[fig_id] != backend:
                rep.error("backend.conflict",
                          f"图 {fig_id} 同图双后端登记冲突："
                          f"{seen[fig_id]} 与 {backend}（约束 2：同图不混后端）",
                          where="backend.json")
            else:
                rep.error("backend.duplicate_override",
                          f"图 {fig_id} 的后端覆写重复登记（{backend}）",
                          where="backend.json")
            continue
        seen[fig_id] = backend
        if backend == "r" and package_backend != "r":
            code = ov.get("reason_code")
            if code not in schema.R_ENABLE_CONDITIONS:
                rep.error("backend.r_without_basis",
                          f"图 {fig_id} 覆写为 R 但 reason_code "
                          f"{code!r} 不在 D2 启用条件 "
                          f"{sorted(schema.R_ENABLE_CONDITIONS)}",
                          where="backend.json")
            if not _nonempty(ov.get("reason")):
                rep.error("backend.r_without_reason",
                          f"图 {fig_id} 覆写为 R 缺依据说明 reason（D2）",
                          where="backend.json")
        if package_backend is not None and backend == package_backend:
            rep.warning("backend.override_redundant",
                        f"图 {fig_id} 的后端覆写与包级默认相同（{backend}），"
                        "冗余登记应删除",
                        where="backend.json")

    # figure.yaml 逐图行后端与登记的一致性（双后端冲突的另一来源）
    for fig_id, row in rows.items():
        if row.get("line") != "data":
            continue
        effective, _ = effective_backend(reg, fig_id)
        declared = row.get("backend")
        if declared is not None and effective is not None \
                and declared != effective:
            rep.error("backend.conflict",
                      f"图 {fig_id} 登记头后端 {declared} 与 backend.json "
                      f"解析结果 {effective} 不一致（同图双后端登记冲突）",
                      where="figure.yaml")
        if declared is not None and declared not in schema.BACKENDS:
            rep.error("backend.vocab",
                      f"图 {fig_id} 登记头后端 {declared!r} 不在 "
                      f"{schema.BACKENDS}",
                      where="figure.yaml")


# ------------------------------------------------------------ provenance

def check_provenance(pkg, rep: Report):
    """provenance 一本账（约束 10）：账行齐备 + produced 段起必填。"""
    head = pkg["head"] or {}
    provenance = pkg["provenance"] or {}
    deep_stages = ("produced", "audited", "delivered")
    for row in head.get("figures") or []:
        fig_id = row.get("fig_id")
        line = row.get("line")
        entry = provenance_row(provenance, fig_id)
        if entry is None:
            rep.error("provenance.row_missing",
                      f"图 {fig_id} 无 provenance 账行（账随图合同开立）",
                      where="provenance.yaml")
            continue
        if entry.get("line") != line:
            rep.error("provenance.line_mismatch",
                      f"图 {fig_id} 账行线别 {entry.get('line')!r} 与"
                      f"登记头 {line!r} 不一致",
                      where="provenance.yaml")
        stage = row.get("stage") or head.get("status")
        deep = stage in deep_stages
        if line == "schematic":
            ref_hash = entry.get("reference_image_hash")
            if ref_hash is not None and not _HEX64.match(str(ref_hash)):
                rep.error("provenance.hash_format",
                          f"方法图 {fig_id} 的参考图哈希不是 SHA-256",
                          where="provenance.yaml")
            if deep and not ref_hash:
                rep.error("provenance.reference_missing",
                          f"方法图 {fig_id} 已进入 {stage} 段但 provenance "
                          "缺参考图哈希（约束 10：账不全不许进 delivered）",
                          where="provenance.yaml")
            redraw = entry.get("redraw_source") or {}
            if deep and (not isinstance(redraw, dict)
                         or not _nonempty(redraw.get("path"))
                         or not _nonempty(redraw.get("hash"))):
                rep.error("provenance.redraw_missing",
                          f"方法图 {fig_id} 已进入 {stage} 段但 provenance "
                          "缺重绘源（redraw_source.path + hash）",
                          where="provenance.yaml")
            label = entry.get("label_check") or {}
            if deep and label.get("done") is not True:
                rep.warning("provenance.label_check_open",
                            f"方法图 {fig_id} 的逐标签核对未完成落字"
                            "（约束 9：照描不核事实是红项）",
                            where="provenance.yaml")
        else:
            for key, code in (("script_hash", "provenance.script_missing"),
                              ("source_data_hash",
                               "provenance.source_data_missing")):
                value = entry.get(key)
                if value is not None and not _HEX64.match(str(value)):
                    rep.error("provenance.hash_format",
                              f"数据图 {fig_id} 的 {key} 不是 SHA-256",
                              where="provenance.yaml")
                if deep and not value:
                    rep.error(code,
                              f"数据图 {fig_id} 已进入 {stage} 段但 "
                              f"provenance 缺 {key}",
                              where="provenance.yaml")


# ------------------------------------------------------------ 登记头

def policy_snapshot_expired(snapshot, today_date=None) -> bool:
    """AI 政策快照是否过期（verified_at + 复核周期，约束 8）。"""
    if not isinstance(snapshot, dict):
        return False
    verified = snapshot.get("verified_at")
    if not verified:
        return False
    try:
        verified_date = date.fromisoformat(str(verified)[:10])
    except ValueError:
        return True
    cycle = snapshot.get("review_cycle_days") \
        or schema.POLICY_REVIEW_CYCLE_DAYS
    today_date = today_date or date.today()
    return (today_date - verified_date).days > cycle


def check_head(pkg, rep: Report):
    head = pkg["head"]
    root = pkg["root"]
    if head.get("status") not in schema.STATES:
        rep.error("package.status_vocab",
                  f"包状态 {head.get('status')!r} 不在 {schema.STATES}",
                  where="figure.yaml")
    intake = head.get("intake")
    if intake is None:
        rep.warning("intake.missing",
                    "尚未承接（intake 为空）：先跑 intake 开立图合同与账行")
    else:
        source_ref = intake.get("source_ref")
        if source_ref:
            source_path = Path(source_ref)
            if not source_path.exists() and (root / source_ref).exists():
                source_path = root / source_ref
            if source_path.exists():
                actual = sha256_file(source_path)
                if actual != intake.get("source_hash"):
                    rep.error("intake.snapshot_drift",
                              "承接源文件哈希与快照不一致：上游已变动，"
                              "承接失效，须重新 intake（不许静默沿用）",
                              where="figure.yaml")
            else:
                rep.warning("intake.source_missing",
                            f"承接源文件已不在原路径：{source_ref}，"
                            "快照哈希无法复验",
                            where="figure.yaml")
    seen = set()
    for row in head.get("figures") or []:
        fig_id = row.get("fig_id")
        if fig_id in seen:
            rep.error("package.figure_duplicate",
                      f"逐图状态表 figure_id 重复：{fig_id}",
                      where="figure.yaml")
        seen.add(fig_id)
        if fig_id not in pkg["contracts"]:
            rep.error("contract.missing_file",
                      f"图 {fig_id} 缺图合同文件 contracts/{fig_id}.yaml",
                      where="figure.yaml")
    for fig_id in pkg["contracts"]:
        if fig_id not in seen:
            rep.warning("contract.orphan",
                        f"图合同 {fig_id} 不在登记头逐图状态表中",
                        where=f"contracts/{fig_id}.yaml")
    target = head.get("target_journal")
    if target is not None:
        snapshot = target.get("ai_policy_snapshot")
        if snapshot is not None:
            missing = [f for f in schema.AI_POLICY_FIELDS
                       if snapshot.get(f) is None
                       and f != "exhibit_exemption"]
            if "exhibit_exemption" not in snapshot:
                missing.append("exhibit_exemption")
            for f in missing:
                rep.error("policy.snapshot_incomplete",
                          f"AI 政策快照缺字段 {f}（约束 8：逐刊核对字段）",
                          where="figure.yaml")
            if policy_snapshot_expired(snapshot):
                rep.warning("policy.expired",
                            "AI 政策快照已过期（verified_at 超过复核周期）："
                            "须按目标刊当期政策原文重新核对（约束 8）",
                            where="figure.yaml")


# ------------------------------------------------------------ 全量

def validate_package(root) -> dict:
    root = Path(root)
    pkg = load_package(root)
    rep = Report()
    if pkg["head"] is None:
        rep.error("package.missing",
                  f"图包不存在或 figure.yaml 缺失：{root}")
        return _report_dict(rep)
    check_head(pkg, rep)
    check_journal_contract(pkg["journal_contract"], rep)
    for fig_id in sorted(pkg["contracts"]):
        check_contract(pkg["contracts"][fig_id], rep)
    check_backend(pkg, rep)
    check_provenance(pkg, rep)
    return _report_dict(rep)


def _report_dict(rep: Report) -> dict:
    return {
        "ok": rep.ok,
        "errors": rep.errors,
        "warnings": rep.warnings,
        "error_count": len(rep.errors),
        "warning_count": len(rep.warnings),
    }
