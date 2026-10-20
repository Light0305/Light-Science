"""SC0 软件定版冻结：源码快照（文件清单 + 哈希 + 行数）。

冻结后一切材料由此快照派生；源码再变，verify 以哈希逐个指出漂移，
须重新冻结（新案件或新版本），不许在漂移的源码上继续出材料（HC-1）。
扫描面：文本源文件。快照文件 snapshot.json 落案件根。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .case import CaseError, log_tool_use
from .util import dump_json, load_structured, sha256_file, today

SNAPSHOT_FILE = "snapshot.json"

#: 快照收录的文本文件扩展（源程序与相关文本）；二进制/媒体不进快照。
TEXT_EXTS = set(schema.LANGUAGE_BY_EXT) | {
    ".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".xml", ".html",
    ".css", ".sh", ".sql", ".r", ".m", ".pl", ".lua",
}
MAX_FILE_BYTES = 2_000_000


def iter_source_files(source_dir: Path):
    """按相对路径排序遍历（顺序确定性是分页可复现的前提）。"""
    out = []
    for p in sorted(Path(source_dir).rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(source_dir)
        if any(part in schema.EXCLUDED_DIR_NAMES for part in rel.parts[:-1]):
            continue
        if p.suffix.lower() not in TEXT_EXTS:
            continue
        if p.stat().st_size > MAX_FILE_BYTES:
            continue
        out.append(p)
    return out


def freeze(root, source_dir) -> dict:
    root, source_dir = Path(root), Path(source_dir)
    if not source_dir.is_dir():
        raise CaseError([f"源码目录不存在：{source_dir}"])
    files = []
    for p in iter_source_files(source_dir):
        rel = p.relative_to(source_dir).as_posix()
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        files.append({
            "path": rel,
            "sha256": sha256_file(p),
            "bytes": p.stat().st_size,
            "total_lines": len(lines),
            "nonempty_lines": sum(1 for ln in lines if ln.strip()),
            "language": schema.LANGUAGE_BY_EXT.get(p.suffix.lower(), ""),
        })
    if not files:
        raise CaseError(["源码目录内无可收录的文本源文件"])
    snap = {
        "kind": "light-software-copyright/snapshot",
        "frozen_at": today(),
        "source_dir": str(source_dir),
        "file_count": len(files),
        "total_lines": sum(f["total_lines"] for f in files),
        "nonempty_lines": sum(f["nonempty_lines"] for f in files),
        "languages": sorted({f["language"] for f in files if f["language"]}),
        "files": files,
    }
    dump_json(root / SNAPSHOT_FILE, snap)
    log_tool_use(root, "tool", "freeze", "snapshot",
                 f"{len(files)} 个文件 / 源程序量 {snap['total_lines']} 行")
    return snap


def load_snapshot(root) -> dict:
    p = Path(root) / SNAPSHOT_FILE
    if not p.exists():
        raise CaseError(["尚无冻结快照（先 freeze）"])
    return load_structured(p)


def verify_snapshot(root) -> list:
    """逐项比对冻结快照：漂移逐个点名（文件消失/新增/哈希变化）。"""
    snap = load_snapshot(root)
    source_dir = Path(snap["source_dir"])
    gaps = []
    frozen = {f["path"]: f for f in snap["files"]}
    current = {}
    if source_dir.is_dir():
        for p in iter_source_files(source_dir):
            current[p.relative_to(source_dir).as_posix()] = p
    for rel, meta in frozen.items():
        p = current.get(rel)
        if p is None:
            gaps.append(f"冻结后文件消失：{rel}")
        elif sha256_file(p) != meta["sha256"]:
            gaps.append(f"冻结后源码漂移：{rel}（哈希不符，须重新冻结）")
    for rel in current:
        if rel not in frozen:
            gaps.append(f"冻结后新增源文件：{rel}（不在快照内，须重新冻结）")
    return gaps
