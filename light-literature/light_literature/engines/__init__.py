"""解析引擎适配器接口（Engine Adapter 协议）。

产品实现是 `doc2x.py`（Doc2X 轨，`parse` 命令的解析后端）。任何引擎
只要实现本协议即可替换接入：输入 = PDF + 页范围，输出 = 同一份
middle_json 块列表——换引擎不换产物契约。

middle_json 块契约（与 source_map 的块字段对齐）：
- 必备字段：`type`（text/caption/figure/table/equation 之一）、`page`
  （1 起页码）、`bbox`（[x0, y0, x1, y1]，PDF 点坐标）、`provenance`
  （来源标注，如 ``engine:doc2x``，逐块必填，不许留空）。
- 类型字段：text/caption 带 `text`；equation 带 `text`（LaTeX）
  或 `asset`（公式裁片的引擎侧定位符）二者居其一——只检出公式
  区域、不做转写的引擎只能给 asset，块上须另有 note 说明未转写，
  不许拿空 text 冒充；
  figure 带 `asset`（相对论文目录的资产路径或引擎侧路径/定位符，
  落盘由调用方负责）；table 带 `table_body`（HTML）或 `table_md`。
- 可选字段：`confidence`（0–1）、`text_level`、`caption_id` /
  `caption_number` 等，与 extract 的 source_map 块保持同名同义。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

MIDDLE_TYPES = ("text", "caption", "figure", "table", "equation")
MIDDLE_REQUIRED_FIELDS = ("type", "page", "bbox", "provenance")


class EngineUnavailableError(RuntimeError):
    """引擎在本机不可用（未安装/未配置）。

    适配器必须显式抛这个错并给出安装/配置提示，**不许静默跳过**——
    静默跳过会让调用方误以为页面已解析（见 SKILL.md 解析诚实规则）。
    """


@runtime_checkable
class EngineAdapter(Protocol):
    """引擎适配器协议：任何引擎实现这三个成员即可接入管线。"""

    name: str

    def available(self) -> bool:
        """本机是否可用（CLI 存在/Key 已配置等），只探测不调用。"""
        ...

    def parse(self, pdf_path: Path,
              pages: Optional[list[int]] = None) -> list[dict]:
        """解析 PDF 的指定页（1 起页码列表，None = 全部）。

        返回 middle_json 块列表（契约见本模块 docstring）。不可用时
        抛 EngineUnavailableError；解析失败抛 RuntimeError 并说明原因。
        """
        ...


def validate_middle_blocks(blocks: list[dict],
                           pages: Optional[list[int]] = None) -> list[str]:
    """校验一组 middle_json 块是否满足契约，返回错误列表（空 = 合格）。

    供适配器实现方与单测共用：字段齐全、类型合法、页范围被遵守、
    provenance 逐块标注。
    """
    errors: list[str] = []
    for i, b in enumerate(blocks):
        tag = f"块[{i}]"
        for field in MIDDLE_REQUIRED_FIELDS:
            if field not in b or b[field] in (None, ""):
                errors.append(f"{tag}：缺必备字段 {field}")
        if b.get("type") not in MIDDLE_TYPES:
            errors.append(f"{tag}：type 非法（{b.get('type')!r}）")
            continue
        bbox = b.get("bbox")
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
            errors.append(f"{tag}：bbox 须为 [x0, y0, x1, y1]")
        if pages is not None and b.get("page") not in pages:
            errors.append(f"{tag}：page={b.get('page')} 不在请求页范围 {pages}")
        if b["type"] in ("text", "caption") and not b.get("text"):
            errors.append(f"{tag}：{b['type']} 块缺 text")
        if b["type"] == "equation" and not (b.get("text") or b.get("asset")):
            errors.append(f"{tag}：equation 块缺 text（LaTeX）与 asset（裁片）")
        if b["type"] == "figure" and not b.get("asset"):
            errors.append(f"{tag}：figure 块缺 asset")
        if b["type"] == "table" and not (b.get("table_body") or b.get("table_md")):
            errors.append(f"{tag}：table 块缺 table_body/table_md")
        conf = b.get("confidence")
        if conf is not None and not (0.0 <= float(conf) <= 1.0):
            errors.append(f"{tag}：confidence 越界（{conf}）")
    return errors
