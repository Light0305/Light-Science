"""抽取双档（clean_profile）测试：登记、深档接入、如实降级。

深档依赖可选包 trafilatura：装了跑真抽取断言，没装时相关用例
skip；降级路径用 monkeypatch 模拟缺席，恒可跑。
"""

from __future__ import annotations

import pytest

from light_crawler import extractors, storage

ARTICLE = b"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Harbour Study Results - Journal of Examples</title>
<meta name="author" content="Priya Nair">
</head><body>
<nav><a href="/">Home</a> <a href="/ads">Advertise with us</a></nav>
<article>
<h1>Harbour Study Results</h1>
<p>The harbour study counted 412 seals during the spring survey, up from
389 the previous year, according to the report released on Monday.</p>
<p>Researchers attributed the increase to the new fishing exclusion zone
that took effect along the northern breakwater in January.</p>
<p>The team will repeat the survey next spring with two additional
observation posts on the eastern pier.</p>
</article>
<footer><p>Copyright notice for the journal site.</p></footer>
</body></html>"""


def test_registry_has_both_profiles():
    assert extractors.PROFILE_BACKENDS[extractors.LIGHT_PROFILE] \
        == "builtin_html_text"
    assert extractors.PROFILE_BACKENDS[extractors.DEEP_PROFILE] \
        == "trafilatura"


def test_light_profile_unchanged_shape():
    out = storage.clean_content(ARTICLE, "text/html; charset=utf-8",
                                profile=extractors.LIGHT_PROFILE)
    assert out["kind"] == "html"
    assert out["profile"] == "html_text_v1"
    assert "extractor" not in out  # 轻档产物形状与接入前一致
    assert "412 seals" in out["text"]
    assert "Advertise with us" in out["text"]  # 轻档含导航，已知形态


@pytest.mark.skipif(not extractors.deep_available(),
                    reason="trafilatura 未安装（可选依赖）")
def test_deep_profile_extracts_and_registers():
    out = storage.clean_content(ARTICLE, "text/html; charset=utf-8",
                                profile=extractors.DEEP_PROFILE)
    assert out["kind"] == "html"
    reg = out["extractor"]
    assert reg["profile_requested"] == "trafilatura_v1"
    assert reg["backend"] == "trafilatura"
    assert reg["backend_version"] == extractors.trafilatura_version()
    assert reg["degraded"] is False
    assert "412 seals" in out["text"]
    assert "Advertise with us" not in out["text"]  # 深档剔导航
    assert out["metadata"].get("author") == "Priya Nair"


def test_deep_profile_degrades_honestly_when_backend_missing(monkeypatch):
    monkeypatch.setattr(extractors, "trafilatura_version", lambda: None)
    out = storage.clean_content(ARTICLE, "text/html; charset=utf-8",
                                profile=extractors.DEEP_PROFILE)
    reg = out["extractor"]
    assert reg["backend"] == "trafilatura"
    assert reg["degraded"] is True
    assert "未安装" in reg["degrade_reason"]
    # 降级产物 = 轻档文本（回退路径），且标题/meta 与轻档一致
    light = storage.clean_content(ARTICLE, "text/html; charset=utf-8",
                                  profile=extractors.LIGHT_PROFILE)
    assert out["text"] == light["text"]
    assert out["title"] == light["title"]
    assert out["text_sha256"] == light["text_sha256"]


def test_deep_profile_degrades_on_empty_extraction(monkeypatch):
    # trafilatura 在场但对该页返回空：同样走登记降级，不冒充深档
    monkeypatch.setattr(extractors, "extract_deep",
                        lambda html: {"backend": "trafilatura",
                                      "backend_version": "test",
                                      "degraded": True,
                                      "degrade_reason": "未抽出正文（返回空）",
                                      "title": None, "metadata": {},
                                      "text": ""})
    out = storage.clean_content(ARTICLE, "text/html; charset=utf-8",
                                profile=extractors.DEEP_PROFILE)
    assert out["extractor"]["degraded"] is True
    assert "412 seals" in out["text"]  # 回退轻档后正文仍在


def test_unknown_profile_falls_back_to_light_path():
    out = storage.clean_content(ARTICLE, "text/html; charset=utf-8",
                                profile="some_future_profile")
    assert out["profile"] == "some_future_profile"
    light = storage.clean_content(ARTICLE, "text/html; charset=utf-8")
    assert out["text"] == light["text"]
