"""选刊包文件群：布局、骨架创建、读写。

文件群（落本地项目目录，每次投稿一包）：
  selection.yaml         登记头（权威）：指纹 + 约束 + 候选池 +
                         风险门结果 + excluded[] 留痕 + 状态机
  evidence/              先例路原始响应留痕（OpenAlex JSON，逐查询一份）
  SELECTION_REPORT.md    选刊报告（三档证据卡，report 生成）
  selection.json         机器可读全集导出（report 生成，供衔接段消费）
  journal/target/        定刊后单刊目录（Phase 2，E5 口径）
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .util import dump_yaml, load_structured, sha256_text, slugify, today

FILES = {
    "selection": "selection.yaml",
    "report": "SELECTION_REPORT.md",
    "selection_json": "selection.json",
    "evidence_dir": "evidence",
    # 定刊交接物（Phase 2，E5 单刊单目录）
    "target_dir": "journal/target",
    "manifest": "journal/target/download-manifest.json",
    "check_record": "journal/target/check-record.json",
    "handoff_md": "journal/target/handoff.md",
}


def selection_id_for(title: str) -> str:
    return f"{slugify(title, fallback='selection')}_{sha256_text(title or '')[:6]}"


def candidate_id_for(name: str) -> str:
    return f"J-{slugify(name, fallback='journal')}_{sha256_text(name or '')[:6]}"


def new_selection(title: str, language: str, manuscript_type: str) -> dict:
    return {
        "kind": "light-journal-select/selection",
        "version": "1.0",
        "selection_id": selection_id_for(title),
        "title": title,
        "status": "draft",
        "status_history": [
            {"state": "draft", "at": today(), "by": "light-journal-select init"},
        ],
        "created_at": today(),
        "updated_at": today(),
        # 稿件指纹（fingerprint 命令落）：题摘 + 结构化指纹
        "manuscript": {
            "title": title,
            "abstract": None,
            "keywords": [],
            "type": manuscript_type,
            "language": language,
            "source_ref": None,   # Analysis 结论包 / Write 稿件包路径（如有）
        },
        "fingerprint": None,
        "queries": [],
        # 约束（键全集见 schema.CONSTRAINT_KEYS，缺项不许静默默认）
        "constraints": {key: None for key in schema.CONSTRAINT_KEYS},
        "constraints_confirmed": False,
        # 先例路运行留痕：逐查询 {query, window, status, ...}
        "precedent_runs": [],
        # 低于入门门槛的近失刊（候选全集含未入围者，供报告附录）
        "precedent_near_misses": [],
        "candidates": [],
        # 被排除刊与理由（只增不改，永不删除条目）
        "excluded": [],
        # 定刊（Phase 2 decide 回填）
        "decision": None,
        # 交接（Phase 2 handoff 回填）
        "handoff": None,
        "notes": [],
    }


def new_candidate(name: str, source: str) -> dict:
    return {
        "candidate_id": candidate_id_for(name),
        "name": name,
        "issn": None,
        "eissn": None,
        "publisher": None,
        "homepage_url": None,
        "guide_url": None,
        "openalex_source_id": None,
        "source": source,            # precedent | search | finder_manual
        "source_detail": None,       # 如 finder 名 / 检索补充出处
        "precedent": None,           # 先例统计块（precedent.py 落）
        "verification": None,        # 核验块（verify.py 落）
        "risk": None,                # 风险门块（gate.py 落）
        "tier": None,                # challenge|target|safety|excluded
        "provisional": False,        # 仅刊名/指标支撑 → 至多「暂定」（JS-04）
        "match_reasons": [],         # 分档时由证据生成的匹配理由（report.py 落）
        "flags": [],                 # 约束冲突等机器标记（report.py 落）
    }


def init_package(root, title: str, language: str,
                 manuscript_type: str = "research") -> dict:
    root = Path(root)
    if (root / FILES["selection"]).exists():
        raise FileExistsError(f"选刊包已存在：{root / FILES['selection']}")
    root.mkdir(parents=True, exist_ok=True)
    (root / FILES["evidence_dir"]).mkdir(exist_ok=True)
    selection = new_selection(title, language, manuscript_type)
    save_selection(root, selection)
    return selection


def load_selection(root) -> dict | None:
    path = Path(root) / FILES["selection"]
    if not path.exists():
        return None
    data = load_structured(path)
    return data if isinstance(data, dict) else None


def save_selection(root, selection: dict) -> None:
    selection["updated_at"] = today()
    dump_yaml(Path(root) / FILES["selection"], selection)


def find_candidate(selection: dict, ref: str) -> dict | None:
    """按 candidate_id 或刊名找候选（核验/风险门登记的寻址口径）。"""
    for cand in selection.get("candidates") or []:
        if cand.get("candidate_id") == ref or cand.get("name") == ref:
            return cand
    return None
