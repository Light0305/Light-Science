"""案件包文件群：布局、骨架创建、登记头读写、状态流转。

文件群（落本地项目目录，一案一包；未申请案件材料只存本地，Q9）：
  case.yaml            登记头（权威）：状态机 + 当事人占位 + 硬门
                       blocked 字段（与 leader LD-04 blocked_gate 族同形）
  intake/              P0 公开审计 + P1 源图谱/候选/交底书
  novelty/             P2 检索日志（jsonl 只增）+ 候选池 + D1 锁定
  draft/               P3 权要/说明书/摘要/标记/支持映射 + filing/ 申报副本
  check/               P4 检查报告 + 红队记录
  oa/                  P5 审查意见/修改账（jsonl 只增）+ 会稿问题清单
  ledger.yaml          P6 期限清单 + 版本链 + worth-it + memory_export 段
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .util import dump_yaml, load_structured, sha256_text, slugify, today

FILES = {
    "case": "case.yaml",
    "audit": "intake/public_audit.yaml",
    "source_map": "intake/source_map.yaml",
    "candidates": "intake/candidates.yaml",
    "disclosure": "intake/disclosure.md",
    "search_log": "novelty/search_log.jsonl",
    "pool": "novelty/pool.yaml",
    "d1": "novelty/d1.yaml",
    "claims": "draft/claims.yaml",
    "claims_md": "draft/claims.md",
    "specification_md": "draft/specification.md",
    "abstract_md": "draft/abstract.md",
    "numerals": "draft/numerals.yaml",
    "support_map": "draft/support_map.yaml",
    "gaps": "draft/gaps.yaml",
    "filing_dir": "draft/filing",
    "check_report": "check/check_report.yaml",
    "redteam": "check/redteam.yaml",
    "oa_actions": "oa/actions.jsonl",
    "oa_amendments": "oa/amendments.jsonl",
    "meeting_questions": "oa/meeting_questions.md",
    "ledger": "ledger.yaml",
}


class PatentError(Exception):
    """纪律错误：逐项点名（gaps），不给整体式含糊失败。"""

    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def case_id_for(title: str) -> str:
    return f"PT-{slugify(title, fallback='case')}_{sha256_text(title or '')[:6]}"


def case_path(root, key: str) -> Path:
    return Path(root) / FILES[key]


def new_case(title: str, *, patent_type: str = "invention",
             jurisdiction: str = "CN", ai_related: bool = False) -> dict:
    gaps = []
    if patent_type not in schema.PATENT_TYPES_V1:
        gaps.append(
            f"专利类型 {patent_type!r} 不在 v1 范围：v1 只做发明"
            "（实用新型与外观登记 v1.1，拍板 Q1）")
    if jurisdiction not in schema.JURISDICTIONS_V1:
        gaps.append(
            f"法域 {jurisdiction!r} 不在 v1 范围：v1 只做中国"
            "（PCT 只给时间窗提示，拍板 Q2）")
    if not (title or "").strip():
        gaps.append("缺发明名称")
    if gaps:
        raise PatentError(gaps)
    return {
        "kind": "light-patent/case",
        "version": "1.0",
        "case_id": case_id_for(title),
        "title": title,
        "patent_type": patent_type,
        "jurisdiction": jurisdiction,
        "ai_related": bool(ai_related),
        "status": "intake",
        "status_history": [
            {"state": "intake", "at": today(), "by": "light-patent init"},
        ],
        "created_at": today(),
        "updated_at": today(),
        # 当事人：未知即占位（LP-12）；发明人只记自然人姓名，
        # 身份信息线下核对、不落本包（84 号令 4.1.2 / LP-12）。
        "parties": {
            "applicant": "待填写/需确认",
            "inventors": [],
            "priority": [],
        },
        "filing": {
            "application_no": None,
            "filing_date": None,
            "planned_filing_date": None,
        },
        # 硬门落点（leader LD-04 blocked_gate 字段族同形）：
        # null = 无门；否则 {gate_id, detail, fix_pointer}。
        "blocked": None,
        "degraded": None,  # 查新不过等降级点名（非阻断）
        "disclaimers": [schema.DRAFT_DISCLAIMER],
    }


def init_package(root, title: str, **kwargs) -> dict:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    case = new_case(title, **kwargs)
    for sub in ("intake", "novelty", "draft", "draft/filing", "check", "oa"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    save_case(root, case)
    save_ledger(root, new_ledger(case))
    return case


def new_ledger(case: dict) -> dict:
    return {
        "kind": "light-patent/ledger",
        "case_id": case["case_id"],
        "deadlines": [],
        "version_chain": [],
        "worth_it": None,
        "memory_export": {"objects": [], "events": [], "facts": []},
    }


def load_case(root) -> dict:
    case = load_structured(case_path(root, "case"))
    if not case:
        raise PatentError(["案件包不存在（先 init）"])
    return case


def save_case(root, case: dict) -> None:
    case["updated_at"] = today()
    dump_yaml(case_path(root, "case"), case)


def load_ledger(root) -> dict:
    ledger = load_structured(case_path(root, "ledger"))
    if ledger is None:
        case = load_case(root)
        ledger = new_ledger(case)
    return ledger


def save_ledger(root, ledger: dict) -> None:
    dump_yaml(case_path(root, "ledger"), ledger)


def set_status(root, case: dict, state: str, by: str) -> None:
    if state not in schema.CASE_STATES:
        raise PatentError([f"未知状态 {state!r}"])
    case["status"] = state
    case.setdefault("status_history", []).append(
        {"state": state, "at": today(), "by": by})
    save_case(root, case)


def load_yaml_or(root, key: str, default):
    data = load_structured(case_path(root, key))
    return default if data is None else data
