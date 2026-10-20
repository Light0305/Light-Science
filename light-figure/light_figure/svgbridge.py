"""Illustrator 精修路线的 SVG 桥入口校验（FIG-D03）。

入口纪律（采 scientific-illustrator-agent 的受限子集口径）：SVG
只收受限矢量/文本子集——拒位图图片、外部资源引用、脚本、滤镜、
CSS 与 foreignObject。理由：.ai 不开放、SVG 是唯一可审计的桥；
且 SVG 导入 Illustrator 存在实测坑——字体缺字形时静默丢字且
报告成功。故本校验同时逐字抽取全部文本节点成清单，供导入后
逐字对账（不许只核对象计数）。
"""

from __future__ import annotations

import re
from pathlib import Path
import xml.etree.ElementTree as ET

FORBIDDEN_ELEMENTS = {
    "image": "位图图片（桥只收矢量/文本子集，位图走残留登记）",
    "script": "脚本元素",
    "filter": "滤镜（宿主间表现不可审计）",
    "foreignObject": "foreignObject（HTML 嵌入，不可审计）",
    "style": "CSS 样式元素（样式须内联为属性才可审计）",
    "animate": "动画元素",
    "set": "动画元素",
}
_EXTERNAL_HREF = re.compile(r"^(https?:|file:|data:|//)")


class SvgBridgeError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def validate_svg_subset(path) -> dict:
    """校验 SVG 是否落在受限子集内；返回 {ok, gaps, texts, counts}。

    texts = 全部文本节点逐字清单（导入宿主后须逐字对账——缺字形
    静默丢字是本桥的头号坑，对账不许只核计数）。
    """
    path = Path(path)
    if not path.exists():
        raise SvgBridgeError([f"SVG 文件不存在：{path}"])
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise SvgBridgeError([f"SVG 不是良构 XML：{e}"])
    root = tree.getroot()
    if _local(root.tag) != "svg":
        raise SvgBridgeError([f"根元素是 {_local(root.tag)}，不是 svg"])
    gaps = []
    texts = []
    counts = {"elements": 0, "text_elements": 0, "paths": 0}
    for el in root.iter():
        counts["elements"] += 1
        tag = _local(el.tag)
        if tag in FORBIDDEN_ELEMENTS:
            gaps.append(f"含禁用元素 <{tag}>：{FORBIDDEN_ELEMENTS[tag]}")
        if tag == "path":
            counts["paths"] += 1
        if tag in ("text", "tspan"):
            content = "".join(el.itertext()).strip()
            if tag == "text":
                counts["text_elements"] += 1
                if content:
                    texts.append(content)
        for attr, value in el.attrib.items():
            attr_local = _local(attr)
            if attr_local in ("href",) and _EXTERNAL_HREF.match(
                    str(value).strip()):
                gaps.append(f"元素 <{tag}> 的 href 指向外部/数据资源 "
                            f"{value!r}（桥只收自包含子集）")
            if attr_local == "style" and "url(" in str(value):
                gaps.append(f"元素 <{tag}> 的 style 含 url() 外部引用")
    return {"ok": not gaps, "gaps": gaps, "texts": texts,
            "counts": counts, "file": str(path)}
