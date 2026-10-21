"""参考图入包登记与验收（F4，约束 8/9/10）。

- 入包登记：用户提供的 AI 参考图复制进 schematic/reference/，
  SHA-256 钉进 provenance 账（reference_image_hash），生成模型与
  版本同账登记——账是政策硬拦（policy_block 按哈希比对）与逐刊
  披露生成的唯一事实源。
- 验收（约束 9）：参考图入包后、重绘开工前执行一次科学复核，
  三项清单（逐标签逐字核对 / 逐结构对领域事实核对 / 公式分子式
  数值算对）须由核对人逐项明示落字才算完成；披露 ≠ 免责，照描
  不核事实是红项，验收不许由登记动作顺带自动完成。

- 变体所据（2026-10-21 补丁）：合同已登记提示词变体集
  （prompt_variants）时，登记须以 variant 指明所据变体且与
  selected_variant 一致——未选定 / 未指明 / 与选定不一致均拦；
  所据变体记入账面 reference_variant，验收同口径复核并记入验收
  记录。无变体集的单版图不设此门（存量兼容）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .project import load_package, provenance_row
from .provenance import update_provenance_row
from .util import sha256_file, today

REFERENCE_DIR = "schematic/reference"
ACCEPTANCE_CHECKS = ["labels_verbatim", "structures_factual",
                     "formulas_values_checked"]


class ReferenceError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def reference_relpath(root, fig_id) -> str | None:
    """已入包的参考图（schematic/reference/<fig_id>.<ext>）相对路径。"""
    ref_dir = Path(root) / REFERENCE_DIR
    if not ref_dir.exists():
        return None
    for path in sorted(ref_dir.glob(f"{fig_id}.*")):
        if path.is_file() and path.suffix != ".yaml":
            return f"{REFERENCE_DIR}/{path.name}"
    return None


def _variant_gate(pkg, fig_id: str, variant) -> str | None:
    """变体模式下参考图登记的所据变体门：返回应记账的所据变体；
    非变体模式返回 variant 原值（可为 None）。不过门抛 ReferenceError。"""
    contract = pkg["contracts"].get(fig_id) or {}
    pv = contract.get("prompt_variants") or {}
    if not (pv.get("variants") or []):
        return variant
    selected = pv.get("selected_variant")
    if not selected:
        raise ReferenceError([
            f"图 {fig_id} 已构建提示词变体但未选定：参考图登记须先经 "
            "prompt select 选定变体（未选定不许进登记/验收）"])
    if variant is None:
        raise ReferenceError([
            f"图 {fig_id} 参考图登记须以 --variant 指明所据变体"
            f"（已选定：{selected}）"])
    if variant != selected:
        raise ReferenceError([
            f"图 {fig_id} 参考图所据变体 {variant!r} 与已选定变体 "
            f"{selected!r} 不一致：按选定变体生成的参考图才许登记"])
    return variant


def register_reference(root, fig_id: str, image_path,
                       model_name=None, model_version=None,
                       by=None, variant=None) -> dict:
    root = Path(root)
    pkg = load_package(root)
    if pkg["head"] is None:
        raise ReferenceError(["图包不存在（先 init）"])
    row = next((r for r in pkg["head"].get("figures") or []
                if r.get("fig_id") == fig_id), None)
    if row is None:
        raise ReferenceError([f"图 {fig_id} 不在逐图状态表中"])
    if row.get("line") != "schematic":
        raise ReferenceError([f"图 {fig_id} 不是方法图线：参考图登记"
                                "只服务方法图线"])
    based_on = _variant_gate(pkg, fig_id, variant)
    source = Path(image_path)
    if not source.exists():
        raise ReferenceError([f"参考图文件不存在：{image_path}"])
    existing = reference_relpath(root, fig_id)
    if existing is not None:
        raise ReferenceError([
            f"图 {fig_id} 参考图已入包登记（{existing}）：账面哈希已钉住，"
            "不许静默换图——换图须先撤销验收并走账面更新留痕"])
    suffix = source.suffix.lower() or ".png"
    dest_dir = root / REFERENCE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{fig_id}{suffix}"
    shutil.copyfile(source, dest)
    digest = sha256_file(dest)
    updates = {"reference_image_hash": digest}
    if model_name:
        updates["generation_model"] = {
            "name": model_name, "version": model_version}
    if based_on:
        updates["reference_variant"] = based_on
    entry = update_provenance_row(root, fig_id, updates,
                                  by=by or "light-figure reference add")
    return {
        "fig_id": fig_id,
        "reference": f"{REFERENCE_DIR}/{dest.name}",
        "sha256": digest,
        "generation_model": entry.get("generation_model"),
        "reference_variant": entry.get("reference_variant"),
    }


def accept_reference(root, fig_id: str, by: str,
                     checks: dict) -> dict:
    """参考图验收落字：三项清单全过才许记 done（约束 9）。"""
    root = Path(root)
    pkg = load_package(root)
    entry = provenance_row(pkg["provenance"], fig_id)
    if entry is None:
        raise ReferenceError([f"图 {fig_id} 无 provenance 账行"])
    if not entry.get("reference_image_hash"):
        raise ReferenceError([f"图 {fig_id} 参考图尚未入包登记"
                                "（先 reference add）"])
    if not by:
        raise ReferenceError(["验收须落核对人（--by）：匿名验收不算数"])
    missing = [c for c in ACCEPTANCE_CHECKS if not checks.get(c)]
    if missing:
        raise ReferenceError([
            f"验收清单未逐项明示：{missing}（约束 9 三项——逐标签逐字"
            "核对 / 逐结构对领域事实核对 / 公式分子式数值算对——缺一"
            "不许记完成）"])
    # 变体所据复核（2026-10-21 补丁）：变体模式下验收须确认参考图
    # 所据变体与选定一致，所据变体记入验收记录。
    contract = pkg["contracts"].get(fig_id) or {}
    pv = contract.get("prompt_variants") or {}
    ref_variant = entry.get("reference_variant")
    if pv.get("variants"):
        selected = pv.get("selected_variant")
        if not selected:
            raise ReferenceError([
                f"图 {fig_id} 提示词变体未选定：参考图验收须先经 "
                "prompt select 选定变体（未选定不许进验收）"])
        if not ref_variant:
            raise ReferenceError([
                f"图 {fig_id} 参考图登记未指明所据变体（变体模式）："
                "换图重登记时以 --variant 指明所据变体后才许验收"])
        if ref_variant != selected:
            raise ReferenceError([
                f"图 {fig_id} 参考图所据变体 {ref_variant!r} 与已选定"
                f"变体 {selected!r} 不一致，不许验收"])
    acceptance = {
        "done": True, "by": by, "at": today(),
        "checks": {c: True for c in ACCEPTANCE_CHECKS},
    }
    if ref_variant:
        acceptance["variant"] = ref_variant
    update_provenance_row(root, fig_id, {
        "reference_acceptance": acceptance,
    }, by=by)
    return {"fig_id": fig_id, "accepted_by": by,
            "checks": ACCEPTANCE_CHECKS,
            "variant": ref_variant}
