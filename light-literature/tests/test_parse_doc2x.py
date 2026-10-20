"""parse 命令测试（Doc2X 轨锚点化）+ 失败置 awaiting_model_direct
（不回退任何本地抽取）+ HTML 表格转 MD。

全程 mock 网络层（假 opener + 假凭据注入），不用真实 Key、不产生
费用。Doc2X 响应形态按真实样本构造（layout 块 + 逐页 MD 兜底 +
convert zip 导出图）。

注：发布版不含本地抽取模块，「不回退」由结构保证（parse 不导入
任何本地抽取代码）；失败路径测试断言状态落盘与产物缺席。
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from light_literature import cli, contentlist, parse as parse_mod
from light_literature import translate as translate_mod
from light_literature import verify as verify_mod
from light_literature.engines import EngineUnavailableError
from light_literature.engines import doc2x as doc2x_mod
from light_literature.engines.doc2x import Doc2XClient, Doc2XEngine
from light_literature.util import read_json, read_yaml


# ---------- 假 opener / 假凭据注入（与第五增量同模式）----------

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
    def __init__(self, handler):
        self.handler = handler
        self.requests: list = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        return self.handler(request)


@pytest.fixture(autouse=True)
def fake_surrogate(monkeypatch):
    def _fake(request, credential_name, *, allowed_hosts):
        assert credential_name == "custom.doc2x"
        request.add_header("Authorization", "Bearer hsurr:fake-test")
    monkeypatch.setattr(doc2x_mod, "add_surrogate_to_request", _fake)


def _envelope(data, code="success", msg=""):
    return {"code": code, "msg": msg, "data": data}


def _no_sleep(_s):
    return None


def _result_fixture():
    """两页 Doc2X result：p1 走 layout（图组/图注/公式/表格/页眉页脚），
    p2 无 layout 走逐页 MD 兜底。layout 渲染尺寸取 PDF 点的 2 倍。"""
    page0 = {
        "page_idx": 0, "score": 90, "page_width": 1190, "page_height": 1684,
        "md": "",
        "layout": {"blocks": [
            {"id": "g0", "type": "FigureGroup", "text": "",
             "bbox": [0, 0, 10, 10], "reading_order": 0, "parent_id": ""},
            {"id": "f0", "type": "Figure", "text": "",
             "src": "https://img.doc2x.noedgeai.com/u-test_0.jpg"
                    "?x=10&y=20&w=100&h=50&r=0",
             "bbox": [100, 100, 700, 400], "reading_order": 1,
             "parent_id": "g0"},
            {"id": "f0b", "type": "Figure", "text": "",
             "src": "https://img.doc2x.noedgeai.com/u-test_0.jpg"
                    "?x=999&y=888&w=77&h=66&r=0",
             "bbox": [720, 100, 1100, 400], "reading_order": 2,
             "parent_id": "g0"},
            {"id": "c0", "type": "Caption", "text": "Figure 1: A test figure.",
             "bbox": [100, 420, 1100, 460], "reading_order": 3,
             "parent_id": "g0"},
            {"id": "h0", "type": "Title", "text": "1 Introduction",
             "bbox": [100, 500, 500, 540], "reading_order": 4,
             "parent_id": ""},
            {"id": "t0", "type": "Text",
             "text": "Body paragraph text for parse testing.",
             "bbox": [100, 560, 1100, 640], "reading_order": 5,
             "parent_id": ""},
            {"id": "e0", "type": "Equation", "text": "\\[x^2 + y^2 = z^2\\]",
             "bbox": [100, 660, 600, 720], "reading_order": 6,
             "parent_id": ""},
            {"id": "g1", "type": "TableGroup", "text": "",
             "bbox": [0, 0, 10, 10], "reading_order": 7, "parent_id": ""},
            {"id": "tb0", "type": "Table", "text": "",
             "bbox": [100, 760, 1100, 1000], "reading_order": 8,
             "parent_id": "g1",
             "table_data": {"html": "<table><tr><th>a</th><th>b</th></tr>"
                                    "<tr><td>1</td><td>2</td></tr></table>"}},
            {"id": "c1", "type": "Caption", "text": "Table 1: A test table.",
             "bbox": [100, 1020, 1100, 1060], "reading_order": 9,
             "parent_id": "g1"},
            {"id": "b0", "type": "Text", "text": "7",
             "bbox": [580, 1620, 610, 1660], "reading_order": 10,
             "parent_id": "", "attributes": {"is_boilerplate": True}},
        ]},
    }
    page1 = {
        "page_idx": 1, "score": 80,
        "md": "Scanned page body text.\n\n![scan](images/p2fig.png)\n\n"
              "Figure 2: A scanned figure.",
    }
    return {"pages": [page0, page1], "version": "v3-2026"}


def _export_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("原文.md", "# exported markdown\n")
        # f0 的 src 参数 (x=10,y=20,w=100,h=50,r=0, page 0) 命中的导出图
        zf.writestr("images/0_10_20_100_50_0.jpg", b"\xff\xd8fake-jpg")
        zf.writestr("images/p2fig.png", b"\x89PNG fake")
    return buf.getvalue()


def _make_handler(result=None, fail_preupload=False):
    result = _result_fixture() if result is None else result
    zip_bytes = _export_zip()

    def handler(req):
        url = req.full_url
        if "/parse/preupload" in url:
            if fail_preupload:
                return FakeResponse(200, _envelope(
                    {}, code="invalid_api_key", msg="bad key"))
            return FakeResponse(200, _envelope(
                {"uid": "u-test", "url": "https://oss.example.com/up?sig=x"}))
        if url.startswith("https://oss.example.com/"):
            return FakeResponse(200, b"")
        if "/parse/status" in url:
            return FakeResponse(200, _envelope(
                {"status": "success", "progress": 100, "result": result}))
        if "/convert/parse/result" in url:
            return FakeResponse(200, _envelope(
                {"status": "success",
                 "url": "https://bucket.aliyuncs.com/exp.zip?sig=y"}))
        if "/convert/parse" in url:
            return FakeResponse(200, _envelope(
                {"status": "processing", "url": ""}))
        if url.startswith("https://bucket.aliyuncs.com/"):
            return FakeResponse(200, zip_bytes)
        raise AssertionError(f"unexpected url {url}")

    return handler


def _fake_engine(pdir: Path, **handler_kwargs) -> Doc2XEngine:
    client = Doc2XClient(opener=FakeOpener(_make_handler(**handler_kwargs)),
                         sleep=_no_sleep)
    return Doc2XEngine(client=client, output_dir=pdir / "doc2x")


def _pdir(ingested) -> Path:
    proj, paper_id = ingested
    return proj / "Literature" / paper_id


# ---------- 成功路径：parse → verify → translate-scaffold 全链 ----------

def test_parse_doc2x_full_chain(ingested):
    proj, paper_id = ingested
    pdir = _pdir(ingested)
    stats = parse_mod.parse(pdir, engine=_fake_engine(pdir))

    assert stats["backend"] == "doc2x"
    assert stats["anchors"] == {"S": 3, "C": 3, "F": 3, "T": 1, "E": 1}
    assert stats["total_blocks"] == 12  # 11 锚点块 + 1 boilerplate 留痕
    assert stats["figure_groups"] == 2
    assert stats["multi_fragment_groups"] == 1
    assert stats["uid"] == "u-test"

    smap = read_json(pdir / "source_map.json")
    assert smap["backend"] == "doc2x"
    assert smap["pending_pages"] == []
    by_id = {b["id"]: b for b in smap["blocks"] if b.get("id")}
    # 图组：F001/F002 同组共享 C001；图注 host 指组首块并记 host_ids
    assert by_id["F001"]["group_id"] == "G-F001"
    assert by_id["F002"]["group_id"] == "G-F001"
    assert by_id["F001"]["group_role"] == "fragment"
    assert by_id["F001"]["caption_id"] == "C001"
    assert by_id["F002"]["caption_id"] == "C001"
    assert by_id["C001"]["host_id"] == "F001"
    assert by_id["C001"]["host_ids"] == ["F001", "F002"]
    # 表格：图注配对 + HTML 转 MD + HTML 原件保留
    assert by_id["T001"]["caption_id"] == "C002"
    assert by_id["T001"]["table_md"].splitlines()[0] == "| a | b |"
    assert by_id["T001"]["rows"] == 2 and by_id["T001"]["cols"] == 2
    assert "<table>" in by_id["T001"]["table_html"]
    # 公式：Doc2X LaTeX 直达 text/latex，不再是待视觉通道状态
    assert by_id["E001"]["latex"] == "x^2 + y^2 = z^2"
    assert by_id["E001"]["text"] == "x^2 + y^2 = z^2"
    # confidence 取页 score/100：p1=90 → 0.9，p2=80 → 0.8
    assert by_id["S001"]["confidence"] == 0.9
    assert by_id["S003"]["confidence"] == 0.8
    # 图资产三来源：导出图命中 / PDF 裁片兜底 / MD 路径导出图
    assert by_id["F001"]["asset"] == "assets/figures/0_10_20_100_50_0.jpg"
    assert by_id["F001"]["asset_source"] == "doc2x_export"
    assert by_id["F002"]["asset_source"] == "pdf_crop"
    assert by_id["F003"]["asset"] == "assets/figures/p2fig.png"
    for fid in ("F001", "F002", "F003"):
        assert (pdir / by_id[fid]["asset"]).is_file()

    md_text = (pdir / "原文.md").read_text(encoding="utf-8")
    assert "Doc2X 解析生成" in md_text
    assert "$$\nx^2 + y^2 = z^2\n$$" in md_text

    paper = read_yaml(pdir / "paper.yaml")
    assert paper["parse"]["status"] == "done"
    assert paper["parse"]["backend"] == "doc2x"
    assert paper["parse"]["engine_params"]["model"] == "v3-2026"
    assert paper["parse"]["engine_params"]["formula_mode"] == "dollar"
    assert paper["status"]["extract"] == "done"

    # 下游全链不感知来源：verify 全过、脚手架块数一致、content_list 可导出
    report = verify_mod.verify(proj, paper_id)
    assert report["ok"], report["errors"]
    scaffold = translate_mod.translate_scaffold(proj, paper_id)
    assert scaffold["blocks"] == 11
    report2 = verify_mod.verify(proj, paper_id)
    assert report2["ok"], report2["errors"]
    assert report2["translation"]["status"] == "checked"
    items = contentlist.export_content_list(proj, paper_id)
    assert items["items"] == 8  # 3 图注折入宿主：11 - 3
    cl = read_json(pdir / "content_list.json")
    img = next(i for i in cl if i.get("anchor_id") == "F001")
    assert img["image_caption"] == ["Figure 1: A test figure."]


def test_parse_cli_success_and_local_rejected(ingested, monkeypatch):
    pdir = _pdir(ingested)
    engine = _fake_engine(pdir)
    monkeypatch.setattr(parse_mod, "Doc2XEngine",
                        lambda output_dir=None: engine)
    assert cli.main(["parse", str(pdir)]) == 0
    assert (pdir / "source_map.json").exists()
    # --backend local 不是产品路径：CLI 明确报错退出 2
    assert cli.main(["parse", str(pdir), "--backend", "local"]) == 2


# ---------- 失败路径：awaiting_model_direct，绝不回退本地 extract ----------

def test_parse_no_credential_awaits_model_direct(ingested, monkeypatch):
    proj, paper_id = ingested
    pdir = _pdir(ingested)
    monkeypatch.setattr(doc2x_mod, "add_surrogate_to_request", None)
    with pytest.raises(EngineUnavailableError, match="awaiting_model_direct"):
        parse_mod.parse(pdir)
    paper = read_yaml(pdir / "paper.yaml")
    assert paper["parse"]["status"] == "awaiting_model_direct"
    assert paper["parse"]["backend"] == "doc2x"
    assert "凭据" in paper["parse"]["error"]
    # 本地管线没有被用来顶替：四件套解析产物不存在
    assert not (pdir / "source_map.json").exists()
    assert not (pdir / "原文.md").exists()


def test_parse_doc2x_failure_awaits_model_direct(ingested, monkeypatch):
    proj, paper_id = ingested
    pdir = _pdir(ingested)
    engine = _fake_engine(pdir, fail_preupload=True)
    with pytest.raises(Exception, match="awaiting_model_direct"):
        parse_mod.parse(pdir, engine=engine)
    paper = read_yaml(pdir / "paper.yaml")
    assert paper["parse"]["status"] == "awaiting_model_direct"
    assert "invalid_api_key" in paper["parse"]["error"]
    assert not (pdir / "source_map.json").exists()


def test_parse_backend_local_rejected(ingested):
    pdir = _pdir(ingested)
    with pytest.raises(ValueError, match="研究/对照工具"):
        parse_mod.parse(pdir, backend="local")


# ---------- 纯函数：HTML 表格转 MD / 导出图名推导 ----------

def test_html_table_to_md_spans_and_escape():
    html = ("<table><tr><th>h1</th><th>h|2</th></tr>"
            "<tr><td rowspan='2'>x</td><td>1</td></tr>"
            "<tr><td>2</td></tr></table>")
    md, rows, cols = parse_mod.html_table_to_md(html)
    assert (rows, cols) == (3, 2)
    lines = md.splitlines()
    assert lines[0] == "| h1 | h\\|2 |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| x | 1 |"
    assert lines[3] == "| x | 2 |"  # rowspan 展开后重复出现
    assert parse_mod.html_table_to_md("") == ("", 0, 0)
    assert parse_mod.html_table_to_md("no table") == ("", 0, 0)


def test_export_image_name_derivation():
    src = ("https://img.doc2x.noedgeai.com/01a15552-e683-71af_0.jpg"
           "?x=896&y=647&w=718&h=246&r=0")
    assert parse_mod._export_image_name(src) == "0_896_647_718_246_0.jpg"
    assert parse_mod._export_image_name("images/a.png") is None
    assert parse_mod._export_image_name("https://x.com/no-query.jpg") is None
    assert parse_mod._export_image_name("") is None
