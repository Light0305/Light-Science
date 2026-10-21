"""Obsidian vault 文件层原语（工具层 T1，TOOLING-PLAN §5.1）。

控制层操作的是 vault（视图），不是记忆本体：任何从 vault 流回四账
的内容仍只走 readback 到候选通道，本模块不新开任何入账路径。

纪律：
- frontmatter 改写只做行级外科补丁——只替换目标键所在的行块，
  其余行逐字保留（notesmd-cli 整段重序列化把日期值加引号的教训，
  TOOLING-PLAN §0 P7）。日期值落盘不加引号，注释行不漂移。
- 投影笔记守区标记：机器区（MACHINE_START..END）拒写并指引走
  重投影；frontmatter 只许动登记键白名单之外的键，投影自有键
  （memory_id 等）拒写；标注区与普通笔记全文可写。
- 全部变更先 probe 后 mutate：写前读哈希、写后复读逐字复验，
  回执带前后哈希。
- 删除默认移入 vault 内 .trash 并落 trash-log.jsonl 留痕，不真删。
- obsidian_live_verified 登记字段恒以 false 为默认，只许带齐
  实机冒烟证据（register_live_smoke）置真，证据不齐即拒。
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

import yaml

from . import obsidian as obsidian_mod
from .util import sha256_file, sha256_text, utcnow

VAULT_DIR = obsidian_mod.VAULT_DIR
TRASH_DIR = ".trash"
CONTROL_FILE = ".vault-control.json"

#: 投影自有 frontmatter 键：控制层对投影笔记拒写这些键。
PROJECTION_FM_KEYS = frozenset({
    "light_memory_object", "light_memory_view", "memory_id",
    "object_type", "obj_type", "stage", "status", "source_pkg",
    "valid_from", "invalid_at", "tags",
})

_FM_KEY_RE = re.compile(r"^([A-Za-z0-9_.\-]+):(?:[ \t]+(.*))?$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class VaultError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 路径

def resolve_vault(path) -> Path:
    """把记忆项目根或 vault 目录本身解析为 vault 路径。

    记忆项目根下 vault 在 <root>/obsidian；直接给 vault 目录
    （含 .md 或 .obsidian，或尚不存在的 obsidian 名目录）则用其
    本身。不存在时返回预期路径（由写操作创建）。
    """
    p = Path(path)
    sub = p / VAULT_DIR
    if sub.is_dir():
        return sub
    if p.is_dir() and (any(p.glob("*.md")) or (p / ".obsidian").exists()
                       or p.name == VAULT_DIR):
        return p
    return sub


def _note_path(vault: Path, rel: str) -> Path:
    rel = (rel or "").strip()
    if not rel:
        raise VaultError(["笔记路径为空"])
    pure = Path(rel)
    if pure.is_absolute() or ".." in pure.parts:
        raise VaultError([f"笔记路径越界：{rel}"])
    if pure.suffix != ".md":
        raise VaultError([f"笔记路径须以 .md 结尾：{rel}"])
    if pure.parts and pure.parts[0] == TRASH_DIR:
        raise VaultError([f".trash 内笔记不经普通命令面操作：{rel}"])
    return vault / pure


def list_notes(vault) -> list:
    """vault 内全部笔记相对路径（排序，排除 .trash 与点目录）。"""
    vault = Path(vault)
    if not vault.exists():
        return []
    out = []
    for p in vault.rglob("*.md"):
        rel = p.relative_to(vault)
        if any(part.startswith(".") for part in rel.parts):
            continue
        out.append(rel.as_posix())
    return sorted(out)


def read_note(vault, rel: str) -> str:
    path = _note_path(Path(vault), rel)
    if not path.exists():
        raise VaultError([f"笔记不存在：{rel}"])
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 状态

def _default_control_state() -> dict:
    return {"kind": "light-memory/vault-control", "version": "1.0",
            "obsidian_live_verified": False, "live_verification": None}


def load_control_state(vault) -> dict:
    p = Path(vault) / CONTROL_FILE
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = None
        if isinstance(data, dict):
            state = _default_control_state()
            state.update(data)
            return state
    return _default_control_state()


def register_live_smoke(vault, evidence: dict) -> dict:
    """登记实机冒烟证据并置 obsidian_live_verified 为真。

    只许用户机器一致性套件（TOOLING-PLAN §5.3）跑通后调用本函数：
    证据须齐 surface / app_version / suite / by 四项，缺一即拒，
    本批任何命令面不调用它，登记字段默认恒 false。
    """
    required = ("surface", "app_version", "suite", "by")
    gaps = [f"冒烟证据缺字段：{k}" for k in required
            if not str((evidence or {}).get(k) or "").strip()]
    if (evidence or {}).get("surface") not in (
            "official-cli", "local-rest-api"):
        gaps.append("冒烟证据 surface 须为 official-cli 或 "
                    "local-rest-api")
    if gaps:
        raise VaultError(gaps)
    vault = Path(vault)
    vault.mkdir(parents=True, exist_ok=True)
    state = load_control_state(vault)
    state["obsidian_live_verified"] = True
    state["live_verification"] = {
        "surface": evidence["surface"],
        "app_version": evidence["app_version"],
        "suite": evidence["suite"], "by": evidence["by"],
        "registered_at": utcnow(),
    }
    (vault / CONTROL_FILE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return state


def probe_vault(vault) -> dict:
    vault = Path(vault)
    state = load_control_state(vault)
    return {
        "vault": str(vault), "exists": vault.exists(),
        "file_layer": "available", "notes": len(list_notes(vault)),
        "obsidian_live_verified":
            bool(state.get("obsidian_live_verified")),
        "live_surfaces": "not-implemented（T3 批：livecli / restapi / "
                         "uri 适配器未施工，本批不探测活面）",
    }


# ---------------------------------------------------------------- 区分隔

def is_projected(vault, rel: str, text: str) -> bool:
    """投影笔记判定：含机器区标记，或在 .projection.json 登记内。"""
    if obsidian_mod.MACHINE_START in (text or ""):
        return True
    manifest = Path(vault) / obsidian_mod.MANIFEST_FILE
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {}
        if rel in (data.get("notes") or {}):
            return True
    return False


def _machine_zone_lines(text: str):
    """机器区行区间 [start, end]（含标记行）；无机器区返回 None。"""
    lines = text.split("\n")
    start = end = None
    for i, line in enumerate(lines):
        if obsidian_mod.MACHINE_START in line and start is None:
            start = i
        if obsidian_mod.MACHINE_END in line and start is not None:
            end = i
            break
    if start is None:
        return None
    return (start, len(lines) - 1 if end is None else end)


def _guard_zone(vault, rel: str, text: str, span, what: str) -> None:
    zone = _machine_zone_lines(text)
    if zone is None:
        return
    if span is not None and span[0] <= zone[1] and span[1] >= zone[0]:
        raise VaultError([
            f"{what} 落入投影机器区，拒写：{rel}——机器区由四账投影"
            "生成，请改四账后重投影（project-obsidian），或写标注区"])


# ---------------------------------------------------------------- frontmatter 行级补丁

def split_frontmatter(text: str):
    """拆 frontmatter：返回 (fm_lines, body_start_line_index, lines)。

    fm_lines 为 --- 之间的原始行列表（无 frontmatter 时为 None）。
    全程按行处理，不重序列化任何内容。
    """
    lines = (text or "").split("\n")
    if not lines or lines[0].strip() != "---":
        return None, 0, lines
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], i + 1, lines
    return None, 0, lines


def fm_parse(text: str) -> dict:
    """只读解析 frontmatter 为 dict（解析不落盘，无保真问题）。"""
    fm_lines, _, _ = split_frontmatter(text)
    if fm_lines is None:
        return {}
    data = yaml.safe_load("\n".join(fm_lines)) or {}
    return data if isinstance(data, dict) else {}


def fm_get(text: str, key: str):
    """取 frontmatter 键值：返回 (found, value)。"""
    data = fm_parse(text)
    return (key in data), data.get(key)


def _needs_quote(s: str) -> bool:
    if s == "" or s != s.strip():
        return True
    if _ISO_DATE_RE.match(s):
        return False  # 日期串保持裸写，Obsidian 识别为日期（P7 教训）
    if re.match(r"^(true|false|null|~|yes|no|on|off)$", s, re.I):
        return True  # YAML 1.1 布尔同义词，裸写会被读成布尔
    if re.match(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$", s):
        return True  # 数字形字符串须引号保型
    if s[0] in "-?:,[]{}#&*!|>'\"%@`":
        return True
    if ": " in s or " #" in s or s.endswith(":") or "\t" in s:
        return True
    return False


def render_scalar(value) -> str:
    """标量到 YAML 行内文本的渲染：日期裸写、需保型者双引号。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value)
    if _needs_quote(s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _render_key_lines(key: str, value) -> list:
    if isinstance(value, dict):
        raise VaultError([f"键 {key} 的值是嵌套映射，行级补丁不支持"
                          "（整段重写会破坏其余键的原始格式）"])
    if isinstance(value, (list, tuple)):
        lines = [f"{key}:"]
        for item in value:
            if isinstance(item, (dict, list, tuple)):
                raise VaultError([f"键 {key} 的列表项含复合结构，"
                                  "行级补丁不支持"])
            lines.append(f"  - {render_scalar(item)}")
        return lines
    return [f"{key}: {render_scalar(value)}".rstrip()]


def _key_span(fm_lines: list, key: str):
    """定位键在 fm 行中的行块 [start, end]（含缩进续行）。"""
    for i, line in enumerate(fm_lines):
        m = _FM_KEY_RE.match(line)
        if m and m.group(1) == key:
            j = i + 1
            while j < len(fm_lines) and fm_lines[j].strip() and \
                    fm_lines[j][0] in " \t":
                j += 1
            return (i, j - 1)
    return None


def fm_set_in_text(text: str, key: str, value) -> str:
    """在文本内行级设置 frontmatter 键，返回新文本（纯函数）。

    只动目标键的行块：标量替换该行（保留行内注释）、块列表连同
    其条目行整体替换、缺键插到结束 --- 之前；其余每一行逐字
    不动。目标键现值为嵌套映射时拒（点名）。
    """
    if not re.match(r"^[A-Za-z0-9_.\-]+$", key or ""):
        raise VaultError([f"frontmatter 键名非法：{key}"])
    fm_lines, body_start, lines = split_frontmatter(text)
    new_key_lines = _render_key_lines(key, value)
    if fm_lines is None:
        return "\n".join(["---"] + new_key_lines + ["---"] +
                         lines)
    span = _key_span(fm_lines, key)
    if span is None:
        merged = fm_lines + new_key_lines
    else:
        start, end = span
        block = fm_lines[start:end + 1]
        nested = [ln for ln in block[1:]
                  if ln.strip() and not ln.lstrip().startswith("- ")
                  and ":" in ln]
        if nested:
            raise VaultError([
                f"键 {key} 现值为嵌套映射，行级补丁拒动"
                "（请人工编辑该键，其余键不受影响）"])
        # 保留旧标量行上的行内注释（旧值无引号时才安全切分）
        if len(block) == 1 and not isinstance(value, (list, tuple)):
            old = block[0]
            m = re.match(r"^[^:\n]+:[ \t]+[^\"\n]*?[ \t]+(#.*)$", old)
            if m and len(new_key_lines) == 1:
                new_key_lines = [new_key_lines[0] + "  " + m.group(1)]
        merged = fm_lines[:start] + new_key_lines + fm_lines[end + 1:]
    return "\n".join(["---"] + merged + ["---"] +
                     lines[body_start:])


# ---------------------------------------------------------------- 变更骨架

def _mutate(vault: Path, rel: str, transform, what: str) -> dict:
    """先 probe 后 mutate：读旧文、变换、落盘、复读逐字复验。"""
    path = _note_path(vault, rel)
    if not path.exists():
        raise VaultError([f"笔记不存在：{rel}"])
    old = path.read_text(encoding="utf-8")
    before = sha256_text(old)
    new = transform(old)
    path.write_text(new, encoding="utf-8")
    after_text = path.read_text(encoding="utf-8")
    if after_text != new:
        raise VaultError([f"{what} 落盘复验不一致：{rel}"])
    return {"path": rel, "before_hash": before,
            "after_hash": sha256_text(after_text),
            "changed": after_text != old}


# ---------------------------------------------------------------- 笔记操作

def create_note(vault, rel: str, content: str = "",
                frontmatter: dict = None, template: str = None,
                overwrite: bool = False) -> dict:
    vault = Path(vault)
    path = _note_path(vault, rel)
    if path.exists() and not overwrite:
        raise VaultError([f"笔记已存在（加 --overwrite 才许覆盖）："
                          f"{rel}"])
    body = ""
    if template:
        tpath = _note_path(vault, template)
        if not tpath.exists():
            raise VaultError([f"模板不存在：{template}"])
        body = tpath.read_text(encoding="utf-8")
        stem = Path(rel).stem
        body = body.replace("{{title}}", stem)
        body = body.replace("{{date}}", date.today().isoformat())
        body = body.replace("{{time}}",
                            datetime.now().strftime("%H:%M"))
    if content:
        body = (body.rstrip("\n") + "\n\n" + content) if body \
            else content
    if not body.endswith("\n"):
        body += "\n"
    if frontmatter:
        for key in reversed(list(frontmatter.keys())):
            body = fm_set_in_text(body, key, frontmatter[key])
    vault.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if path.read_text(encoding="utf-8") != body:
        raise VaultError([f"建笔记落盘复验不一致：{rel}"])
    return {"path": rel, "created": True,
            "after_hash": sha256_text(body)}


def append_note(vault, rel: str, addition: str) -> dict:
    """追加内容：投影笔记追加进标注区内（区外追加会在重投影时
    被静默丢弃，故不许落在文末标记之外）；普通笔记追加到文末。"""
    vault = Path(vault)

    def _add(old: str) -> str:
        add = addition if addition.endswith("\n") else addition + "\n"
        if obsidian_mod.ANNO_END in old:
            lines = old.split("\n")
            for i, line in enumerate(lines):
                if obsidian_mod.ANNO_END in line:
                    return "\n".join(lines[:i] + add.split("\n")[:-1]
                                     + lines[i:])
        text = old if old.endswith("\n") else old + "\n"
        return text + add

    return _mutate(vault, rel, _add, "append")


def _heading_lines(lines: list):
    out = []
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})[ \t]+(.*?)[ \t]*$", line)
        if m:
            title = re.sub(r"[ \t]+#+$", "", m.group(2)).strip()
            out.append((i, len(m.group(1)), title))
    return out


def find_section(lines: list, heading_path: str):
    """按标题路径定位段落正文行区间 (body_start, body_end, level)。

    路径以 / 分隔多级标题；正文区间不含标题行本身，止于同级或
    更高层级标题之前。找不到返回 None。
    """
    parts = [p.strip() for p in heading_path.split("/") if p.strip()]
    if not parts:
        return None
    headings = _heading_lines(lines)
    lo, level_floor = 0, 0
    target = None
    for depth, part in enumerate(parts):
        found = None
        for idx, (line_no, level, title) in enumerate(headings):
            if line_no < lo:
                continue
            if depth and level <= level_floor:
                break
            if title == part:
                found = (line_no, level)
                next_lo = len(lines)
                for line_no2, level2, _ in headings[idx + 1:]:
                    if level2 <= level:
                        next_lo = line_no2
                        break
                lo, level_floor = line_no + 1, level
                target = (line_no + 1, next_lo, level)
                break
        if found is None:
            return None
    return target


def patch_section(vault, rel: str, heading_path: str, new_body: str,
                  mode: str = "replace") -> dict:
    vault = Path(vault)
    if mode not in ("replace", "append"):
        raise VaultError([f"patch 模式只许 replace / append：{mode}"])

    def _patch(old: str) -> str:
        lines = old.split("\n")
        sec = find_section(lines, heading_path)
        if sec is None:
            raise VaultError([f"标题路径不存在：{heading_path}"
                              f"（笔记 {rel}）"])
        start, end, _ = sec
        _guard_zone(vault, rel, old, (start, end - 1), "patch")
        body_lines = new_body.split("\n")
        if body_lines and body_lines[-1] == "":
            body_lines = body_lines[:-1]
        if mode == "replace":
            merged = lines[:start] + body_lines + lines[end:]
        else:
            merged = lines[:end] + body_lines + lines[end:]
        result = "\n".join(merged)
        return result if result.endswith("\n") else result + "\n"

    receipt = _mutate(vault, rel, _patch, "patch")
    receipt["heading"] = heading_path
    receipt["mode"] = mode
    return receipt


def fm_set_note(vault, rel: str, key: str, value) -> dict:
    vault = Path(vault)
    path = _note_path(vault, rel)
    if not path.exists():
        raise VaultError([f"笔记不存在：{rel}"])
    text = path.read_text(encoding="utf-8")
    if key in PROJECTION_FM_KEYS and \
            is_projected(vault, rel, text):
        raise VaultError([
            f"键 {key} 是投影自有键，对投影笔记拒写：{rel}"
            "——请改四账后重投影，不要在视图层改投影属性"])
    return _mutate(vault, rel,
                   lambda old: fm_set_in_text(old, key, value),
                   "fm set")


def search_vault(vault, query: str, field: str = None,
                 limit: int = 200) -> dict:
    """全文 + frontmatter 字段检索（自建扫描，规模内够用）。

    field 给定时只查该 frontmatter 键的值（含列表项）；否则逐
    行全文子串匹配。结果带文件与行号，超限点名 truncated。
    """
    vault = Path(vault)
    if not (query or "").strip():
        raise VaultError(["搜索词为空"])
    hits = []
    for rel in list_notes(vault):
        text = (vault / rel).read_text(encoding="utf-8")
        if field:
            found, value = fm_get(text, field)
            values = value if isinstance(value, list) else [value]
            if found and any(query in str(v) for v in values):
                hits.append({"path": rel, "line": None,
                             "text": f"{field}: {value}"})
            continue
        for i, line in enumerate(text.split("\n"), 1):
            if query in line:
                hits.append({"path": rel, "line": i,
                             "text": line.strip()[:200]})
    return {"query": query, "field": field,
            "hits": hits[:limit], "count": len(hits),
            "truncated": len(hits) > limit}


def daily_note(vault, on: date = None) -> dict:
    """按 .obsidian/daily-notes.json 的文件夹/格式算当日笔记。

    配置缺失时用默认（vault 根、YYYY-MM-DD）并在回执点名；
    格式只支持 YYYY/MM/DD 三个令牌的组合。缺则建（带日期标题）。
    """
    vault = Path(vault)
    cfg_path = vault / ".obsidian" / "daily-notes.json"
    folder, fmt, source = "", "YYYY-MM-DD", "default"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except ValueError:
            cfg = {}
        folder = (cfg.get("folder") or "").strip("/")
        fmt = cfg.get("format") or fmt
        source = "config"
    bad = [run for run in re.findall(r"[A-Za-z]+", fmt)
           if run not in ("YYYY", "MM", "DD")]
    if bad:
        raise VaultError([f"日记格式含不支持的令牌：{fmt}"
                          "（只支持 YYYY/MM/DD 组合）"])
    day = on or date.today()
    name = fmt.replace("YYYY", f"{day.year:04d}") \
              .replace("MM", f"{day.month:02d}") \
              .replace("DD", f"{day.day:02d}")
    rel = f"{folder}/{name}.md" if folder else f"{name}.md"
    path = _note_path(vault, rel)
    created = False
    if not path.exists():
        receipt = create_note(vault, rel,
                              content=f"# {day.isoformat()}\n")
        created = True
    return {"path": rel, "created": created, "format": fmt,
            "config_source": source}


def delete_note(vault, rel: str) -> dict:
    """留痕删除：移入 vault/.trash 并记 trash-log.jsonl，不真删。"""
    vault = Path(vault)
    path = _note_path(vault, rel)
    if not path.exists():
        raise VaultError([f"笔记不存在：{rel}"])
    digest = sha256_file(path)
    dest = vault / TRASH_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        stamp = datetime.now().strftime("%H%M%S")
        dest = dest.with_name(dest.stem + f"-{stamp}" + dest.suffix)
    path.rename(dest)
    log = vault / TRASH_DIR / "trash-log.jsonl"
    entry = {"path": rel, "trashed_to": dest.relative_to(vault)
             .as_posix(), "sha256": digest, "at": utcnow()}
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"path": rel, "trashed_to": entry["trashed_to"],
            "sha256": digest}
