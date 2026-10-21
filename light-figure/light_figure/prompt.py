"""提示词产物（F3，约束 6/7）：schematic/prompts/<fig_id>.md。

结构（文件头登记 + 正文六段）：
- 头（YAML front matter）：prompt_id / version / 图库条目 id+版本 /
  风格规则文件 id+版本 / 角色色板指针 / 配色确认记录 / 政策快照指针；
- 正文六段：全局 / 分区 / 全局标注 / 风格规格 / 负面约束 / 政策段
  （底本 = academic-figure-generator 四层模板 + 负面约束独立段 +
  Light 政策段；与 LEARNING 约束 7「五段 + 政策段」的对应：
  全局≈构图+风格锚、分区≈元素清单、全局标注≈文字标注约束、
  风格规格≈角色色板与线条 token 口径）。

纪律：提示词只引角色色板**角色名**、永不写 hex（生成后自检正文无
十六进制色值）；会进图的文本不许含度量字面量（px/pt/% — 生图模型
会把它们画进图里），检出即落 gap 停住；改版 = version 递增 + 旧版
进 archive/ 留档，不许覆写历史版本。

多版变体（2026-10-21 补丁）：build_prompt(variants=[...]) 在同一图库
三元组与角色色板之下并行产多版变体（词表 schema.PROMPT_VARIANTS，
只在构图 / 密度 / 布局流向三维上区分），每版独立文件
schematic/prompts/<fig_id>.<variant>.md、各自六段完整、上述纪律逐版
适用、独立 version 与归档。变体集合与选定登记于合同 prompt_variants
与 provenance 账面；选定经 select_variant 落字，参考图登记/验收须
指明所据变体且与选定一致（见 reference.py）。不带 variants 的构建
行为与单版现状逐字兼容。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import schema
from .project import load_package, provenance_row, save_contract
from .provenance import update_provenance_row
from .style import PANEL_ROLE_TO_PALETTE_ROLE, role_palette
from .util import today

PROMPTS_DIR = "schematic/prompts"
_METRIC_LITERAL_RE = re.compile(r"\d+(?:\.\d+)?\s*(px|pt|mm|cm|%)\b")
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")

NEGATIVE_BASE = [
    "不许出现伪文字、乱码字符与无意义公式符号",
    "不许出现空白占位框：每个模块框必须有子内容",
    "不许用省略号（… / ...）代替内容",
    "不许出现元素清单之外的模块、箭头或图层",
    "不许照片式渲染、3D 立体效果与投影阴影",
    "不许使用彩虹色标与高饱和荧光色",
]


class PromptError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def prompt_path(root, fig_id) -> Path:
    return Path(root) / PROMPTS_DIR / f"{fig_id}.md"


def variant_prompt_path(root, fig_id, variant_id) -> Path:
    return Path(root) / PROMPTS_DIR / f"{fig_id}.{variant_id}.md"


def parse_front_matter(text: str):
    """拆 YAML front matter 与正文：返回 (meta dict, body str)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}, text
    return meta, parts[2].lstrip("\n")


def _existing_version(path: Path) -> int | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    try:
        front = yaml.safe_load(text.split("---", 2)[1])
    except yaml.YAMLError:
        return None
    version = (front or {}).get("version")
    return int(version) if str(version).isdigit() else None


def _panel_labels(panel) -> list:
    labels = panel.get("labels")
    if isinstance(labels, list) and labels:
        return [str(x) for x in labels]
    content = str(panel.get("content") or "").strip()
    return [content] if content else []


def _prompt_context(root, fig_id: str) -> dict:
    """构建前置检查（单版与变体共用）：合同在场、方法图线、配色确认门、
    角色色板指针、面板与标签度量拦截。任一不过逐项点名抛 PromptError。"""
    pkg = load_package(root)
    if pkg["head"] is None:
        raise PromptError(["图包不存在（先 init）"])
    contract = pkg["contracts"].get(fig_id)
    if contract is None:
        raise PromptError([f"图 {fig_id} 无图合同（先 intake 并补齐合同）"])
    if contract.get("line") != "schematic":
        raise PromptError([f"图 {fig_id} 不是方法图线：提示词产物只服务"
                            "方法图线（数据图走代码线，约束 3）"])
    gaps = []
    palette_conf = contract.get("palette_confirmation") or {}
    if not palette_conf.get("confirmed_by") \
            or not palette_conf.get("confirmed_at"):
        gaps.append(f"方法图 {fig_id} 未过配色确认门：角色色板未定"
                    "不许出提示词（约束 7）")
    role_ref = contract.get("role_palette_ref") or {}
    role_reg = role_palette(role_ref.get("entry_id"))
    if role_reg is None:
        gaps.append(f"方法图 {fig_id} 的角色色板指针 role_palette_ref "
                    f"{role_ref.get('entry_id')!r} 不在登记表中")
    panels = contract.get("panel_map") or []
    if not panels:
        gaps.append(f"方法图 {fig_id} 合同 panel_map 为空：无分区可写")
    labels_all = []
    for panel in panels:
        labels_all.extend(_panel_labels(panel))
    for label in labels_all:
        if _METRIC_LITERAL_RE.search(label):
            gaps.append(f"标签含度量字面量（会进图的文本不许带 px/pt/% "
                        f"等度量数字，约束 7）：{label!r}")
    if gaps:
        raise PromptError(gaps)
    gallery = (contract.get("sister_library_refs") or {}).get(
        "method_gallery") or {}
    snapshot = ((pkg["head"].get("target_journal") or {})
                .get("ai_policy_snapshot") or {})
    return {
        "pkg": pkg, "contract": contract, "gallery": gallery,
        "snapshot": snapshot, "role_reg": role_reg, "panels": panels,
        "labels_all": labels_all,
    }


def _render_prompt_file(root, fig_id: str, ctx: dict,
                        variant_id: str | None = None) -> dict:
    """渲染并落盘一版提示词（单版 variant_id=None / 变体各一版）。

    version 语义与归档路径逐版独立：既有文件 → version+1 且旧版进
    archive/；首版取图库条目绑定的提示词版本。变体只改构图 / 密度 /
    布局流向的执行口径，三元组、色板与六段骨架与单版同源。
    """
    contract = ctx["contract"]
    gallery = ctx["gallery"]
    snapshot = ctx["snapshot"]
    role_reg = ctx["role_reg"]
    panels = ctx["panels"]
    labels_all = ctx["labels_all"]
    palette_conf = contract.get("palette_confirmation") or {}
    role_ref = contract.get("role_palette_ref") or {}
    variant = schema.PROMPT_VARIANTS.get(variant_id) \
        if variant_id else None

    if variant_id:
        path = variant_prompt_path(root, fig_id, variant_id)
    else:
        path = prompt_path(root, fig_id)
    old_version = _existing_version(path)
    if old_version is not None:
        version = old_version + 1
    elif str(gallery.get("prompt_version") or "").isdigit():
        version = int(gallery["prompt_version"])
    else:
        version = 1

    front = {
        "prompt_id": f"{fig_id}-prompt-{variant_id}" if variant_id
                     else f"{fig_id}-prompt",
        "fig_id": fig_id,
        "version": version,
        "gallery": {
            "entry_id": gallery.get("entry_id"),
            "version": gallery.get("version"),
            "style_anchor": gallery.get("style_anchor"),
            "bound_prompt_version": gallery.get("prompt_version"),
        } if gallery else None,
        "style_rules": {
            "id": gallery.get("style_anchor"),
            "version": gallery.get("version"),
        } if gallery else None,
        "role_palette": {"entry_id": role_ref.get("entry_id"),
                         "version": role_ref.get("version")},
        "palette_confirmation": {
            "confirmed_by": palette_conf.get("confirmed_by"),
            "confirmed_at": palette_conf.get("confirmed_at"),
        },
        "policy_snapshot_ref": (contract.get("policy_check") or {}).get(
            "policy_snapshot_ref"),
        "generated_at": today(),
        "generator": "light-figure prompt build",
    }
    if variant is not None:
        front["variant"] = {
            "id": variant_id,
            "label": variant["label"],
            "composition": variant["composition"],
            "density": variant["density"],
            "layout_flow": variant["layout_flow"],
        }

    L: list[str] = []
    L.append("---")
    L.append(yaml.safe_dump(front, allow_unicode=True,
                            sort_keys=False).rstrip())
    L.append("---")
    L.append("")
    if variant is not None:
        L.append(f"# 提示词 · {fig_id} · 变体 {variant_id}"
                 f"（{variant['label']}）（v{version}）")
    else:
        L.append(f"# 提示词 · {fig_id}（v{version}）")
    L.append("")
    L.append("## 1 全局")
    L.append("")
    L.append(f"- 核心结论：{contract.get('core_conclusion')}")
    L.append(f"- 本图回答的问题：{contract.get('results_question')}")
    L.append(f"- 图型（原型）：{contract.get('archetype')}")
    anchor = gallery.get("style_anchor") or "（未引图库条目：独立构图）"
    L.append(f"- 风格锚：{anchor}")
    if variant is not None:
        L.append(f"- 变体：{variant_id}（{variant['label']}）")
        L.append(f"- 变体构图：{variant['composition']}")
        L.append(f"- 变体布局流向：{variant['layout_flow']}")
    order = " → ".join(f"面板 {p.get('panel_id')}" for p in panels)
    L.append(f"- 阅读顺序：{order}")
    L.append("- 画面定位：投稿级科学示意图的构图草稿（内部参考），"
             "平涂矢量风、无照片质感。")
    L.append("")
    L.append("## 2 分区")
    L.append("")
    for panel in panels:
        role_name = PANEL_ROLE_TO_PALETTE_ROLE.get(panel.get("role"),
                                                  "neutral")
        L.append(f"### 面板 {panel.get('panel_id')}"
                 f"（推理角色：{panel.get('role')}；证据层级："
                 f"{panel.get('evidence_tier')}）")
        L.append("")
        L.append(f"- 内容：{panel.get('content')}")
        L.append(f"- 主色角色：{role_name}（只引角色名，色值见登记表）")
        L.append("- 子内容：按内容逐项画成带标签的子模块，"
                 "不许留空白占位框。")
        L.append("")
    L.append("## 3 全局标注")
    L.append("")
    L.append("确切标签清单（逐字使用，不许改写、增删或意译）：")
    L.append("")
    for label in labels_all:
        L.append(f"- 「{label}」")
    L.append("")
    L.append("- 维度与公式标注：只许使用标签清单与合同中出现的符号，"
             "不许自创符号体系。")
    L.append("- 非渲染约束声明：本文件其他段落中的一切度量数字"
             "（尺寸、字号、百分比等）仅为排版约束，**不得绘入图中**；"
             "只有语义数字（步骤号、张量形状、轴刻度）可入图。")
    L.append("")
    L.append("## 4 风格规格")
    L.append("")
    L.append(f"- 角色色板：{role_ref.get('entry_id')}"
             f"@{role_ref.get('version')}（已过配色确认门："
             f"{palette_conf.get('confirmed_by')} @ "
             f"{palette_conf.get('confirmed_at')}）")
    breakdown = gallery.get("reference_breakdown") or {}
    if breakdown:
        # FIG-D09：参考图六维拆解入风格段——五维以文本入段；配色
        # 精确 hex 不入正文（正文不落 hex 纪律），只落指针供重绘
        # 阶段查图库条目登记表。
        dim_labels = {
            "layout_flow": "布局流向",
            "module_style": "模块样式",
            "annotation_style": "标注方式",
            "information_density": "信息密度",
            "special_elements": "特殊元素",
        }
        L.append("- 参考图六维拆解（图库条目登记，FIG-D09）：")
        for dim, label in dim_labels.items():
            if breakdown.get(dim):
                L.append(f"  - {label}：{breakdown[dim]}")
        L.append("  - 配色：精确色值已登记于图库条目六维拆解的 "
                 "palette_hex（只供重绘阶段查表，不入提示词正文）")
    if variant is not None:
        L.append(f"- 变体执行口径（本版为准）：布局流向 = "
                 f"{variant['layout_flow']}；信息密度 = "
                 f"{variant['density']}。与图库拆解口径不一致处以本"
                 "变体口径为准（图库三元组与角色色板不变）。")
    L.append("- 角色清单（正文只引角色名，色值由重绘阶段查登记表）：")
    for row_ in role_reg["roles"]:
        L.append(f"  - {row_['role']}：{row_['usage']}")
    L.append("- 线条与形态：统一描边粗细层级（主干 > 支线 > 注记），"
             "圆角矩形表处理模块、直角矩形表数据块、菱形表判定。")
    stance = (contract.get("density_stance") or {})
    L.append(f"- 密度取舍：{stance.get('stance')}（{stance.get('reason')}）")
    L.append("")
    L.append("## 5 负面约束")
    L.append("")
    for item in NEGATIVE_BASE:
        L.append(f"- {item}")
    if stance.get("stance") == "simplicity_first":
        L.append("- 简洁红线：单个框内不许出现整句文字（>15 词判负），"
                 "细节移入图注")
    if stance.get("stance") == "density_first":
        L.append("- 密度优先但每个模块框仍须有子内容，"
                 "不许以密度为名堆叠无标签装饰元素")
    if variant is not None:
        L.append(f"- 变体红线（{variant['label']}）："
                 f"{variant['extra_negative']}")
    L.append("")
    L.append("## 6 政策段")
    L.append("")
    L.append("- 用途定位：本提示词的产物是**内部参考草稿**（构图与"
             "风格参考），不作投稿物件；成品由 Visio 原生重绘"
             "（拍板 D1：重绘成品无 AI 生成像素）。")
    if snapshot:
        L.append(f"- 目标刊 AI 政策快照：ai_images_prohibited="
                 f"{snapshot.get('ai_images_prohibited')}、"
                 f"disclosure_required={snapshot.get('disclosure_required')}"
                 f"（verified_at={snapshot.get('verified_at')}，"
                 f"原文：{snapshot.get('source_url')}）")
    L.append("- 硬拦：参考图本体文件不得进入交付/投稿包"
             "（policy_block 门按哈希机械执行）。")
    L.append("- 参考图验收（约束 9，入包前逐项执行）：逐个标签逐字"
             "对原文核对 / 每个结构对领域事实核对 / 公式、分子式、"
             "数值逐个算对——照描而不核事实是红项。")
    L.append("")
    text = "\n".join(L)

    body = text.split("---", 2)[-1]
    if _HEX_RE.search(body):
        raise PromptError(["生成正文含十六进制色值：提示词只许引角色名"
                           "（内部错误，请查登记表消费路径）"])

    archived = None
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        archive_dir = path.parent / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        if variant_id:
            archived = archive_dir / \
                f"{fig_id}.{variant_id}.v{old_version}.md"
        else:
            archived = archive_dir / f"{fig_id}.v{old_version}.md"
        archived.write_text(path.read_text(encoding="utf-8"),
                            encoding="utf-8")
    path.write_text(text, encoding="utf-8")

    return {
        "prompt": f"{PROMPTS_DIR}/{path.name}",
        "version": version,
        "archived": str(archived.relative_to(root)) if archived else None,
    }


def build_prompt(root, fig_id: str, by: str | None = None,
                 variants: list | None = None) -> dict:
    """生成提示词产物。

    variants=None → 单版（行为与既有口径逐字兼容，文件
    schematic/prompts/<fig_id>.md）；variants=[...] → 多版并行：
    每版独立文件与 version，变体集合登记进合同 prompt_variants 与
    账面，已选变体不在新集合内时选定自动清空（须重选）。
    """
    root = Path(root)
    ctx = _prompt_context(root, fig_id)
    contract = ctx["contract"]

    if variants is None:
        out = _render_prompt_file(root, fig_id, ctx, None)
        update_provenance_row(root, fig_id, {
            "prompt_version": str(out["version"]),
            "policy_snapshot_ref": (contract.get("policy_check") or {})
            .get("policy_snapshot_ref"),
        }, by=by or "light-figure prompt build")
        return {
            "fig_id": fig_id,
            "prompt": out["prompt"],
            "version": out["version"],
            "archived": out["archived"],
        }

    ids: list[str] = []
    for v in variants:
        if v not in ids:
            ids.append(v)
    if not ids:
        raise PromptError(["变体列表为空：至少给一个变体 id"
                           f"（词表 {sorted(schema.PROMPT_VARIANTS)}）"])
    unknown = [v for v in ids if v not in schema.PROMPT_VARIANTS]
    if unknown:
        raise PromptError([
            f"未知提示词变体 {unknown}：词表为 "
            f"{sorted(schema.PROMPT_VARIANTS)}（变体只在构图/密度/"
            "布局流向三维上区分，不许自创）"])
    built = []
    for v in ids:
        out = _render_prompt_file(root, fig_id, ctx, v)
        built.append({"variant_id": v, "file": out["prompt"],
                      "version": out["version"],
                      "archived": out["archived"]})
    prev_selected = (contract.get("prompt_variants") or {}).get(
        "selected_variant")
    selected = prev_selected if prev_selected in ids else None
    contract["prompt_variants"] = {
        "variants": [{"variant_id": b["variant_id"], "file": b["file"],
                      "version": b["version"]} for b in built],
        "selected_variant": selected,
    }
    save_contract(root, contract)
    prov_updates = {
        "prompt_variants": ids,
        "selected_variant": selected,
        "policy_snapshot_ref": (contract.get("policy_check") or {}).get(
            "policy_snapshot_ref"),
    }
    if selected is not None:
        # 选定保留时账面 prompt_version 同步到所选变体的新 version
        sel = next(b for b in built if b["variant_id"] == selected)
        prov_updates["prompt_version"] = str(sel["version"])
    update_provenance_row(root, fig_id, prov_updates,
                          by=by or "light-figure prompt build")
    return {"fig_id": fig_id, "variants": built,
            "selected_variant": selected}


def select_variant(root, fig_id: str, variant_id: str,
                   by: str | None = None) -> dict:
    """变体选定落字：合同 prompt_variants.selected_variant + 账面
    selected_variant / prompt_version（取所选变体的当前 version）。
    未构建登记的变体不许选。"""
    root = Path(root)
    pkg = load_package(root)
    if pkg["head"] is None:
        raise PromptError(["图包不存在（先 init）"])
    contract = pkg["contracts"].get(fig_id)
    if contract is None:
        raise PromptError([f"图 {fig_id} 无图合同（先 intake 并补齐合同）"])
    pv = contract.get("prompt_variants") or {}
    entries = {e.get("variant_id"): e for e in pv.get("variants") or []
               if isinstance(e, dict)}
    if variant_id not in entries:
        raise PromptError([
            f"图 {fig_id} 的变体 {variant_id!r} 未构建登记"
            f"（已登记：{sorted(entries)}）：先 prompt build --variants "
            "构建再选定"])
    pv["selected_variant"] = variant_id
    contract["prompt_variants"] = pv
    save_contract(root, contract)
    version = entries[variant_id].get("version")
    update_provenance_row(root, fig_id, {
        "selected_variant": variant_id,
        "prompt_version": str(version),
    }, by=by or "light-figure prompt select")
    return {"fig_id": fig_id, "selected_variant": variant_id,
            "version": version}
