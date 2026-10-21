"""交付段（Phase 3）：exports/delivery.yaml 生成、交付前 provenance
账行逐行复验、编号冻结配合（SKILL §11）。

纪律：
- Figure 不直接改 Write 的 figures_manifest，只产 delivery.yaml 供
  Write 按 §11 映射回填。
- 交付前账行逐行复验：账面哈希按实物重算比对，被改即拒交付
  （约束 10：账不全/账实不符的图不许进 delivered）。
- 编号冻结：deliver 首次生成即冻结包级编号（与 Write audited 段
  冻结同步）；冻结后交付物变更，不许静默重交付——须先登记解冻
  （deliver --unfreeze --reason），旧 delivery.yaml 标 superseded，
  重新交付时 version 递增。解冻/冻结全程留痕于 figure.yaml 的
  numbering_changes[]。
- 交付只许在 audited 段执行，且逐图审计须 FRESH、总判决不得为
  FIX_BEFORE_DELIVERY / NOT_AUDITABLE。
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .audit import audit_status, record_path
from .produce import script_path, source_data_path
from .project import (
    load_package, provenance_row, save_head, schematic_artifact_relpath,
    schematic_backend,
)
from .redraw import load_manifest
from .reference import reference_relpath
from .style import bundle_current
from .util import dump_yaml, load_structured, sha256_file, today
from .validate import validate_package

DELIVERY_REL = "exports/delivery.yaml"


class DeliveryError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 账行复验

def verify_provenance_rows(root, pkg) -> list:
    """逐图复验 provenance 账行：账面哈希按实物重算比对（约束 10）。

    返回 gaps（空 = 全过）。数据图验脚本/源数据/样式三哈希；方法图
    验参考图与重绘源两哈希（路径 + 哈希成对）。
    """
    root = Path(root)
    gaps = []
    bundle, bundle_problem = bundle_current(root)
    for row in pkg["head"].get("figures") or []:
        fig_id = row["fig_id"]
        entry = provenance_row(pkg["provenance"], fig_id)
        if entry is None:
            gaps.append(f"图 {fig_id} 无 provenance 账行：账不全不许交付")
            continue
        if row.get("line") == "data":
            script = script_path(root, fig_id)
            if not entry.get("script_hash"):
                gaps.append(f"数据图 {fig_id} 账面缺 script_hash")
            elif not script.exists():
                gaps.append(f"数据图 {fig_id} 绘图脚本不存在："
                            f"data/scripts/{fig_id}.py")
            elif entry["script_hash"] != sha256_file(script):
                gaps.append(f"数据图 {fig_id} 账面脚本哈希与实物不符："
                            "交付前复验拒绝（脚本被改后须重跑 produce "
                            "回填账面，再交付）")
            contract = pkg["contracts"].get(fig_id)
            data_path = source_data_path(root, contract)
            if not entry.get("source_data_hash"):
                gaps.append(f"数据图 {fig_id} 账面缺 source_data_hash")
            elif data_path is None or not data_path.exists():
                gaps.append(f"数据图 {fig_id} 源数据文件不存在，"
                            "账面源数据哈希无从复验")
            elif entry["source_data_hash"] != sha256_file(data_path):
                gaps.append(f"数据图 {fig_id} 账面源数据哈希与实物不符："
                            "交付前复验拒绝")
            if not entry.get("style_build_hash"):
                gaps.append(f"数据图 {fig_id} 账面缺 style_build_hash")
            elif bundle_problem:
                gaps.append(f"数据图 {fig_id} 样式 bundle 当前不可用："
                            f"{bundle_problem}")
            elif entry["style_build_hash"] != bundle["style_build_hash"]:
                gaps.append(f"数据图 {fig_id} 账面 style_build_hash 与"
                            "当前编译 bundle 不一致：样式变更后须重跑 "
                            "produce 回填，再交付")
        else:
            ref_rel = reference_relpath(root, fig_id)
            if not entry.get("reference_image_hash"):
                gaps.append(f"方法图 {fig_id} 账面缺 reference_image_hash")
            elif ref_rel is None:
                gaps.append(f"方法图 {fig_id} 参考图未入包登记，"
                            "账面参考图哈希无从复验")
            elif entry["reference_image_hash"] \
                    != sha256_file(root / ref_rel):
                gaps.append(f"方法图 {fig_id} 账面参考图哈希与包内"
                            "文件不符：交付前复验拒绝")
            redraw = entry.get("redraw_source") or {}
            contract = pkg["contracts"].get(fig_id) or {}
            art_rel = schematic_artifact_relpath(contract, fig_id)
            artifact = root / art_rel
            if not redraw.get("hash"):
                gaps.append(f"方法图 {fig_id} 账面缺重绘源哈希")
            elif not artifact.exists():
                gaps.append(f"方法图 {fig_id} 成品不存在：{art_rel}")
            elif redraw["hash"] != sha256_file(artifact):
                gaps.append(f"方法图 {fig_id} 账面重绘源哈希与成品"
                            "不符：交付前复验拒绝（成品被改后须重跑 "
                            "对应后端 build 回填）")
            if redraw.get("path") and redraw["path"] != art_rel:
                gaps.append(f"方法图 {fig_id} 账面重绘源路径 "
                            f"{redraw['path']} 与包内成品 "
                            f"{art_rel} 不一致")
    return gaps


# ---------------------------------------------------------------- 编号冻结

def _freeze_state(head) -> dict:
    return (head or {}).get("numbering_freeze") or {"frozen": False}


def _append_change(head, action, by, reason=None):
    head.setdefault("numbering_changes", []).append({
        "action": action, "at": today(), "by": by or "light-figure deliver",
        **({"reason": reason} if reason else {}),
    })


def register_unfreeze(root, reason, by=None) -> dict:
    """冻结后变更的前置登记：解冻 + 旧 delivery.yaml 标 superseded。

    解冻不删任何产物，只把「编号已冻结」状态解除并留痕；重新交付
    须再走 deliver（version 递增）并重新冻结。
    """
    if not reason:
        raise DeliveryError(["解冻登记必须给理由（--reason）：冻结后"
                             "改图须解冻登记，理由留痕不许空"])
    root = Path(root)
    pkg = load_package(root)
    head = pkg["head"]
    if head is None:
        raise DeliveryError(["图包不存在（先 init）"])
    if not _freeze_state(head).get("frozen"):
        raise DeliveryError(["编号尚未冻结，无须解冻登记"])
    head["numbering_freeze"] = {
        "frozen": False, "at": today(),
        "by": by or "light-figure deliver", "reason": reason,
    }
    _append_change(head, "unfreeze", by, reason)
    save_head(root, head)
    delivery_path = root / DELIVERY_REL
    superseded = False
    if delivery_path.exists():
        doc = load_structured(delivery_path) or {}
        doc["status"] = "superseded"
        doc["superseded_at"] = today()
        doc["superseded_reason"] = reason
        dump_yaml(delivery_path, doc)
        superseded = True
    return {"unfrozen": True, "reason": reason,
            "delivery_superseded": superseded}


# ---------------------------------------------------------------- 交付生成

def _caption_hashes(head) -> dict:
    snapshot = (head.get("intake") or {}).get("entries_snapshot") or []
    return {e.get("figure_id"): e.get("caption_draft_hash")
            for e in snapshot}


def _correspondence(root, pkg, row, entry) -> dict:
    """对应件清单（REV-D09 交叉项）：源资产 → 交付件映射 + 内容级
    哈希，供 Review 在源资产与交付件异名异格式时做内容级比对
    （数字↔图边的图哈希项从 not_assessable 升为真检）。缺件落
    null + note，不冒充齐备。"""
    from .util import component_hash

    fig_id = row["fig_id"]
    sources = []
    content_hashes = {}
    note = None
    if row.get("line") == "data":
        script = script_path(root, fig_id)
        if script.exists():
            sources.append({"role": "plotting_script",
                            "path": f"data/scripts/{fig_id}.py",
                            "sha256": sha256_file(script)})
        contract = pkg["contracts"].get(fig_id)
        data_path = source_data_path(root, contract)
        if data_path is not None and data_path.exists():
            sources.append({
                "role": "source_data",
                "path": str(data_path.relative_to(root))
                if data_path.is_relative_to(root) else str(data_path),
                "sha256": sha256_file(data_path)})
        bundle_path = root / "data" / "styles" / "bundle.json"
        if bundle_path.exists():
            sources.append({"role": "style_bundle",
                            "path": "data/styles/bundle.json",
                            "sha256": sha256_file(bundle_path)})
        align_path = root / "audit" / f"{fig_id}.alignment-input.json"
        if align_path.exists():
            align = load_structured(align_path)
            content_hashes["alignment_panels"] = component_hash(
                align.get("panels") or [])
        else:
            note = "缺量测清单：内容级哈希（alignment_panels）不可用"
    else:
        contract = pkg["contracts"].get(fig_id) or {}
        if schematic_backend(contract) == "powerpoint":
            from .pptxbuild import (
                load_pptx_manifest, pptx_manifest_path,
            )
            manifest = load_pptx_manifest(root, fig_id) or {}
            mpath = pptx_manifest_path(root, fig_id)
            mrel = f"schematic/redraw/{fig_id}.pptx-manifest.json"
        elif schematic_backend(contract) == "illustrator":
            from .aibuild import ai_manifest_path, load_ai_manifest
            manifest = load_ai_manifest(root, fig_id) or {}
            mpath = ai_manifest_path(root, fig_id)
            mrel = f"schematic/redraw/{fig_id}.ai-manifest.json"
        else:
            manifest = load_manifest(root, fig_id) or {}
            mpath = root / "schematic" / "redraw" \
                / f"{fig_id}.manifest.json"
            mrel = f"schematic/redraw/{fig_id}.manifest.json"
        if mpath.exists():
            sources.append({"role": "redraw_manifest", "path": mrel,
                            "sha256": sha256_file(mpath)})
        if entry.get("reference_image_hash"):
            sources.append({
                "role": "reference_image",
                "path": None,  # 参考图本体不进交付集，只给哈希指针
                "sha256": entry["reference_image_hash"]})
        if manifest.get("extracted_shapes_hash"):
            content_hashes["extracted_shapes"] = \
                manifest["extracted_shapes_hash"]
        else:
            note = "成品未反抽：内容级哈希（extracted_shapes）不可用"
    return {"source_assets": sources, "content_hashes": content_hashes,
            "note": note}


def _delivery_row(root, pkg, row, captions) -> dict:
    fig_id = row["fig_id"]
    entry = provenance_row(pkg["provenance"], fig_id) or {}
    contract = pkg["contracts"].get(fig_id) or {}
    out = {
        "fig_id": fig_id,
        "kind": row.get("kind"),
        "line": row.get("line"),
        "caption_hash": captions.get(fig_id),
    }
    if row.get("line") == "data":
        pdf = root / "exports" / f"{fig_id}.pdf"
        files = [{"path": f"exports/{fig_id}.pdf",
                  "sha256": sha256_file(pdf), "role": "main_pdf"}]
        preview = root / "data" / "previews" / f"{fig_id}.png"
        if preview.exists():
            files.append({"path": f"data/previews/{fig_id}.png",
                          "sha256": sha256_file(preview),
                          "role": "preview"})
        out["files"] = files
        out["provenance"] = {
            "backend": entry.get("backend"),
            "runtime_version": entry.get("runtime_version"),
            "script_hash": entry.get("script_hash"),
            "source_data_hash": entry.get("source_data_hash"),
            "style_build_hash": entry.get("style_build_hash"),
            "palette_registry_version":
                entry.get("palette_registry_version"),
        }
    else:
        backend = schematic_backend(contract)
        art_rel = schematic_artifact_relpath(contract, fig_id)
        artifact = root / art_rel
        if backend == "powerpoint":
            from .pptxbuild import load_pptx_manifest
            manifest = load_pptx_manifest(root, fig_id) or {}
            build = manifest.get("build") or {}
            out["files"] = [{"path": art_rel,
                             "sha256": sha256_file(artifact),
                             "role": "powerpoint_source"}]
            out["powerpoint_verified"] = \
                build.get("powerpoint_verified")
            out["powerpoint_note"] = (
                "PPT 文件层产物（python-pptx 构建 + OPC 反读证据），"
                "未过 PowerPoint 实机验证（FIG-D02：如实标注）")
            redraw_route = build.get("backend")
        elif backend == "illustrator":
            from .aibuild import load_ai_manifest
            manifest = load_ai_manifest(root, fig_id) or {}
            build = manifest.get("build") or {}
            out["files"] = [{"path": art_rel,
                             "sha256": sha256_file(artifact),
                             "role": "illustrator_source"}]
            out["illustrator_verified"] = \
                build.get("illustrator_verified")
            if build.get("illustrator_verified") is True:
                out["illustrator_note"] = (
                    "Illustrator 生产路线产物（ExtendScript 构建脚本"
                    "实机执行 + DOM 枚举回读对账已登记，证据等级 "
                    "dom_readback）")
            else:
                out["illustrator_note"] = (
                    "Illustrator 生产路线产物未经实机 DOM 回读对账"
                    "登记验证（如实标注：verified 只认 ai extract "
                    "合格登记）")
            redraw_route = build.get("backend")
        else:
            manifest = load_manifest(root, fig_id) or {}
            build = manifest.get("build") or {}
            out["files"] = [{"path": art_rel,
                             "sha256": sha256_file(artifact),
                             "role": "visio_source"}]
            out["visio_verified"] = build.get("visio_verified")
            if build.get("route") == "file_build":
                out["visio_note"] = ("文件级路线产物，未过 Visio 实机"
                                     "验证（拍板 D4：如实标注）")
            redraw_route = build.get("route")
        out["provenance"] = {
            "ledger_ref": f"provenance.yaml#{fig_id}",
            "prompt_version": entry.get("prompt_version"),
            "generation_model": entry.get("generation_model"),
            "reference_image_hash": entry.get("reference_image_hash"),
            "redraw_source": entry.get("redraw_source"),
        }
        out["ai_disclosure"] = {
            "generation_model": entry.get("generation_model"),
            "prompt_version": entry.get("prompt_version"),
            "redraw_route": redraw_route,
            "reference_not_in_delivery": True,
        }
        out["sister_library_refs"] = contract.get("sister_library_refs")
    out["correspondence"] = _correspondence(root, pkg, row, entry)
    return out


def _artifact_hash_now(root, pkg, row):
    fig_id = row["fig_id"]
    if row.get("line") == "data":
        path = root / "exports" / f"{fig_id}.pdf"
    else:
        contract = (pkg or {}).get("contracts", {}).get(fig_id) or {}
        path = root / schematic_artifact_relpath(contract, fig_id)
    return sha256_file(path) if path.exists() else None


def generate_delivery(root, by=None) -> dict:
    """生成 exports/delivery.yaml（交付前全验 + 首次生成即冻结编号）。"""
    root = Path(root)
    pkg = load_package(root)
    head = pkg["head"]
    if head is None:
        raise DeliveryError(["图包不存在（先 init）"])
    gaps = []
    if head.get("status") not in ("audited", "delivered"):
        gaps.append(f"包状态为 {head.get('status')}：交付只许在 audited "
                    "段生成（先 advance 至 audited）")
    report = validate_package(root)
    for e in report["errors"]:
        gaps.append(f"[{e['code']}] {e['message']}")
    status = audit_status(root)["figures"]
    for row in head.get("figures") or []:
        fig_id = row["fig_id"]
        state = (status.get(fig_id) or {}).get("state")
        if state != "FRESH":
            gaps.append(f"图 {fig_id} 审计状态为 {state}：交付前审计"
                        "须 FRESH（改动后重跑 audit run）")
            continue
        record = load_structured(record_path(root, fig_id))
        if record.get("overall") in ("FIX_BEFORE_DELIVERY",
                                     "NOT_AUDITABLE"):
            gaps.append(f"图 {fig_id} 审计总判决为 "
                        f"{record.get('overall')}：不许交付")
    gaps.extend(verify_provenance_rows(root, pkg))

    delivery_path = root / DELIVERY_REL
    old_doc = None
    if delivery_path.exists():
        old_doc = load_structured(delivery_path)
    frozen = _freeze_state(head).get("frozen")
    if old_doc and old_doc.get("status") != "superseded":
        old_hashes = {r["fig_id"]: (r.get("files") or [{}])[0].get("sha256")
                      for r in old_doc.get("figures") or []}
        changed = [row["fig_id"] for row in head.get("figures") or []
                   if old_hashes.get(row["fig_id"])
                   != _artifact_hash_now(root, pkg, row)]
        if changed and frozen:
            gaps.append(
                "编号已冻结且交付物在交付后变更（"
                + "、".join(changed)
                + "）：先登记解冻（deliver --unfreeze --reason）"
                "再重新交付，不许静默覆盖已冻结交付")
        elif changed and old_doc.get("status") == "current":
            gaps.append("交付物已变更但旧 delivery.yaml 未标 superseded："
                        "先登记解冻再重新交付")
    if gaps:
        raise DeliveryError(gaps)

    version = 1
    if old_doc and old_doc.get("status") == "superseded":
        version = int(old_doc.get("version") or 1) + 1
    captions = _caption_hashes(head)
    figures = [_delivery_row(root, pkg, row, captions)
               for row in head.get("figures") or []]
    if not frozen:
        head["numbering_freeze"] = {
            "frozen": True, "at": today(),
            "by": by or "light-figure deliver",
        }
        _append_change(head, "freeze", by)
        save_head(root, head)
    freeze = _freeze_state(head)
    doc = {
        "kind": "light-figure/delivery",
        "version": version,
        "status": "current",
        "tool_version": __version__,
        "package_id": head.get("package_id"),
        "package_status": head.get("status"),
        "generated_at": today(),
        "generated_by": by or "light-figure deliver",
        "numbering": {
            "frozen": True,
            "frozen_at": freeze.get("at"),
            "frozen_by": freeze.get("by"),
        },
        "figures": figures,
    }
    delivery_path.parent.mkdir(parents=True, exist_ok=True)
    dump_yaml(delivery_path, doc)
    return {"delivery": DELIVERY_REL, "version": version,
            "figures": [f["fig_id"] for f in figures],
            "numbering_frozen": True}


# ---------------------------------------------------------------- delivered 门

def delivered_gaps(pkg) -> list:
    """audited→delivered 入口门：delivery.yaml 在场且为现行版、编号
    已冻结、逐图交付行与当前产物哈希/图注哈希一致、账行复验全过、
    审计 FRESH。"""
    root = pkg["root"]
    head = pkg["head"]
    gaps = []
    report = validate_package(root)
    for e in report["errors"]:
        gaps.append(f"[{e['code']}] {e['message']}")
    delivery_path = root / DELIVERY_REL
    if not delivery_path.exists():
        gaps.append("缺 exports/delivery.yaml：先跑 deliver 生成交付"
                    "清单（交付前账行逐行复验 + 编号冻结在该步执行）")
        return gaps
    doc = load_structured(delivery_path) or {}
    if doc.get("status") == "superseded":
        gaps.append("delivery.yaml 已被解冻登记标 superseded："
                    "重新跑 deliver 生成现行版再交付")
    if not _freeze_state(head).get("frozen"):
        gaps.append("编号未冻结：deliver 生成交付清单时同步冻结，"
                    "冻结缺失不许 delivered")
    delivered = {r.get("fig_id"): r for r in doc.get("figures") or []}
    captions = _caption_hashes(head)
    status = audit_status(root)["figures"]
    for row in head.get("figures") or []:
        fig_id = row["fig_id"]
        drow = delivered.get(fig_id)
        if drow is None:
            gaps.append(f"图 {fig_id} 不在 delivery.yaml 交付行中")
            continue
        files = drow.get("files") or []
        current = _artifact_hash_now(root, pkg, row)
        if not files or files[0].get("sha256") != current:
            gaps.append(f"图 {fig_id} 交付行主文件哈希与当前产物不符："
                        "交付后产物已变更——登记解冻后重新交付")
        if drow.get("caption_hash") != captions.get(fig_id):
            gaps.append(f"图 {fig_id} 交付行图注哈希与承接快照不一致"
                        "（图注漂移须回 Write 对账）")
        if (status.get(fig_id) or {}).get("state") != "FRESH":
            gaps.append(f"图 {fig_id} 审计非 FRESH：交付前须重跑审计")
    gaps.extend(verify_provenance_rows(root, pkg))
    return gaps
