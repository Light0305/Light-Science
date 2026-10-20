"""light-leader 演示驱动：拼装真实登记头的项目并跑 init/status/route/registry。

拼装口径（与 demo-report 同源）：
- 项目骨架由 light-leader init 真生成；
- 各阶段内容只复制各包真实 demo 的登记头与关键交接件（status 的设计
  边界就是只读登记头）；复制时把文件内的机器绝对路径前缀（仓库根的
  绝对路径，由脚本位置推导）改写为仓库根相对路径；
- memory 四账复制自发布版 light-memory 演示世界 proj-a（已相对化）；
- registry-view.json 不由总控生成：先跑一次 light-leader registry
  记录缺失形态，再由 light-memory 自家命令对副本导出，最后总控消费。
可整删 project/ 与 evidence/ 后重跑复现。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]              # light-science 仓库根
PROJ = HERE / "project"
EVID = HERE / "evidence"
BIN = Path(sys.executable).parent
ABS_PREFIX = str(ROOT) + "/"  # 上游登记头里写死的本机仓库绝对路径前缀


def run(cmd, name, expect_fail=False):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    out = (p.stdout or "") + (p.stderr or "")
    (EVID / name).write_text(out, encoding="utf-8")
    ok = (p.returncode != 0) if expect_fail else (p.returncode == 0)
    print(f"[{'OK' if ok else 'FAIL'} rc={p.returncode}] {' '.join(cmd)}")
    if not ok:
        print(out)
        raise SystemExit(1)
    return out


def copy_rel(src: Path, dst: Path):
    """复制文本文件并把机器绝对路径前缀改写为仓库根相对路径。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8")
    dst.write_text(text.replace(ABS_PREFIX, ""), encoding="utf-8")


def copy_tree_rel(src: Path, dst: Path):
    for f in sorted(src.rglob("*")):
        if f.is_file() and f.suffix in (".yaml", ".md", ".json", ".jsonl",
                                        ".csv", ".bib"):
            copy_rel(f, dst / f.relative_to(src))


def main():
    if PROJ.exists():
        shutil.rmtree(PROJ)
    EVID.mkdir(exist_ok=True)
    for old in EVID.glob("*.txt"):
        old.unlink()

    leader = str(BIN / "light-leader")
    memory = str(BIN / "light-memory")

    # 1) init 真建骨架
    run([leader, "init", "project", "--name", "turkey-threshold-prediction",
         "--title", "火鸡异常行为检测：零调参跟踪阈值预测（总控演示拼装）"],
        "01-init.txt")

    # 2) 拼装各包真实登记头
    lit = ROOT / "light-literature/examples/demo-cea/Literature"
    copy_rel(lit / "文献索引.csv", PROJ / "literature/Literature/文献索引.csv")
    copy_rel(lit / "证据表.jsonl", PROJ / "literature/Literature/证据表.jsonl")
    copy_rel(lit / "参考文献.bib", PROJ / "literature/Literature/参考文献.bib")

    c1 = ROOT / ("light-idea/examples/demo-poultry/cards/"
                 "zero-tuning-tracker-thresholds-predicted_77cdb7")
    copy_tree_rel(c1, PROJ / "idea/cards" / c1.name)

    design = ROOT / ("light-design/examples/demo-poultry-design/designs/"
                     "zero-tuning-tracker-thresholds_979ee7")
    copy_tree_rel(design, PROJ / "design/designs" / design.name)

    exp = ROOT / "light-experiment/examples/demo-synthetic/proj/executions"
    for b in ("video-threshold-predict_synth01-b1",
              "video-threshold-predict_synth01-b2"):
        copy_rel(exp / b / "execution.yaml",
                 PROJ / "experiment/executions" / b / "execution.yaml")

    ana = ROOT / "light-analysis/examples/demo-synthetic/analysis-pkg"
    copy_tree_rel(ana, PROJ / "analysis/analysis-pkg")

    sel = ROOT / "light-journal-select/examples/demo-fullrun/selection-pkg"
    copy_rel(sel / "selection.yaml", PROJ / "journal-select/selection.yaml")
    copy_rel(sel / "journal/target/check-record.json",
             PROJ / "journal/target/check-record.json")
    copy_rel(sel / "journal/target/handoff.md",
             PROJ / "journal/target/handoff.md")

    wpkg = ROOT / "light-write/examples/demo-fullrun/manuscript-pkg"
    copy_rel(wpkg / "manuscript.yaml", PROJ / "write/manuscript-pkg/manuscript.yaml")
    copy_rel(wpkg / "claims_register.yaml",
             PROJ / "write/manuscript-pkg/claims_register.yaml")

    copy_rel(ROOT / "light-figure/examples/demo-fullrun/figure-pkg/figure.yaml",
             PROJ / "figure/figure-pkg/figure.yaml")
    copy_rel(ROOT / "light-review/examples/demo-fullrun/review-pkg/review.yaml",
             PROJ / "review/review-pkg/review.yaml")

    mem_src = ROOT / "release/light-memory/examples/demo-fullrun/world/proj-a"
    for f in ("memory.yaml", "objects.jsonl", "events.jsonl", "facts.jsonl",
              "relations.jsonl", "disputes.jsonl", "promotions.jsonl"):
        copy_rel(mem_src / f, PROJ / "memory" / f)

    # 3) registry 缺失形态（总控点名 + 生成方式指针，不自行生成）
    run([leader, "registry", "project"], "02-registry-missing.txt",
        expect_fail=True)

    # 4) 由 light-memory 自家命令对副本导出 registry-view.json
    run([memory, "registry", "project/memory", "export"],
        "03-memory-registry-export.txt")

    # 5) 总控三命令全链
    run([leader, "status", "project"], "04-status.txt")
    run([leader, "route", "project"], "05-route.txt")
    run([leader, "registry", "project"], "06-registry.txt")
    print("演示完成：见 evidence/ 与 demo-report.md")


if __name__ == "__main__":
    main()
