"""light-patent 小评测集评分器（Q10）。

形态来源（只借形态、不复制数据）：IPBench 的 DOK 四级分层；
patent-bench 的引证真值形态（判定点对错有客观锚，不靠印象分）。
案例与参考答案全部自建脱敏，见 cases.jsonl / reference_answers.jsonl。

评分：decision 须与 expected.decision 完全一致；expected.required
关键词须全部出现在答案 points 拼接文本中；expected.forbidden
关键词一个不许出现。三者全合才算该例通过。

用法：python run_eval.py [--answers reference_answers.jsonl]
退出码：全过 0，否则 1。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_jsonl(path):
    return [json.loads(line) for line in
            Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def score_answers(cases, answers) -> dict:
    by_id = {a["case_id"]: a for a in answers}
    rows = []
    for case in cases:
        exp = case["expected"]
        ans = by_id.get(case["case_id"])
        failures = []
        if ans is None:
            failures.append("缺答案")
        else:
            if ans.get("decision") != exp["decision"]:
                failures.append(
                    f"decision 实得 {ans.get('decision')!r}，"
                    f"应为 {exp['decision']!r}")
            text = " ".join(ans.get("points") or [])
            for kw in exp.get("required") or []:
                if kw not in text:
                    failures.append(f"缺必备要点：{kw}")
            for kw in exp.get("forbidden") or []:
                if kw in text or kw == ans.get("decision"):
                    failures.append(f"命中禁用表述：{kw}")
        rows.append({"case_id": case["case_id"],
                     "dok_level": case["dok_level"],
                     "passed": not failures, "failures": failures})
    passed = sum(1 for r in rows if r["passed"])
    return {"total": len(rows), "passed": passed,
            "pass_rate": passed / len(rows) if rows else 0.0,
            "rows": rows}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(HERE / "cases.jsonl"))
    parser.add_argument("--answers",
                        default=str(HERE / "reference_answers.jsonl"))
    args = parser.parse_args(argv)
    report = score_answers(_load_jsonl(args.cases),
                           _load_jsonl(args.answers))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
