"""Obsidian 官方 CLI 适配器（工具层 T3 增强面一，TOOLING-PLAN §5.1）。

官方 `obsidian` 命令（随 Obsidian 1.12 安装器，须 1.12.7+ 启用并
注册 CLI，且应用运行中）补文件层没有的三件：活索引的
backlinks/unresolved、应用模板引擎、官方 move/rename 链更新。

定位与纪律：
- **增强面，默认主路仍是文件层**（vaultio）。本适配器只在探测到
  命令可用且版本达标时才可启用；探测不到、版本过低、应用未运行
  一律点名降级到文件层，不许报错中断文件层流程，更不许假装
  活面可用——每次调用的回执都带 surface=official-cli 与实测
  结果，失败以 LiveCliError 点名（命令、退出码、stderr 摘录）。
- 执行器可注入：runner(argv, timeout) -> (rc, stdout, stderr)。
  默认 runner 走 subprocess（参数以 argv 列表传递、无 shell，
  parameter=value 拼装不存在引号转义面）；测试注入替身验解析
  与降级，VM 内不真跑官方 CLI（无 Obsidian 活应用）。
- 验证等级：本模块的输出形态按官方帮助页与 kepano/obsidian-skills
  的 obsidian-cli 技能（本地克隆实读）建模，属**夹具级**；
  `obsidian_live_verified` 不因本模块存在而置真，实机冒烟
  （22-user-machine/checklist 第 4 项）回填真品输出后另行登记。
- 内容不进回执：create/append 的 content 只记 sha256 与字符数，
  回执与报错不落笔记正文。
"""

from __future__ import annotations

import re
import shutil
import subprocess

from .util import sha256_text

SURFACE = "official-cli"
MIN_VERSION = (1, 12, 7)
FALLBACK = "file-layer"
DEFAULT_TIMEOUT = 15.0

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class LiveCliError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 执行器

def find_binary():
    """PATH 上找 obsidian 命令；无则 None（整面不可用的第一形态）。"""
    return shutil.which("obsidian")


def default_runner():
    """subprocess 执行器：argv 列表直传、无 shell、无字符串拼装。"""
    def _run(argv, timeout):
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    return _run


def _invoke(runner, argv, timeout=DEFAULT_TIMEOUT):
    """执行一条 obsidian 命令，非零退出/超时/二进制缺失都点名。"""
    try:
        rc, out, err = runner(argv, timeout)
    except FileNotFoundError:
        raise LiveCliError([
            f"obsidian 命令不可用（{argv[0]} 不在 PATH）：活面降级，"
            f"请走文件层（{FALLBACK}）"])
    except subprocess.TimeoutExpired:
        raise LiveCliError([
            f"obsidian {' '.join(argv[1:3])} 超时（{timeout}s）："
            "Obsidian 可能未运行或无响应，活面降级走文件层"])
    except OSError as exc:
        raise LiveCliError([f"obsidian 命令执行失败：{exc}"])
    if rc != 0:
        detail = (err or out or "").strip().split("\n")[0][:200]
        raise LiveCliError([
            f"obsidian {' '.join(argv[1:])} 退出码 {rc}：{detail}"
            "（应用未运行/未注册 CLI/vault 未打开时为此形态）"])
    return out


def _argv(vault, command, params):
    """参数拼装：vault= 定向恒为第一参数，其余 parameter=value。"""
    argv = ["obsidian"]
    if vault:
        argv.append(f"vault={vault}")
    argv.append(command)
    argv.extend(params)
    return argv


def _receipt(command, params, extra=None):
    """调用回执：标注执行面；content 只留哈希与长度，不落正文。"""
    safe = {}
    for item in params:
        if item.startswith("content="):
            body = item[len("content="):]
            safe["content"] = {"sha256": sha256_text(body),
                               "chars": len(body)}
        elif "=" in item:
            key, value = item.split("=", 1)
            safe[key] = value
        else:
            safe[item] = True
    receipt = {"surface": SURFACE, "command": command,
               "params": safe}
    if extra:
        receipt.update(extra)
    return receipt


# ---------------------------------------------------------------- 探测

def parse_version(text):
    """从 version 命令输出解析语义版本；解析不出返回 None。"""
    m = _VERSION_RE.search(text or "")
    if not m:
        return None
    return tuple(int(g) for g in m.groups())


def probe_cli(runner=None, vault=None, timeout=DEFAULT_TIMEOUT):
    """探测官方 CLI 面：命令在否、版本是否达标、目标 vault 可达否。

    永不抛错：一切失败收敛为 status + reason 点名，fallback 恒为
    文件层。status 取值 available / unavailable / too-old / error。
    """
    base = {"surface": SURFACE, "fallback": FALLBACK,
            "verified": False}
    if runner is None:
        if find_binary() is None:
            return {**base, "status": "unavailable",
                    "reason": "PATH 上未找到 obsidian 命令"
                              "（未装 Obsidian 1.12.7+ 安装器，"
                              "或未在设置内启用并注册 CLI）"}
        runner = default_runner()
    try:
        out = _invoke(runner, ["obsidian", "version"], timeout)
    except LiveCliError as exc:
        return {**base, "status": "error", "reason": exc.gaps[0]}
    version = parse_version(out)
    if version is None:
        return {**base, "status": "error",
                "reason": f"version 输出无法解析：{out.strip()[:120]}"}
    version_text = ".".join(str(v) for v in version)
    if version < MIN_VERSION:
        return {**base, "status": "too-old", "version": version_text,
                "reason": f"Obsidian CLI 版本 {version_text} 低于"
                          f"最低要求 {'.'.join(map(str, MIN_VERSION))}，"
                          "活面不启用，降级走文件层"}
    result = {**base, "status": "available", "version": version_text}
    if vault:
        try:
            result["files_total"] = cli_files_total(
                runner, vault=vault, timeout=timeout)
        except LiveCliError as exc:
            return {**base, "status": "error", "version": version_text,
                    "reason": f"目标 vault 不可达：{exc.gaps[0]}"}
    return result


# ---------------------------------------------------------------- 操作

def _target_params(file=None, path=None):
    if file and path:
        raise LiveCliError(["file 与 path 只许给其一"])
    if path:
        return [f"path={path}"]
    if file:
        return [f"file={file}"]
    return []


def cli_files_total(runner, vault=None, timeout=DEFAULT_TIMEOUT):
    """vault 内文件总数（活索引口径）：files total。"""
    out = _invoke(runner, _argv(vault, "files", ["total"]), timeout)
    m = re.search(r"\d+", out or "")
    if not m:
        raise LiveCliError([f"files total 输出无法解析：{out!r:.120}"])
    return int(m.group(0))


def cli_read(runner, file=None, path=None, vault=None,
             timeout=DEFAULT_TIMEOUT):
    params = _target_params(file, path)
    out = _invoke(runner, _argv(vault, "read", params), timeout)
    return {"text": out,
            "receipt": _receipt("read", params)}


def cli_create(runner, name, content=None, template=None, vault=None,
               overwrite=False, silent=True, timeout=DEFAULT_TIMEOUT):
    """建笔记：create name=... （可带 template/overwrite/silent）。"""
    params = [f"name={name}"]
    if content is not None:
        params.append(f"content={content}")
    if template:
        params.append(f"template={template}")
    if overwrite:
        params.append("overwrite")
    if silent:
        params.append("silent")
    out = _invoke(runner, _argv(vault, "create", params), timeout)
    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    created = lines[-1] if lines and lines[-1].endswith(".md") else None
    return {"created_path": created, "raw": out,
            "receipt": _receipt("create", params)}


def cli_append(runner, content, file=None, path=None, vault=None,
               timeout=DEFAULT_TIMEOUT):
    params = _target_params(file, path) + [f"content={content}"]
    out = _invoke(runner, _argv(vault, "append", params), timeout)
    return {"raw": out, "receipt": _receipt("append", params)}


def cli_search(runner, query, vault=None, limit=None,
               timeout=DEFAULT_TIMEOUT):
    """全文搜索（路径集口径）：search query=...，逐行解析路径。"""
    params = [f"query={query}"]
    if limit:
        params.append(f"limit={limit}")
    out = _invoke(runner, _argv(vault, "search", params), timeout)
    paths = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    return {"paths": paths, "receipt": _receipt("search", params)}


def cli_backlinks(runner, file=None, path=None, vault=None,
                  timeout=DEFAULT_TIMEOUT):
    """活索引入边：backlinks file=...，逐行解析来源文件。"""
    params = _target_params(file, path)
    out = _invoke(runner, _argv(vault, "backlinks", params), timeout)
    sources = [ln.strip() for ln in (out or "").splitlines()
               if ln.strip()]
    return {"backlinks": sources,
            "receipt": _receipt("backlinks", params)}


def cli_property_set(runner, name, value, file=None, path=None,
                     vault=None, timeout=DEFAULT_TIMEOUT):
    params = [f"name={name}", f"value={value}"] + \
        _target_params(file, path)
    out = _invoke(runner, _argv(vault, "property:set", params),
                  timeout)
    return {"raw": out, "receipt": _receipt("property:set", params)}
