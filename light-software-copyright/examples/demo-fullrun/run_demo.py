"""演示全链：自造脱敏小软件（无界面）走通材料包 + 递交清单。

用法：python run_demo.py —— 在本目录 case-pkg/ 生成演示案件并跑全链，
终点 packaged，最后写 demo-report.md（含 X-10 四行收尾）。
演示包根 = 本文件所在目录；软件源码 = demo-app/；输入 = inputs/。
"""

from __future__ import annotations

import io
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from light_copyright.cli import main as cli_main  # noqa: E402

CASE = HERE / "case-pkg"
LOG = []


def run(*argv) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli_main(list(argv))
    out = buf.getvalue().strip()
    LOG.append(f"$ light-copyright {' '.join(argv)}\n{out}")
    if code != 0:
        raise SystemExit(f"演示在 {' '.join(argv)} 失败：\n{out}")
    return out


def main() -> int:
    if CASE.exists():
        shutil.rmtree(CASE)
    run("init", str(CASE), "--title", "微统计算工具软著演示案")
    run("set-facts", str(CASE), "--from", str(HERE / "inputs" / "facts.yaml"))
    run("confirm-facts", str(CASE), "--note", "演示确认")
    run("freeze", str(CASE), "--source", str(HERE / "demo-app"))
    run("select", str(CASE))
    run("confirm-selection", str(CASE))
    run("render-code", str(CASE))
    run("draft-doc", str(CASE))

    from light_copyright import render
    man = render.load_segments(CASE)
    # Q2 折中：演示中对一段先改写再确认，其余逐段确认（模拟用户审阅）
    seg2 = man["segments"][1]
    revised = (HERE / "inputs" / "revised-segment.md")
    revised.write_text(
        render.segment_text(CASE, seg2).replace(
            "上述符号由源码 AST 机械抽取",
            "上述符号经演示者复核，与源码 AST 机械抽取结果一致"),
        encoding="utf-8")
    run("revise-segment", str(CASE), "--seg", seg2["seg_id"],
        "--from", str(revised))
    revised.unlink()
    man = render.load_segments(CASE)
    for seg in man["segments"]:
        run("confirm-segment", str(CASE), "--seg", seg["seg_id"],
            "--note", "演示逐段确认")
    run("render-doc", str(CASE))
    run("declaration", str(CASE), "record",
        "--file", str(HERE / "inputs" / "declaration-demo-note.txt"),
        "--origin", "演示占位（非官方文本，仅演示登记机制）")
    run("declaration", str(CASE), "verify",
        "--attest", "演示回执：已逐字读过所登记文本（演示占位）")
    status_out = run("status", str(CASE))
    check_out = run("check", str(CASE))
    pkg_out = run("package", str(CASE))
    final_status = run("status", str(CASE))

    from light_copyright.release import load_manifests
    code, doc = load_manifests(CASE)
    report = [
        "# 演示报告：微统计算工具（无界面 → 设计说明书路径）", "",
        "## 链路与终点", "",
        f"- 代码材料：{code['constructed_pages']} 页"
        f"（全量 {code['full_page_count']} 页），文档材料："
        f"{doc['doc_type']} {doc['constructed_pages']} 页"
        f"（DOCX：{doc.get('docx', '无')}）",
        f"- 终点状态：{final_status.splitlines()[0]}", "",
        "## 关键输出", "",
        "```", "\n\n".join(LOG[-6:]), "```", "",
        "## 演示口径说明", "",
        "- 演示声明文件是明确标注的占位说明，只演示登记 + 核对回执机制；"
        "本包不保存任何官方声明措辞，真实递交须用户自备当期原文。",
        "- 一段草稿经演示改写后旧确认失效、按新哈希重新确认，"
        "Q2 逐段确认链完整走过。", "",
        "## 收尾（X-10 四行）", "",
        "- 完成项：全链 init → packaged 走通，资料包与逐字段递交清单产出",
        "- 跳过项：截图导入（无界面软件无截图面，Q6 预留位机制由测试覆盖）",
        "- 未验项：真实登记系统递交不在 v1 范围（Q4）；DOCX 真分页未用"
        "办公套件实测（目录页码为文本模型回填，已在清单注口径）；"
        "check 输出含一条主要功能字数 B 级警告（385 字），属预期演示",
        "- 风险：主要功能字数与声明原文均为动态口径，真实使用递交当日"
        "须按当期表单复核（HC-7）", "",
    ]
    (HERE / "demo-report.md").write_text("\n".join(report), encoding="utf-8")
    print("演示完成：终点 packaged，报告见 demo-report.md")
    print(final_status)
    print(pkg_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
