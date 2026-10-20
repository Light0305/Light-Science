"""init：生成标准项目骨架（目录 + project.yaml 登记头 + 项目 README）。

只建骨架，不代跑任何阶段包的 init：各包在自己的阶段目录里用自家命令
建包（如在 literature/ 下跑 light-literature 的项目初始化）。骨架已
存在 project.yaml 时拒绝覆盖。
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .layout import PIPELINE, SCAFFOLD_DIRS, STAGES
from .util import dump_yaml, today

PROJECT_FILE = "project.yaml"

_README = """# {title}

Light-Science 科研项目（总控 light-leader 登记）。

## 目录

| 目录 | 阶段 | 说明 |
|---|---|---|
{rows}
| journal/target/ | 选刊交接落点 | light-journal-select 定刊 handoff 的模板与作者指南（仅本地使用） |
| memory/ | light-memory | 跨阶段沉淀（四账 + Obsidian 投影），由 light-memory 在此建包 |

## 用法

- 看全项目状态：`light-leader status .`
- 问下一步：`light-leader route .`
- 看对象注册统一视图：`light-leader registry .`
- 每阶段的内部规程见对应技能的 SKILL.md；总控规程见 light-leader SKILL.md。
"""


def init_project(root, name: str, title: str = "", goal: str = "") -> Path:
    """在 root 建骨架；已存在 project.yaml 则抛 FileExistsError。"""
    root = Path(root)
    head = root / PROJECT_FILE
    if head.exists():
        raise FileExistsError(f"项目登记头已存在，拒绝覆盖：{head}")
    for d in SCAFFOLD_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    stages = []
    for sid in PIPELINE + ("memory",):
        spec = STAGES[sid]
        stages.append({
            "stage": sid,
            "skill": spec["skill"],
            "dir": spec["dir"],
            "carrier": spec["carrier"],
        })
    data = {
        "kind": "light-leader/project",
        "version": "1.0",
        "leader_version": __version__,
        "name": name,
        "title": title or name,
        "goal": goal,
        "created_at": today(),
        "stages": stages,
    }
    dump_yaml(head, data)
    rows = "\n".join(
        f"| {STAGES[s]['dir']}/ | {STAGES[s]['skill']} | {STAGES[s]['carrier']} |"
        for s in PIPELINE)
    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(_README.format(title=title or name, rows=rows),
                          encoding="utf-8")
    return head


def load_project_head(root):
    """读 project.yaml（若有）；无则返回 None（扫描不依赖登记头）。"""
    from .util import load_yaml
    return load_yaml(Path(root) / PROJECT_FILE)
