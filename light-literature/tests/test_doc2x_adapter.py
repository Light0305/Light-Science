"""Doc2X 适配器测试：状态机 mock、layout/MD 双路转换、
materialize 与凭据脱敏。全程不联网、不用真实 Key（凭据注入
被 monkeypatch 成假 surrogate）。

（源自开发期第五增量测试；其中对照打分器部分的测试随研究
存档一并剔除，不在本产品发布中。）
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from light_literature.engines import validate_middle_blocks
from light_literature.engines import doc2x as doc2x_mod
from light_literature.engines.doc2x import (Doc2XClient, Doc2XError,
                                            Doc2XTimeoutError,
                                            convert_doc2x_result,
                                            materialize_export)


# ---------- 假 opener / 假凭据注入 ----------

class FakeResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self._body = payload if isinstance(payload, bytes) \
            else json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    """按 handler 函数应答并记录全部请求（url/method/headers/body）。"""

    def __init__(self, handler):
        self.handler = handler
        self.requests: list = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        return self.handler(request)


@pytest.fixture(autouse=True)
def fake_surrogate(monkeypatch):
    """把凭据注入换成假实现：只加一个可断言的假 Authorization 头。"""
    def _fake(request, credential_name, *, allowed_hosts):
        assert credential_name == "custom.doc2x"
        assert "v2.doc2x.noedgeai.com" in allowed_hosts
        request.add_header("Authorization", "Bearer hsurr:fake-test")
    monkeypatch.setattr(doc2x_mod, "add_surrogate_to_request", _fake)


def _envelope(data, code="success", msg=""):
    return {"code": code, "msg": msg, "data": data}


def _no_sleep(_s):
    return None


# ---------- 适配器状态机 ----------

def test_submit_flow_preupload_put_status():
    seen = {}

    def handler(req):
        url = req.full_url
        if url.endswith("/parse/preupload"):
            seen["preupload_auth"] = req.get_header("Authorization")
            body = json.loads(req.data.decode())
            assert body == {"model": "v3-2026"}
            return FakeResponse(200, _envelope(
                {"uid": "u-1", "url": "https://oss.example.com/up?sig=x"}))
        if url.startswith("https://oss.example.com/"):
            seen["put_auth"] = req.get_header("Authorization")
            seen["put_method"] = req.get_method()
            return FakeResponse(200, b"")
        raise AssertionError(f"unexpected url {url}")

    client = Doc2XClient(opener=FakeOpener(handler), sleep=_no_sleep)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-fake")
        pdf = Path(f.name)
    uid = client.submit(pdf)
    assert uid == "u-1"
    assert seen["preupload_auth"] == "Bearer hsurr:fake-test"
    assert seen["put_auth"] is None  # 预签名 PUT 不带 Authorization
    assert seen["put_method"] == "PUT"


def test_wait_parse_processing_then_success():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(200, _envelope(
                {"status": "processing", "progress": 40}))
        return FakeResponse(200, _envelope(
            {"status": "success", "progress": 100,
             "result": {"pages": [{"page_idx": 0, "md": "hi"}]}}))

    client = Doc2XClient(opener=FakeOpener(handler), sleep=_no_sleep)
    result = client.wait_parse("u-2", max_wait_s=60)
    assert result["pages"][0]["md"] == "hi"
    assert calls["n"] == 2


def test_wait_parse_failed_raises_with_detail():
    def handler(req):
        return FakeResponse(200, _envelope(
            {"status": "failed", "detail": "unsupported file"}))

    client = Doc2XClient(opener=FakeOpener(handler), sleep=_no_sleep)
    with pytest.raises(Doc2XError, match="unsupported file"):
        client.wait_parse("u-3", max_wait_s=60)


def test_wait_parse_timeout_carries_uid():
    def handler(req):
        return FakeResponse(200, _envelope(
            {"status": "processing", "progress": 1}))

    ticks = iter([0.0, 100.0, 1000.0, 2000.0])
    client = Doc2XClient(opener=FakeOpener(handler), sleep=_no_sleep,
                         monotonic=lambda: next(ticks, 9999.0))
    with pytest.raises(Doc2XTimeoutError) as excinfo:
        client.wait_parse("u-4", max_wait_s=600)
    assert excinfo.value.uid == "u-4"


def test_business_error_and_http_401_not_retried_silently():
    calls = {"n": 0}

    def handler_code(req):
        calls["n"] += 1
        return FakeResponse(200, _envelope({}, code="invalid_api_key",
                                           msg="bad key"))

    client = Doc2XClient(opener=FakeOpener(handler_code), sleep=_no_sleep)
    with pytest.raises(Doc2XError, match="invalid_api_key"):
        client.status("u-5")
    assert calls["n"] == 1  # 不可重试业务码只打一次

    import urllib.error
    def handler_401(req):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized",
                                     {}, io.BytesIO(b"no"))

    client = Doc2XClient(opener=FakeOpener(handler_401), sleep=_no_sleep)
    with pytest.raises(Doc2XError, match="401") as excinfo:
        client.status("u-5")
    assert "hsurr" not in str(excinfo.value)  # 异常不带凭据痕迹


def test_convert_flow_and_zip_materialize(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 用相对路径调 materialize（回归测试）

    def handler(req):
        url = req.full_url
        if url.endswith("/convert/parse"):
            body = json.loads(req.data.decode())
            assert body["formula_mode"] == "dollar"
            assert body["formula_level"] == 0
            assert body["merge_cross_page_forms"] is True
            return FakeResponse(200, _envelope(
                {"status": "processing", "url": ""}))
        if "/convert/parse/result" in url:
            return FakeResponse(200, _envelope(
                {"status": "success",
                 "url": "https://bucket.aliyuncs.com/exp.zip?sig=y"}))
        if url.startswith("https://bucket.aliyuncs.com/"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("paper.md", "# Title\n\nbody")
                zf.writestr("images/a.jpg", b"\xff\xd8fake")
            return FakeResponse(200, buf.getvalue())
        raise AssertionError(url)

    client = Doc2XClient(opener=FakeOpener(handler), sleep=_no_sleep)
    client.convert_submit("u-6", to="md", formula_mode="dollar",
                          formula_level=0, merge_cross_page_forms=True)
    url = client.wait_convert("u-6")
    payload = client.download(url)
    out = materialize_export(payload, Path("relative-out"))
    assert out["kind"] == "zip"
    assert Path(out["markdown_path"]).read_text(encoding="utf-8") \
        .startswith("# Title")
    assert out["assets"] == ["images/a.jpg"]


def test_download_host_allowlist():
    client = Doc2XClient(opener=FakeOpener(lambda req: None),
                         sleep=_no_sleep)
    with pytest.raises(Doc2XError, match="白名单"):
        client.download("https://evil.example.org/x.zip")
    with pytest.raises(Doc2XError, match="白名单"):
        client.download("http://bucket.aliyuncs.com/x.zip")  # 非 https


def test_scrub_removes_credential_shapes():
    dirty = "Bearer abc.def hsurr:xyz123 sk-1234567890abcdef tail"
    clean = doc2x_mod._scrub(dirty)
    assert "hsurr:" not in clean and "sk-1234" not in clean
    assert "abc.def" not in clean


# ---------- result → middle_json 转换 ----------

def _layout_result():
    def page(idx, blocks):
        return {"page_idx": idx, "md": "", "page_width": 1000,
                "page_height": 2000, "layout": {"blocks": blocks}}
    p0 = page(0, [
        {"id": "g0", "type": "TableGroup", "text": "", "bbox": [0, 0, 10, 10],
         "reading_order": 0, "parent_id": ""},
        {"id": "t0", "type": "Table", "text": "", "bbox": [100, 100, 900, 400],
         "reading_order": 1, "parent_id": "g0",
         "table_data": {"html": "<table><tr><td>1</td></tr></table>"}},
        {"id": "c0", "type": "Caption", "text": "Table 1: demo",
         "bbox": [100, 50, 900, 90], "reading_order": 2, "parent_id": "g0"},
        {"id": "h0", "type": "Title", "text": "3.5 Methods",
         "bbox": [100, 500, 400, 540], "reading_order": 3, "parent_id": ""},
        {"id": "e0", "type": "Equation", "text": "\\[x^2 + y^2 = z^2\\]",
         "bbox": [100, 600, 500, 660], "reading_order": 4, "parent_id": ""},
        {"id": "n0", "type": "EquationNumber", "text": "(1)",
         "bbox": [900, 600, 950, 660], "reading_order": 5, "parent_id": ""},
        {"id": "b0", "type": "Text", "text": "7",
         "bbox": [490, 1900, 510, 1950], "reading_order": 6,
         "parent_id": "", "attributes": {"is_boilerplate": True}},
    ])
    p1 = page(1, [
        {"id": "g1", "type": "FigureGroup", "text": "", "bbox": [0, 0, 9, 9],
         "reading_order": 0, "parent_id": ""},
        {"id": "f1", "type": "Figure", "text": "", "src": "https://img/f.jpg",
         "bbox": [100, 100, 900, 800], "reading_order": 1,
         "parent_id": "g1"},
        {"id": "c1", "type": "Caption", "text": "Figure 1: demo",
         "bbox": [100, 820, 900, 880], "reading_order": 2,
         "parent_id": "g1"},
    ])
    return {"pages": [p0, p1], "version": "v3-2026"}


def test_convert_layout_blocks_types_bbox_and_caption_offset():
    blocks = convert_doc2x_result(_layout_result())
    types = [b["type"] for b in blocks]
    assert types == ["table", "caption", "text", "equation", "text",
                     "figure", "caption"]
    # 页内图注 caption_of 是全篇下标：p1 的图注须指向 p1 的图（下标 5）
    cap2 = blocks[-1]
    assert blocks[cap2["caption_of"]]["type"] == "figure"
    cap1 = blocks[1]
    assert blocks[cap1["caption_of"]]["type"] == "table"
    # 无 PDF 页尺寸时 bbox 为 per-mille
    assert blocks[0]["bbox"] == [100, 50, 900, 200]
    assert blocks[0]["bbox_space"] == "per_mille"
    # 公式定界符剥离、公式编号并入、页码块标 boilerplate、标题层级
    eq = blocks[3]
    assert eq["latex"] == "x^2 + y^2 = z^2"
    assert eq["equation_number"] == "(1)"
    assert blocks[4].get("is_boilerplate") is True
    assert blocks[2]["text_level"] == 2
    assert validate_middle_blocks(blocks) == []
    # 给页尺寸时换算为 PDF 点
    blocks_pt = convert_doc2x_result(
        _layout_result(), page_sizes_pt={1: (500.0, 1000.0),
                                         2: (500.0, 1000.0)})
    assert blocks_pt[0]["bbox"] == [50.0, 50.0, 450.0, 200.0]
    assert "bbox_space" not in blocks_pt[0]


def test_convert_md_fallback_without_layout():
    result = {"pages": [{"page_idx": 0, "md":
                         "# Intro\n\nSome body text with $x^2$ inline.\n\n"
                         "$$E = mc^2$$\n\n"
                         "<table><tr><td>a</td></tr></table>\n\n"
                         "![fig](img1.png)\n\n"
                         "Figure 1: A caption paragraph."}]}
    blocks = convert_doc2x_result(result)
    types = [b["type"] for b in blocks]
    assert types == ["text", "text", "equation", "table", "figure",
                     "caption"]
    assert blocks[0]["text_level"] == 1
    assert blocks[1]["inline_latex"] == ["$x^2$"]
    assert blocks[2]["latex"] == "E = mc^2"
    assert blocks[4]["asset"] == "img1.png"
    assert all(b["bbox_space"] == "missing" for b in blocks)
    assert validate_middle_blocks(blocks) == []

