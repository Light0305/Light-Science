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
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .project import load_package, provenance_row
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


def build_prompt(root, fig_id: str, by: str | None = None) -> dict:
    root = Path(root)
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
    path = prompt_path(root, fig_id)
    old_version = _existing_version(path)
    if old_version is not None:
        version = old_version + 1
    elif str(gallery.get("prompt_version") or "").isdigit():
        version = int(gallery["prompt_version"])
    else:
        version = 1

    snapshot = ((pkg["head"].get("target_journal") or {})
                .get("ai_policy_snapshot") or {})
    front = {
        "prompt_id": f"{fig_id}-prompt",
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

    L: list[str] = []
    L.append("---")
    L.append(yaml.safe_dump(front, allow_unicode=True,
                            sort_keys=False).rstrip())
    L.append("---")
    L.append("")
    L.append(f"# 提示词 · {fig_id}（v{version}）")
    L.append("")
    L.append("## 1 全局")
    L.append("")
    L.append(f"- 核心结论：{contract.get('core_conclusion')}")
    L.append(f"- 本图回答的问题：{contract.get('results_question')}")
    L.append(f"- 图型（原型）：{contract.get('archetype')}")
    anchor = gallery.get("style_anchor") or "（未引图库条目：独立构图）"
    L.append(f"- 风格锚：{anchor}")
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
        archived = archive_dir / f"{fig_id}.v{old_version}.md"
        archived.write_text(path.read_text(encoding="utf-8"),
                            encoding="utf-8")
    path.write_text(text, encoding="utf-8")

    update_provenance_row(root, fig_id, {
        "prompt_version": str(version),
        "policy_snapshot_ref": (contract.get("policy_check") or {}).get(
            "policy_snapshot_ref"),
    }, by=by or "light-figure prompt build")

    return {
        "fig_id": fig_id,
        "prompt": f"{PROMPTS_DIR}/{fig_id}.md",
        "version": version,
        "archived": str(archived.relative_to(root)) if archived else None,
    }
