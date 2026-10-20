"""registry：只读消费 light-memory 的 registry-view.json 并渲染统一视图。

归属裁决（承 10-memory/REDESIGN-DRAFT §5.2 预置条件，本包定版采纳）：
(a) ID 分配权留在各上游包，注册视图只登记映射、不发号；
(b) 注册记录只增、状态变更落 memory 的事件账，总控不写注册表；
(c) registry-view 格式自 light-memory v1.0 冻结（kind 与 version 校验），
    不兼容时点名报错，不静默降级、不自行重建。
总控是消费方：本模块只读、只渲染，绝不生成或修改 registry-view.json。
生成方式指针：由 light-memory 在记忆项目目录运行 registry 导出命令刷新。
"""

from __future__ import annotations

from pathlib import Path

from .scan import find_files
from .util import load_json

EXPECTED_KIND = "light-memory/registry-view"
EXPECTED_VERSION = "1.0"

GENERATE_POINTER = (
    "生成方式：在记忆项目目录运行 light-memory registry "
    "（export 刷新 registry-view.json 只读导出）；总控只消费不生成。"
)


class RegistryError(Exception):
    pass


def locate_view(root) -> Path | None:
    """在项目内定位 registry-view.json：先 memory/ 直下，再全树搜索。"""
    root = Path(root)
    direct = root / "memory" / "registry-view.json"
    if direct.is_file():
        return direct
    hits = find_files(root, "registry-view.json")
    return hits[0] if hits else None


def load_view(root) -> tuple:
    """返回 (路径, 视图 dict)；缺失或格式不符抛 RegistryError 点名。"""
    path = locate_view(root)
    if path is None:
        raise RegistryError("未找到 registry-view.json。" + GENERATE_POINTER)
    view = load_json(path)
    if view is None:
        raise RegistryError(f"registry-view.json 存在但解析失败：{path}")
    kind = view.get("kind")
    if kind != EXPECTED_KIND:
        raise RegistryError(
            f"registry-view 种类不符：期望 {EXPECTED_KIND}，实为 {kind}；"
            "格式自 light-memory v1.0 冻结，总控不静默降级。"
            + GENERATE_POINTER)
    version = str(view.get("version"))
    if version != EXPECTED_VERSION:
        raise RegistryError(
            f"registry-view 版本不兼容：期望 {EXPECTED_VERSION}，实为 "
            f"{version}；须由 light-memory 侧提供兼容导出或迁移器。"
            + GENERATE_POINTER)
    return path, view


def render_view(view: dict) -> str:
    """按对象类型分组渲染：当前版本指针（短哈希）与状态。"""
    lines = []
    counts = view.get("counts") or {}
    total = sum(counts.values())
    lines.append(f"对象注册统一视图（{EXPECTED_KIND} v{view.get('version')}）"
                 f"：共 {total} 个对象，生成于 {view.get('generated_at')}")
    by_type = view.get("objects_by_type") or {}
    for otype in sorted(by_type):
        rows = by_type[otype]
        lines.append(f"\n[{otype}] {len(rows)} 个")
        for r in rows:
            ver = r.get("current_version")
            ver_s = (str(ver)[:12] + "…") if ver else "—"
            lines.append(
                f"  - {r.get('upstream_id')} | 状态 {r.get('status')} | "
                f"当前版本 {ver_s} | 项目 {r.get('project') or '—'} | "
                f"{r.get('title') or ''}")
    return "\n".join(lines)
