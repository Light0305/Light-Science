"""ask 问语料模式 (LIT-D01)：对已入库语料提问，答案只许引用命中块。

与 light-memory recall 的边界 (SKILL §6)：ask 查的是文献全文证据
(source_map 块)，recall 查的是沉淀后的事实账——两者不互相替代。

纪律 (形态学 paper-qa，按诊断 D01 落地)：
- 块级检索：对已入库论文的 source_map 块做词项/数字机械匹配，
  逐块分数与命中信号全部留痕。
- 引用白名单：答案的引用只能取自本次命中块的锚点，且引用数不许
  超过上限 (默认 5)；白名单外的锚点一律拒绝落盘。
- 固定拒答：无任一块命中时，产物只写固定拒答句；此时即使调用方
  传入答案也报错拒绝——证据不足不许生成答案。
- 证据资格门：paper.yaml 顶层 identity_status 非 verified 或
  retraction_status=retracted 的论文 (若有标记)，其块不进命中集
  (未核实文献不入成稿层，硬规则 1 在问答面的落点)。
- 产物全留痕：Literature/问答记录/<日期>-<序号>.md (问题、命中块、
  答案或拒答、引用清单)。

检索升级 (2026-10-21，qa-eval gold 基线五条根因的逐条回修)：
- 检索面扩到 equation / figure_text 块：公式型问题此前按构造
  不可答 (Adam 690 块中 400 块为公式块)。
- 查询侧跨语言扩展 (textmatch.expand_cross_lingual)：中文问题
  的术语并入英文对应词，修跨语言系统性漏检。
- CJK 证据单元改双字组 (textmatch.tokenize)：单字碰撞不再灌门。
- IDF 加权排序替代原始计数：分数 = 词项 IDF 和 + 2 x 数字 IDF
  和，泛词与高频数字的区分度被压低，真锚点不再被稀释。
- 证据单元门 (见 _is_evidence)：过门须命中 >=3 个不同证据单元
  且词项 IDF 过线，或数字命中 + 词项锚定且总分过线，或高区分
  度数字独立成证 (公式块通道)，或双拉丁词项强证据 (IDF 总和
  过高线)；纯 CJK 双字组证据另走子语料池内相对门槛 (单元数与
  池内 IDF 双线)，防小语料内泛词碰撞灌门。
- 问题级硬缺席拒答：问题命中的词表概念若有 >=2 个在语料里双
  缺席 (概念原文不在任何块中、其英文扩展词也全部无命中)，说
  明所问事实不在语料内，整题回到固定拒答 (陷阱题通道)，不再
  全靠执行者兜底。
- 命名实体缺席拒答：问题中大写/全大写的命名实体 (BERT、
  ResNet 之类) 若在语料词项里零命中，该实体不在语料内——其
  余通用词 (token / training / ...) 在语料里散列共现凑出的
  命中不构成证据，整题拒答 (干净拒答题通道)。
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

from . import textmatch
from .util import (corpus_paper_ids, literature_dir, load_paper_yaml,
                   read_json)

#: 证据不足时的固定拒答句 (措辞冻结，改动须同步 SKILL 与测试)。
REFUSAL_TEXT = ("证据不足：已入库语料中未找到可支持回答的证据块，"
                "本次拒答。")
DEFAULT_MAX_CITATIONS = 5
_RECORD_DIRNAME = "问答记录"
_EXCERPT_CHARS = 200
_BLOCK_TYPES = ("text", "caption", "table", "equation", "figure_text")

#: 证据单元门常量 (qa-eval gold 上实测标定，标定数据见批次报告)。
_MIN_DISTINCT_TERMS = 3     # 纯词项证据须 >=3 个不同证据单元
_MIN_TERM_IDF = 4.0         # 且词项 IDF 总和过线
_STRONG_PAIR_IDF = 9.0      # 双拉丁词项强证据：恰 2 单元且 IDF 过此线
_NUM_TOTAL_IDF = 4.0        # 数字命中 + >=1 词项时，总分过此线
_DISTINCTIVE_NUM_IDF = 2.5  # 高区分度数字可独立成证 (公式块通道)
_NUMBER_WEIGHT = 2.0        # 数字 IDF 在总分中的权重
_CJK_MIN_DISTINCT = 4       # 纯 CJK 双字组证据须 >=4 个不同单元
_CJK_MIN_POOL_IDF = 8.0     # 且 CJK 子语料池内 IDF 总和过此线
_HARD_ABSENT_MIN = 2        # 硬缺席概念 >=2 个时整题拒答


def _paper_eligible(paper: dict) -> tuple[bool, str | None]:
    """证据资格门：只排除被显式标记未核实/已撤稿的论文。"""
    identity = paper.get("identity_status")
    if identity is not None and identity != "verified":
        return False, f"identity_status={identity}"
    if paper.get("retraction_status") == "retracted":
        return False, "retraction_status=retracted"
    return True, None


def _is_cjk_term(term: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in term)


def _score_blocks(project_dir: Path,
                  question: str) -> tuple[list, list, list, dict]:
    """全块 IDF 打分 (不过证据门)。

    返回 (scored, excluded, hard_absent, df_terms)：scored 每项
    含 paper_id / anchor / page / type / score / matched_terms /
    matched_numbers / term_idf / num_idf / cjk_pool_idf /
    cjk_terms / latin_terms / latin_term_idf / text；hard_absent
    是问题级硬缺席概念清单 (见模块 docstring)；df_terms 是语料
    词项文档频率表 (命名实体缺席判定用)。retrieve 在此之上过
    门；本函数供诊断与标定使用，口径一致。
    """
    project_dir = Path(project_dir)
    if not (question or "").strip():
        raise ValueError("问题不许为空")
    q_terms = textmatch.tokenize(question) | \
        textmatch.expand_cross_lingual(question)
    q_numbers = textmatch.extract_numbers(question)
    universe: list[tuple[str, dict, str, set]] = []
    excluded: list[dict] = []
    for pid in corpus_paper_ids(project_dir):
        pdir, paper = load_paper_yaml(project_dir, pid)
        ok, why = _paper_eligible(paper)
        if not ok:
            excluded.append({"paper_id": pid, "reason": why})
            continue
        smap = read_json(pdir / "source_map.json")
        for block in smap.get("blocks", []):
            if not block.get("id") or block.get("type") not in _BLOCK_TYPES:
                continue
            text = textmatch.block_text(block)
            universe.append((pid, block, text, textmatch.tokenize(text)))
    n = max(len(universe), 1)
    cjk_pool = [u for u in universe if any("\u4e00" <= ch <= "\u9fff"
                                           for ch in u[2])]
    n_cjk = max(len(cjk_pool), 1)

    def _idf(df: int) -> float:
        return math.log(1 + n / max(df, 1))

    def _idf_cjk(df: int) -> float:
        return math.log(1 + n_cjk / max(df, 1))

    df_terms = {t: sum(1 for _, _, _, bt in universe if t in bt)
                for t in q_terms}
    df_nums = {num: sum(1 for _, _, text, _ in universe
                        if textmatch.number_in_text(num, text))
               for num in q_numbers}
    df_cjk = {t: sum(1 for _, _, _, bt in cjk_pool if t in bt)
              for t in q_terms if _is_cjk_term(t)}

    # 硬缺席概念：词表键原文不在任何块中、且其英文扩展词全数无命中。
    hard_absent: list[str] = []
    for key in textmatch.matched_glossary_keys(question):
        if any(key in text for _, _, text, _ in universe):
            continue
        expansion = textmatch.tokenize(
            textmatch.CROSS_LINGUAL_GLOSSARY[key])
        if any(df_terms.get(t, 0) >= 1 for t in expansion):
            continue
        hard_absent.append(key)

    scored: list[dict] = []
    for pid, block, text, btokens in universe:
        matched_terms = sorted(q_terms & btokens)
        matched_numbers = [num for num in q_numbers
                           if textmatch.number_in_text(num, text)]
        term_idf = sum(_idf(df_terms[t]) for t in matched_terms)
        num_idf = sum(_idf(df_nums[num]) for num in matched_numbers)
        scored.append({
            "paper_id": pid,
            "anchor": block["id"],
            "page": block.get("page"),
            "type": block.get("type"),
            "score": round(term_idf + _NUMBER_WEIGHT * num_idf, 3),
            "matched_terms": matched_terms,
            "matched_numbers": matched_numbers,
            "term_idf": term_idf,
            "num_idf": num_idf,
            "cjk_pool_idf": sum(_idf_cjk(df_cjk.get(t, 0))
                                for t in matched_terms
                                if _is_cjk_term(t)),
            "cjk_terms": sum(1 for t in matched_terms
                             if _is_cjk_term(t)),
            "latin_terms": sum(1 for t in matched_terms
                               if not _is_cjk_term(t)),
            "latin_term_idf": sum(_idf(df_terms[t])
                                  for t in matched_terms
                                  if not _is_cjk_term(t)),
            "text": text,
        })
    scored.sort(key=lambda h: (-h["score"], h["paper_id"], h["anchor"]))
    return scored, excluded, hard_absent, df_terms


def _absent_entities(question: str, df_terms: dict) -> set[str]:
    """问题里语料零命中的命名实体。

    候选 = NFKC 归一后以大写开头或全大写的字母词元 (BERT /
    ResNet / ImageNet / LeNet 之类)；逐个经 tokenize 归一后，
    其全部词形在 df_terms 里都为 0 才算缺席。普通小写词 (动词
    等) 不作实体看，避免把语料的词汇缺口误判成实体缺席。
    """
    normalized = unicodedata.normalize("NFKC", question)
    absent: set[str] = set()
    for i, match in enumerate(
            re.finditer(r"[A-Za-z][A-Za-z0-9\-]*", normalized)):
        raw = match.group(0)
        if len(raw) < 2:
            continue
        if not (raw[0].isupper() or raw.isupper()):
            continue
        # 句首的纯首字母大写词是正字法大写，不是实体信号 (What /
        # Accuracy 起句)；全大写、驼峰、含数字的词元不受此限
        # (BERT / ImageNet / Byte3Track 起句仍是实体)。
        if i == 0 and raw.isalpha() and raw[1:].islower():
            continue
        toks = {t for t in textmatch.tokenize(raw) if len(t) >= 2}
        if toks and all(df_terms.get(t, 0) == 0 for t in toks):
            absent.add(raw)
    return absent


def _latin_evidence(scored: dict) -> bool:
    """拉丁侧独立成证判定 (只计拉丁词项与数字的贡献)。

    通道：(1) >=3 个拉丁词项 + 拉丁 IDF 过线；(2) 数字命中 +
    >=1 拉丁词项 + (拉丁 IDF + 2 x 数字 IDF) 过线；(3) 恰 2 个
    拉丁词项但 IDF 总和过高线 (强强联合)。
    """
    lt = scored["latin_terms"]
    lidf = scored["latin_term_idf"]
    if scored["matched_numbers"] and lt >= 1 and \
            lidf + _NUMBER_WEIGHT * scored["num_idf"] >= _NUM_TOTAL_IDF:
        return True
    if lt >= _MIN_DISTINCT_TERMS and lidf >= _MIN_TERM_IDF:
        return True
    if lt == 2 and lidf >= _STRONG_PAIR_IDF:
        return True
    return False


def _is_evidence(scored: dict) -> bool:
    """证据单元门 (qa-eval gold 实测标定，常量见上)。

    按证据构成路由，两侧不许互相搭便车：
    - 纯 CJK 双字组证据：只认池内相对门槛 (>=4 个不同单元且
      CJK 子语料池内 IDF 总和过线)——全局 IDF 下中文泛词个个
      「稀有」，小语料内的碰撞必须以池内尺度量。
    - 混合证据 (CJK + 拉丁)：CJK 侧过池内门槛，或拉丁侧独立
      成证 (_latin_evidence)，任一成立即可。
    - 无 CJK：拉丁侧成证，或高区分度数字独立成证 (公式块通
      道：问题所问数字本身即强信号，块内无词项亦可)。
    """
    has_cjk = scored["cjk_terms"] > 0
    has_latin = scored["latin_terms"] > 0
    cjk_ok = scored["cjk_terms"] >= _CJK_MIN_DISTINCT and \
        scored["cjk_pool_idf"] >= _CJK_MIN_POOL_IDF
    if has_cjk and not has_latin and not scored["matched_numbers"]:
        return cjk_ok
    if has_cjk and has_latin:
        return cjk_ok or _latin_evidence(scored)
    if _latin_evidence(scored):
        return True
    return bool(scored["matched_numbers"]) and \
        scored["num_idf"] >= _DISTINCTIVE_NUM_IDF


def retrieve(project_dir: Path, question: str) -> dict:
    """块级检索：返回 hits (命中块) 与 excluded (资格门排除留痕)。

    问题级拒答两条：硬缺席概念 >=2 个，或命名实体在语料零命
    中 (见模块 docstring)；命中其一整题无命中 (固定拒答通
    道)，其余按 _is_evidence 逐块过门。
    """
    scored, excluded, hard_absent, df_terms = _score_blocks(
        project_dir, question)
    if len(hard_absent) >= _HARD_ABSENT_MIN or \
            _absent_entities(question, df_terms):
        return {"hits": [], "excluded": excluded}
    hits = [{
        "paper_id": s["paper_id"],
        "anchor": s["anchor"],
        "page": s["page"],
        "type": s["type"],
        "score": s["score"],
        "matched_terms": s["matched_terms"],
        "matched_numbers": s["matched_numbers"],
        "excerpt": " ".join(s["text"].split())[:_EXCERPT_CHARS],
    } for s in scored if _is_evidence(s)]
    return {"hits": hits, "excluded": excluded}


def _parse_citation(raw: str, whitelist: dict[str, dict]) -> str:
    """引用解析：接受 'paper_id#S001' 或裸锚点 (须在命中集内唯一)。"""
    if "#" in raw:
        pid, anchor = raw.split("#", 1)
        key = f"{pid}#{anchor}"
        if key in whitelist:
            return key
        raise ValueError(f"引用不在本次命中白名单内：{raw}")
    matches = [k for k in whitelist if k.endswith(f"#{raw}")]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"引用不在本次命中白名单内：{raw}")
    raise ValueError(f"裸锚点 {raw} 在命中集中不唯一，须写 paper_id#锚点")


def ask(project_dir: Path, question: str, answer: str | None = None,
        citations: list[str] | None = None,
        max_citations: int = DEFAULT_MAX_CITATIONS) -> dict:
    """执行一次问语料：检索 → (拒答 | 待答 | 落答案) → 写问答记录。"""
    project_dir = Path(project_dir)
    citations = list(citations or [])
    found = retrieve(project_dir, question)
    hits = found["hits"]

    if not hits:
        if answer is not None:
            raise ValueError(
                "无命中证据块：固定拒答，不许附答案 (证据不足拒答纪律)")
        status = "refused"
    elif answer is not None:
        if not citations:
            raise ValueError("给出答案时必须同时给出引用锚点 (--cite)")
        if len(citations) > max_citations:
            raise ValueError(
                f"引用数 {len(citations)} 超过上限 {max_citations}")
        whitelist = {f"{h['paper_id']}#{h['anchor']}": h for h in hits}
        citations = [_parse_citation(c, whitelist) for c in citations]
        status = "answered"
    else:
        status = "awaiting_answer"

    rec_dir = literature_dir(project_dir) / _RECORD_DIRNAME
    rec_dir.mkdir(parents=True, exist_ok=True)
    seq = len(list(rec_dir.glob("*.md"))) + 1
    rec_path = rec_dir / f"{date.today().isoformat()}-{seq:03d}.md"

    lines = [
        "# 问答记录 (ask-the-corpus)",
        "",
        f"- 问题：{question}",
        f"- 时间 (UTC)：{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 状态：{status}",
        f"- 引用上限：{max_citations}",
        "",
        "## 命中证据块",
        "",
    ]
    if hits:
        lines += ["| 论文 | 锚点 | 页 | 分数 | 命中词项 | 摘录 |",
                  "|---|---|---|---|---|---|"]
        for h in hits:
            terms = ", ".join(h["matched_terms"][:8])
            lines.append(
                f"| {h['paper_id']} | {h['anchor']} | {h['page']} "
                f"| {h['score']} | {terms} | {h['excerpt']} |")
    else:
        lines.append("（无命中）")
    if found["excluded"]:
        lines += ["", "## 证据资格门排除（未核实/撤稿，不入证据）", ""]
        for e in found["excluded"]:
            lines.append(f"- {e['paper_id']}：{e['reason']}")
    lines += ["", "## 答案", ""]
    if status == "refused":
        lines.append(REFUSAL_TEXT)
    elif status == "answered":
        lines.append(answer or "")
        lines += ["", "引用："]
        for c in citations:
            lines.append(f"- {c}")
    else:
        lines.append(
            "（待执行 agent 依据上表命中块作答；引用只能取自上表锚点，"
            f"且不超过 {max_citations} 条。用 ask --answer/--cite 落盘。）")
    lines.append("")
    rec_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "question": question,
        "status": status,
        "hits": len(hits),
        "excluded": found["excluded"],
        "citations": citations if status == "answered" else [],
        "record": str(rec_path),
    }
