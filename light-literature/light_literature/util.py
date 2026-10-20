"""通用小工具：YAML/JSON 读写、题名 slug、路径定位。"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import yaml

LITERATURE_DIRNAME = "Literature"


def slugify(title: str, max_len: int = 40) -> str:
    """把题名转成文件系统安全的短名；全非 ASCII 时退化为 'paper'。"""
    text = unicodedata.normalize("NFKD", title or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "paper"


def read_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def literature_dir(project_dir: Path) -> Path:
    return Path(project_dir) / LITERATURE_DIRNAME


def paper_dir(project_dir: Path, paper_id: str) -> Path:
    pdir = literature_dir(project_dir) / paper_id
    if not pdir.is_dir():
        raise FileNotFoundError(f"未找到论文目录：{pdir}（先运行 ingest）")
    return pdir


def corpus_paper_ids(project_dir: Path) -> list[str]:
    """已入库且已有 source_map 的论文 ID 列表 (目录名字典序)。

    claim-check 定位与 ask 检索的语料范围：Literature/ 下同时具备
    paper.yaml 与 source_map.json 的单篇目录。
    """
    lit = literature_dir(project_dir)
    if not lit.is_dir():
        return []
    return sorted(
        d.name for d in lit.iterdir()
        if d.is_dir() and (d / "paper.yaml").exists()
        and (d / "source_map.json").exists())


def load_paper_yaml(project_dir: Path, paper_id: str) -> tuple[Path, dict]:
    pdir = paper_dir(project_dir, paper_id)
    ypath = pdir / "paper.yaml"
    if not ypath.exists():
        raise FileNotFoundError(f"缺少 paper.yaml：{ypath}")
    return pdir, read_yaml(ypath)


def save_paper_yaml(pdir: Path, data: dict) -> None:
    write_yaml(pdir / "paper.yaml", data)
