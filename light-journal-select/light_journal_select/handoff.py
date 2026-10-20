"""定刊交接（handoff，Phase 2，拍板 E5）。

在稿件项目目录建 `journal/target/` 单刊目录：
  guideline/<日期或版本>/   作者指南（按版本分子目录，修订并存）
  templates/                模板文件
  download-manifest.json    逐文件登记（来源 URL/日期/SHA-256）
  check-record.json         Write 九组核查记录（现场生成+自检）
  handoff.md                给 Write 的交接清单

诚实纪律：
- 下载登记逐条落 status：本机真拿到文件并入库存
  `downloaded`（SHA-256 按入库字节算）；拿不到的外站文件只许
  以 `pending_download` 待下载条目存在（sha256=None），
  **不许伪造已下载**；登记了本地路径但文件不存在同样落
  pending 并注明；
- check-record 先在内存组装并过本地结构校验（镜像 Write
  校验器规则）；配了 --write-root / 环境变量时再过一遍真正的
  Write `check_template_record` 子进程自检；任一 error →
  整批拒绝、不写交接物、不进 handed_off；
- 记录语言强制 = 稿件指纹语言（字段文件报的语言与指纹
  不符 = 拿错指南，报错拦截）；
- 指南修订（handed_off 后重跑 handoff）：新版本子目录并存，
  manifest 新条目以 supersedes 指向被取代的旧指南条目，
  旧条目回填 superseded_by，check-record 按新 verified_at
  重新生成并重新自检。

模板与指南仅本地使用、不分发、不入公开仓（E5）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import schema
from .checkrecord import (
    build_check_record, check_record_structure, record_hash,
    resolve_write_root, run_write_selfcheck,
)
from .gates import GateError, advance_to, require_selection
from .project import FILES, find_candidate, save_selection
from .util import dump_json, load_structured, sha256_file, today
from .verify import Report, check_policy_checks

ENTRY_KINDS = ["guideline", "template"]


def _safe_filename(name: str) -> str:
    return Path(str(name or "")).name or "unnamed"


def _process_files(root: Path, target: Path, file_specs: list[dict],
                   guideline_version: str, today_str: str,
                   existing_entries: list[dict]) -> list[dict]:
    """把下载登记落成 manifest 条目（新条目接续编号）。"""
    entries: list[dict] = []
    seq = len(existing_entries)
    prev_guideline = None
    for old in existing_entries:
        if old.get("kind") == "guideline":
            prev_guideline = old
    for spec in file_specs or []:
        kind = spec.get("kind")
        if kind not in ENTRY_KINDS:
            raise GateError([f"下载登记 kind {kind!r} 不在 {ENTRY_KINDS}"])
        seq += 1
        filename = _safe_filename(spec.get("filename"))
        if kind == "guideline":
            subdir = target / "guideline" / guideline_version
        else:
            subdir = target / "templates"
        entry = {
            "entry_id": f"DL-{seq:03d}",
            "kind": kind,
            "filename": filename,
            "source_url": spec.get("source_url"),
            "status": "pending_download",
            "downloaded_at": None,
            "sha256": None,
            "stored_path": None,
            "supersedes": None,
            "superseded_by": None,
            "note": spec.get("note"),
        }
        if kind == "guideline" and prev_guideline is not None:
            entry["supersedes"] = prev_guideline.get("entry_id")
            prev_guideline["superseded_by"] = entry["entry_id"]
        local_path = spec.get("local_path")
        if local_path:
            src = Path(local_path)
            if not src.is_absolute():
                src = root / src
            if src.is_file():
                subdir.mkdir(parents=True, exist_ok=True)
                dest = subdir / filename
                shutil.copyfile(src, dest)
                entry.update({
                    "status": "downloaded",
                    "downloaded_at": today_str,
                    "sha256": sha256_file(dest),
                    "stored_path": dest.relative_to(root).as_posix(),
                })
            else:
                entry["note"] = (
                    f"登记的本地文件不存在（{local_path}），未下载；"
                    + (entry["note"] or "")).strip()
        entries.append(entry)
        if kind == "guideline":
            prev_guideline = entry
    return entries


def _policy_section_lines(selection: dict) -> list[str]:
    """政策核读段（JS-13）：必查项点名带回 + 缺项显形。"""
    items = selection.get("policy_checks") or []
    gaps = (selection.get("handoff") or {}).get("policy_gaps")
    if gaps is None:
        covered = {i.get("topic") for i in items if isinstance(i, dict)}
        gaps = [t for t in schema.POLICY_REQUIRED_TOPICS
                if t not in covered]
    lines = ["", "## 政策核读（JS-13：定刊时点逐刊现行页面）", ""]
    if items:
        for item in items:
            mark = "冲突（阻断项）" if item.get("status") == "conflict" \
                else item.get("status")
            lines.append(
                f"- {item.get('topic')}：{mark}——"
                f"{item.get('finding') or item.get('note') or ''}"
                f"（{item.get('source_url') or '无出处'}，访问于 "
                f"{item.get('accessed_at') or '未标'}；政策是活文本，"
                "投稿间隔过长或页面更新须复核）")
    else:
        lines.append("- 本轮交接未带回逐刊政策核读条目（见下方缺项）。")
    if gaps:
        lines.append("- **政策必查项未覆盖**："
                     + "、".join(gaps)
                     + "——投稿前必须逐刊核读补齐，不许以通行惯例"
                     "代替该刊现行政策（JS-13）。")
    return lines


def _render_handoff_md(selection: dict, candidate: dict, record: dict,
                       manifest: dict, self_check: dict,
                       root: Path, today_str: str) -> str:
    decision = selection.get("decision") or {}
    counts = {"downloaded": 0, "pending_download": 0}
    pending_names = []
    for e in manifest.get("entries") or []:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
        if e["status"] == "pending_download":
            pending_names.append(e["filename"])
    lines = [
        "# 定刊交接清单（light-journal-select → light-write）", "",
        f"- 目标刊：{candidate.get('name')}"
        f"（ISSN {candidate.get('issn') or '未确认'}，"
        f"出版商 {candidate.get('publisher') or '未确认'}）",
        f"- 定刊：{decision.get('decided_at')} 由 "
        f"{decision.get('decided_by')} 定刊，理由：{decision.get('reason')}",
        f"- 交接目录：{FILES['target_dir']}/（本机绝对路径 {root / FILES['target_dir']}）",
        f"- 核查记录：{FILES['check_record']}（record_id "
        f"{record['A'].get('record_id')}，内容哈希 {record_hash(record)}）",
        f"- 自检结论：本地结构校验 {self_check['local_structure']}；"
        f"Write 校验器自检 {self_check['write_check']}"
        + (f"（{self_check['write_note']}）" if self_check.get("write_note")
           else ""),
        f"- 下载清单：{FILES['manifest']}（已下载 "
        f"{counts['downloaded']} 件 / 待下载 {counts['pending_download']} 件"
        + (f"：{', '.join(pending_names)}" if pending_names else "") + "）",
    ]
    lines += _policy_section_lines(selection)
    lines += [
        "", "## Write 开工提示", "",
        "在 Write 稿件包目录执行（--record 指向本清单同目录的 "
        "check-record.json）：", "",
        "```bash",
        f"light-write register-template <稿件包目录> "
        f"--record {root / FILES['check_record']}",
        "```", "",
        "- 待下载条目请按 manifest 的 source_url 从官网取回后"
        "回填登记（状态与哈希不许手改冒充）；",
        "- 本目录的模板与作者指南仅本地投稿使用，不分发、"
        "不入任何公开仓库（E5）；",
        f"- 生成日期：{today_str}（light-journal-select handoff）",
        "",
    ]
    return "\n".join(lines)


def run_handoff(root, fields: dict | None = None,
                file_specs: list[dict] | None = None,
                write_root: str | None = None,
                guideline_version: str | None = None,
                today_str: str | None = None) -> dict:
    """执行交接。decided → handed_off；handed_off 重跑 = 指南
    修订刷新（状态不动，manifest/记录/清单就地更新）。"""
    root = Path(root)
    selection = require_selection(root)
    status = selection.get("status")
    if status not in ("decided", "handed_off"):
        raise GateError([f"状态 {status} 不许交接（须先 decide 定刊）"])
    refresh = status == "handed_off"
    decision = selection.get("decision") or {}
    candidate = find_candidate(selection, decision.get("candidate_id") or "")
    if candidate is None:
        raise GateError(["定刊候选已不在候选池中，交接无从对齐"
                         "（decision 与候选池不一致）"])
    today_str = today_str or today()
    guideline_version = guideline_version or today_str

    target = root / FILES["target_dir"]
    manifest_path = root / FILES["manifest"]
    existing_manifest = None
    existing_entries: list[dict] = []
    if refresh and manifest_path.exists():
        existing_manifest = load_structured(manifest_path)
        existing_entries = list(existing_manifest.get("entries") or [])

    if not refresh and fields is None:
        raise GateError(["缺指南字段文件（--fields）：B–I 组指南派生"
                         "字段须由执行者读官网作者指南后提供，"
                         "工具不许凭空编造"])

    # ---- 政策必查项（JS-13）：字段文件 policies 逐刊核读条目
    # 先校验后落字；条目报 conflict = 政策冲突阻断项，不许
    # 静默交接（须回报告处置或改定刊）。未覆盖的必查项落
    # policy_gaps 显形（构建单判断 J3：缺项显形 + 冲突硬阻断）。
    policy_items = (fields or {}).get("policies")
    if policy_items is not None:
        rep_p = Report()
        check_policy_checks(policy_items, rep_p, where="policies")
        if rep_p.errors:
            raise GateError([f"{i['code']}: {i['message']}"
                             for i in rep_p.errors])
        conflicts = [i.get("topic") for i in policy_items
                     if isinstance(i, dict)
                     and i.get("status") == "conflict"]
        if conflicts:
            raise GateError([
                f"政策核读报冲突（{', '.join(conflicts)}）：本稿情形"
                "与目标刊现行政策冲突，是阻断项不是提示项（JS-13）"
                "——请回报告处置（改定刊或调整稿件情形）后再交接"])
        selection["policy_checks"] = policy_items
    covered = {i.get("topic") for i in selection.get("policy_checks") or []
               if isinstance(i, dict)}
    policy_gaps = [t for t in schema.POLICY_REQUIRED_TOPICS
                   if t not in covered]

    # ---- 先组装并自检 check-record，有 error 整批拒绝（不落盘）
    record, gaps = build_check_record(selection, candidate, fields,
                                      today_str)
    if gaps:
        raise GateError(gaps)
    rep = check_record_structure(record)
    if rep.errors:
        raise GateError([f"{i['code']}: {i['message']}" for i in rep.errors])
    self_check = {"local_structure": "pass",
                  "write_check": "not_run", "write_note": None,
                  "write_errors": []}
    resolved_write_root = resolve_write_root(write_root)
    record_tmp = None
    if resolved_write_root:
        target.mkdir(parents=True, exist_ok=True)
        record_tmp = target / ".check-record.pending.json"
        dump_json(record_tmp, record)
        result = run_write_selfcheck(record_tmp, resolved_write_root)
        if result["status"] == "unavailable":
            record_tmp.unlink(missing_ok=True)
            raise GateError(["Write 自检被显式要求但不可用："
                             f"{result['note']}"])
        self_check["write_check"] = result["status"]
        self_check["write_errors"] = result["errors"]
        if result["errors"]:
            record_tmp.unlink(missing_ok=True)
            raise GateError(
                ["Write 校验器自检未过："]
                + [f"{i['code']}: {i['message']}" for i in result["errors"]])

    # ---- 落盘：目录、文件、manifest、记录、清单
    (target / "guideline" / guideline_version).mkdir(parents=True,
                                                     exist_ok=True)
    (target / "templates").mkdir(parents=True, exist_ok=True)
    new_entries = _process_files(root, target, file_specs or [],
                                 guideline_version, today_str,
                                 existing_entries)
    if not refresh and not new_entries:
        # 未给下载登记：至少把作者指南列入待下载清单（诚实占位）
        guide_url = candidate.get("guide_url") or \
            candidate.get("homepage_url")
        if guide_url:
            new_entries = _process_files(root, target, [{
                "kind": "guideline", "filename": "author-guide",
                "source_url": guide_url,
                "note": "未提供本地文件，待从官网下载后回填登记",
            }], guideline_version, today_str, existing_entries)
    manifest = existing_manifest or {
        "kind": "light-journal-select/download-manifest",
        "usage": "local_use_only",
        "journal": {"candidate_id": candidate.get("candidate_id"),
                    "name": candidate.get("name"),
                    "issn": candidate.get("issn")},
        "generated_at": today_str,
        "entries": [],
    }
    manifest["entries"] = existing_entries + new_entries
    manifest["updated_at"] = today_str
    dump_json(manifest_path, manifest)
    dump_json(root / FILES["check_record"], record)
    if record_tmp is not None:
        record_tmp.unlink(missing_ok=True)
    md = _render_handoff_md(selection, candidate, record, manifest,
                            self_check, root, today_str)
    (root / FILES["handoff_md"]).write_text(md, encoding="utf-8")

    selection["handoff"] = {
        "journal": candidate.get("name"),
        "candidate_id": candidate.get("candidate_id"),
        "target_dir": FILES["target_dir"],
        "check_record": FILES["check_record"],
        "download_manifest": FILES["manifest"],
        "handoff_list": FILES["handoff_md"],
        "record_id": record["A"].get("record_id"),
        "record_hash": record_hash(record),
        "self_check": self_check,
        "policy_gaps": policy_gaps,
        "at": today_str,
    }
    selection.setdefault("handoff_history", []).append({
        "at": today_str,
        "kind": "guideline_refresh" if refresh else "initial",
        "guideline_version": guideline_version,
        "record_id": record["A"].get("record_id"),
    })
    save_selection(root, selection)
    if not refresh:
        advance_to(root, "handed_off", by="light-journal-select handoff")
    return {"journal": candidate.get("name"),
            "target_dir": FILES["target_dir"],
            "record_id": record["A"].get("record_id"),
            "record_hash": record_hash(record),
            "entries": len(new_entries),
            "self_check": self_check,
            "refresh": refresh,
            "status": "handed_off"}
