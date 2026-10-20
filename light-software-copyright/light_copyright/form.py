"""SC6 申请表信息：字段只许从单一事实源与实测派生（HC-2）。

derive_application 产出有序字段表（字段名/值/来源/填写位置/注意），
SC7 的递交清单与一致性核对都消费这一份派生结果——任何材料各填一份
的做法在结构上不存在。
"""

from __future__ import annotations

from pathlib import Path

from .snapshot import load_snapshot

DEV_MODE_LABELS = {
    "independent": "独立开发", "cooperative": "合作开发",
    "commissioned": "委托开发", "assigned": "下达任务开发",
}
PUBLICATION_LABELS = {"published": "已发表", "unpublished": "未发表"}


def derive_application(root, facts, code_manifest=None, doc_manifest=None):
    root = Path(root)
    sw = facts.get("software") or {}
    owner = facts.get("owner") or {}
    dev = facts.get("development") or {}
    pub = facts.get("publication") or {}
    rights = facts.get("rights") or {}
    fn = facts.get("functions") or {}
    env = facts.get("environment") or {}
    snap = None
    try:
        snap = load_snapshot(root)
    except Exception:
        snap = None

    def row(field, value, source, where, note=""):
        return {"field": field, "value": value, "source": source,
                "where": where, "note": note}

    rows = [
        row("软件全称", sw.get("full_name", ""), "facts.software",
            "申请表/软件名称", "页眉、封面、文件名同源派生"),
        row("软件简称", sw.get("short_name", ""), "facts.software",
            "申请表/软件名称"),
        row("版本号", sw.get("version", ""), "facts.software", "申请表"),
        row("软件分类", sw.get("category", ""), "facts.software", "申请表"),
        row("开发完成日期", dev.get("completion_date", ""),
            "facts.development", "申请表", "与发表日期逻辑不得矛盾"),
        row("开发方式", DEV_MODE_LABELS.get(dev.get("mode", ""),
            dev.get("mode", "")), "facts.development", "申请表"),
        row("原创/修改", "原创" if dev.get("original") else "修改（含原权利人许可）",
            "facts.development", "申请表"),
        row("发表状态", PUBLICATION_LABELS.get(pub.get("status", ""),
            pub.get("status", "")), "facts.publication",
            "申请表", "按事实登记，不默认未发表"),
        row("首次发表日期", pub.get("first_date", ""), "facts.publication",
            "申请表", "未发表则空"),
        row("首次发表地点", pub.get("first_place", ""), "facts.publication",
            "申请表"),
        row("著作权人", owner.get("name", ""), "facts.owner", "申请表",
            "证件号等敏感项在系统内按当期要求填，不落本包材料"),
        row("权利取得方式", rights.get("acquisition", ""), "facts.rights",
            "申请表"),
        row("权利范围", rights.get("scope", ""), "facts.rights", "申请表"),
        row("源程序量", f"{snap['total_lines']} 行" if snap else "",
            "snapshot 实测", "申请表", "须带「行」单位，漏单位为补正高频错"),
        row("编程语言", "、".join(snap["languages"]) if snap else "",
            "snapshot 派生", "申请表"),
        row("软件主要功能", fn.get("main_function", ""), "facts.functions",
            "申请表", "字数口径为动态字段，递交当日复核当期表单"),
        row("开发硬件环境", env.get("dev_hardware", ""), "facts.environment",
            "申请表"),
        row("开发操作系统", env.get("dev_os", ""), "facts.environment",
            "申请表"),
        row("开发工具", env.get("dev_tools", ""), "facts.environment",
            "申请表"),
        row("运行硬件环境", env.get("runtime_hardware", ""),
            "facts.environment", "申请表"),
        row("运行操作系统", env.get("runtime_os", ""), "facts.environment",
            "申请表"),
        row("支撑软件环境", env.get("runtime_platform", ""),
            "facts.environment", "申请表"),
    ]
    if code_manifest:
        rows.append(row("源程序鉴别材料页数",
                        f"{code_manifest['constructed_pages']} 页"
                        f"（全量 {code_manifest['full_page_count']} 页）",
                        "render 实测", "材料清单",
                        "页数只作实测登记，不作目标"))
    if doc_manifest:
        rows.append(row("文档鉴别材料页数",
                        f"{doc_manifest['constructed_pages']} 页",
                        "render 实测", "材料清单"))
    return rows
