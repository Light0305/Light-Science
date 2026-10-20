"""数据图生产路径（F2，约束 3/13/14）：登记脚本 → 源级预检 →
matplotlib 执行 → 最终 PDF + PNG 预览 + 对齐量测清单 + provenance 回填。

脚本契约（data/scripts/<fig_id>.py）：
- 文件头登记块（`# --- light-figure-script ---` … `# --- end ---`，
  注释内 YAML）：fig_id / style_build_hash / column / panels{rows,cols} /
  axes{轴名: {direction, limits, data_min, data_max, truncated,
  truncation_declared}} / aspect{ratio, declared} / area_encoding /
  palette{categorical, continuous}。诚实门（audit.honesty）消费 axes
  登记判读，本预检只查登记齐备与样式绑定。
- 脚本定义 `draw(fig, axes)`：axes 为行优先展开的 Axes 列表（长度
  rows*cols）；脚本不许自带 figsize（尺寸由样式编译从栏宽推导）、
  不许自存文件（落盘由本模块统一执行，保证产物与量测同源）。

运行时缺失/后端非 Python 时如实落 gap 停住，不许跨后端兜底（约束 2）。
"""

from __future__ import annotations

import importlib.util
import platform
import re
import sys
from pathlib import Path

import yaml

from .project import effective_backend, load_package
from .provenance import update_provenance_row
from .style import bundle_current, derive_figsize
from .util import dump_json, sha256_file

HEADER_START = "# --- light-figure-script ---"
HEADER_END = "# --- end light-figure-script ---"

_BANNED_CMAP_RE = re.compile(
    r"""(?:cmap|colormap)\s*=\s*['"]?(rainbow|jet|hsv)['"]?\b
        |plt\.cm\.(rainbow|jet|hsv)\b
        |cm\.(rainbow|jet|hsv)\b""",
    re.VERBOSE)
_FIGSIZE_RE = re.compile(r"figsize\s*=|set_size_inches\s*\(")


class ProduceError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 脚本头登记

def parse_script_header(text: str) -> dict | None:
    """抽取脚本头登记块并解析为 dict；无登记块返回 None，块内 YAML
    损坏抛 ValueError（由调用方落 gap，不许静默当无登记）。"""
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines)
                     if ln.strip() == HEADER_START)
        end = next(i for i, ln in enumerate(lines)
                   if ln.strip() == HEADER_END and i > start)
    except StopIteration:
        return None
    body = []
    for ln in lines[start + 1:end]:
        stripped = ln.lstrip()
        if stripped.startswith("#"):
            content = stripped[1:]
            if content.startswith(" "):
                content = content[1:]
            body.append(content)  # 只剥 "# "，保留相对缩进（嵌套 YAML 靠它）
        else:
            body.append(ln)
    data = yaml.safe_load("\n".join(body))
    if not isinstance(data, dict):
        raise ValueError("脚本头登记块不是 YAML 对象")
    return data


def script_path(root, fig_id) -> Path:
    return Path(root) / "data" / "scripts" / f"{fig_id}.py"


def source_data_path(root, contract) -> Path | None:
    ref = ((contract or {}).get("evidence_requirements") or {}).get(
        "source_data")
    if not ref or ref == "none":
        return None
    path = Path(ref)
    return path if path.is_absolute() else Path(root) / path


def precheck_script(root, fig_id, bundle) -> tuple[dict | None, list]:
    """源级预检（草案 §1.3：警告/阻断的第一层，交付判定以产物审计为准）。

    返回 (header, gaps)：gaps 非空即不许执行。
    """
    gaps = []
    path = script_path(root, fig_id)
    if not path.exists():
        return None, [f"数据图 {fig_id} 缺绘图脚本 data/scripts/{fig_id}.py"]
    text = path.read_text(encoding="utf-8")
    try:
        header = parse_script_header(text)
    except ValueError as e:
        return None, [f"数据图 {fig_id} 脚本头登记块损坏：{e}"]
    if header is None:
        return None, [f"数据图 {fig_id} 脚本缺文件头登记块"
                      "（light-figure-script：fig_id/style_build_hash/"
                      "panels/axes/aspect/area_encoding/palette）"]
    if header.get("fig_id") != fig_id:
        gaps.append(f"脚本头登记 fig_id={header.get('fig_id')!r} 与"
                    f"目标图 {fig_id} 不一致")
    if bundle is not None:
        declared_hash = header.get("style_build_hash")
        if declared_hash != bundle["style_build_hash"]:
            gaps.append(
                f"脚本头声明的 style_build_hash {str(declared_hash)[:12]}… "
                f"与当前编译 bundle {bundle['style_build_hash'][:12]}… "
                "不一致：脚本只许消费当前编译产物，样式变更后须同步脚本头")
    panels = header.get("panels") or {}
    if not isinstance(panels.get("rows"), int) \
            or not isinstance(panels.get("cols"), int):
        gaps.append("脚本头登记缺 panels{rows, cols}（尺寸推导的输入）")
    if header.get("column") not in ("single", "double"):
        gaps.append("脚本头登记 column 须为 single / double（栏位决定图宽）")
    axes = header.get("axes")
    if not isinstance(axes, dict) or not axes:
        gaps.append("脚本头登记缺 axes 坐标轴口径（诚实门判据，约束 15）")
    else:
        for axis_name, axis in axes.items():
            if not isinstance(axis, dict) \
                    or axis.get("direction") not in ("increasing",
                                                     "decreasing"):
                gaps.append(f"axes.{axis_name} 缺 direction 登记"
                            "（increasing / decreasing）")
    if not isinstance(header.get("aspect"), dict):
        gaps.append("脚本头登记缺 aspect{ratio, declared}（宽高比登记）")
    if header.get("area_encoding") is None:
        gaps.append("脚本头登记缺 area_encoding（none / area / radius）")
    if _BANNED_CMAP_RE.search(text):
        gaps.append("脚本使用禁用色标（rainbow/jet/hsv，约束 4：彩虹色标禁用）")
    if _FIGSIZE_RE.search(text):
        gaps.append("脚本自带 figsize：尺寸只许由样式编译从栏宽推导"
                    "（约束 14：禁止逐图手填 figsize）")
    if not re.search(r"^\s*def\s+draw\s*\(", text, re.MULTILINE):
        gaps.append("脚本未定义 draw(fig, axes) 入口（生产路径的执行契约）")
    return header, gaps


# ---------------------------------------------------------------- 执行

def _load_module(path: Path, fig_id: str):
    name = f"light_figure_script_{fig_id.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _measure_alignment(fig, header, contract) -> list:
    """最终布局 draw 后量测 plot-area 矩形（PDF pt，左上原点）。

    量测分工学 Yuan：物理契约一份（bbox_pt + 行列组），量测由选中
    后端在自己的最终布局上完成——本函数是 Python 侧的量测实现。
    """
    import matplotlib

    fig.canvas.draw()
    dpi = fig.dpi
    page_w_pt = fig.get_figwidth() * 72.0
    page_h_pt = fig.get_figheight() * 72.0
    panels = []
    axes = list(fig.axes)
    cols = (header.get("panels") or {}).get("cols") or 1
    contract_ids = [p.get("panel_id")
                    for p in (contract or {}).get("panel_map") or []]
    for i, ax in enumerate(axes):
        extent = ax.get_window_extent()
        x0 = extent.x0 / dpi * 72.0
        x1 = extent.x1 / dpi * 72.0
        y0 = page_h_pt - extent.y1 / dpi * 72.0
        y1 = page_h_pt - extent.y0 / dpi * 72.0
        panels.append({
            "panel_id": contract_ids[i] if i < len(contract_ids)
                        else f"panel-{i + 1}",
            "bbox_pt": [round(x0, 3), round(y0, 3),
                        round(x1, 3), round(y1, 3)],
            "row": i // cols, "col": i % cols,
        })
    return panels


def produce_data_figure(root, fig_id: str, by: str | None = None) -> dict:
    root = Path(root)
    pkg = load_package(root)
    head = pkg["head"]
    if head is None:
        raise ProduceError(["图包不存在（先 init）"])
    row = next((r for r in head.get("figures") or []
                if r.get("fig_id") == fig_id), None)
    if row is None:
        raise ProduceError([f"图 {fig_id} 不在逐图状态表中"])
    if row.get("line") != "data":
        raise ProduceError([f"图 {fig_id} 是方法图线，produce 只执行数据图线"
                            "（约束 3：定量图代码分流）"])
    effective, _ = effective_backend(pkg["backend"], fig_id)
    if effective is None:
        raise ProduceError([f"图 {fig_id} 后端未决定（先落盘 backend.json）"])
    if effective != "python":
        raise ProduceError([
            f"图 {fig_id} 登记后端为 {effective}：Phase 2 执行路径只含 "
            "Python（matplotlib）；R 线只产 theme 文本产物，执行留后续"
            "阶段——不许跨后端兜底（约束 2）"])

    bundle, problem = bundle_current(root)
    if problem:
        raise ProduceError([problem])
    header, gaps = precheck_script(root, fig_id, bundle)
    if gaps:
        raise ProduceError(gaps)
    contract = pkg["contracts"].get(fig_id)
    data_path = source_data_path(root, contract)
    if data_path is None:
        raise ProduceError([
            f"图 {fig_id} 的合同 evidence_requirements.source_data "
            "未登记源数据路径（数据图须有源数据或指针+哈希）"])
    if not data_path.exists():
        raise ProduceError([f"图 {fig_id} 源数据不存在：{data_path}"])

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError as e:  # 运行时缺失：报确切阻塞，不跨后端兜底
        raise ProduceError([
            f"Python 后端运行时缺失（{e}）：安装命令 "
            "pip install 'matplotlib>=3.8'（约束 2：不许用其他后端画替代图）"])

    # 样式只许消费编译产物：rcParams 全部来自 bundle
    rc = dict(bundle["rcparams"])
    colors = rc.pop("axes.prop_cycle_colors")
    from cycler import cycler
    rc["axes.prop_cycle"] = cycler(color=colors)
    requested_family = rc.get("font.family")
    available = {f.name for f in font_manager.fontManager.ttflist}
    font_substituted = None
    if requested_family not in available:
        font_substituted = {"requested": requested_family,
                            "used": "DejaVu Sans"}
        rc["font.family"] = "DejaVu Sans"
    if bundle["palettes"]["continuous"]:
        from matplotlib.colors import LinearSegmentedColormap
        lut = bundle["palettes"]["continuous"]["colors"]
        cmap = LinearSegmentedColormap.from_list("light_seq", lut)
        try:
            matplotlib.colormaps.register(cmap)
        except ValueError:
            pass  # 已注册（同进程重跑）

    aspect = None
    for ov in ((contract or {}).get("export_contract_ref") or {}).get(
            "overrides") or []:
        if ov.get("key") == "aspect_ratio" and ov.get("value"):
            aspect = float(ov["value"])
    if aspect is None and (header.get("aspect") or {}).get("ratio"):
        aspect = float(header["aspect"]["ratio"])
    size = derive_figsize(bundle, header["column"],
                          header["panels"]["rows"], header["panels"]["cols"],
                          aspect)

    module = _load_module(script_path(root, fig_id), fig_id)
    with plt.rc_context(rc):
        fig = plt.figure(figsize=tuple(size["figsize_in"]))
        grid = fig.subplots(header["panels"]["rows"],
                            header["panels"]["cols"], squeeze=False)
        axes = [ax for row_ in grid for ax in row_]
        module.draw(fig, axes)
        panels = _measure_alignment(fig, header, contract)
        exports_dir = root / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = exports_dir / f"{fig_id}.pdf"
        fig.savefig(pdf_path, format="pdf")
        preview_path = root / "data" / "previews" / f"{fig_id}.png"
        fig.savefig(preview_path, format="png", dpi=300)
        plt.close(fig)

    artifact_hash = sha256_file(pdf_path)
    exemptions = []
    for ov in ((contract or {}).get("export_contract_ref") or {}).get(
            "overrides") or []:
        if ov.get("key") == "alignment_exemption" \
                and isinstance(ov.get("value"), dict):
            exemptions.append(ov["value"])
    alignment_input = {
        "fig_id": fig_id,
        "artifact": f"exports/{fig_id}.pdf",
        "artifact_sha256": artifact_hash,
        "page_size_pt": [round(size["figsize_in"][0] * 72, 3),
                         round(size["figsize_in"][1] * 72, 3)],
        "panels": panels,
        "exemptions": exemptions,
    }
    audit_dir = root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    dump_json(audit_dir / f"{fig_id}.alignment-input.json", alignment_input)

    cat = bundle["palettes"]["categorical"]
    cont = bundle["palettes"]["continuous"]
    update_provenance_row(root, fig_id, {
        "backend": "python",
        "runtime_version": f"python {platform.python_version()} / "
                           f"matplotlib {matplotlib.__version__}",
        "script_hash": sha256_file(script_path(root, fig_id)),
        "source_data_hash": sha256_file(data_path),
        "style_build_hash": bundle["style_build_hash"],
        "palette_registry_version":
            f"{cat['entry_id']}@{cat['version']} + "
            f"{cont['entry_id']}@{cont['version']}",
    }, by=by or "light-figure produce")

    return {
        "fig_id": fig_id,
        "artifact": f"exports/{fig_id}.pdf",
        "artifact_sha256": artifact_hash,
        "preview": f"data/previews/{fig_id}.png",
        "size": size,
        "alignment_input": f"audit/{fig_id}.alignment-input.json",
        "panels_measured": len(panels),
        "font_substituted": font_substituted,
    }
