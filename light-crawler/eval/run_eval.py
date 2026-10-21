"""抽取双档对照回归运行器：本地 fixture 页 + 人工标注，无网络。

对 annotations.json 里每页分别跑 html_text_v1（轻档）与
trafilatura_v1（深档），机械核查：标题命中、元数据在场、正文要点
召回（key_points）、噪声泄漏（noise_points 在场记泄漏）。结果写
results.json，并生成 REPORT.md（双档对照表）。判定口径见
annotations.json 的 note；本运行器只读 fixture、只写本目录产物。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG = ROOT.parent
sys.path.insert(0, str(PKG))

from light_crawler import extractors, storage  # noqa: E402

PROFILES = (extractors.LIGHT_PROFILE, extractors.DEEP_PROFILE)


def collapse(s: str | None) -> str:
    return " ".join((s or "").split())


def check_page(cleaned: dict, ann: dict) -> dict:
    text = collapse(cleaned.get("text"))
    title = collapse(cleaned.get("title"))
    meta_blob = collapse(" ".join(str(v) for v in
                                  (cleaned.get("metadata") or {}).values()))
    key_hit = [k for k in ann["key_points"] if collapse(k) in text]
    noise_hit = [n for n in ann["noise_points"] if collapse(n) in text]
    meta_hit = [m for m in ann["metadata_contains"] if collapse(m) in meta_blob]
    return {
        "title_ok": collapse(ann["title_contains"]) in title,
        "metadata_found": meta_hit,
        "metadata_total": len(ann["metadata_contains"]),
        "key_found": key_hit,
        "key_total": len(ann["key_points"]),
        "noise_leaked": noise_hit,
        "noise_total": len(ann["noise_points"]),
        "text_chars": len(cleaned.get("text") or ""),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="2026-10-21")
    args = ap.parse_args()
    ann = json.loads((ROOT / "annotations.json").read_text("utf-8"))
    results = {"tag": args.tag, "set": ann["set"],
               "trafilatura_version": extractors.trafilatura_version(),
               "profiles": {}}
    for profile in PROFILES:
        per_page = {}
        agg = {"key_found": 0, "key_total": 0, "noise_leaked": 0,
               "noise_total": 0, "metadata_found": 0, "metadata_total": 0,
               "title_ok": 0, "pages": 0}
        for page in ann["pages"]:
            raw = (ROOT / "pages" / page["file"]).read_bytes()
            cleaned = storage.clean_content(
                raw, "text/html; charset=utf-8", profile=profile)
            chk = check_page(cleaned, page)
            chk["extractor"] = cleaned.get("extractor")
            per_page[page["file"]] = chk
            agg["key_found"] += len(chk["key_found"])
            agg["key_total"] += chk["key_total"]
            agg["noise_leaked"] += len(chk["noise_leaked"])
            agg["noise_total"] += chk["noise_total"]
            agg["metadata_found"] += len(chk["metadata_found"])
            agg["metadata_total"] += chk["metadata_total"]
            agg["title_ok"] += 1 if chk["title_ok"] else 0
            agg["pages"] += 1
        results["profiles"][profile] = {"pages": per_page, "aggregate": agg}
        print(profile, json.dumps(agg, ensure_ascii=False))

    (ROOT / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [
        "# 抽取双档对照报表（标注页回归集 v1）",
        "",
        f"- 运行标签：{args.tag}；trafilatura 版本："
        f"{results['trafilatura_version']}",
        "- 口径：key_points 命中 = 清洗文本空白折叠后子串在场；"
        "noise_points 在场记泄漏；标题/元数据同口径。",
        "",
        "| 档位 | 标题 | 元数据 | 正文要点召回 | 噪声泄漏 |",
        "|---|---|---|---|---|",
    ]
    for profile in PROFILES:
        a = results["profiles"][profile]["aggregate"]
        lines.append(
            f"| {profile} | {a['title_ok']}/{a['pages']} "
            f"| {a['metadata_found']}/{a['metadata_total']} "
            f"| {a['key_found']}/{a['key_total']} "
            f"| {a['noise_leaked']}/{a['noise_total']} |")
    lines += ["", "逐页明细见 results.json（由本运行器生成，勿手改）。", ""]
    (ROOT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote results.json + REPORT.md")


if __name__ == "__main__":
    main()
