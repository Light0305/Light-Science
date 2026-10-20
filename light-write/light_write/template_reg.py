"""目标期刊模板核查记录登记（register-template）。

消费对象是核查记录（草案 §四），不是模板文件：记录连同核查日期与哈希
快照进稿件包；稿件语言必须与记录的期刊语言一致（一篇稿一个语言，
模板库范围含中文期刊模板）。
"""

from __future__ import annotations

from pathlib import Path

from .project import FILES, load_package, save_manuscript
from .util import component_hash, dump_json, load_structured
from .validate import Report, check_template_record


class TemplateError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def register_template(root, record_path) -> dict:
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"]
    if manuscript is None:
        raise TemplateError(["稿件包不存在（先 init）"])
    record_path = Path(record_path)
    if not record_path.exists():
        raise TemplateError([f"模板核查记录不存在：{record_path}"])
    record = load_structured(record_path)
    rep = Report()
    check_template_record(record, rep)
    if rep.errors:
        raise TemplateError([f"{i['code']}: {i['message']}" for i in rep.errors])
    group_a = record.get("A") or {}
    journal_language = group_a.get("journal_language")
    if journal_language != manuscript.get("language"):
        raise TemplateError([
            f"模板记录期刊语言 {journal_language} 与稿件语言 "
            f"{manuscript.get('language')} 不一致：一篇稿一个语言，"
            "请改投对应语言的期刊记录或新建对应语言的稿件包"])
    dump_json(root / FILES["template_record"], record)
    record_hash = component_hash(record)
    group_h = record.get("H") or {}
    manuscript["target_journal"] = {
        "template_record_id": group_a.get("record_id"),
        "journal_name": group_a.get("journal_name"),
        "journal_language": journal_language,
        "record_hash": record_hash,
        "verified_at": group_h.get("verified_at"),
        "bundled": group_h.get("bundled"),
        "source_record_path": str(record_path),
    }
    save_manuscript(root, manuscript)
    return {
        "template_record_id": group_a.get("record_id"),
        "journal_name": group_a.get("journal_name"),
        "record_hash": record_hash,
        "warnings": [i["message"] for i in rep.warnings],
    }
