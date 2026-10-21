"""抽取后端注册表：clean_profile 选档的实现面（C3 清洗的深档）。

两档登记在册（PROFILE_BACKENDS 是唯一登记点）：

- ``html_text_v1``（轻档）：包内自研最小抽取（storage._TextExtractor），
  零第三方依赖，标题 + meta + 可见文本。实现在 storage，本模块只登记。
- ``trafilatura_v1``（深档）：trafilatura 谱系深度抽取（正文 + 元数据），
  可选依赖——未安装、版本探针失败或抽取抛错时**如实降级**回轻档，
  并在结果里留 degraded / degrade_reason，不许静默冒充深档产物。

降级路径是登记在册的正式行为而非异常：深档产物与降级产物在
``backend`` 字段上可区分，下游与验收据此读数。合规层（预检、
robots、速率、熔断）与本模块无关，抽取只处理已放行落盘的字节。
"""

from __future__ import annotations

LIGHT_PROFILE = "html_text_v1"
DEEP_PROFILE = "trafilatura_v1"

#: 档位登记：档位名 -> 后端名。新增档位先在此登记，再实现后端函数。
PROFILE_BACKENDS = {
    LIGHT_PROFILE: "builtin_html_text",
    DEEP_PROFILE: "trafilatura",
}


def trafilatura_version() -> str | None:
    """探针：已安装的 trafilatura 版本；未安装/不可用返回 None。"""
    try:
        import trafilatura
        return str(getattr(trafilatura, "__version__", "unknown"))
    except Exception:
        return None


def deep_available() -> bool:
    return trafilatura_version() is not None


def extract_deep(html_text: str) -> dict:
    """深档抽取：返回 title / metadata / text + 后端登记信息。

    本函数被调用即意味着目标档位是深档；trafilatura 不可用或抽取
    失败时返回 degraded 结果（text 为空、degrade_reason 点名原因），
    由调用方（storage.clean_content）决定回退轻档文本——降级决定权
    与留痕都在调用方，本函数不吞异常细节。
    """
    version = trafilatura_version()
    if version is None:
        return {"backend": "trafilatura", "backend_version": None,
                "degraded": True,
                "degrade_reason": "trafilatura 未安装（可选依赖缺席）",
                "title": None, "metadata": {}, "text": ""}
    try:
        import json as _json

        import trafilatura

        raw = trafilatura.extract(
            html_text, output_format="json", with_metadata=True,
            include_tables=True, include_comments=False,
            include_links=False, deduplicate=True)
        if not raw:
            return {"backend": "trafilatura", "backend_version": version,
                    "degraded": True,
                    "degrade_reason": "trafilatura 未抽出正文（返回空）",
                    "title": None, "metadata": {}, "text": ""}
        doc = _json.loads(raw)
    except Exception as exc:  # 抽取异常一律走登记降级，不向上冒泡
        return {"backend": "trafilatura", "backend_version": version,
                "degraded": True,
                "degrade_reason": f"trafilatura 抽取异常：{exc!r}"[:200],
                "title": None, "metadata": {}, "text": ""}
    metadata = {}
    for key in ("author", "date", "description", "sitename", "hostname",
                "language", "title"):
        val = doc.get(key)
        if val:
            metadata[key] = val
    return {"backend": "trafilatura", "backend_version": version,
            "degraded": False, "degrade_reason": None,
            "title": doc.get("title") or None,
            "metadata": metadata,
            "text": (doc.get("text") or "").strip()}


def registration(profile: str, deep: dict | None = None) -> dict:
    """清洗件里的抽取登记段：选了哪档、实际由哪个后端产出、是否降级。"""
    if profile == DEEP_PROFILE and deep is not None:
        return {"profile_requested": profile,
                "backend": deep["backend"],
                "backend_version": deep["backend_version"],
                "degraded": deep["degraded"],
                "degrade_reason": deep["degrade_reason"]}
    return {"profile_requested": profile,
            "backend": PROFILE_BACKENDS.get(profile, "builtin_html_text"),
            "backend_version": "builtin",
            "degraded": False, "degrade_reason": None}
