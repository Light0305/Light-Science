"""light-crawler 演示全链（对本地夹具站点，确定性、无真实目标风险）。

链：init → 登记四目标 → 预检（含两例 blocked 留痕）→ 具名确认 →
gate-check → 采集 → 条件请求增量 → 人工导入 → validate → refusals。
末段以同一全链试跑一次真实官方 API（OpenAlex 单请求），结果如实
记录（成功或被拒都是合规链的真实产物，不挑拣）。
证据逐段落 evidence/*.txt；结论见同目录 demo-report.md。

运行：从包根执行 ../.venv-lit/bin/python examples/demo-fullrun/run_demo.py
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from light_crawler import fetch as fetch_mod  # noqa: E402
from light_crawler import precheck as pc  # noqa: E402
from light_crawler import project, render, storage  # noqa: E402
from light_crawler.validate import validate_workspace  # noqa: E402

HERE = Path(__file__).resolve().parent
PROJECT_DIR = HERE / "project"
WS = PROJECT_DIR / "data-sources"
EVIDENCE = HERE / "evidence"
NO_SLEEP = lambda s: None  # noqa: E731

ROBOTS = "User-agent: *\nAllow: /\nDisallow: /private\n"
HTML = (b"<!doctype html><html><head><title>Fixture Dataset Page</title>"
        b"<meta name=\"author\" content=\"Fixture Team\"></head><body>"
        b"<h1>Fixture dataset</h1><p>Public fixture data for demo.</p>"
        b"</body></html>")
DATA = json.dumps({"dataset": "fixture-broiler-weights",
                   "rows": 3, "unit": "kg"}).encode()


def etag_of(body: bytes) -> str:
    import hashlib
    return '"' + hashlib.sha256(body).hexdigest()[:12] + '"'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body=b"", ctype="text/plain", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/robots.txt":
            self._send(200, ROBOTS.encode())
        elif path == "/data.json":
            if self.headers.get("If-None-Match") == etag_of(DATA):
                self._send(304)
            else:
                self._send(200, DATA, "application/json",
                           {"ETag": etag_of(DATA)})
        elif path == "/page.html":
            self._send(200, HTML, "text/html")
        elif path == "/about.html":
            self._send(200, HTML.replace(b"Fixture Dataset Page",
                                         b"Fixture About Page"), "text/html")
        elif path == "/private/secret.json":
            self._send(200, b'{"should": "never be fetched"}',
                       "application/json")
        else:
            self._send(404, b"not found")


def log_evidence(name: str, text: str) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(text, encoding="utf-8")
    print(text)


def reg(target_id, base, channel, **kw):
    r = {"target_id": target_id, "name": f"演示目标 {target_id}",
         "base_url": base, "project": "demo-poultry-research",
         "purpose_kind": "dataset_batch",
         "consumer": "light-experiment 数据入口", "channel": channel,
         "terms_basis": "夹具站点条款页（本地演示用）"}
    r.update(kw)
    return r


def main() -> int:
    if PROJECT_DIR.exists():
        shutil.rmtree(PROJECT_DIR)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for old in EVIDENCE.glob("*.txt"):
        old.unlink()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    closed_port = sock.getsockname()[1]
    sock.close()
    down_base = f"http://127.0.0.1:{closed_port}"

    lines = []
    header = project.init_workspace(WS, "demo-poultry-research")
    lines.append(f"1) init：工作区 {WS}（{header['workspace_id']}），"
                 f"夹具站点 {base}")

    project.register_target(WS, reg("demo-api", base, "official_api"))
    project.register_target(WS, reg("demo-web", base, "web_page"))
    project.register_target(WS, reg(
        "demo-private", base, "official_api",
        url_patterns=[base + "/private/secret.json"]))
    project.register_target(WS, reg("demo-down", down_base, "official_api"))
    lines.append("2) 登记四目标：demo-api（官方 API 档）、demo-web（网页档）、"
                 "demo-private（URL 模式含 /private）、demo-down（主机不可达）")

    results = {}
    for tid in ("demo-api", "demo-web", "demo-private", "demo-down"):
        rec = pc.run_precheck(WS, tid)
        results[tid] = rec["status"]
    lines.append(f"3) 预检结论：{results}")
    blocked = pc.current_precheck(WS, "demo-private")["record"]
    lines.append(f"   demo-private 被拒原因：{blocked['blocked_reasons']}")
    down = pc.current_precheck(WS, "demo-down")["record"]
    lines.append(f"   demo-down 被拒原因：{down['blocked_reasons']}")

    pc.confirm_precheck(WS, "demo-web", confirmer="演示用户",
                        note="夹具站点条款已核对（演示）")
    lines.append("4) demo-web 高危通道经具名确认生效（S4）")

    verdict = fetch_mod.gate_check(WS, "demo-api")
    lines.append(f"5) gate-check demo-api：ready={verdict['ready']}，"
                 f"有效间隔 {verdict['effective_interval_sec']}s，"
                 f"precheck {verdict['precheck_id']}")
    log_evidence("05-gate-check.json",
                 json.dumps(verdict, ensure_ascii=False, indent=1))

    rec = fetch_mod.fetch_run(
        WS, "demo-api", urls=[base + "/data.json", base + "/page.html"],
        sleep=NO_SLEEP)
    lines.append(f"6) fetch demo-api：请求 {rec['requested']}、落盘 "
                 f"{rec['stored']}（run {rec['run_id']}）")
    rec_web = fetch_mod.fetch_run(
        WS, "demo-web", urls=[base + "/about.html"], sleep=NO_SLEEP)
    lines.append(f"7) fetch demo-web：落盘 {rec_web['stored']}"
                 "（与 demo-api 同 URL 会被已见集按指纹跳过，故取另一页）")

    try:
        fetch_mod.fetch_run(WS, "demo-private", sleep=NO_SLEEP)
        lines.append("8) fetch demo-private：未被拒绝（异常！）")
    except fetch_mod.Refusal as e:
        lines.append(f"8) fetch demo-private 被 guard 拒绝：{e.reasons[:1]}")

    rec304 = fetch_mod.fetch_run(
        WS, "demo-api", urls=[base + "/data.json"], sleep=NO_SLEEP,
        refetch_seen=True)
    lines.append(f"9) 增量重取 /data.json：未变更 {rec304['not_modified']}"
                 "（ETag 条件请求 304，不落新版）")

    export_file = PROJECT_DIR / "manual-export.csv"
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    export_file.write_bytes(b"pen,weight_kg\nA,2.31\nB,2.28\n")
    prov = fetch_mod.import_file(
        WS, "demo-api", export_file, note="演示用户从夹具后台人工导出",
        by="演示用户")
    lines.append(f"10) 人工导入：{prov['prov_id']}（通道 manual_import，"
                 f"sha256 {prov['sha256'][:12]}...）")

    problems = validate_workspace(WS)
    lines.append(f"11) validate：{'ok' if not problems else problems}")
    refusals = [e for e in project.read_events(WS)
                if e["type"] in ("precheck_blocked", "fetch_refused",
                                "http_refused", "circuit_broken")]
    lines.append(f"12) 拒绝留痕共 {len(refusals)} 条（refusals 命令可查）")
    render.write_report(WS)
    server.shutdown()

    # ---- 真实官方 API 试跑（同链，结果如实记录）
    lines.append("13) 真实试跑：登记 OpenAlex 官方 API 目标并走同一全链")
    try:
        project.register_target(WS, {
            "target_id": "openalex-live", "name": "OpenAlex（真实试跑）",
            "base_url": "https://api.openalex.org",
            "project": "demo-poultry-research",
            "purpose_kind": "literature_leads_batch",
            "consumer": "light-literature 线索批",
            "channel": "official_api",
            "terms_basis": "OpenAlex 官方文档与使用条款（api.openalex.org）",
        })
        rec = pc.run_precheck(WS, "openalex-live", robots_timeout=20.0)
        lines.append(f"    预检：{rec['status']}（robots outcome "
                     f"{rec['checks']['robots']['outcome']}）")
        if rec["status"] == "effective":
            run = fetch_mod.fetch_run(WS, "openalex-live", urls=[
                "https://api.openalex.org/works/"
                "https://doi.org/10.1016/j.compag.2025.110856"])
            lines.append(f"    fetch：请求 {run['requested']}、落盘 "
                         f"{run['stored']}、状态 {run['status']}、"
                         f"errors {run['errors']}")
        else:
            lines.append(f"    未 fetch：预检未生效 {rec['blocked_reasons']}")
    except Exception as e:  # 网络不可达等：如实记录，不挑拣结果
        lines.append(f"    试跑异常（原文记录）：{type(e).__name__}: {e}")

    log_evidence("demo-transcript.txt", "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
