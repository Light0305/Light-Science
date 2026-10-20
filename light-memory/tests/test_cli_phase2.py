"""Phase 2 CLI 冒烟：新子命令经 main() 真跑一轮（候选/检索/配方/
投影/回读/画像/评测/晋升），且成功执行后摘除对应 pending 登记。"""

import json

from light_memory import bench
from light_memory.cli import main
from light_memory import project as project_mod


def test_cli_phase2_end_to_end(tmp_path, capsys):
    world = tmp_path / "world"
    bench.build_mini_world(world)
    a, g, b = (str(world / "proj-a"), str(world / "global"),
               str(world / "proj-b"))

    # 候选：propose（文件给内容）→ list → accept
    content = tmp_path / "cand.json"
    content.write_text(json.dumps({"nomination": {
        "verdict": "store",
        "fact": {"statement": "CLI 候选教训", "fact_type": "lesson",
                 "object_id": "run:R-NEG-a1",
                 "valid_at": "2026-03-01"}}}), encoding="utf-8")
    assert main(["candidate", a, "propose", "--kind", "fact",
                 "--file", str(content), "--nominator", "cli"]) == 0
    out = capsys.readouterr().out
    cid = out.split("：")[1].split("（")[0]
    assert main(["candidate", a, "accept", "--id", cid,
                 "--by", "user"]) == 0
    capsys.readouterr()

    # 检索与配方
    assert main(["recall", a, "MOTA 提升"]) == 0
    assert "命中" in capsys.readouterr().out
    assert main(["recipe", a, "list"]) == 0
    capsys.readouterr()
    assert main(["recipe", a, "set", "--name", "default",
                 "--weights", "fts=1.5", "--by", "user"]) == 0
    capsys.readouterr()

    # 投影 + 回读
    assert main(["project-obsidian", a]) == 0
    capsys.readouterr()
    assert main(["readback", a]) == 0
    capsys.readouterr()

    # 画像
    assert main(["profile", a, "build"]) == 0
    capsys.readouterr()
    assert main(["profile", a, "check"]) == 0
    capsys.readouterr()
    assert main(["stance", a, "--object", "method:tracker-threshold",
                 "--also", b]) == 0
    assert "turkey-b" in capsys.readouterr().out

    # 晋升
    facts = project_mod.load_package(a)["facts"]
    fid = next(f["fact_id"] for f in facts
               if f["fact_type"] == "lesson"
               and "核验版本" in f["statement"])
    assert main(["promote", g, "propose", "--from", a,
                 "--fact-id", fid, "--by", "user"]) == 0
    out = capsys.readouterr().out
    pcid = out.split("：")[1].split("（")[0]
    assert main(["promote", g, "confirm", "--id", pcid,
                 "--by", "user"]) == 0
    capsys.readouterr()
    assert main(["promote", g, "list"]) == 0
    assert "PRM-0001" in capsys.readouterr().out
    assert main(["promote", g, "withdraw", "--promotion-id",
                 "PRM-0001", "--by", "user"]) == 0
    capsys.readouterr()

    # 评测（run 不需要包路径即可跑；带 --path 摘 eval 登记）
    report = tmp_path / "report.json"
    assert main(["bench", "run", "--world", str(world),
                 "--set", "mini", "--out", str(report),
                 "--path", a]) == 0
    capsys.readouterr()
    assert json.loads(report.read_text(encoding="utf-8"))["verdict"] \
        == "not_judged"

    # Phase 2 命令成功后 pending 登记逐件摘除（摘的是被执行命令
    # 的那个包）：A 上跑过的五件已摘除，只剩未在 A 执行的 promote
    pending = project_mod.load_package(a)["memory"]["phase2_pending"]
    assert len(pending) == 1 and pending[0].startswith("promote:")
    gpending = project_mod.load_package(g)["memory"]["phase2_pending"]
    assert not any(p.startswith("promote:") for p in gpending)
    assert len(gpending) == 5
