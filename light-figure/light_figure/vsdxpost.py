"""Visio 文件级后处理格（工具规划 T2 批：vsdx vendored 化落地）。

定位（SKILL §8 第 2 项三格分工 / §16.2 后处理格）：对文件级构建
产出的 .vsdx 做批量改字、改色、形状抽取与两文件 diff——**不承担
从零重建**（vsdx 无从零绘制 API，重建只走 redraw build）。工具
本体 = dave-howard/vsdx 0.6.1（BSD-3-Clause），已 vendored 进
light_figure/vendor/vsdx/（逐字节收编、许可与署名见该目录
LICENSE 与 VENDOR.md），本模块是包内唯一加载口。

加载纪律（§16.1 三：真依赖硬依赖、不降级冒充）：
- vendored 源码缺失、版本与钉死值不符、或已有外来 vsdx 占用
  顶层模块名——一律 PostError 点名停住，不许悄悄换用未钉版的
  环境库冒充 vendored 本体；
- 上游声明的 Jinja2 / deprecation 两依赖只服务于模板渲染与
  弃用装饰路径，本包后处理面不用：缺位时注册惰性占位（真用到
  才报错点名），装有真依赖时优先用真的，不许因无关依赖缺位
  拖垮改字改色主面。

变更纪律（§16.2 写后回读 + extract/审计重跑）：变更类操作先
备份现行成品（同目录时间戳副本），在临时目录的副本上动手
（vsdx 会在源文件旁解压暂存，不许污染图包），写回后机械刷新
manifest 的 build.artifact_sha256、把操作记进 manifest 的
post_processing 账，并**强制重跑 extract 对账**——后处理把成品
改得与清单不一致时对账如实报 diff（先改清单再后处理对齐，或
后处理完同步清单，是执行者的顺序，本命令不替清单放行）；
provenance 的 redraw_source 哈希随之刷新；审计绑定产物哈希，
变更后审计自动 STALE、交付前必须重跑 audit run（结果里点名）。
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import types
from pathlib import Path

from .project import load_package, provenance_row
from .provenance import update_provenance_row
from .redraw import (
    extract_and_reconcile, load_manifest, save_manifest, vsdx_relpath,
)
from .util import sha256_file, utcnow

VSDX_PINNED_VERSION = "0.6.1"
_VENDOR_DIR = Path(__file__).parent / "vendor" / "vsdx"
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_TOOL_TAG = f"vsdx {VSDX_PINNED_VERSION} (vendored, BSD-3)"


class PostError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- vendored 加载

_VSDX_MODULE = None


def _register_dependency_stubs() -> None:
    """上游 vsdx 的 Jinja2 / deprecation 依赖缺位时注册惰性占位。

    占位只兜「import 能过」：真走到模板渲染（jinja2.Template）
    时抛错点名缺依赖；deprecation.deprecated 退化为透传装饰器
    + DeprecationWarning（与真库的可见行为一致：只是不拦截）。
    已装真依赖的环境不注册任何占位。
    """
    if "jinja2" not in sys.modules:
        try:
            import jinja2  # noqa: F401
        except ImportError:
            stub = types.ModuleType("jinja2")

            class _Template:
                def __init__(self, *args, **kwargs):
                    raise ImportError(
                        "jinja2 未安装：vsdx 的 Jinja 模板渲染路径"
                        "不可用（light-figure 后处理面不使用该路径；"
                        "如需模板变体请先 pip install jinja2）")

            stub.Template = _Template
            sys.modules["jinja2"] = stub
    if "deprecation" not in sys.modules:
        try:
            import deprecation  # noqa: F401
        except ImportError:
            import warnings as _warnings
            stub = types.ModuleType("deprecation")

            def _deprecated(*dargs, **dkwargs):
                def deco(fn):
                    def wrapper(*args, **kwargs):
                        _warnings.warn(
                            f"{fn.__name__} 已弃用（vsdx 上游标记）",
                            DeprecationWarning, stacklevel=2)
                        return fn(*args, **kwargs)
                    return wrapper
                # @deprecated(...) 带参用法返回装饰器；无参直贴时
                # 第一个位置参数即函数本体
                if dargs and callable(dargs[0]) and len(dargs) == 1:
                    return deco(dargs[0])
                return deco

            stub.deprecated = _deprecated
            stub.DeprecatedWarning = DeprecationWarning
            sys.modules["deprecation"] = stub


def load_vendored_vsdx():
    """加载 vendored 的 vsdx 0.6.1（包内唯一加载口）。

    vsdx 内部以顶层名 vsdx 绝对自引用（import vsdx /
    from vsdx import Shape），故以顶层名注册进 sys.modules 后
    执行 vendored 源码——上游预期形态，源码零改动（VENDOR.md
    有逐文件哈希）。版本断言钉死：不是 0.6.1 不许用。
    """
    global _VSDX_MODULE
    if _VSDX_MODULE is not None:
        return _VSDX_MODULE
    existing = sys.modules.get("vsdx")
    if existing is not None:
        if getattr(existing, "__light_figure_vendored__", False):
            _VSDX_MODULE = existing
            return existing
        raise PostError([
            "顶层模块名 vsdx 已被非 vendored 来源占用"
            f"（{getattr(existing, '__file__', '?')}）：不许混用未钉版"
            "的环境库冒充 vendored 本体，先排查导入来源"])
    init_py = _VENDOR_DIR / "__init__.py"
    if not init_py.exists():
        raise PostError([
            f"vendored vsdx 源码缺失：{_VENDOR_DIR}（收编物不在包内，"
            "后处理格停摆；按 vendor/vsdx/VENDOR.md 的哈希表恢复）"])
    _register_dependency_stubs()
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "vsdx", init_py, submodule_search_locations=[str(_VENDOR_DIR)])
    module = importlib.util.module_from_spec(spec)
    module.__light_figure_vendored__ = True
    sys.modules["vsdx"] = module
    try:
        spec.loader.exec_module(module)
    except ImportError as e:
        sys.modules.pop("vsdx", None)
        raise PostError([f"vendored vsdx 加载失败（依赖缺位）：{e}"])
    if getattr(module, "__version__", None) != VSDX_PINNED_VERSION:
        sys.modules.pop("vsdx", None)
        raise PostError([
            f"vendored vsdx 版本 {getattr(module, '__version__', None)!r}"
            f" 与钉死值 {VSDX_PINNED_VERSION} 不符：版本钉死纪律，"
            "升级须重走 VENDOR.md 核对流程"])
    _VSDX_MODULE = module
    return module


# ---------------------------------------------------------------- 公共前置

def _artifact_and_manifest(root, fig_id: str):
    root = Path(root)
    manifest = load_manifest(root, fig_id)
    if manifest is None:
        raise PostError([f"图 {fig_id} 无重绘 manifest"
                         "（后处理只对已登记清单的成品下手）"])
    if not manifest.get("build"):
        raise PostError([f"图 {fig_id} 无构建记录"
                         "（后处理对象是 redraw build 的文件级成品，"
                         "先 build）"])
    artifact = root / vsdx_relpath(fig_id)
    if not artifact.exists():
        raise PostError([f"图 {fig_id} 的成品 .vsdx 不存在"
                         "（先 redraw build）"])
    return root, manifest, artifact


def _open_copy(artifact: Path):
    """在临时目录打开成品副本（vsdx 会在源文件旁解压暂存，
    不许把暂存物落进图包）。返回 (tmp, work_path, vis)。

    保存口径（vsdx 0.6.1 上游形态，实测钉死）：构造器只收
    .vsdx/.vsdm；save_vsdx 必须显式传目标路径（无参保存在
    0.6.1 有缺陷），传回副本自身路径即原地写回，暂存目录由
    close_vsdx 清理。故变更流程 = 副本上改 → save_vsdx(副本)
    → _commit_mutation 以副本覆盖成品。
    """
    vsdx = load_vendored_vsdx()
    tmp = tempfile.TemporaryDirectory(prefix="light-figure-post-")
    work = Path(tmp.name) / artifact.name
    shutil.copy2(artifact, work)
    try:
        vis = vsdx.VisioFile(str(work))
    except Exception:
        tmp.cleanup()
        raise
    return tmp, work, vis


def _save_back(vis, work: Path) -> Path:
    """把变更后的 VisioFile 原地写回副本路径，返回副本路径。"""
    vis.save_vsdx(str(work))
    return work


def _close(tmp, vis, *, keep_work: bool = False) -> None:
    """关闭 VisioFile 并清暂存。keep_work=True 时只关文件、留住
    临时目录与已保存的 work 副本——变更流程的 _commit_mutation
    还要用 work 覆盖成品，清理由其在提交后经 _cleanup_tmp 做；
    只读流程直接全清。"""
    try:
        vis.close_vsdx()
    except Exception:
        pass
    if not keep_work:
        tmp.cleanup()


def _cleanup_tmp(tmp) -> None:
    try:
        tmp.cleanup()
    except Exception:
        pass


def _shape_rows(vis) -> list:
    rows = []
    for page in vis.pages:
        for shape in page.all_shapes:
            def _num(fn):
                try:
                    value = fn()
                    return float(value) if value is not None else None
                except Exception:
                    return None
            rows.append({
                "shape_id": shape.shape_name,
                "id": shape.ID,
                "text": shape.text,
                "fill": shape.fill_color,
                "line": shape.line_color,
                "pin_x": _num(lambda: shape.x),
                "pin_y": _num(lambda: shape.y),
                "width": _num(lambda: shape.width),
                "height": _num(lambda: shape.height),
            })
    return rows


def _commit_mutation(root, fig_id, artifact, work, op_record, by):
    """变更写回 + 纪律收尾：备份 → 覆盖 → manifest 账与构建哈希
    刷新 → 强制 extract 对账 → provenance redraw_source 刷新。
    work 是 _save_back 已原地写回的临时副本。"""
    stamp = re.sub(r"[^0-9A-Za-z]", "", utcnow())[:14]
    backup = artifact.with_name(
        f"{artifact.stem}.pre-post-{stamp}{artifact.suffix}")
    shutil.copy2(artifact, backup)
    shutil.copy2(work, artifact)
    new_hash = sha256_file(artifact)
    manifest = load_manifest(root, fig_id)
    build = manifest.get("build") or {}
    build["artifact_sha256"] = new_hash
    manifest["build"] = build
    entry = {
        **op_record,
        "at": utcnow(),
        "by": by,
        "tool": _TOOL_TAG,
        "backup": backup.name,
        "artifact_sha256": new_hash,
    }
    manifest.setdefault("post_processing", []).append(entry)
    save_manifest(root, manifest)
    outcome = extract_and_reconcile(root, fig_id)
    updates = {"redraw_source": {"path": vsdx_relpath(fig_id),
                                  "hash": new_hash}}
    # provenance 修正日志指针（§16.2）：后处理明细账在 manifest 的
    # post_processing 段，账行只落指针不复制明细（单一真相源）
    pointer = f"schematic/redraw/{fig_id}.manifest.json#post_processing"
    row = provenance_row(load_package(root)["provenance"], fig_id) or {}
    if row.get("manual_corrections_log") != pointer:
        updates["manual_corrections_log"] = pointer
    update_provenance_row(root, fig_id, updates,
                          by=by or "light-figure redraw post")
    return {
        "fig_id": fig_id,
        "op": op_record["op"],
        "artifact": vsdx_relpath(fig_id),
        "artifact_sha256": new_hash,
        "backup": f"{vsdx_relpath(fig_id).rsplit('/', 1)[0]}/"
                  f"{backup.name}",
        "reconciliation": outcome,
        "post_processing_entries":
            len(manifest.get("post_processing") or []),
        "audit_note": "产物已变更：既有审计记录即 STALE，交付前"
                      "重跑 audit run（§16.2 后处理纪律）",
    }


# ---------------------------------------------------------------- 命令面

def post_extract(root, fig_id: str) -> dict:
    """抽取：以 vsdx 枚举成品全部形状（名/文本/填充/描边/几何）。"""
    _root, _manifest, artifact = _artifact_and_manifest(root, fig_id)
    tmp, work, vis = _open_copy(artifact)
    try:
        rows = _shape_rows(vis)
    finally:
        _close(tmp, vis)
    return {
        "fig_id": fig_id,
        "tool": _TOOL_TAG,
        "artifact": vsdx_relpath(fig_id),
        "shape_count": len(rows),
        "shapes": rows,
    }


def post_replace_text(root, fig_id: str, find: str, replace: str,
                      *, regex: bool = False,
                      by: str | None = None) -> dict:
    """改字：跨全部形状替换文本（子串或正则），逐形状点名命中。"""
    if not find:
        raise PostError(["--find 不许为空（空模式会命中一切文本）"])
    root, _manifest, artifact = _artifact_and_manifest(root, fig_id)
    tmp, work, vis = _open_copy(artifact)
    try:
        hits = []
        total = 0
        pattern = re.compile(find) if regex else None
        for page in vis.pages:
            for shape in page.all_shapes:
                old = shape.text or ""
                if not old:
                    continue
                if pattern is not None:
                    new, n = pattern.subn(replace, old)
                else:
                    n = old.count(find)
                    new = old.replace(find, replace) if n else old
                if n:
                    shape.text = new
                    hits.append({"shape_id": shape.shape_name,
                                 "from": old, "to": new, "count": n})
                    total += n
        if not hits:
            raise PostError([
                f"文本 {find!r} 在成品任何形状中都未命中：未做任何"
                "修改（如是清单侧的文字，先核对清单与成品现状——"
                "post extract 可抽取现行文本）"])
        saved = _save_back(vis, work)
    finally:
        _close(tmp, vis, keep_work=True)
    try:
        result = _commit_mutation(root, fig_id, artifact, saved, {
            "op": "replace_text", "find": find, "replace": replace,
            "regex": regex, "hits": hits,
        }, by)
    finally:
        _cleanup_tmp(tmp)
    result["hits"] = hits
    result["replacements"] = total
    return result


def post_set_fill(root, fig_id: str, *, shape_id: str | None = None,
                  text: str | None = None, fill: str | None = None,
                  line: str | None = None,
                  by: str | None = None) -> dict:
    """改色：按语义 ID（形状 NameU）或逐字文本唯一定位一形状，
    改填充色 / 描边色（#RRGGBB，与文件级构建的 Cell 编码同形态）。
    """
    if bool(shape_id) == bool(text):
        raise PostError(["定位方式二选一：--shape <语义 ID> 或 "
                         "--text <逐字文本>，不许同给或都不给"])
    if fill is None and line is None:
        raise PostError(["至少给一项：--fill <#RRGGBB> 或 "
                         "--line <#RRGGBB>"])
    for label, value in (("fill", fill), ("line", line)):
        if value is not None and not _HEX_COLOR.match(value):
            raise PostError([f"--{label} 颜色 {value!r} 不是 #RRGGBB"
                             "（与 manifest 角色色的编码同形态）"])
    root, _manifest, artifact = _artifact_and_manifest(root, fig_id)
    tmp, work, vis = _open_copy(artifact)
    try:
        targets = []
        for page in vis.pages:
            for shape in page.all_shapes:
                if shape_id and shape.shape_name == shape_id:
                    targets.append(shape)
                elif text is not None and (shape.text or "") == text:
                    targets.append(shape)
        if not targets:
            locator = f"语义 ID {shape_id!r}" if shape_id \
                else f"文本 {text!r}"
            raise PostError([f"成品中没有定位为 {locator} 的形状："
                             "未做任何修改（post extract 可抽取现行"
                             "形状清单）"])
        if len(targets) > 1:
            names = [s.shape_name for s in targets]
            raise PostError([f"定位命中 {len(targets)} 个形状 {names}："
                             "改色只许单点命中，改用 --shape 语义 ID"
                             "唯一定位"])
        shape = targets[0]
        before = {"fill": shape.fill_color, "line": shape.line_color}
        if fill is not None:
            shape.fill_color = fill.lower()
            # 与文件级构建同口径：有填充色必配 FillPattern=1
            shape.set_cell_value("FillPattern", "1")
        if line is not None:
            shape.line_color = line.lower()
        after = {"fill": shape.fill_color, "line": shape.line_color}
        saved = _save_back(vis, work)
    finally:
        _close(tmp, vis, keep_work=True)
    try:
        result = _commit_mutation(root, fig_id, artifact, saved, {
            "op": "set_fill", "shape_id": shape.shape_name,
            "before": before, "after": after,
        }, by)
    finally:
        _cleanup_tmp(tmp)
    result["shape_id"] = shape.shape_name
    result["before"] = before
    result["after"] = after
    return result


def post_diff(root, fig_id: str, other) -> dict:
    """diff：成品与另一 .vsdx 逐包成员比对（vsdxdiff）。

    vsdxdiff 会在被比文件旁解压暂存——两边都先复制进临时目录
    再比，图包与外部文件原样不动。
    """
    _root, _manifest, artifact = _artifact_and_manifest(root, fig_id)
    other = Path(other)
    if not other.exists():
        raise PostError([f"比对文件不存在：{other}"])
    if other.suffix.lower() != ".vsdx":
        raise PostError([f"比对文件不是 .vsdx：{other}"])
    load_vendored_vsdx()
    import importlib
    diff_mod = importlib.import_module("vsdx.vsdxdiff")
    with tempfile.TemporaryDirectory(
            prefix="light-figure-diff-") as tmp:
        a = Path(tmp) / "a.vsdx"
        b = Path(tmp) / "b.vsdx"
        shutil.copy2(artifact, a)
        shutil.copy2(other, b)
        diff = diff_mod.VisioFileDiff(str(a), str(b))
        changed = {}
        for member, lines in (diff.diffs or {}).items():
            changed[member] = {
                "added_lines": sum(1 for ln in lines
                                    if ln.startswith("+ ")),
                "removed_lines": sum(1 for ln in lines
                                      if ln.startswith("- ")),
            }
        result = {
            "fig_id": fig_id,
            "tool": _TOOL_TAG,
            "artifact": vsdx_relpath(fig_id),
            "other": str(other),
            "same_members": diff.compare_members(),
            "added_members": sorted(diff.added_members()),
            "removed_members": sorted(diff.removed_members()),
            "changed_members": changed,
        }
        result["identical"] = not changed \
            and result["same_members"] \
            and not result["added_members"] \
            and not result["removed_members"]
        return result
