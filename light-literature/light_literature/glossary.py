"""术语账本：向项目级 术语账本.md 的表格追加术语行，重复拒绝。

账本格式由 project.init_project 建立：
| 原文术语 | 规范译名 | 首次出现（论文/锚点） | 备注 |
去重口径：原文术语与规范译名任一与已有行相同（英文不区分大小写）即拒绝，
并把已有行原文返回给调用者，避免同一术语两套译名在项目里漂移。
"""

from __future__ import annotations

from pathlib import Path

from . import project as project_mod
from .util import literature_dir


def _clean(cell: str) -> str:
    """单元格清洗：竖线会破坏 Markdown 表格，替换为斜杠；去首尾空白。"""
    return (cell or "").replace("|", "/").strip()


def _existing_rows(text: str) -> list[tuple[int, list[str]]]:
    """返回 (行号, 单元格列表) 列表，仅数据行（跳过表头与分隔行）。"""
    rows = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [_clean(c) for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if cells[0] in ("原文术语",) or set(cells[0]) <= set("-: "):
            continue  # 表头 / 分隔行
        rows.append((lineno, cells))
    return rows


def add_term(project_dir: Path, term: str, zh: str,
             note: str | None = None) -> dict:
    """追加一条术语；重复（中英任一相同）抛 ValueError 并提示已有行。"""
    term, zh = _clean(term), _clean(zh)
    if not term or not zh:
        raise ValueError("term 与 zh 都不能为空")
    project_mod.init_project(project_dir)  # 确保账本文件存在
    path = literature_dir(project_dir) / "术语账本.md"
    text = path.read_text(encoding="utf-8")
    for lineno, cells in _existing_rows(text):
        if cells[0].lower() == term.lower() or cells[1] == zh:
            raise ValueError(
                f"术语重复：与术语账本第 {lineno} 行冲突（已有行："
                f"「{cells[0]} → {cells[1]}」）。如需改译名，先人工修订账本"
                "原行，不要追加第二行")
    line = f"| {term} | {zh} |  | {_clean(note or '')} |"
    with open(path, "a", encoding="utf-8") as f:
        if not text.endswith("\n"):
            f.write("\n")
        f.write(line + "\n")
    return {"term": term, "zh": zh, "row": line}
