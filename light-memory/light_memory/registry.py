"""对象注册：消费上游既有 ID，不自建 ID 体系（MM-01）。

- 注册只增：同一对象（类型 + 上游 ID 派生的 object_id）跨次收编自动
  合并——更新当前版本指针与状态，不长第二行。
- 前向登记：只被指针引用、本体尚未收编的对象以 status=referenced
  落账（MM-26），本体日后收编时就地转正。
- registry-view.json：对象注册统一视图的只读导出，按对象类型分组、
  带当前版本指针与状态；总控可直接消费（草案 §5.2 的预留形态，
  导出格式自本版冻结）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import FILES
from .util import dump_json, utcnow


def register_object(pkg: dict, object_type: str, upstream_id: str,
                    provenance: dict, *, project: str = "", title: str = "",
                    status: str = "active", current_version=None) -> dict:
    """登记或合并一个对象，返回对象行（调用方负责落盘）。"""
    objects = pkg.setdefault("objects", [])
    oid = schema.derive_object_id(object_type, upstream_id)
    for row in objects:
        if row.get("object_id") == oid:
            # 本体收编转正：referenced → active；版本指针取新值。
            if row.get("status") == "referenced" and status != "referenced":
                row["status"] = status
            elif status in ("superseded", "archived"):
                row["status"] = status
            if current_version is not None:
                row["current_version"] = current_version
            if title:
                row["title"] = title
            row["source_version"] = provenance.get("source_version")
            row["updated_at"] = utcnow()
            return row
    row = schema.new_object(object_type, upstream_id, provenance,
                            project=project, title=title, status=status,
                            current_version=current_version)
    objects.append(row)
    return row


def reference_object(pkg: dict, object_type: str, upstream_id: str,
                     provenance: dict, *, project: str = "") -> dict:
    """前向登记一个只被引用的对象（本体未收编，status=referenced）。"""
    objects = pkg.setdefault("objects", [])
    oid = schema.derive_object_id(object_type, upstream_id)
    for row in objects:
        if row.get("object_id") == oid:
            return row
    return register_object(pkg, object_type, upstream_id, provenance,
                           project=project, status="referenced")


def get_object(pkg: dict, object_id: str):
    for row in pkg.get("objects") or []:
        if row.get("object_id") == object_id:
            return row
    return None


def export_registry_view(root, pkg: dict) -> dict:
    """把对象注册导出为 registry-view.json（只读统一视图）。"""
    grouped: dict[str, list] = {}
    for row in pkg.get("objects") or []:
        grouped.setdefault(row.get("object_type"), []).append({
            "object_id": row.get("object_id"),
            "upstream_id": row.get("upstream_id"),
            "project": row.get("project"),
            "title": row.get("title"),
            "status": row.get("status"),
            "current_version": row.get("current_version"),
            "source_package": row.get("source_package"),
        })
    view = {
        "kind": "light-memory/registry-view",
        "version": "1.0",
        "memory_id": (pkg.get("memory") or {}).get("memory_id"),
        "generated_at": utcnow(),
        "counts": {t: len(rows) for t, rows in sorted(grouped.items())},
        "objects_by_type": dict(sorted(grouped.items())),
    }
    dump_json(Path(root) / FILES["registry_view"], view)
    return view
