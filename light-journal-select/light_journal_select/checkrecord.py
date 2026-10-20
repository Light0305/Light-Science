"""Write 九组（A–I）目标刊核查记录的生成与自检（Phase 2）。

字段口径以 light-write 的 `light_write/template_reg.py` +
`validate.check_template_record` + `schema.TEMPLATE_GROUPS`
为唯一权威（46 顶层字段、九组）。本模块不 import light_write
（产品代码不形成跨包运行时依赖）：

- 本地结构校验 `check_record_structure`：把 Write 校验器的
  error 级规则（组/必填字段、D 组限额至少一项且全数值、G 组
  AI 政策子字段与披露位置、H 组 verified_at 形态、词表值）
  在本包内镜像执行，错误码与 Write 同名，handoff 有 error
  不许进入 handed_off；
- 可选外部自检钩子 `run_write_selfcheck`：以子进程 + sys.path
  路径注入调用真正的 Write `check_template_record`（测试与
  操作员显式 --write-root 时用），结果原样回带。

记录生成分工：A 组身份字段由选刊包机械回填（刊名/ISSN/
出版商来自候选，journal_language 强制等于稿件指纹语言——
一篇稿一个语言）；B–I 的指南派生字段由执行者读官网作者
指南后经字段文件提供，工具不许凭空编造指南事实。H 组时效
字段由工具按交接当日落字。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .gates import GateError
from .util import component_hash, sha256_text, today
from .verify import Report

# ------------------------------------------------- 本地镜像口径
# 与 light_write.schema.TEMPLATE_GROUPS 对齐（组名/必填/全字段）。
# 姊妹包改口径时此处须同步；外部自检钩子负责兜底检出漂移。
TEMPLATE_GROUPS = {
    "A": {"name": "身份与版本",
          "required": ["record_id", "journal_name", "publisher",
                       "template_version", "journal_language"],
          "fields": ["record_id", "journal_name", "issn", "eissn",
                     "publisher", "journal_group", "template_version",
                     "applicable_years", "journal_language"]},
    "B": {"name": "格式轨与选项轴",
          "required": ["format_track"],
          "fields": ["format_track", "latex_class", "class_version",
                     "options_axis", "word_template",
                     "citation_package"]},
    "C": {"name": "栏目与结构",
          "required": ["section_sequence"],
          "fields": ["section_sequence", "abstract_form",
                     "keyword_limit", "special_sections"]},
    "D": {"name": "限额（数值化）",
          "required": [],
          "fields": ["word_limit_total", "word_limit_abstract",
                     "page_limit", "figure_limit", "table_limit",
                     "reference_limit", "title_char_limit",
                     "short_title_char_limit"],
          "at_least_one": True},
    "E": {"name": "参考文献",
          "required": ["style_name", "csl_id"],
          "fields": ["style_name", "csl_id", "bst_name",
                     "citation_style_kind"]},
    "F": {"name": "图件",
          "required": ["figure_submission_mode"],
          "fields": ["figure_submission_mode", "figure_formats",
                     "figure_resolution", "caption_position"]},
    "G": {"name": "声明与披露",
          "required": ["declarations", "ai_policy"],
          "fields": ["declarations", "ai_policy"],
          "ai_policy_required": ["has_guideline", "disclosure_required"]},
    "H": {"name": "来源与时效",
          "required": ["source_url", "official_channel", "verified_at"],
          "fields": ["source_url", "official_channel", "verified_at",
                     "review_cycle_days", "verified_by", "bundled"]},
    "I": {"name": "条款",
          "required": ["redistribution"],
          "fields": ["redistribution", "terms_pointer",
                     "purpose_restriction"]},
}

FORMAT_TRACKS = ["latex", "word"]
LANGUAGES = ["en", "zh"]
REDISTRIBUTION_VALUES = ["packageable", "channel_only", "prohibited"]
BUNDLED_VALUES = ["official", "generic_scaffold"]

# E5 缺省口径：模板/指南只用不分发——条款组未逐项核实时取最
# 保守的 channel_only，不许默认成可打包。
DEFAULT_REDISTIBUTION = "channel_only"
DEFAULT_PURPOSE_RESTRICTION = "submission use only"
DEFAULT_REVIEW_CYCLE_DAYS = 180


def record_id_for(selection: dict, candidate: dict, today_str: str) -> str:
    digest = sha256_text(
        f"{selection.get('selection_id')}|{candidate.get('candidate_id')}"
    )[:6]
    return f"TR-{today_str[:4]}-{digest}"


def build_check_record(selection: dict, candidate: dict,
                       fields: dict | None,
                       today_str: str | None = None) -> tuple[dict, list[str]]:
    """组装九组记录。返回 (record, gaps)：语言冲突等装配级
    缺口单列 gaps；字段完整性由 check_record_structure 判。"""
    today_str = today_str or today()
    fields = fields or {}
    gaps: list[str] = []
    manuscript = selection.get("manuscript") or {}
    language = manuscript.get("language")
    fa = fields.get("A") or {}
    if fa.get("journal_language") not in (None, language):
        gaps.append(
            f"字段文件 A.journal_language={fa.get('journal_language')!r} "
            f"与稿件指纹语言 {language!r} 不一致（一篇稿一个语言，"
            "记录语言以稿件为准——请核对是否拿错刊的指南）")
    group_h_in = fields.get("H") or {}
    record = {
        "A": {
            "record_id": record_id_for(selection, candidate, today_str),
            "journal_name": candidate.get("name"),
            "issn": candidate.get("issn"),
            "eissn": candidate.get("eissn"),
            "publisher": candidate.get("publisher"),
            "journal_group": fa.get("journal_group"),
            "template_version": fa.get("template_version"),
            "applicable_years": fa.get("applicable_years")
                or [int(today_str[:4])],
            "journal_language": language,
        },
        "B": dict(fields.get("B") or {}),
        "C": dict(fields.get("C") or {}),
        "D": dict(fields.get("D") or {}),
        "E": dict(fields.get("E") or {}),
        "F": dict(fields.get("F") or {}),
        "G": dict(fields.get("G") or {}),
        "H": {
            "source_url": group_h_in.get("source_url")
                or candidate.get("guide_url")
                or candidate.get("homepage_url"),
            "official_channel": group_h_in.get("official_channel")
                or "journal homepage",
            "verified_at": today_str,
            "review_cycle_days": group_h_in.get("review_cycle_days")
                or DEFAULT_REVIEW_CYCLE_DAYS,
            "verified_by": group_h_in.get("verified_by")
                or "light-journal-select handoff",
            "bundled": group_h_in.get("bundled") or "official",
        },
        "I": {
            "redistribution": (fields.get("I") or {}).get("redistribution")
                or DEFAULT_REDISTIBUTION,
            "terms_pointer": (fields.get("I") or {}).get("terms_pointer")
                or candidate.get("homepage_url"),
            "purpose_restriction": (fields.get("I") or {}).get(
                "purpose_restriction") or DEFAULT_PURPOSE_RESTRICTION,
        },
    }
    return record, gaps


def check_record_structure(record) -> Report:
    """本地结构校验：镜像 Write check_template_record 的 error
    级规则（错误码同名）。绿灯只表示结构过关，不表示指南
    事实为真——事实来自官网指南，核查责任在执行者。"""
    from datetime import date

    rep = Report()
    if not isinstance(record, dict):
        rep.error("template.not_object", "模板核查记录须为 {A..I 分组} 对象")
        return rep
    for group_id, spec in TEMPLATE_GROUPS.items():
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
            present = [f for f in spec["fields"]
                       if group.get(f) is not None]
            if not present:
                rep.error("template.limits_empty",
                          f"模板记录 {group_id} 组（限额）无任何限额字段",
                          where=f"template.{group_id}")
            for f in present:
                if not isinstance(group[f], (int, float)) or \
                        isinstance(group[f], bool):
                    rep.error("template.limit_not_numeric",
                              f"模板记录限额字段 {f} 须为数值，"
                              f"实为 {group[f]!r}",
                              where=f"template.D.{f}")
    group_b = record.get("B") or {}
    if group_b.get("format_track") and \
            group_b["format_track"] not in FORMAT_TRACKS:
        rep.error("template.format_track",
                  f"format_track {group_b['format_track']!r} "
                  f"不在 {FORMAT_TRACKS}")
    group_a = record.get("A") or {}
    if group_a.get("journal_language") and \
            group_a["journal_language"] not in LANGUAGES:
        rep.error("template.language",
                  f"journal_language {group_a['journal_language']!r} "
                  f"不在 {LANGUAGES}")
    group_g = record.get("G") or {}
    ai = group_g.get("ai_policy")
    if isinstance(ai, dict):
        for field in TEMPLATE_GROUPS["G"]["ai_policy_required"]:
            if ai.get(field) is None:
                rep.error("template.ai_policy_field",
                          f"AI 政策组缺子字段 {field}",
                          where="template.G.ai_policy")
        if ai.get("disclosure_required"):
            positions = ai.get("disclosure_positions")
            if not positions or not isinstance(positions, list):
                rep.error("template.ai_disclosure_positions",
                          "AI 政策要求披露但 disclosure_positions 为空"
                          "（披露位置须多值落字）",
                          where="template.G.ai_policy")
            if not ai.get("disclosure_title") and \
                    not ai.get("disclosure_wording_template"):
                rep.warning("template.ai_disclosure_wording",
                            "AI 政策要求披露但无规定声明标题与措辞模板字段"
                            "（有规定口径的期刊宜补）",
                            where="template.G.ai_policy")
        decls = group_g.get("declarations")
        if isinstance(decls, list):
            for d in decls:
                if not isinstance(d, dict) or not d.get("type") \
                        or "position" not in d:
                    rep.error("template.declaration_shape",
                              "声明清单条目须含 {type, required, position, "
                              "field_name}", where="template.G.declarations")
    group_h = record.get("H") or {}
    verified_at = group_h.get("verified_at")
    if verified_at:
        try:
            date.fromisoformat(str(verified_at)[:10])
        except ValueError:
            rep.error("template.verified_at_format",
                      f"verified_at {verified_at!r} 不是 ISO 日期")
    group_i = record.get("I") or {}
    if group_i.get("redistribution") and \
            group_i["redistribution"] not in REDISTRIBUTION_VALUES:
        rep.error("template.redistribution",
                  f"redistribution {group_i['redistribution']!r} 不在词表")
    if group_h.get("bundled") and \
            group_h["bundled"] not in BUNDLED_VALUES:
        rep.error("template.bundled",
                  f"bundled {group_h['bundled']!r} 不在 {BUNDLED_VALUES}"
                  "（库存诚实）")
    return rep


_SELF_CHECK_CODE = (
    "import sys, json\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from light_write.validate import Report, check_template_record\n"
    "rec = json.load(open(sys.argv[2], encoding='utf-8'))\n"
    "rep = Report()\n"
    "check_template_record(rec, rep)\n"
    "print(json.dumps({'errors': rep.errors, 'warnings': rep.warnings},"
    " ensure_ascii=False))\n"
)


def run_write_selfcheck(record_path, write_root) -> dict:
    """可选外部自检钩子：子进程调用真正的 Write 校验器。

    返回 {status: pass|fail|unavailable, errors, warnings, note}。
    unavailable = Write 包不在场/不可导入（调用方显式要求自检
    时如何处置由调用方决定）；本模块不缓存、不改记录。
    """
    write_root = Path(write_root)
    if not (write_root / "light_write" / "validate.py").exists():
        return {"status": "unavailable", "errors": [], "warnings": [],
                "note": f"Write 包不在场：{write_root}"}
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _SELF_CHECK_CODE,
             str(write_root), str(record_path)],
            capture_output=True, text=True, timeout=120)
    except Exception as exc:  # 子进程起不来 = 自检不可用，如实报
        return {"status": "unavailable", "errors": [], "warnings": [],
                "note": f"自检子进程失败：{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        return {"status": "unavailable", "errors": [], "warnings": [],
                "note": f"自检子进程退出 {proc.returncode}："
                        f"{proc.stderr.strip()[:300]}"}
    payload = json.loads(proc.stdout)
    return {"status": "fail" if payload["errors"] else "pass",
            "errors": payload["errors"],
            "warnings": payload["warnings"], "note": None}


def resolve_write_root(explicit: str | None = None) -> str | None:
    """自检目标解析：显式参数 > 环境变量；皆无 = 不跑外部自检。"""
    return explicit or os.environ.get("LIGHT_JOURNAL_SELECT_WRITE_ROOT")


def record_hash(record: dict) -> str:
    return component_hash(record)


def raise_if_record_errors(record) -> Report:
    """本地结构校验 + 便捷抛错口（handoff 用）。"""
    rep = check_record_structure(record)
    if rep.errors:
        raise GateError([f"{i['code']}: {i['message']}" for i in rep.errors])
    return rep
