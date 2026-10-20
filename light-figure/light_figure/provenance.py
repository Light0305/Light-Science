"""provenance 一本账的更新命令（约束 10，草案 §1.6）。

纪律：账行只增不改历史——每次更新先把旧行规范化哈希记进 history 的
`supersedes`，再覆盖当前行并追加一条 history 记录（时点/操作者/逐字段
from→to）。当前行（entries）是消费方（validate / gates / audit /
Write 披露生成）读的权威现状，history 是审计链，两者同文件落盘。

哈希字段在本层做格式校验（SHA-256 64 位十六进制），非法哈希不许入账。
"""

from __future__ import annotations

import re
from pathlib import Path

from .project import load_package, provenance_row, save_provenance
from .util import component_hash, today, utcnow

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# 账行中的哈希字段（更新时强制 SHA-256 格式）
HASH_FIELDS = {
    "reference_image_hash",
    "script_hash",
    "source_data_hash",
    "style_build_hash",
}


class ProvenanceError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _check_value(fig_id, key, value, gaps):
    if key in HASH_FIELDS and value is not None \
            and not _HEX64.match(str(value)):
        gaps.append(f"图 {fig_id} 的账字段 {key} 不是 SHA-256：{value!r}")
    if key == "redraw_source" and value is not None:
        if not isinstance(value, dict) or not value.get("path") \
                or not _HEX64.match(str(value.get("hash") or "")):
            gaps.append(f"图 {fig_id} 的 redraw_source 须为 "
                        "{path, hash(SHA-256)}")


def update_provenance_row(root, fig_id: str, updates: dict,
                          by: str | None = None) -> dict:
    """更新一图账行并追加 history（supersede 链）。返回更新后的账行。"""
    root = Path(root)
    pkg = load_package(root)
    provenance = pkg["provenance"]
    row = provenance_row(provenance, fig_id)
    if row is None:
        raise ProvenanceError(
            [f"图 {fig_id} 无 provenance 账行（账随图合同开立，先 intake）"])
    gaps = []
    for key, value in updates.items():
        _check_value(fig_id, key, value, gaps)
    if gaps:
        raise ProvenanceError(gaps)

    prior_hash = component_hash(row)
    changes = {}
    for key, value in updates.items():
        if row.get(key) != value:
            changes[key] = {"from": row.get(key), "to": value}
        row[key] = value
    history = provenance.setdefault("history", [])
    history.append({
        "fig_id": fig_id,
        "at": utcnow(),
        "date": today(),
        "by": by or "light-figure",
        "supersedes": prior_hash,
        "row_hash": component_hash(row),
        "changes": changes,
    })
    save_provenance(root, provenance)
    return row


def provenance_history(root, fig_id: str | None = None) -> list:
    pkg = load_package(Path(root))
    history = (pkg["provenance"] or {}).get("history") or []
    if fig_id is None:
        return history
    return [h for h in history if h.get("fig_id") == fig_id]
