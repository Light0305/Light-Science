"""地基命令：init（建项目级产物）与 ingest（单篇入库）。"""

from __future__ import annotations

import csv
import hashlib
import shutil
from datetime import date
from pathlib import Path

import pymupdf

from .util import literature_dir, slugify, write_yaml

# 项目级产物及其初始内容（与 REDESIGN-DRAFT 产物规范一致）
_PROJECT_FILES = {
    "00-文献总览.md": "# 文献总览\n\n| 论文 | 版本 | 状态 | 备注 |\n|---|---|---|---|\n",
    "研究证据矩阵.md": (
        "# 研究证据矩阵\n\n"
        "多篇论文按共同研究问题对齐：方法 / 数据 / 结论 / 局限，冲突显式记录，不静默选一。\n"
    ),
    "参考文献.bib": "% 由 Light-Literature 维护；是 Light-Write 引用的唯一来源。\n",
    "术语账本.md": (
        "# 术语账本\n\n全项目共用一份：原文术语 → 规范中文译名。翻译与笔记共用，不自造术语。\n\n"
        "| 原文术语 | 规范译名 | 首次出现（论文/锚点） | 备注 |\n|---|---|---|---|\n"
    ),
}

_INDEX_COLUMNS = [
    "paper_id", "title", "doi", "source_version", "sha256",
    "pages", "status", "ingested_at",
]


def init_project(project_dir: Path) -> Path:
    """创建 Literature/ 与项目级产物文件；已存在的文件不覆盖。"""
    project_dir = Path(project_dir)
    lit = literature_dir(project_dir)
    lit.mkdir(parents=True, exist_ok=True)
    for name, content in _PROJECT_FILES.items():
        target = lit / name
        if not target.exists():
            target.write_text(content, encoding="utf-8")
    index_path = lit / "文献索引.csv"
    if not index_path.exists():
        with open(index_path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(_INDEX_COLUMNS)
    evidence_path = lit / "证据表.jsonl"
    if not evidence_path.exists():
        evidence_path.write_text("", encoding="utf-8")
    return lit


def _infer_title(pdf_path: Path, doc: pymupdf.Document) -> str:
    """题名推断顺序：PDF 元数据 → 首页最大字号文本行 → 文件名。"""
    meta_title = (doc.metadata or {}).get("title") or ""
    if meta_title.strip():
        return meta_title.strip()
    if len(doc) > 0:
        best_text, best_size = "", 0.0
        for block in doc[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if span["size"] > best_size and span["text"].strip():
                        best_size, best_text = span["size"], span["text"].strip()
        if best_text:
            return best_text
    return pdf_path.stem


def ingest(project_dir: Path, pdf: Path, doi: str | None = None,
           title: str | None = None, source_version: str = "preprint",
           source: str | None = None) -> dict:
    """把一篇 PDF 入库：建单篇目录、复制 原文.pdf、算 SHA-256、写 paper.yaml。

    论文目录名 = 题名 slug + '_' + 内容 SHA-256 前 6 位（稳定 ID 的雏形）。
    """
    project_dir = Path(project_dir)
    pdf = Path(pdf)
    if not pdf.exists():
        raise FileNotFoundError(f"PDF 不存在：{pdf}")
    lit = init_project(project_dir)

    raw = pdf.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    doc = pymupdf.open(pdf)
    pages = len(doc)
    final_title = title or _infer_title(pdf, doc)
    doc.close()

    paper_id = f"{slugify(final_title)}_{sha256[:6]}"
    pdir = lit / paper_id
    (pdir / "assets" / "figures").mkdir(parents=True, exist_ok=True)
    (pdir / "assets" / "tables").mkdir(parents=True, exist_ok=True)
    (pdir / "supplementary").mkdir(parents=True, exist_ok=True)
    dest = pdir / "原文.pdf"
    if not dest.exists():
        shutil.copyfile(pdf, dest)

    today = date.today().isoformat()
    paper_yaml = {
        "paper_id": paper_id,
        "title": final_title,
        "doi": doi,
        "source_version": source_version,  # version_of_record | preprint | abstract_only
        "source": source or str(pdf),
        "sha256": sha256,
        "pages": pages,
        "ingested_at": today,
        # locator_mode：page-grounded（全文可定位）/ structure-grounded / source-limited
        "locator_mode": "page-grounded" if source_version != "abstract_only" else "source-limited",
        "status": {
            "ingested": True,
            "triage": "pending",
            "extract": "pending",
            "translate": "pending",
            "notes": "pending",
            "verify": "pending",
        },
        "triage": None,  # 分诊执行后写入逐页体检结果
    }
    write_yaml(pdir / "paper.yaml", paper_yaml)

    # 追加一行到文献索引（同一 paper_id 已存在则不重复追加）
    index_path = lit / "文献索引.csv"
    existing = ""
    if index_path.exists():
        existing = index_path.read_text(encoding="utf-8")
    if paper_id not in existing:
        with open(index_path, "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow([
                paper_id, final_title, doi or "", source_version,
                sha256, pages, "ingested", today,
            ])
    paper_yaml["paper_dir"] = str(pdir)
    return paper_yaml
