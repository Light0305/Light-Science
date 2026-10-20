"""Doc2X 引擎适配器：与本地视觉通道平级的 Engine Adapter（云端后端）。

定位见 `../../01-literature/deep-read-C.md` 第二节第 6 小节：输入 = PDF +
页范围，输出 = 同一份 middle_json + assets，`provenance=engine:doc2x`
逐块标注。用途：无 GPU 兜底、难例兜底、对照评测的基准侧（同一适配器
同进同出，保证评测公平）。

REST 端点（2026-10-20 据官方开源 MCP 服务器 NoEdgeAI/doc2x-mcp 源码
`src/doc2x/{paths,pdf,convert,client}.ts` 核实，并经真实调用复核）：

- 通用：base ``https://v2.doc2x.noedgeai.com``，路径前缀 ``/api/v2``；
  请求头 ``Authorization: Bearer <key>``；响应 envelope
  ``{code, msg, data}``，``code == "success"`` 才算成功。
- 解析三段：``POST /parse/preupload``（body 可选 ``{"model": ...}``）
  → ``data {uid, url}``；PUT 文件字节到预签名 ``url``（不带
  Authorization，签名在 URL 里）；``GET /parse/status?uid=`` →
  ``data {status, progress, detail, result}``，status ∈ processing /
  success / failed，``result.pages[]`` 为 ``{page_idx, md, ...}``
  逐页 Markdown。
- 导出两段：``POST /convert/parse``（body ``{uid, to, formula_mode,
  formula_level?, merge_cross_page_forms?, filename?}``）→
  ``data {status, url}``；``GET /convert/parse/result?uid=`` 轮询至
  success 后 GET ``data.url`` 下载（md 导出为 zip 或单个 .md，按
  魔数判别）。同一 uid 的多格式导出必须串行。
- 参数枚举（官方源码 + README 核实）：``model`` ∈ {v2, v3-2026}；
  ``to`` ∈ {md, tex, docx}；``formula_mode`` ∈ {normal, dollar}
  （必填）；``formula_level`` ∈ {0, 1, 2}（仅 model=v3-2026 生效：
  0 保留公式、1 仅退化行内公式、2 退化全部公式）。

费用纪律：按解析页数计费（¥0.01–0.02/页）。Doc2X 解析的是整篇 PDF，
``pages`` 参数只过滤输出块、**不过滤计费**；重提前先查 status，
不许无记录地重复提交（会重复计费）。解析结果云端只存 24 小时，
success 后必须立即取回落盘。

凭据纪律：只经 dynamic_credentials 的 surrogate 注入（连接名
``custom.doc2x``，bearer_header），真实 Key 不进代码/日志/命令行/
异常信息；本模块所有异常消息过 `_scrub` 脱敏，预签名/下载 URL
只报 host 不报全串。认证请求禁用重定向。
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from . import EngineUnavailableError

# dynamic_credentials 是连接器基础设施（不在本包内），按连接文档给的
# 绝对路径导入；导入失败即视为凭据通道不可用，parse() 显式报错。
_CRED_BIN = "/opt/muse/skills/custom-connector-setup/bin"
if _CRED_BIN not in sys.path:
    sys.path.insert(0, _CRED_BIN)
try:
    from dynamic_credentials import add_surrogate_to_request
except Exception:  # pragma: no cover - 环境缺失时走 available()=False
    add_surrogate_to_request = None  # type: ignore[assignment]

BASE_URL = "https://v2.doc2x.noedgeai.com"
API_PREFIX = "/api/v2"
CREDENTIAL_NAME = "custom.doc2x"
ALLOWED_HOSTS = ("v2.doc2x.noedgeai.com", "doc2x.noedgeai.com")

# 轮询/超时纪律（连接文档：间隔 2s、最大等待 600s、HTTP 超时 60s）
POLL_INTERVAL_S = 2.0
MAX_WAIT_S = 600.0
HTTP_TIMEOUT_S = 60.0
MAX_RETRIES = 3  # 单次请求对 429/5xx/可重试业务码的最大重试次数

# 本增量评测口径（写入运行记录，预注册后再跑的不许中途改）
DEFAULT_MODEL = "v3-2026"
DEFAULT_FORMULA_MODE = "dollar"   # $...$ / $$...$$，与本地 Markdown 渲染对齐
DEFAULT_FORMULA_LEVEL = 0         # 0 = 保留公式（不退化）
DEFAULT_MERGE_CROSS_PAGE_FORMS = True  # 论文类文档默认开跨页表格合并

MODELS = ("v2", "v3-2026")
FORMULA_MODES = ("normal", "dollar")
FORMULA_LEVELS = (0, 1, 2)
EXPORT_FORMATS = ("md", "tex", "docx")

# 官方源码 client.ts：这些业务码可重试（限流/并发/状态未就绪类）
RETRYABLE_BUSINESS_CODES = frozenset({
    "parse_error", "parse_create_task_error", "parse_task_limit_exceeded",
    "parse_concurrency_limit", "parse_status_not_found",
})

# 导出下载 host 白名单（后缀匹配，与官方 MCP 默认值一致）
DOWNLOAD_HOST_SUFFIXES = (".amazonaws.com.cn", ".aliyuncs.com",
                          ".noedgeai.com")

_SECRET_PATTERNS = (
    re.compile(r"hsurr:[^\s\"'<>]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]+"),
)


def _scrub(text: object) -> str:
    """异常消息脱敏：抹掉任何疑似凭据串（纵深防御，本模块本不持有 Key）。"""
    out = str(text)
    for pat in _SECRET_PATTERNS:
        out = pat.sub("<redacted>", out)
    return out


class Doc2XError(RuntimeError):
    """Doc2X 调用失败（业务码/HTTP 错误/任务 failed），消息已脱敏。"""


class Doc2XTimeoutError(Doc2XError):
    """轮询超过 MAX_WAIT_S 仍未完成；带 uid 供事后查状态，不许盲目重提。"""

    def __init__(self, message: str, uid: Optional[str] = None):
        super().__init__(message)
        self.uid = uid


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """认证请求禁用重定向（连接文档纪律）：3xx 直接抛 HTTPError。"""

    def redirect_request(self, *args, **kwargs):
        return None


# v3-2026 layout 块类型（官方开放平台类型表 + 2026-10-20 实测页样本）：
# Title/Text/Equation/EquationNumber/Table/Figure/Caption/Code/Underline
# 与组容器 TableGroup/FigureGroup/EquationGroup/CodeGroup/TOCGroup/
# FootnoteGroup/ReferenceGroup/SideGroup；组容器不单独成块，只用于
# 图注归属与阅读顺序。attributes.is_boilerplate 标页眉页脚页码。
_LAYOUT_GROUPS = frozenset({
    "TableGroup", "FigureGroup", "EquationGroup", "CodeGroup",
    "TOCGroup", "FootnoteGroup", "ReferenceGroup", "SideGroup",
})
_LAYOUT_TEXT_TYPES = frozenset({"Text", "Code", "Underline"})


def _title_level(text: str) -> int:
    """由标题编号深度推层级（"4 Why…" → 1、"3.5 …" → 2），无编号 → 1。"""
    m = re.match(r"^\s*(\d+(?:\.\d+)*)\.?\s", text or "")
    if not m:
        return 1
    return max(1, m.group(1).count(".") + 1)


def _convert_layout_page(entry: dict, page_sizes_pt: Optional[dict],
                         ) -> Optional[list[dict]]:
    """单页 layout.blocks → middle_json 块；无 layout 时返回 None。

    bbox 为页面渲染像素坐标，按 page_width/page_height 换算：给了
    page_sizes_pt（{1 起页码: (宽, 高) PDF 点}）则换算为 PDF 点，
    否则换算为 0–1000 相对坐标并标 bbox_space="per_mille"。
    """
    layout = entry.get("layout")
    raw = layout.get("blocks") if isinstance(layout, dict) else None
    if not isinstance(raw, list) or not raw:
        return None
    page = _as_int(entry.get("page_idx"), 0) + 1
    pw = float(entry.get("page_width") or 0)
    ph = float(entry.get("page_height") or 0)
    size_pt = (page_sizes_pt or {}).get(page)

    def conv_bbox(bbox: object) -> tuple[list, Optional[str]]:
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4
                and pw > 0 and ph > 0):
            return [0, 0, 0, 0], "missing"
        if size_pt:
            w, h = size_pt
            return [round(float(bbox[0]) / pw * w, 1),
                    round(float(bbox[1]) / ph * h, 1),
                    round(float(bbox[2]) / pw * w, 1),
                    round(float(bbox[3]) / ph * h, 1)], None
        return [round(float(bbox[0]) / pw * 1000),
                round(float(bbox[1]) / ph * 1000),
                round(float(bbox[2]) / pw * 1000),
                round(float(bbox[3]) / ph * 1000)], "per_mille"

    ordered = sorted(
        raw, key=lambda b: _as_int(b.get("reading_order"), 0))
    by_id = {str(b.get("id")): b for b in raw}
    blocks: list[dict] = []
    block_by_layout_id: dict[str, dict] = {}

    def emit(block: dict, src_block: dict) -> dict:
        bbox, space = conv_bbox(src_block.get("bbox"))
        block["page"] = page
        block["bbox"] = bbox
        if space:
            block["bbox_space"] = space
        block["provenance"] = "engine:doc2x"
        block["layout_id"] = str(src_block.get("id") or "")
        if _as_int(src_block.get("reading_order"), -1) >= 0:
            block["order_in_page"] = _as_int(src_block["reading_order"], 0)
        attrs = src_block.get("attributes")
        if isinstance(attrs, dict) and attrs.get("is_boilerplate"):
            block["is_boilerplate"] = True
        blocks.append(block)
        block_by_layout_id[block["layout_id"]] = block
        return block

    pending_numbers: list[dict] = []  # EquationNumber 先攒着，尽量并入公式
    for b in ordered:
        btype = str(b.get("type") or "")
        text = str(b.get("text") or "")
        if btype in _LAYOUT_GROUPS or btype == "Underline":
            continue  # 组容器/下划线不成块（下划线是格式伪影）
        if btype == "Title":
            emit({"type": "text", "text": text,
                  "text_level": _title_level(text),
                  "doc2x_type": "Title"}, b)
        elif btype in _LAYOUT_TEXT_TYPES:
            block = {"type": "text", "text": text}
            if btype != "Text":
                block["doc2x_type"] = btype
            inline = _INLINE_MATH_RE.findall(text)
            if inline:
                block["inline_latex"] = inline
            emit(block, b)
        elif btype == "Equation":
            latex = text.strip()
            if latex.startswith("\\[") and latex.endswith("\\]"):
                latex = latex[2:-2].strip()
            elif latex.startswith("$$") and latex.endswith("$$"):
                latex = latex[2:-2].strip()
            emit({"type": "equation", "text": text, "latex": latex}, b)
        elif btype == "EquationNumber":
            pending_numbers.append(b)
        elif btype == "Table":
            table_data = b.get("table_data")
            html_body = ""
            if isinstance(table_data, dict):
                html_body = str(table_data.get("html") or "")
            emit({"type": "table", "table_body": html_body,
                  "text": text}, b)
        elif btype == "Figure":
            emit({"type": "figure", "asset": str(b.get("src") or ""),
                  "text": text}, b)
        elif btype == "Caption":
            emit({"type": "caption", "text": text}, b)
        elif text:
            emit({"type": "text", "text": text, "doc2x_type": btype}, b)

    # EquationNumber 并入同组（parent 相同）或最近的公式块；无处可并
    # 时退化为 text 块，不丢弃。
    equations = [blk for blk in blocks if blk["type"] == "equation"]
    for num in pending_numbers:
        num_text = str(num.get("text") or "").strip()
        if not num_text:
            continue
        parent = str(num.get("parent_id") or "")
        host = None
        for eq in equations:
            src = by_id.get(eq["layout_id"]) or {}
            if parent and str(src.get("parent_id") or "") == parent:
                host = eq
                break
        if host is None and equations:
            host = equations[-1]
        if host is not None:
            host["equation_number"] = num_text
        else:
            emit({"type": "text", "text": num_text,
                  "doc2x_type": "EquationNumber"}, num)

    # 图注归属：Caption 的 parent 若是组容器，组内 Figure/Table 即宿主
    for b in ordered:
        if str(b.get("type") or "") != "Caption":
            continue
        cap_block = block_by_layout_id.get(str(b.get("id")))
        parent_id = str(b.get("parent_id") or "")
        if cap_block is None or parent_id not in by_id:
            continue
        if str(by_id[parent_id].get("type")) not in _LAYOUT_GROUPS:
            continue
        for sibling in ordered:
            if str(sibling.get("parent_id") or "") != parent_id:
                continue
            if str(sibling.get("type")) in ("Figure", "Table"):
                host = block_by_layout_id.get(str(sibling.get("id")))
                if host is not None:
                    cap_block["caption_of"] = blocks.index(host)
                break
    return blocks


def convert_doc2x_result(result: dict,
                         pages: Optional[list[int]] = None,
                         page_sizes_pt: Optional[dict] = None,
                         ) -> list[dict]:
    """把 parse status 的 result 转成 middle_json 块列表（纯函数）。

    v3-2026 的 result.pages[] 带 layout.blocks（类型化块 + 像素 bbox +
    reading_order），优先按 layout 转换（见 `_convert_layout_page`）；
    某页没有 layout（如 v2 模型）时退化为解析该页 Markdown
    （`_split_page_md`）：HTML 表格 → table 块、``$$...$$`` → equation
    块、图片行 → figure 块、标题行 → 带 text_level 的 text 块、
    Figure/Table 编号段 → caption 块、其余段落 → text 块；该路径无
    坐标，bbox 一律 [0,0,0,0] 并标 bbox_space="missing"，不许编造。
    """
    raw_pages = []
    for entry in (result or {}).get("pages") or []:
        if isinstance(entry, dict):
            raw_pages.append(entry)
    raw_pages.sort(key=lambda e: _as_int(e.get("page_idx"), 0))

    blocks: list[dict] = []
    for entry in raw_pages:
        page = _as_int(entry.get("page_idx"), 0) + 1
        if pages is not None and page not in pages:
            continue
        layout_blocks = _convert_layout_page(entry, page_sizes_pt)
        if layout_blocks is not None:
            # caption_of 在页内是局部下标（_convert_layout_page 口径），
            # 拼成全篇列表时须加页偏移（全局下标口径，见模块 docstring）
            # 对齐（2026-10-20 实测教训：不加偏移会让图注挂到别页的块
            # 上、配对率失真）。
            offset = len(blocks)
            for block in layout_blocks:
                if block.get("caption_of") is not None:
                    block["caption_of"] += offset
            blocks.extend(layout_blocks)
            continue
        for block in _split_page_md(str(entry.get("md") or "")):
            block["page"] = page
            block["bbox"] = [0, 0, 0, 0]
            block["bbox_space"] = "missing"
            block["provenance"] = "engine:doc2x"
            blocks.append(block)
    return blocks


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


_TABLE_RE = re.compile(r"<table\b.*?</table>", re.DOTALL | re.IGNORECASE)
_DISPLAY_MATH_RE = re.compile(
    r"\$\$(.+?)\$\$|\\\[(.+?)\\\]", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\$[^$\n]+?\$|\\\([^\n]+?\\\)")
_IMG_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_CAPTION_RE = re.compile(
    r"^\s*(Figure|Fig\.?|Table|图|表)\s*(\d+)\s*[:：\.]", re.IGNORECASE)


def _split_page_md(md: str) -> list[dict]:
    """单页 Markdown → 块列表（不含 page/bbox/provenance，调用方补）。"""
    blocks: list[dict] = []

    def add_text_segment(segment: str) -> None:
        for para in re.split(r"\n\s*\n", segment):
            para = para.strip()
            if not para:
                continue
            img = _IMG_LINE_RE.match(para)
            if img:
                blocks.append({"type": "figure", "asset": img.group(2),
                               "alt": img.group(1)})
                continue
            heading = _HEADING_RE.match(para)
            if heading and "\n" not in para:
                blocks.append({"type": "text",
                               "text": heading.group(2).strip(),
                               "text_level": len(heading.group(1))})
                continue
            if _CAPTION_RE.match(para):
                blocks.append({"type": "caption", "text": para})
                continue
            block: dict = {"type": "text", "text": para}
            inline = _INLINE_MATH_RE.findall(para)
            if inline:
                block["inline_latex"] = inline
            blocks.append(block)

    # 先按 HTML 表格与独立公式切出结构块，其余进文本段切分
    token_re = re.compile(
        r"(<table\b.*?</table>|\$\$.+?\$\$|\\\[.+?\\\])",
        re.DOTALL | re.IGNORECASE)
    pos = 0
    for m in token_re.finditer(md):
        add_text_segment(md[pos:m.start()])
        token = m.group(0)
        if token.lstrip().lower().startswith("<table"):
            blocks.append({"type": "table", "table_body": token})
        else:
            latex = token[2:-2].strip()  # $$...$$ 与 \[...\] 都是 2 字符定界
            blocks.append({"type": "equation", "text": latex,
                           "latex": latex})
        pos = m.end()
    add_text_segment(md[pos:])
    return blocks


class Doc2XClient:
    """Doc2X REST 低层客户端（三段解析 + 两段导出）。

    opener 可注入（单测用假 opener 模拟状态机）；sleep/monotonic 可注入
    以便测试超时而不真等。所有方法抛 Doc2XError（消息已脱敏）。
    """

    def __init__(self, opener=None, sleep=time.sleep,
                 monotonic=time.monotonic):
        self._opener = opener or urllib.request.build_opener(_NoRedirect())
        # 下载/PUT 用无凭据 opener；注入 opener（单测）时共用同一个
        self._dl_opener = opener or urllib.request.build_opener()
        self._sleep = sleep
        self._monotonic = monotonic

    # ---------- 基础请求 ----------

    def _open(self, request: urllib.request.Request, opener=None):
        """执行一次请求，返回 (status, body_bytes)；HTTPError 不外抛。"""
        op = opener or self._opener
        try:
            with op.open(request, timeout=HTTP_TIMEOUT_S) as resp:
                return int(resp.status), resp.read()
        except urllib.error.HTTPError as exc:
            try:
                return int(exc.code), exc.read()
            except Exception:
                return int(exc.code), b""

    def _request_json(self, method: str, path: str,
                      query: Optional[dict] = None,
                      body: Optional[dict] = None) -> dict:
        """带凭据的 API 请求，解 envelope，返回 data；含有限重试。"""
        if add_surrogate_to_request is None:
            raise EngineUnavailableError(
                "dynamic_credentials 不可用，无法注入 Doc2X 凭据；"
                "确认 /opt/muse/skills/custom-connector-setup/bin 存在。")
        url = BASE_URL + API_PREFIX + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        payload = json.dumps(body).encode("utf-8") if body is not None \
            else None
        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            request = urllib.request.Request(url, data=payload,
                                             method=method)
            if payload is not None:
                request.add_header("Content-Type", "application/json")
            try:
                add_surrogate_to_request(
                    request, CREDENTIAL_NAME,
                    allowed_hosts=list(ALLOWED_HOSTS))
            except Exception as exc:
                raise EngineUnavailableError(
                    f"Doc2X 凭据注入失败：{_scrub(exc)}") from exc
            try:
                status, raw = self._open(request)
            except Exception as exc:  # 网络层错误：可重试
                last_error = Doc2XError(f"Doc2X 网络错误：{_scrub(exc)}")
                if attempt < MAX_RETRIES:
                    self._sleep(POLL_INTERVAL_S * (attempt + 1))
                    continue
                raise last_error from exc
            if status == 429 or status >= 500:
                last_error = Doc2XError(f"Doc2X HTTP {status}（可重试）")
                if attempt < MAX_RETRIES:
                    self._sleep(POLL_INTERVAL_S * (attempt + 1))
                    continue
                raise last_error
            if status != 200:
                snippet = _scrub(raw[:300].decode("utf-8", "replace"))
                raise Doc2XError(
                    f"Doc2X HTTP {status}（{path}）：{snippet}")
            try:
                envelope = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise Doc2XError(
                    f"Doc2X 返回非 JSON（{path}）") from exc
            code = str(envelope.get("code") or "")
            if code == "success":
                data = envelope.get("data")
                return data if isinstance(data, dict) else {}
            msg = _scrub(envelope.get("msg") or "Doc2X 业务错误")
            if code in RETRYABLE_BUSINESS_CODES and attempt < MAX_RETRIES:
                last_error = Doc2XError(f"Doc2X 业务码 {code}：{msg}")
                self._sleep(POLL_INTERVAL_S * (attempt + 1))
                continue
            raise Doc2XError(f"Doc2X 业务码 {code}：{msg}")
        assert last_error is not None
        raise last_error

    # ---------- 解析三段 ----------

    def preupload(self, model: str = DEFAULT_MODEL) -> tuple[str, str]:
        """第一段：申请预签名上传地址，返回 (uid, url)。"""
        if model not in MODELS:
            raise ValueError(f"model 须为 {MODELS}，收到 {model!r}")
        data = self._request_json("POST", "/parse/preupload",
                                  body={"model": model})
        uid, url = str(data.get("uid") or ""), str(data.get("url") or "")
        if not uid or not url:
            raise Doc2XError("preupload 响应缺 uid/url")
        return uid, url

    def upload(self, signed_url: str, pdf_bytes: bytes) -> None:
        """第二段：PUT 文件字节到预签名地址（不带 Authorization）。

        错误消息只报 host——预签名 URL 含签名参数，不许进日志/异常。
        """
        host = urllib.parse.urlparse(signed_url).hostname or "<unknown>"
        request = urllib.request.Request(signed_url, data=pdf_bytes,
                                         method="PUT")
        request.add_header("Content-Type", "application/pdf")
        request.add_header("Content-Length", str(len(pdf_bytes)))
        try:
            status, _ = self._open(request, opener=self._dl_opener)
        except Exception as exc:
            raise Doc2XError(
                f"上传到预签名地址失败（host={host}）：{_scrub(exc)}"
            ) from exc
        if status not in (200, 201, 204):
            raise Doc2XError(
                f"上传到预签名地址失败（host={host}）：HTTP {status}")

    def submit(self, pdf_path: Path, model: str = DEFAULT_MODEL) -> str:
        """preupload + upload，返回 uid。调用方须把 uid 记入运行记录，
        后续一切操作优先用 uid 续查，不许无记录地重复 submit。"""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 不存在：{pdf_path}")
        uid, url = self.preupload(model)
        self.upload(url, pdf_path.read_bytes())
        return uid

    def status(self, uid: str) -> dict:
        """查解析状态：{status, progress, detail, result}。"""
        data = self._request_json("GET", "/parse/status",
                                  query={"uid": uid})
        return {
            "status": str(data.get("status") or ""),
            "progress": _as_int(data.get("progress"), 0),
            "detail": str(data.get("detail") or ""),
            "result": data.get("result"),
        }

    def wait_parse(self, uid: str, max_wait_s: float = MAX_WAIT_S) -> dict:
        """轮询至 success 并返回 result；failed/超时抛错（带 uid）。"""
        start = self._monotonic()
        while True:
            if self._monotonic() - start > max_wait_s:
                raise Doc2XTimeoutError(
                    f"解析等待超时（{max_wait_s:.0f}s，uid={uid}）；"
                    "先 status 查状态再决定，勿盲目重提", uid=uid)
            st = self.status(uid)
            if st["status"] == "success":
                result = st["result"]
                if not isinstance(result, dict) or not result.get("pages"):
                    raise Doc2XError(
                        f"解析 success 但 result 无 pages（uid={uid}）")
                return result
            if st["status"] == "failed":
                raise Doc2XError(
                    f"解析失败（uid={uid}）：{_scrub(st['detail'])}")
            self._sleep(POLL_INTERVAL_S)

    # ---------- 导出两段 ----------

    def convert_submit(self, uid: str, to: str = "md",
                       formula_mode: str = DEFAULT_FORMULA_MODE,
                       formula_level: int = DEFAULT_FORMULA_LEVEL,
                       merge_cross_page_forms: bool =
                       DEFAULT_MERGE_CROSS_PAGE_FORMS,
                       filename: Optional[str] = None) -> dict:
        """发起导出，返回 {status, url}（url 可能在 result 阶段才有）。"""
        if to not in EXPORT_FORMATS:
            raise ValueError(f"to 须为 {EXPORT_FORMATS}，收到 {to!r}")
        if formula_mode not in FORMULA_MODES:
            raise ValueError(
                f"formula_mode 须为 {FORMULA_MODES}，收到 {formula_mode!r}")
        if formula_level not in FORMULA_LEVELS:
            raise ValueError(
                f"formula_level 须为 {FORMULA_LEVELS}，收到 {formula_level!r}")
        body: dict = {"uid": uid, "to": to, "formula_mode": formula_mode,
                      "formula_level": formula_level,
                      "merge_cross_page_forms": merge_cross_page_forms}
        if filename:
            body["filename"] = filename
        data = self._request_json("POST", "/convert/parse", body=body)
        return {"status": str(data.get("status") or ""),
                "url": str(data.get("url") or "")}

    def convert_result(self, uid: str) -> dict:
        data = self._request_json("GET", "/convert/parse/result",
                                  query={"uid": uid})
        return {"status": str(data.get("status") or ""),
                "url": str(data.get("url") or "").replace("\\u0026", "&")}

    def wait_convert(self, uid: str, max_wait_s: float = MAX_WAIT_S) -> str:
        """轮询导出至 success 并返回下载 URL；同 uid 导出必须串行。"""
        start = self._monotonic()
        while True:
            if self._monotonic() - start > max_wait_s:
                raise Doc2XTimeoutError(
                    f"导出等待超时（{max_wait_s:.0f}s，uid={uid}）", uid=uid)
            res = self.convert_result(uid)
            if res["status"] == "success" and res["url"]:
                return res["url"]
            if res["status"] == "failed":
                raise Doc2XError(f"导出失败（uid={uid}）")
            self._sleep(POLL_INTERVAL_S)

    def download(self, url: str) -> bytes:
        """下载导出产物（无凭据；只许 https + 白名单 host 后缀）。"""
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not any(
                host.endswith(sfx) for sfx in DOWNLOAD_HOST_SUFFIXES):
            raise Doc2XError(f"下载地址不在白名单内（host={host or '?'}）")
        request = urllib.request.Request(url, method="GET")
        try:
            status, raw = self._open(request, opener=self._dl_opener)
        except Exception as exc:
            raise Doc2XError(
                f"下载导出产物失败（host={host}）：{_scrub(exc)}") from exc
        if status != 200:
            raise Doc2XError(
                f"下载导出产物失败（host={host}）：HTTP {status}")
        return raw


def materialize_export(payload: bytes, out_dir: Path) -> dict:
    """把导出下载物落盘：zip → 解包（.md + 图片资产）；单个 .md 原样存。

    返回 {"markdown_path": ..., "assets": [相对路径...], "kind": ...}。
    zip 解包做路径穿越防护（成员名含 .. 或绝对路径直接拒绝该成员）。
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if payload[:4] == b"PK\x03\x04":
        assets: list[str] = []
        md_path: Optional[Path] = None
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for info in zf.infolist():
                name = info.filename
                if info.is_dir() or not name:
                    continue
                target = (out_dir / name).resolve()
                if not str(target).startswith(str(out_dir)):
                    continue  # 路径穿越成员：跳过
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
                rel = str(target.relative_to(out_dir))
                if name.lower().endswith(".md"):
                    md_path = target
                else:
                    assets.append(rel)
        if md_path is None:
            raise Doc2XError("导出 zip 中未找到 .md 文件")
        return {"kind": "zip", "markdown_path": str(md_path),
                "assets": sorted(assets)}
    text = payload.decode("utf-8", errors="replace")
    md_path = out_dir / "doc2x.md"
    md_path.write_text(text, encoding="utf-8")
    return {"kind": "markdown", "markdown_path": str(md_path),
            "assets": []}


class Doc2XEngine:
    """Doc2X 引擎适配器（实现 EngineAdapter 协议）。

    output_dir 给出时，全部云端产物立即物化到该目录（结果云端只存
    24 小时）：doc2x_result.json（status 原始 result）、doc2x.md 与
    assets（convert 导出解包）、run_record.json（uid/参数/时间，
    不含任何凭据与签名 URL）。parse() 返回 middle_json 块。
    """

    name = "doc2x"

    def __init__(self, client: Optional[Doc2XClient] = None,
                 output_dir: Optional[Path] = None,
                 model: str = DEFAULT_MODEL,
                 formula_mode: str = DEFAULT_FORMULA_MODE,
                 formula_level: int = DEFAULT_FORMULA_LEVEL,
                 merge_cross_page_forms: bool =
                 DEFAULT_MERGE_CROSS_PAGE_FORMS):
        self._client = client or Doc2XClient()
        self._output_dir = Path(output_dir) if output_dir else None
        self.model = model
        self.formula_mode = formula_mode
        self.formula_level = formula_level
        self.merge_cross_page_forms = merge_cross_page_forms
        self.last_run: dict = {}

    def _flush_run(self, run: dict) -> None:
        if self._output_dir is None:
            return
        self._output_dir.mkdir(parents=True, exist_ok=True)
        (self._output_dir / "run_record.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")

    def available(self) -> bool:
        """只探测凭据通道是否可注入，不发任何计费请求。"""
        if add_surrogate_to_request is None:
            return False
        try:
            request = urllib.request.Request(BASE_URL + API_PREFIX)
            add_surrogate_to_request(request, CREDENTIAL_NAME,
                                     allowed_hosts=list(ALLOWED_HOSTS))
            return True
        except Exception:
            return False

    def parse(self, pdf_path: Path,
              pages: Optional[list[int]] = None) -> list[dict]:
        """整篇解析（计费按整篇页数，pages 只过滤输出块）。

        流程：submit → wait_parse → convert 导出 md → wait_convert →
        download → materialize。任一步失败抛 Doc2XError 且带 uid，
        调用方应凭 uid 续查而非重新 submit。
        """
        if add_surrogate_to_request is None:
            raise EngineUnavailableError(
                "dynamic_credentials 不可用，Doc2X 凭据无法注入。")
        pdf_path = Path(pdf_path)
        uid = self._client.submit(pdf_path, model=self.model)
        run: dict = {
            "engine": "doc2x", "uid": uid, "model": self.model,
            "formula_mode": self.formula_mode,
            "formula_level": self.formula_level,
            "merge_cross_page_forms": self.merge_cross_page_forms,
            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        self.last_run = run
        # 崩溃安全：uid 一拿到就落盘。后段任何失败都能凭 uid 续查，
        # 不必重新 submit 重复计费（2026-10-20 实测教训：materialize
        # 阶段的路径 bug 曾让一次已付费任务的 uid 随进程退出而丢失）。
        self._flush_run(run)
        result = self._client.wait_parse(uid)
        run["parse_status"] = "success"
        run["result_pages"] = len(result.get("pages") or [])
        scores = [p.get("score") for p in result.get("pages") or []
                  if isinstance(p, dict)
                  and isinstance(p.get("score"), (int, float))]
        if scores:
            run["page_score_mean"] = round(sum(scores) / len(scores), 1)

        self._client.convert_submit(
            uid, to="md", formula_mode=self.formula_mode,
            formula_level=self.formula_level,
            merge_cross_page_forms=self.merge_cross_page_forms,
            filename=pdf_path.stem)
        url = self._client.wait_convert(uid)
        payload = self._client.download(url)
        run["export_status"] = "success"

        if self._output_dir is not None:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            (self._output_dir / "doc2x_result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8")
            materialized = materialize_export(payload, self._output_dir)
            run["export_kind"] = materialized["kind"]
            run["export_markdown"] = Path(
                materialized["markdown_path"]).name
            run["export_assets"] = materialized["assets"]
            self._flush_run(run)
        page_sizes_pt: dict = {}
        try:
            import pymupdf
            doc = pymupdf.open(pdf_path)
            try:
                page_sizes_pt = {i + 1: (p.rect.width, p.rect.height)
                                 for i, p in enumerate(doc)}
            finally:
                doc.close()
        except Exception:
            page_sizes_pt = {}  # 读不到页尺寸则退化 per-mille，不中断解析
        blocks = convert_doc2x_result(result, pages=pages,
                                      page_sizes_pt=page_sizes_pt)
        return blocks
