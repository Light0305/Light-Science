"""I4 评估与排序（三期）：两两对决记录 + 胜率矩阵 + Elo 风格参考分。

设计依据：02-idea/LEARNING.md §5 + REDESIGN-DRAFT §5。写死的纪律：

- **相对判断优先**：排序主信号是两两对决（相对判断是 LLM 唯一被验证
  有非平凡准确率的形态），绝对分数只作粗筛；本模块产出的 Elo 与胜率
  一律写进卡的 aux 区并标「暂定，未经执行验证」，**不作淘汰依据**；
- **淘汰只凭三类证据**：查新 ABANDON（点名论文）/ 试点 negative /
  客观不可行（预算门）——对决输赢只决定「先查新/先试点谁」的顺序，
  输了不许据此 killed（ARIS「让证据杀想法」）；
- **循环胜负如实提示**：对决图出现环（A 胜 B、B 胜 C、C 胜 A 这类）
  时明示「锦标赛分不开它们」，不假装小数点后有精度（EvoSkills 诚实
  条款）；此时 Elo 只作并列参考。

对决记录落点：双方卡的 aux.pairwise_record（列表，每条
{opponent, result(win/loss/draw，该卡视角), date, by, note}）。
rank 是纯计算（不写卡）：CLI 层决定是否把 Elo 回写 aux.elo。
"""

from __future__ import annotations

from pathlib import Path

from .util import today

ELO_START = 1500.0
ELO_K = 32.0

RESULTS = ("win", "loss", "draw")
_OPPOSITE = {"win": "loss", "loss": "win", "draw": "draw"}


class DuelError(Exception):
    """对决记录/排序的校验失败。errors 为逐条人读原因。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


def record_duel(card_a: dict, card_b: dict, winner: str, *,
                by: str, note: str = "", date: str | None = None) -> dict:
    """把一次对决追加进双方卡的 aux.pairwise_record（就地修改两卡）。

    winner ∈ {card_a 的 idea_id, card_b 的 idea_id, "draw"}。
    返回对决记录 dict（a/b 视角的规范化表示）。
    """
    date = date or today()
    a_id, b_id = card_a.get("idea_id"), card_b.get("idea_id")
    errs: list[str] = []
    if not a_id or not b_id:
        errs.append("对决双方卡必须有 idea_id")
    elif a_id == b_id:
        errs.append("不许自己和自己对决")
    if winner not in (a_id, b_id, "draw"):
        errs.append(f"winner 非法：{winner!r}（须为对决双方 idea_id 之一或 draw）")
    if errs:
        raise DuelError(errs)

    if winner == "draw":
        res_a = res_b = "draw"
    elif winner == a_id:
        res_a, res_b = "win", "loss"
    else:
        res_a, res_b = "loss", "win"
    for card, opponent, result in ((card_a, b_id, res_a), (card_b, a_id, res_b)):
        aux = card.setdefault("aux", {})
        record = aux.get("pairwise_record")
        if not isinstance(record, list):
            record = []
            aux["pairwise_record"] = record
        record.append({"opponent": opponent, "result": result,
                       "date": date, "by": by or "", "note": note or ""})
        card["updated"] = date
    return {"a": a_id, "b": b_id, "winner": winner, "date": date,
            "by": by or "", "note": note or ""}


def collect_matches(cards: list[dict]) -> list[dict]:
    """从各卡 pairwise_record 还原对决清单（每场只取一次）。

    还原规则：卡按 idea_id 排序，只取「本卡 idea_id < opponent」的
    记录作为该场的权威视角（对决落卡时双方各存一份镜像，取一侧即
    全量）；镜像缺失/矛盾不另行合成，如实按权威侧记录走。
    每场：{a, b, result_a(win/loss/draw，a 视角), date, by, note}，
    按日期稳定排序（Elo 按时间顺序结算）。
    """
    by_id = {c["idea_id"]: c for c in cards}
    matches: list[dict] = []
    for card in sorted(cards, key=lambda c: c["idea_id"]):
        me = card["idea_id"]
        for rec in (card.get("aux") or {}).get("pairwise_record") or []:
            opp = rec.get("opponent")
            if opp not in by_id or not (me < opp):
                continue
            matches.append({
                "a": me, "b": opp,
                "result_a": rec.get("result"),
                "date": rec.get("date") or "",
                "by": rec.get("by") or "",
                "note": rec.get("note") or "",
            })
    matches.sort(key=lambda m: (m["date"], m["a"], m["b"]))
    return matches


def win_matrix(matches: list[dict]) -> dict[str, dict[str, dict]]:
    """胜率矩阵：matrix[a][b] = {win, loss, draw}（a 对 b 的战绩）。"""
    matrix: dict[str, dict[str, dict]] = {}

    def cell(x: str, y: str) -> dict:
        return matrix.setdefault(x, {}).setdefault(
            y, {"win": 0, "loss": 0, "draw": 0})

    for m in matches:
        a, b, r = m["a"], m["b"], m["result_a"]
        if r == "win":
            cell(a, b)["win"] += 1
            cell(b, a)["loss"] += 1
        elif r == "loss":
            cell(a, b)["loss"] += 1
            cell(b, a)["win"] += 1
        elif r == "draw":
            cell(a, b)["draw"] += 1
            cell(b, a)["draw"] += 1
    return matrix


def elo_ratings(cards: list[dict], matches: list[dict]) -> dict[str, float]:
    """Elo 风格参考分：全员 1500 起、K=32，按对决日期顺序结算。

    只含打过对决的卡（无对决不给分——没证据不编数）。返回 {idea_id: 分}。
    分数是 aux 辅助信号：只作粗排序参考，不作淘汰依据（见模块头）。
    """
    ratings: dict[str, float] = {}
    for m in matches:
        a, b = m["a"], m["b"]
        ra = ratings.setdefault(a, ELO_START)
        rb = ratings.setdefault(b, ELO_START)
        ea = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
        sa = {"win": 1.0, "draw": 0.5, "loss": 0.0}.get(m["result_a"], 0.5)
        ratings[a] = ra + ELO_K * (sa - ea)
        ratings[b] = rb + ELO_K * ((1.0 - sa) - (1.0 - ea))
    return ratings


def find_cycles(matches: list[dict]) -> list[list[str]]:
    """找对决胜负图中的循环（强连通分量 ≥2)：A 胜 B 胜 C 胜 A 这类。

    边 a→b 表示 a 至少胜过 b 一次。用 Tarjan SCC；返回每个循环内
    的卡清单（排序后）。有循环 = 锦标赛在这些卡之间分不开。
    """
    graph: dict[str, set[str]] = {}
    for m in matches:
        if m["result_a"] == "win":
            graph.setdefault(m["a"], set()).add(m["b"])
            graph.setdefault(m["b"], set())
        elif m["result_a"] == "loss":
            graph.setdefault(m["b"], set()).add(m["a"])
            graph.setdefault(m["a"], set())

    index_counter = [0]
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        indices[v] = lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])
        if lowlink[v] == indices[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))

    for v in list(graph):
        if v not in indices:
            strongconnect(v)
    return sorted(sccs)


def rank_project(root: Path, cards: list[dict]) -> dict:
    """项目级排序汇总（纯计算，不写任何文件/卡）。

    返回 {matches, matrix, elo, cycles, standings}；standings 按 Elo
    降序（同分按胜场、对决数、idea_id），每行含胜/负/平与胜率。
    root 参数保留给调用方口径一致（当前计算只依赖卡本身）。
    """
    matches = collect_matches(cards)
    matrix = win_matrix(matches)
    elo = elo_ratings(cards, matches)
    cycles = find_cycles(matches)
    standings = []
    for idea_id, rating in elo.items():
        w = l = d = 0
        for opp, celldata in matrix.get(idea_id, {}).items():
            w += celldata["win"]
            l += celldata["loss"]
            d += celldata["draw"]
        games = w + l + d
        standings.append({
            "idea_id": idea_id,
            "elo": round(rating, 1),
            "win": w, "loss": l, "draw": d, "games": games,
            "win_rate": round(w / games, 4) if games else 0.0,
        })
    standings.sort(key=lambda s: (-s["elo"], -s["win"], -s["games"],
                                  s["idea_id"]))
    return {"matches": matches, "matrix": matrix, "elo": elo,
            "cycles": cycles, "standings": standings}
