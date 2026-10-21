"""自动捕获层 + 内容寻址产物池（总纲三第四批 P1，PLAN §3.3）。

差距原型（bench-methods §2.3.2 / §2.3.3）：Sacred 的 fd 级捕获与
源码快照、MLflow 的系统标签自动抓取均为框架层自动完成；本包此前
git / 环境 / 执行者全靠 spec 声明，产物池只有路径 + sha256 登记、
无内容副本、工具不主动巡检。本模块补两件：

1. **开跑捕获**（run-start 内置）：工具在开跑时实测落账——
   - git 状态：文件级探针直读 .git（HEAD / refs / packed-refs /
     config / index v2），**不起子进程**——本包「规程执行、不托管
     子进程」的口径不变（拍板 ① = C），捕获是只读元数据探针，
     不是执行后端。dirty 只在 index v2 + 跟踪文件全量比对下给
     出，未覆盖形态（无 index / v3+ / 非 git 目录）如实报
     unprobed / 缺席，绝不猜。
   - 环境指纹：OS / 平台 / Python / 主机名 / CPU 数（stdlib 实测）；
   - 执行者身份：OS 用户 + 主机名；
   - 输入文件：spec 声明的 input_files 由工具在开跑时逐个算
     sha256 + 字节数落账（声明给路径、哈希工具实测）；缺失即
     拦开跑（GateError）——声明的输入不存在，不许带病开跑。
   - 命令行：spec 的 command 文本落账，来源标 declared（工具
     不托管子进程，命令文本只能由执行端声明、工具锚定）。
   字段来源逐项标记 provenance：captured（工具实测）/ declared
   （spec 声明）。捕获块整体哈希（capture_hash）钉进 run_started
   事件锚、块自带 start_hash 自洽——事后改捕获记录，校验器以锚
   对账点名。**与 identity_hash 的分工**：identity_hash 仍是
   spec 声明身份（配置 / 代码快照哈希 / 数据版本 / 环境声明，
   开跑冻结、复现判据走它）；捕获块是工具实测的环境证据，
   两者并存对读——声明与实测不符本身即证据，不互相覆盖。

2. **内容寻址产物池**（executions/<exec_id>/artifacts/objects/
   <sha256[:2]>/<sha256>）：run-finish 的 metrics / salvage /
   stdout / stderr 与 artifact add 的产物文件，按内容哈希拷贝
   入池，run 记录以 sha256 + pool_ref 引用；同内容只存一份
   （去重，二次入池先验存量对象哈希完好）；validate 主动巡检
   池对象（存在性 + 字节重哈希与地址一致，见 schema 校验器），
   artifact verify 给全池体检（对象数 / 字节 / 损坏 / 未引用）。

stdout/stderr 的形态如实标注：工具不托管子进程，无从做 fd 级
拦截——执行端把实际输出文件交给 run-finish（--stdout-file /
--stderr-file），工具入池登记；未交时 finish 捕获块明确落
outputs=not_provided，不冒充已捕获（Sacred fd 级形态仍为差距，
见 SKILL 已知边界 4）。
"""

from __future__ import annotations

import getpass
import hashlib
import os
import platform
import re
import shutil
import socket
import struct
from pathlib import Path

from .events import append_event
from .gates import GateError
from .util import component_hash, utcnow

ARTIFACTS_DIRNAME = "artifacts"
OBJECTS_DIRNAME = "objects"

_CHUNK = 1024 * 1024


# ---------- 文件哈希 ----------

def hash_file(path: Path) -> tuple[str, int]:
    """流式 sha256 + 字节数（大文件不整读入内存）。"""
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


# ---------- 内容寻址池 ----------

def pool_object_relpath(sha256: str) -> str:
    """池对象相对执行包目录的路径（内容即地址）。"""
    return f"{ARTIFACTS_DIRNAME}/{OBJECTS_DIRNAME}/{sha256[:2]}/{sha256}"


def pool_put(exec_path: Path, src: Path) -> dict:
    """把 src 的内容按哈希拷入池。返回 {sha256, size, pool_ref,
    deduplicated}。已存在同地址对象时先重哈希验完好（损坏即报错，
    不许拿坏对象顶替新内容），验过即去重不重拷。"""
    sha, size = hash_file(src)
    dest = exec_path / ARTIFACTS_DIRNAME / OBJECTS_DIRNAME / sha[:2] / sha
    deduplicated = False
    if dest.exists():
        have, _ = hash_file(dest)
        if have != sha:
            raise ValueError(
                f"产物池对象损坏：{pool_object_relpath(sha)} 字节重哈希"
                f" {have[:16]}… 与地址 {sha[:16]}… 不符——池内内容已被"
                "改动，拒绝以坏对象登记新产物（先 artifact verify 体检）")
        deduplicated = True
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)
    return {"sha256": sha, "size": size,
            "pool_ref": pool_object_relpath(sha),
            "deduplicated": deduplicated}


def pool_entry_for(exec_path: Path, src: Path, kind: str) -> dict:
    """run 记录用的产物登记条：外部指纹 + 池引用合一。"""
    if not src.exists():
        raise FileNotFoundError(f"登记文件不存在：{src}")
    pooled = pool_put(exec_path, src)
    return {"name": src.name, "path": str(src),
            "sha256": pooled["sha256"], "size": pooled["size"],
            "kind": kind, "pool_ref": pooled["pool_ref"]}


def iter_pool_objects(exec_path: Path) -> list[Path]:
    base = exec_path / ARTIFACTS_DIRNAME / OBJECTS_DIRNAME
    if not base.exists():
        return []
    return sorted(p for p in base.glob("*/*") if p.is_file())


def verify_pool(exec_path: Path) -> dict:
    """全池体检：逐对象重哈希验地址一致 + 扇出目录名与地址前缀
    一致。返回 {objects, bytes, corrupt: [{pool_ref, reason}]}。"""
    corrupt: list[dict] = []
    total = 0
    objects = iter_pool_objects(exec_path)
    for p in objects:
        rel = p.relative_to(exec_path).as_posix()
        sha, size = hash_file(p)
        total += size
        if p.name != sha:
            corrupt.append({"pool_ref": rel,
                            "reason": f"字节重哈希 {sha[:16]}… 与对象地址"
                                      f" {p.name[:16]}… 不符（内容被改动）"})
        elif p.parent.name != sha[:2]:
            corrupt.append({"pool_ref": rel,
                            "reason": f"扇出目录 {p.parent.name} 与地址前缀"
                                      f" {sha[:2]} 不符（对象被挪位）"})
    return {"objects": len(objects), "bytes": total, "corrupt": corrupt}


def referenced_pool_shas(pkg: dict) -> set[str]:
    """全包 run 记录引用到的池对象哈希集（artifacts / metrics_ref /
    salvage 中带 pool_ref 的条目）。"""
    out: set[str] = set()
    for run in (pkg.get("runs") or {}).values():
        obs = run.get("observation") or {}
        entries = list(obs.get("artifacts") or [])
        mr = obs.get("metrics_ref")
        if isinstance(mr, dict):
            entries.append(mr)
        entries.extend((run.get("conclusion") or {}).get("salvage") or [])
        for e in entries:
            if isinstance(e, dict) and e.get("pool_ref"):
                out.add(str(e.get("sha256")))
    return out


# ---------- git 文件级探针（不起子进程） ----------

def _find_git_dir(start: Path) -> Path | None:
    """自 start 逐级上溯找 .git（目录，或 worktree 指针文件）。"""
    try:
        cur = start.resolve()
    except OSError:
        return None
    while True:
        cand = cur / ".git"
        if cand.is_dir():
            return cand
        if cand.is_file():
            try:
                text = cand.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
            m = re.search(r"gitdir:\s*(.+)", text)
            if m:
                target = (cur / m.group(1).strip()).resolve()
                return target if target.is_dir() else None
            return None
        if cur.parent == cur:
            return None
        cur = cur.parent


def _read_ref(git_dir: Path, ref: str) -> str | None:
    f = git_dir / ref
    try:
        if f.exists():
            return f.read_text(encoding="utf-8").strip() or None
        packed = git_dir / "packed-refs"
        if packed.exists():
            for line in packed.read_text(
                    encoding="utf-8", errors="replace").splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
    except OSError:
        return None
    return None


def _read_remote_url(git_dir: Path) -> str | None:
    """从 .git/config 取 remote origin 的 url（手工分节解析，
    不引 configparser——git config 语法与 ini 有出入）。"""
    cfg = git_dir / "config"
    try:
        if not cfg.exists():
            return None
        lines = cfg.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    in_origin = False
    for line in lines:
        s = line.strip()
        if s.startswith("["):
            in_origin = s == '[remote "origin"]'
            continue
        if in_origin:
            m = re.match(r"url\s*=\s*(.+)", s)
            if m:
                return m.group(1).strip()
    return None


def _probe_dirty(git_dir: Path) -> tuple[bool | None, str]:
    """工作树脏否（只认 index v2 + 跟踪文件全量内容比对）：
    逐条读 index 条目（stat + blob sha1 + 相对路径），与工作树
    文件逐个比 blob 哈希；文件缺失即脏。未跟踪文件不计（口径
    落字在 basis）。其余形态如实报 unprobed，不猜。"""
    index = git_dir / "index"
    if not index.exists():
        return None, "no_index（尚无暂存区，无从比对）"
    try:
        data = index.read_bytes()
    except OSError as e:
        return None, f"index_unreadable（{e}）"
    if len(data) < 12 or data[:4] != b"DIRC":
        return None, "index_unparsable（非 DIRC 格式）"
    version, count = struct.unpack(">II", data[4:12])
    if version != 2:
        return None, f"index_v{version}_unsupported（探针只认 v2）"
    worktree = git_dir.parent
    gitdir_file = git_dir / "gitdir"  # 链接工作树：真实工作区路径在此
    if gitdir_file.exists():
        try:
            worktree = Path(gitdir_file.read_text(
                encoding="utf-8", errors="replace").strip()).parent
        except OSError:
            pass
    offset = 12
    dirty = False
    for _ in range(count):
        if offset + 62 > len(data):
            return None, "index_truncated（条目区不完整）"
        entry = data[offset:offset + 62]
        fields = struct.unpack(">10I", entry[:40])
        size = fields[9]
        mode = fields[6]
        blob_sha1 = entry[40:60].hex()
        flags = struct.unpack(">H", entry[60:62])[0]
        name_len = flags & 0x0FFF
        name_start = offset + 62
        if name_len < 0x0FFF:
            name = data[name_start:name_start + name_len].decode(
                "utf-8", errors="replace")
            entry_len = (62 + name_len + 8) // 8 * 8
        else:
            end = data.find(b"\x00", name_start)
            if end < 0:
                return None, "index_truncated（文件名无终止符）"
            name = data[name_start:end].decode("utf-8", errors="replace")
            entry_len = (62 + (end - name_start) + 8) // 8 * 8
        target = worktree / name
        if mode & 0o170000 == 0o160000:
            pass  # gitlink（子模块）：文件级探针不下探子模块状态，不判脏
        elif not target.is_file():
            dirty = True
        else:
            raw = target.read_bytes()
            blob = hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()
            if len(raw) != size or blob != blob_sha1:
                dirty = True
        offset += entry_len
    return dirty, "index_v2_tracked_files（未跟踪文件不计）"


def probe_git(start: Path) -> tuple[dict | None, str | None]:
    """git 状态探针。返回 (block, None) 或 (None, 缺席原因)。
    只读 .git 文件，不起子进程、不写任何东西。"""
    git_dir = _find_git_dir(start)
    if git_dir is None:
        return None, "项目目录不在 git 工作树内（文件级探针未找到 .git）"
    try:
        head = (git_dir / "HEAD").read_text(
            encoding="utf-8", errors="replace").strip()
    except OSError as e:
        return None, f".git/HEAD 不可读（{e}）"
    block: dict = {"repo_root": str(git_dir.parent),
                   "probe": "file_level（直读 .git，不起子进程）"}
    if head.startswith("ref:"):
        ref = head[4:].strip()
        block["branch"] = ref[len("refs/heads/"):] \
            if ref.startswith("refs/heads/") else ref
        block["commit"] = _read_ref(git_dir, ref)
    else:
        block["branch"] = None
        block["commit"] = head or None
    block["remote_url"] = _read_remote_url(git_dir)
    dirty, basis = _probe_dirty(git_dir)
    block["dirty"] = dirty
    block["dirty_probe"] = basis
    return block, None


# ---------- 环境指纹 / 执行者 ----------

def environment_fingerprint() -> dict:
    """工具实测的运行环境指纹（stdlib 可得项；GPU 无通用探针，
    不冒充——GPU 信息仍走 spec 环境声明对读）。"""
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "hostname": socket.gethostname(),
        "cpu_count": os.cpu_count(),
    }


def executor_identity() -> dict:
    try:
        user = getpass.getuser()
    except Exception:  # 无 passwd 条目等环境下 getuser 可抛错
        user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
    return {"user": user, "hostname": socket.gethostname(),
            "provenance": "captured"}


# ---------- 开跑 / 终止捕获 ----------

def build_start_capture(root: Path, run: dict) -> tuple[dict, str]:
    """开跑捕获块 + 其规范化哈希（capture_hash）。
    spec 声明的 input_files 在此逐个实测哈希；缺失即 GateError。"""
    ident = run.get("identity") or {}
    inputs: list[dict] = []
    missing: list[str] = []
    for raw in ident.get("input_files") or []:
        p = Path(str(raw))
        if not p.is_file():
            missing.append(str(raw))
            continue
        sha, size = hash_file(p)
        inputs.append({"name": p.name, "path": str(p), "sha256": sha,
                       "size": size, "provenance": "captured"})
    if missing:
        raise GateError(
            [f"spec 声明的输入文件不存在：{m}（输入由工具在开跑时实测"
             "哈希落账，声明的输入缺失不许带病开跑）" for m in missing])
    git, git_reason = probe_git(root)
    command = ident.get("command")
    block = {
        "captured_at": utcnow(),
        "provenance": "captured",
        "git": git,
        "git_unavailable_reason": git_reason,
        "environment_fingerprint": environment_fingerprint(),
        "executor": executor_identity(),
        "command": {"text": command, "provenance": "declared"}
                   if command else None,
        "inputs": inputs,
    }
    return block, component_hash(block)


def register_artifact(root: Path, exec_id: str, run_id: str,
                      file: Path, *, kind: str = "product",
                      by: str = "") -> dict:
    """把一个 run 产物文件入池并登记进该 run 的观测区 artifacts，
    落 artifact_registered 事件锚。planned（尚无产物）与
    reconciled（终态封账）拒绝登记。"""
    from .project import exec_dir, load_run, save_run
    run = load_run(root, exec_id, run_id)
    status = run.get("status")
    if status == "planned":
        raise GateError([f"run {run_id} 尚未开跑（planned）："
                         "产物登记须在开跑之后"])
    if status == "reconciled":
        raise GateError([f"run {run_id} 已 reconciled（终态封账）："
                         "产物补登记请新开 attempt，不许改终态记录"])
    d = exec_dir(root, exec_id)
    entry = pool_entry_for(d, Path(file), kind)
    run.setdefault("observation", {}).setdefault("artifacts", []).append(entry)
    save_run(root, exec_id, run)
    append_event(d, "artifact_registered", run_id=run_id,
                 payload={"kind": kind, "name": entry["name"],
                          "sha256": entry["sha256"],
                          "pool_ref": entry["pool_ref"],
                          "by": by or "light-experiment artifact add"})
    return entry
