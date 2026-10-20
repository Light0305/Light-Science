"""参考图入包登记与验收（F4，约束 8/9/10）。

- 入包登记：用户提供的 AI 参考图复制进 schematic/reference/，
  SHA-256 钉进 provenance 账（reference_image_hash），生成模型与
  版本同账登记——账是政策硬拦（policy_block 按哈希比对）与逐刊
  披露生成的唯一事实源。
- 验收（约束 9）：参考图入包后、重绘开工前执行一次科学复核，
  三项清单（逐标签逐字核对 / 逐结构对领域事实核对 / 公式分子式
  数值算对）须由核对人逐项明示落字才算完成；披露 ≠ 免责，照描
  不核事实是红项，验收不许由登记动作顺带自动完成。
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


def register_reference(root, fig_id: str, image_path,
                       model_name=None, model_version=None,
                       by=None) -> dict:
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
    entry = update_provenance_row(root, fig_id, updates,
                                  by=by or "light-figure reference add")
    return {
        "fig_id": fig_id,
        "reference": f"{REFERENCE_DIR}/{dest.name}",
        "sha256": digest,
        "generation_model": entry.get("generation_model"),
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
    update_provenance_row(root, fig_id, {
        "reference_acceptance": {
            "done": True, "by": by, "at": today(),
            "checks": {c: True for c in ACCEPTANCE_CHECKS},
        },
    }, by=by)
    return {"fig_id": fig_id, "accepted_by": by,
            "checks": ACCEPTANCE_CHECKS}
