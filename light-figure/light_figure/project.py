"""图包文件群：布局、骨架创建、读写。

文件群（草案 §一）：
  figure.yaml            登记头（权威）：承接快照 + 包状态机 + 逐图状态表
  contracts/<fig_id>.yaml  图合同（F0 五点合同，每图一份）
  backend.json           数据图后端登记（解析顺序结果落盘）
  journal_contract.yaml  期刊图形合同登记（逐刊，可被同刊多包复用）
  provenance.yaml        一本账（每图一条，约束 10）
  FIGURE_REPORT.md       report 生成（手工区保留）
  data/                  数据图线（scripts/ source-data/ previews/）
  schematic/             方法图线（prompts/ reference/ redraw/）
  audit/                 审计产物（Phase 2）
  exports/               交付物 + delivery.yaml（Phase 3）
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .util import (
    dump_json, dump_yaml, load_structured, sha256_text, slugify, today,
)

FILES = {
    "head": "figure.yaml",
    "backend": "backend.json",
    "journal_contract": "journal_contract.yaml",
    "provenance": "provenance.yaml",
    "report": "FIGURE_REPORT.md",
}

DIRS = [
    "contracts",
    "data/scripts", "data/source-data", "data/previews",
    "schematic/prompts", "schematic/reference", "schematic/redraw",
    "audit", "exports",
]


def package_id_for(title: str) -> str:
    return f"{slugify(title, fallback='figures')}_{sha256_text(title or '')[:6]}"


def contract_relpath(fig_id: str) -> str:
    return f"contracts/{fig_id}.yaml"


# ---------------------------------------------------------------- 骨架

def new_head(title: str) -> dict:
    return {
        "package_id": package_id_for(title),
        "title": title,
        "status": "intake",
        "status_history": [
            {"state": "intake", "at": today(), "by": "light-figure init"},
        ],
        "created_at": today(),
        "updated_at": today(),
        "intake": None,
        "target_journal": None,
        "figures": [],
        "reflux": [],
    }


def new_backend() -> dict:
    """后端登记骨架：未决定状态（backend=None），决定后按 D2 落盘。"""
    return {
        "backend": None,
        "decided_via": None,
        "decided_at": None,
        "scope": "package",
        "overrides": [],
    }


def new_journal_contract() -> dict:
    """期刊合同骨架：尺寸锚为 Nature 现行值（约束 14），registered=False
    表示尚未按目标刊官方指南逐项登记——骨架值不许当登记值用。"""
    anchors = schema.JOURNAL_ANCHORS
    return {
        "registered": False,
        "journal": None,
        "version": None,
        "checked_at": None,
        "source_url": None,
        "columns_mm": {
            "single": anchors["single_column_mm"],
            "double": anchors["double_column_mm"],
        },
        "max_height_mm": anchors["max_height_mm"],
        "font": {
            "family": None,
            "min_pt": anchors["font_min_pt"],
            "max_pt": anchors["font_max_pt"],
            "glyph_floor_pt": anchors["glyph_floor_pt"],
        },
        "formats_main": ["pdf", "eps", "svg"],
        "preview": {"tiff_dpi": 600, "png": True},
        "palettes": {"categorical": None, "continuous": None},
        "tolerances": {
            param: spec["default"]
            for param, spec in schema.TOLERANCE_PARAMS.items()
        },
        "tolerance_exemptions": [],
        "overrides": [],
    }


def new_provenance() -> dict:
    return {
        "kind": "light-figure/provenance",
        "version": "1.0",
        "entries": [],
    }


def new_provenance_row(fig_id: str, line: str) -> dict:
    """账行骨架（约束 10）：随图合同开立，字段随产物逐步落实；
    历史行只增不改的纪律在 Phase 2 的更新命令里执行。"""
    row = {
        "fig_id": fig_id,
        "line": line,
        "opened_at": today(),
    }
    if line == "schematic":
        row.update({
            "prompt_version": None,
            "generation_model": None,      # {name, version}
            "reference_image_hash": None,
            "reference_acceptance": {      # 约束 9 参考图验收（Phase 2）
                "done": False, "by": None, "at": None, "checks": {}},
            "redraw_source": None,         # {path, hash}
            "label_check": {"done": False, "by": None, "at": None},
            "policy_snapshot_ref": None,
            "manual_corrections_log": None,
        })
    else:
        row.update({
            "backend": None,
            "runtime_version": None,
            "script_hash": None,
            "source_data_hash": None,
            "style_build_hash": None,
            "palette_registry_version": None,
        })
    return row


def new_contract_stub(fig_id: str, line: str) -> dict:
    """图合同骨架（草案 §1.2）：字段先行、内容待 contracted 段前补齐，
    校验器对缺项逐项点名（约束 1：合同不过不许出图）。"""
    contract = {
        "fig_id": fig_id,
        "line": line,
        "core_conclusion": None,
        "results_question": None,
        "archetype": None,
        "panel_map": [],
        "evidence_requirements": {
            "statistics": None,
            "source_data": None,
            "image_integrity_notes": None,
        },
        "density_stance": {"stance": None, "reason": None},
        "export_contract_ref": {
            "journal_contract": FILES["journal_contract"],
            "overrides": [],
        },
        "reviewer_risk": [],
        "data_integrity": {"exclusions": None},
        "sister_library_refs": {
            "method_gallery": None,
            "visio_components": [],
            "data_gallery": None,
        },
    }
    if line == "schematic":
        contract["policy_check"] = {
            "policy_snapshot_ref": None,
            "reference_not_in_delivery": None,
            "degradation_path": "normal",
        }
        contract["role_palette_ref"] = None
        contract["palette_confirmation"] = {
            "confirmed_by": None, "confirmed_at": None,
        }
    return contract


def new_figure_row(fig_id: str, kind: str, line: str) -> dict:
    """figure.yaml 逐图状态表行：包状态由逐图状态机械汇总（草案 §1.1），
    本行是汇总的输入，不许手写包级结论。"""
    return {
        "fig_id": fig_id,
        "kind": kind,
        "line": line,
        "contract_ref": contract_relpath(fig_id),
        "backend": None,
        "stage": "intake",
        "audit_final": "pending",
        "delivery_status": "pending",
    }


def init_package(root, title: str) -> dict:
    root = Path(root)
    if (root / FILES["head"]).exists():
        raise FileExistsError(f"图包已存在：{root / FILES['head']}")
    root.mkdir(parents=True, exist_ok=True)
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    head = new_head(title)
    save_head(root, head)
    dump_json(root / FILES["backend"], new_backend())
    dump_yaml(root / FILES["journal_contract"], new_journal_contract())
    dump_yaml(root / FILES["provenance"], new_provenance())
    return head


# ---------------------------------------------------------------- 读写

def _load_or(path: Path, default):
    if not path.exists():
        return default
    data = load_structured(path)
    return data if data is not None else default


def load_package(root) -> dict:
    root = Path(root)
    head = None
    if (root / FILES["head"]).exists():
        head = load_structured(root / FILES["head"])
    contracts = {}
    contracts_dir = root / "contracts"
    if contracts_dir.exists():
        for p in sorted(contracts_dir.glob("*.yaml")):
            data = load_structured(p)
            if isinstance(data, dict) and data.get("fig_id"):
                contracts[data["fig_id"]] = data
    return {
        "root": root,
        "head": head,
        "backend": _load_or(root / FILES["backend"], new_backend()),
        "journal_contract": _load_or(
            root / FILES["journal_contract"], new_journal_contract()),
        "provenance": _load_or(root / FILES["provenance"], new_provenance()),
        "contracts": contracts,
    }


def save_head(root, head: dict) -> None:
    head["updated_at"] = today()
    dump_yaml(Path(root) / FILES["head"], head)


def save_backend(root, backend: dict) -> None:
    dump_json(Path(root) / FILES["backend"], backend)


def save_journal_contract(root, contract: dict) -> None:
    dump_yaml(Path(root) / FILES["journal_contract"], contract)


def save_provenance(root, provenance: dict) -> None:
    dump_yaml(Path(root) / FILES["provenance"], provenance)


def save_contract(root, contract: dict) -> None:
    path = Path(root) / contract_relpath(contract["fig_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_yaml(path, contract)


# ---------------------------------------------------------------- 查询

def figure_row(head: dict, fig_id: str):
    for row in (head or {}).get("figures") or []:
        if row.get("fig_id") == fig_id:
            return row
    return None


def provenance_row(provenance: dict, fig_id: str):
    for row in (provenance or {}).get("entries") or []:
        if row.get("fig_id") == fig_id:
            return row
    return None


def effective_backend(backend_reg: dict, fig_id: str):
    """逐图实际后端解析：逐图覆写优先于包级默认。

    返回 (backend, override_row|None)；未决定时 backend 为 None。
    同图在 overrides 中出现多次由校验器判冲突（本函数取首条不许静默
    掩盖冲突——validate 会报错，消费方不得在 validate 未过时取用）。
    """
    reg = backend_reg or {}
    for row in reg.get("overrides") or []:
        if row.get("fig_id") == fig_id:
            return row.get("backend"), row
    return reg.get("backend"), None
