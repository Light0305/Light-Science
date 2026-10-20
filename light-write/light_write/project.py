"""稿件包文件群：布局、骨架创建、读写。

文件群（草案 §一）：
  manuscript.yaml        登记头（权威）
  claims_register.yaml   主张登记
  numbers_ledger.yaml    数字溯源账
  references.lock.json   引用解析快照（verified 集快照子集）
  references.bib         生成物（由 lock 回填渲染，禁手改）
  figures_manifest.yaml  图表清单
  submission_checklist.yaml 投稿检查（schema 本期定，填充 Phase 2）
  acceptance_contract.yaml  验收合同
  template_record.json   目标刊核查记录快照（register-template 落）
  sections/              逐节 MD
  terminology.yaml       术语账（D-W02，补课采纳）
  body_allocation.yaml   正文分配纪律：主张位置图/结果功能分类/删除日志（D-W01）
  audit/                 审计产物（Phase 2）
  revision/              W7 返修子包（Phase 2/3）
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .util import (
    component_hash, dump_json, dump_yaml, load_structured, sha256_text,
    slugify, today,
)

FILES = {
    "manuscript": "manuscript.yaml",
    "claims": "claims_register.yaml",
    "numbers": "numbers_ledger.yaml",
    "lock": "references.lock.json",
    "bib": "references.bib",
    "figures": "figures_manifest.yaml",
    "checklist": "submission_checklist.yaml",
    "contract": "acceptance_contract.yaml",
    "template_record": "template_record.json",
    "terminology": "terminology.yaml",
    "allocation": "body_allocation.yaml",
}


def manuscript_id_for(title: str) -> str:
    return f"{slugify(title, fallback='manuscript')}_{sha256_text(title or '')[:6]}"


def new_manuscript(title: str, language: str) -> dict:
    return {
        "manuscript_id": manuscript_id_for(title),
        "title": title,
        "language": language,
        "status": "intake",
        "status_history": [
            {"state": "intake", "at": today(), "by": "light-write init"},
        ],
        "created_at": today(),
        "updated_at": today(),
        "intake": None,
        "contribution": None,
        "target_journal": None,
        "authors": [],
        "guarantor": None,
        "declarations": {
            key: {"state": "absent", "note": None}
            for key in schema.DECLARATION_KEYS
        },
        "use_log": [],
        "sections": [],
        "acceptance_contract": {
            "file": FILES["contract"],
            "status": "unset",
            "content_hash": None,
        },
        "protected_statements": [],
        "datasets": [],
        "contract_contested": False,
        "submission_blocked_reason": None,
        "reflux": [],
    }


def new_lock() -> dict:
    return {
        "kind": "light-write/references-lock",
        "version": "1.0",
        "generated_at": None,
        "source": None,
        "entries": [],
    }


def new_contract() -> dict:
    return {
        "kind": "light-write/acceptance-contract",
        "version": "1.0",
        "status": "draft",
        "frozen": False,
        "frozen_at": None,
        "content_hash": None,
        "assertions": [],
    }


def contract_content_hash(contract: dict) -> str:
    """合同内容哈希：只覆盖断言本体（id/text/可判定方式/状态），不含冻结元数据。"""
    from .util import component_hash

    body = [
        {
            "assertion_id": a.get("assertion_id"),
            "text": a.get("text"),
            "checkable_via": a.get("checkable_via"),
            "status": a.get("status"),
        }
        for a in contract.get("assertions") or []
    ]
    return component_hash(body)


def init_package(root, title: str, language: str) -> dict:
    root = Path(root)
    if (root / FILES["manuscript"]).exists():
        raise FileExistsError(f"稿件包已存在：{root / FILES['manuscript']}")
    root.mkdir(parents=True, exist_ok=True)
    (root / "sections").mkdir(exist_ok=True)
    (root / "audit").mkdir(exist_ok=True)
    (root / "revision").mkdir(exist_ok=True)
    manuscript = new_manuscript(title, language)
    save_manuscript(root, manuscript)
    dump_yaml(root / FILES["claims"], {"claims": []})
    dump_yaml(root / FILES["numbers"], {"numbers": []})
    dump_yaml(root / FILES["figures"], {"figures": []})
    dump_yaml(root / FILES["checklist"], {"items": []})
    dump_yaml(root / FILES["contract"], new_contract())
    dump_yaml(root / FILES["terminology"], {"locked": False, "terms": []})
    dump_yaml(root / FILES["allocation"],
              {"enforced": False, "locations": [], "results": [],
               "deletion_log": [], "word_count_delta": 0})
    dump_json(root / FILES["lock"], new_lock())
    from .render import render_bib

    (root / FILES["bib"]).write_text(render_bib([]), encoding="utf-8")
    return manuscript


def _load_yaml_or(path: Path, default):
    if not path.exists():
        return default
    data = load_structured(path)
    return data if data is not None else default


def load_package(root) -> dict:
    root = Path(root)
    manuscript_path = root / FILES["manuscript"]
    manuscript = None
    if manuscript_path.exists():
        manuscript = load_structured(manuscript_path)
    return {
        "root": root,
        "manuscript": manuscript,
        "claims": _load_yaml_or(root / FILES["claims"], {"claims": []}),
        "numbers": _load_yaml_or(root / FILES["numbers"], {"numbers": []}),
        "figures": _load_yaml_or(root / FILES["figures"], {"figures": []}),
        "checklist": _load_yaml_or(root / FILES["checklist"], {"items": []}),
        "contract": _load_yaml_or(root / FILES["contract"], new_contract()),
        "terminology": _load_yaml_or(root / FILES["terminology"],
                                     {"locked": False, "terms": []}),
        "allocation": _load_yaml_or(
            root / FILES["allocation"],
            {"enforced": False, "locations": [], "results": [],
             "deletion_log": [], "word_count_delta": 0}),
        "lock": _load_yaml_or(root / FILES["lock"], new_lock()),
        "template_record": (
            load_structured(root / FILES["template_record"])
            if (root / FILES["template_record"]).exists()
            else None
        ),
    }


def save_manuscript(root, manuscript: dict) -> None:
    manuscript["updated_at"] = today()
    dump_yaml(Path(root) / FILES["manuscript"], manuscript)


def save_claims(root, claims: dict) -> None:
    dump_yaml(Path(root) / FILES["claims"], claims)


def save_lock(root, lock: dict) -> None:
    dump_json(Path(root) / FILES["lock"], lock)


def save_contract(root, contract: dict) -> None:
    dump_yaml(Path(root) / FILES["contract"], contract)


def save_numbers(root, numbers: dict) -> None:
    dump_yaml(Path(root) / FILES["numbers"], numbers)


def save_figures(root, figures: dict) -> None:
    dump_yaml(Path(root) / FILES["figures"], figures)


def save_terminology(root, terminology: dict) -> None:
    dump_yaml(Path(root) / FILES["terminology"], terminology)


def save_allocation(root, allocation: dict) -> None:
    dump_yaml(Path(root) / FILES["allocation"], allocation)


def save_checklist(root, checklist: dict) -> None:
    dump_yaml(Path(root) / FILES["checklist"], checklist)


def manuscript_hash(root) -> str:
    """稿件内容哈希（Phase 2 审计/复核/披露/返修绑定的唯一锚）。

    覆盖：全部节文件原文 + 主张登记 + 数字账 + 图表清单 + 检查清单 +
    lock 条目集 + 登记头的声明区/use_log/语言/标题。任一内容变动 →
    哈希漂移 → 绑此哈希的审计产物、复核收据、披露与回复信一律 STALE。
    纯状态字段（status/时间戳/审计指针本身）不入哈希，防自引用循环。
    """
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"] or {}
    sections = section_files(root)
    from .render import lock_entries_hash

    body = {
        "title": manuscript.get("title"),
        "language": manuscript.get("language"),
        "declarations": manuscript.get("declarations"),
        "use_log": manuscript.get("use_log") or [],
        "sections_meta": [
            {"section_id": s.get("section_id"), "file": s.get("file"),
             "role": s.get("role")}
            for s in manuscript.get("sections") or []
        ],
        "section_texts": {name: sha256_text(text)
                          for name, text in sorted(sections.items())},
        "claims": (pkg["claims"] or {}).get("claims") or [],
        "numbers": (pkg["numbers"] or {}).get("numbers") or [],
        "figures": (pkg["figures"] or {}).get("figures") or [],
        "checklist": (pkg["checklist"] or {}).get("items") or [],
        "lock_entries_hash": lock_entries_hash(
            (pkg["lock"] or {}).get("entries") or []),
    }
    return component_hash(body)


def section_files(root) -> dict:
    """sections/ 下实际存在的节文件：{文件名: 文本}。"""
    sec_dir = Path(root) / "sections"
    out = {}
    if sec_dir.exists():
        for p in sorted(sec_dir.glob("*.md")):
            out[p.name] = p.read_text(encoding="utf-8")
    return out
