"""索引层（.index/）：FTS5 词法 + 向量，全派生、可整删重建（MM-03）。

纪律锚点（LEARNING.md）：
- MM-03：索引是真相文件的影子——删掉 .index 不丢任何记忆，一条
  命令从真相全量重建；索引里不许有真相的唯一副本。
- MM-04：块 ID 含嵌入模型名，换模型构造性失效；维度在建索引时
  校验，不许静默混用两代向量。向量由「有效嵌入器」产生，块 ID
  用有效模型名。真实嵌入已接入（MM2-02）：登记 provider=local +
  模型名 → 本地 ONNX 真实嵌入（fastembed，本机运行零外发）；
  provider=api + endpoint + 密钥环境变量名（密钥只经环境注入、
  永不落盘）→ API 真实嵌入。登记不全或真实实现不可用时，有效
  嵌入如实回落确定性测试嵌入并在台账注明，绝不冒充已用登记模型
  ——台账标注与实际使用者必须一致（有测试断言钉住）。
- MM-05：同步走台账——index-state.json 逐真相文件记哈希与状态，
  校验器据此对账；真相变了索引即 stale，明示不静默。
- 向量存储借嵌入式底层件：sqlite-vec 可用则优先（vec0 表加速），
  不可用走同一 sqlite 文件内的 JSON 列 + 纯 Python 余弦，不阻塞。
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path

from . import project as project_mod
from .util import (component_hash, load_structured, read_jsonl,
                   sha256_file, utcnow)

INDEX_DIR = ".index"
INDEX_DB = "memory_index.sqlite"
INDEX_STATE = "index-state.json"

TEST_EMBEDDER = "deterministic-test"
TEST_MODEL = "deterministic-test-v1"
TEST_DIM = 64


class IndexError_(Exception):
    """索引操作被拒。gaps 为逐条人读原因。（类名避开内置 IndexError）"""

    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 嵌入器

_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")


def tokenize(text: str) -> list:
    return _TOKEN_RE.findall((text or "").lower())


class DeterministicEmbedder:
    """确定性测试嵌入：哈希分桶词袋向量，无外部依赖、跨运行一致。

    只用于在没有真实嵌入模型时让索引管线可跑可测；产物一律标注
    embedder=deterministic-test，不许冒充语义嵌入质量（MM-23 降级明示）。
    """

    name = TEST_EMBEDDER
    model = TEST_MODEL
    dim = TEST_DIM

    def embed(self, text: str) -> list:
        import hashlib
        vec = [0.0] * self.dim
        for tok in tokenize(text):
            digest = hashlib.sha256(tok.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:2], "big") % self.dim
            vec[bucket] += 1.0 if digest[2] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


class LocalOnnxEmbedder:
    """真实本地嵌入（fastembed / ONNX 运行时）：本机运行、零外发。

    模型按登记名加载（首次从官方模型仓下载到缓存目录，之后离线
    可用）；缓存目录可用环境变量 LIGHT_MEMORY_EMBED_CACHE 覆盖。
    实例按模型名在进程内复用，避免反复加载。
    """

    name = "local-onnx"

    def __init__(self, model: str):
        self.model = model
        self._te = None
        self.dim = self._lookup_dim(model)

    @staticmethod
    def _lookup_dim(model: str) -> int:
        from fastembed import TextEmbedding
        for m in TextEmbedding.list_supported_models():
            if m.get("model") == model:
                return int(m["dim"])
        raise ValueError(f"fastembed 不支持的本地嵌入模型：{model}")

    def _load(self):
        if self._te is None:
            import os
            from fastembed import TextEmbedding
            cache = os.environ.get("LIGHT_MEMORY_EMBED_CACHE") or None
            try:
                self._te = TextEmbedding(model_name=self.model,
                                         cache_dir=cache)
            except Exception:
                # 网络客户端初始化失败（如代理环境变量格式异常）时，
                # 若模型已在缓存中，以离线模式重试——本地嵌入的
                # 本分是本机运行，不该被一次性的下载通道故障否决；
                # 缓存也没有时原样抛错，走 resolve 的诚实回落。
                os.environ["HF_HUB_OFFLINE"] = "1"
                self._te = TextEmbedding(model_name=self.model,
                                         cache_dir=cache)
        return self._te

    def embed(self, text: str) -> list:
        vec = next(iter(self._load().embed([text or ""])))
        return _normalize([float(v) for v in vec])

    def embed_query(self, text: str) -> list:
        te = self._load()
        fn = getattr(te, "query_embed", None) or te.embed
        vec = next(iter(fn([text or ""])))
        return _normalize([float(v) for v in vec])


class ApiEmbedder:
    """真实 API 嵌入（登记制）：OpenAI 兼容 embeddings 端点。

    密钥只从登记的环境变量名读取、永不落盘、永不进台账；端点与
    模型名在登记头登记。维度由登记 dim 声明，建索引时校验。
    """

    name = "api"

    def __init__(self, model: str, endpoint: str, api_key: str,
                 dim: int):
        self.model = model
        self.endpoint = endpoint
        self._api_key = api_key
        self.dim = dim

    def embed(self, text: str) -> list:
        import requests
        resp = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self.model, "input": text or ""},
            timeout=60)
        resp.raise_for_status()
        vec = resp.json()["data"][0]["embedding"]
        return _normalize([float(v) for v in vec])

    embed_query = embed


def _normalize(vec: list) -> list:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


_LOCAL_CACHE: dict = {}


def _local_embedder(model: str) -> LocalOnnxEmbedder:
    """进程内复用本地嵌入实例，并以一次真实加载探活。

    只有模型确实加载成功才许声称 effective=local-onnx——登记了
    却加载不了（无 fastembed、模型不支持、下载失败）时抛错给
    resolve_embedder 走诚实回落，不冒充。
    """
    if model not in _LOCAL_CACHE:
        emb = LocalOnnxEmbedder(model)
        emb._load()
        _LOCAL_CACHE[model] = emb
    return _LOCAL_CACHE[model]


def resolve_embedder(memory: dict) -> dict:
    """解析有效嵌入器：登记信息照录，有效实现与台账标注必须一致。

    - provider=local + model：真实本地 ONNX 嵌入；加载失败回落。
    - provider=api + model + endpoint + api_key_env（且环境变量
      已设）+ dim：真实 API 嵌入；登记不全回落。
    - 其余：确定性测试嵌入（未登记者默认）。
    """
    reg = (memory or {}).get("embedder") or {}
    provider = reg.get("provider")
    base = {"registered_provider": provider,
            "registered_model": reg.get("model")}
    if provider == "local" and reg.get("model"):
        try:
            emb = _local_embedder(reg["model"])
            return {**base, "effective": emb.name, "model": emb.model,
                    "dim": emb.dim, "embedder": emb,
                    "note": "本地真实嵌入（ONNX/fastembed，本机运行"
                            "零外发），向量由登记模型产生"}
        except Exception as exc:  # 加载失败：如实回落并注明原因
            emb = DeterministicEmbedder()
            return {**base, "effective": emb.name, "model": emb.model,
                    "dim": emb.dim, "embedder": emb,
                    "note": f"登记 local 嵌入不可用（{type(exc).__name__}"
                            f"：{exc}），有效嵌入回落确定性测试嵌入"
                            "并如实标注"}
    if provider == "api" and reg.get("model"):
        import os
        endpoint = reg.get("endpoint")
        key_env = reg.get("api_key_env")
        api_key = os.environ.get(key_env) if key_env else None
        if endpoint and api_key and reg.get("dim"):
            emb = ApiEmbedder(reg["model"], endpoint, api_key,
                              int(reg["dim"]))
            return {**base, "effective": emb.name, "model": emb.model,
                    "dim": emb.dim, "embedder": emb,
                    "note": "API 真实嵌入（登记端点；密钥经环境变量"
                            "注入、永不落盘），向量由登记模型产生"}
    emb = DeterministicEmbedder()
    return {
        **base,
        "effective": emb.name,
        "model": emb.model,
        "dim": emb.dim,
        "embedder": emb,
        "note": ("登记的嵌入提供者本期无真实实现，有效嵌入回落确定性"
                 "测试嵌入并如实标注" if provider
                 else "未登记嵌入提供者，使用确定性测试嵌入"),
    }


def _vec_backend(con) -> str:
    """sqlite-vec 可用则优先：尝试建 vec0 表探活。"""
    try:
        import sqlite_vec  # noqa: F401
        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
        return "sqlite-vec"
    except Exception:
        return "python-json"


# ---------------------------------------------------------------- 真相清单

#: truth_manifest 进程内备忘：键为包路径，值为（文件签名，清单）。
#: 签名 = 逐文件 (相对名, mtime_ns, size)；任一真相文件或笔记被
#: 改写签名即变、备忘自然失效——校验语义与每次全量算哈希一致，
#: 只是把「每查一次全量哈希」降为「每查一次 stat」（D-S1）。
_MANIFEST_CACHE: dict = {}


def _manifest_signature(root) -> tuple:
    sig = []
    for name in project_mod.TRUTH_FILES:
        p = root / name
        if p.exists():
            st = p.stat()
            sig.append((name, st.st_mtime_ns, st.st_size))
        else:
            sig.append((name, -1, -1))
    notes_dir = root / "notes"
    if notes_dir.exists():
        for p in sorted(notes_dir.rglob("*.md")):
            st = p.stat()
            sig.append((str(p.relative_to(root)),
                        st.st_mtime_ns, st.st_size))
    return tuple(sig)


def truth_manifest(root) -> dict:
    """逐真相文件算哈希（索引台账与对账的范围，MM-05）。

    结果按文件签名备忘（见 _MANIFEST_CACHE）：签名未变直接回
    备忘副本，变了才重算——对账结论不变，成本不再随规模线性涨。
    """
    root = Path(root)
    sig = _manifest_signature(root)
    cached = _MANIFEST_CACHE.get(str(root))
    if cached and cached[0] == sig:
        return dict(cached[1])
    manifest = {}
    for name in project_mod.TRUTH_FILES:
        p = root / name
        if p.exists():
            manifest[name] = sha256_file(p)
    notes_dir = root / "notes"
    if notes_dir.exists():
        for p in sorted(notes_dir.rglob("*.md")):
            manifest[str(p.relative_to(root))] = sha256_file(p)
    _MANIFEST_CACHE[str(root)] = (sig, manifest)
    return dict(manifest)


def _collect_chunks(pkg: dict, root) -> list:
    chunks = []
    for f in pkg.get("facts") or []:
        chunks.append({
            "source_kind": "fact",
            "source_id": f.get("fact_id"),
            "anchor": f.get("object_id"),
            "text": f.get("statement") or "",
        })
    notes_dir = Path(root) / "notes"
    if notes_dir.exists():
        for p in sorted(notes_dir.rglob("*.md")):
            rel = str(p.relative_to(root))
            section = ""
            buf: list = []
            anchor = "top"
            for line in p.read_text(encoding="utf-8").splitlines() + ["#"]:
                if line.startswith("#"):
                    text = "\n".join(buf).strip()
                    if text:
                        chunks.append({
                            "source_kind": "note",
                            "source_id": f"note:{rel}#{anchor}",
                            "anchor": rel, "text": text})
                    anchor = line.lstrip("# ").strip() or "section"
                    buf = []
                else:
                    buf.append(line)
    return chunks


def chunk_id(model: str, source_kind: str, source_id: str, text: str) -> str:
    """块 ID 含嵌入模型名（MM-04）：换模型即平行新 ID，天然不碰撞。"""
    digest = component_hash({"model": model, "kind": source_kind,
                             "id": source_id, "text": text})
    return f"chk_{digest[:24]}"


# ---------------------------------------------------------------- 构建

def build_index(root) -> dict:
    """从真相文件全量构建索引（.index 整删重建的安全实现）。

    只动 .index 目录内的文件；真相文件只读。构建后写台账并回写
    登记头的索引摘要。
    """
    root = Path(root)
    pkg = project_mod.load_package(root)
    if pkg.get("memory") is None:
        raise IndexError_([f"记忆项目不存在或缺登记头：{root}"])
    memory = pkg["memory"]
    resolved = resolve_embedder(memory)
    emb = resolved["embedder"]

    index_dir = root / INDEX_DIR
    index_dir.mkdir(parents=True, exist_ok=True)
    db_path = index_dir / INDEX_DB
    if db_path.exists():
        db_path.unlink()

    manifest = truth_manifest(root)
    chunks = _collect_chunks(pkg, root)
    con = sqlite3.connect(db_path)
    try:
        backend = _vec_backend(con)
        con.execute("CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, "
                    "source_kind TEXT, source_id TEXT, anchor TEXT, "
                    "model TEXT, dim INTEGER, vector TEXT)")
        con.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5("
                    "chunk_id UNINDEXED, source_kind UNINDEXED, "
                    "source_id UNINDEXED, text)")
        if backend == "sqlite-vec":
            con.execute(
                f"CREATE VIRTUAL TABLE chunks_vec USING vec0("
                f"chunk_id TEXT PRIMARY KEY, embedding float[{emb.dim}])")
        for c in chunks:
            cid = chunk_id(emb.model, c["source_kind"], c["source_id"],
                           c["text"])
            vec = emb.embed(c["text"])
            if len(vec) != emb.dim:
                raise IndexError_(
                    [f"嵌入维度不符：期望 {emb.dim}，实得 {len(vec)}"
                     f"（块 {cid}）；请按台账指明的路径重建索引"])
            con.execute("INSERT OR REPLACE INTO chunks VALUES "
                        "(?,?,?,?,?,?,?)",
                        (cid, c["source_kind"], c["source_id"],
                         c["anchor"], emb.model, emb.dim,
                         json.dumps(vec)))
            con.execute("INSERT INTO chunks_fts VALUES (?,?,?,?)",
                        (cid, c["source_kind"], c["source_id"],
                         _fts_text(c["text"])))
            if backend == "sqlite-vec":
                con.execute("INSERT OR REPLACE INTO chunks_vec VALUES "
                            "(?,?)", (cid, json.dumps(vec)))
        con.commit()
    finally:
        con.close()

    state = {
        "kind": "light-memory/index-state",
        "version": "1.0",
        "built_at": utcnow(),
        "embedder": {k: resolved[k] for k in
                     ("registered_provider", "registered_model",
                      "effective", "model", "dim", "note")},
        "backend": backend,
        "truth_files": {rel: {"sha256": h, "status": "done"}
                        for rel, h in sorted(manifest.items())},
        "truth_manifest_hash": component_hash(manifest),
        "counts": {
            "chunks": len(chunks),
            "fact_chunks": sum(1 for c in chunks
                               if c["source_kind"] == "fact"),
            "note_chunks": sum(1 for c in chunks
                               if c["source_kind"] == "note"),
        },
    }
    (index_dir / INDEX_STATE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    memory["index"] = {"status": "built",
                       "embedder_effective": resolved["effective"],
                       "model": resolved["model"],
                       "built_at": state["built_at"],
                       "truth_manifest_hash": state["truth_manifest_hash"]}
    project_mod.save_memory(root, memory)
    return state


def index_status(root) -> dict:
    """对账：台账哈希 vs 当前真相文件。absent/current/stale 三态明示。"""
    root = Path(root)
    state_path = root / INDEX_DIR / INDEX_STATE
    if not state_path.exists():
        return {"status": "absent", "changed": [], "embedder": None}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    current = truth_manifest(root)
    recorded = {rel: v.get("sha256")
                for rel, v in (state.get("truth_files") or {}).items()}
    changed = sorted(rel for rel, h in current.items()
                     if recorded.get(rel) != h)
    changed += sorted(rel for rel in recorded if rel not in current)
    return {"status": "stale" if changed else "current",
            "changed": changed,
            "embedder": state.get("embedder"),
            "backend": state.get("backend"),
            "built_at": state.get("built_at"),
            "counts": state.get("counts")}


def _fts_text(text: str) -> str:
    """FTS 入索引形态：与查询侧同一 tokenizer 切分后以空格连接。

    FTS5 的 unicode61 把连续中文当作单个 token，整段入索引则子串
    查询永不命中；两侧统一切分（中文单字 + 拉丁词）后才对得上。
    chunks 表保留原文，FTS 表只存切分形态（索引是派生物，允许变形）。
    """
    return " ".join(tokenize(text))


# ---------------------------------------------------------------- 检索原语
# 三路融合与渐进披露是 Phase 2；此处只给索引层可用的两路原语，
# 供构建验收与 Phase 2 管线消费。

def _open_db(root):
    db_path = Path(root) / INDEX_DIR / INDEX_DB
    if not db_path.exists():
        raise IndexError_(["索引不存在：先运行 index rebuild"])
    return sqlite3.connect(db_path)


def _query_units(query: str) -> list:
    """查询侧证据单元：拉丁/数字 token 原样成单元，中文取相邻字对
    （bigram）成单元——单字命中多是巧合子串（如「采集」对「数据集」），
    不构成词法证据；相邻字对才是中文的词级信号。查询只有一个单元
    时（如两字词）该单元即全部证据，不再加门槛。"""
    tokens = tokenize(query)
    units: list = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if len(tok) == 1 and "一" <= tok <= "鿿":
            j = i
            while j < len(tokens) and len(tokens[j]) == 1 \
                    and "一" <= tokens[j] <= "鿿":
                j += 1
            run = tokens[i:j]
            if len(run) == 1:
                units.append((run[0],))
            else:
                units.extend(tuple(run[k:k + 2])
                             for k in range(len(run) - 1))
            i = j
        else:
            units.append((tok,))
            i += 1
    return units


def _matched_units(unit_set: set, chunk_tokens: list) -> int:
    """块与查询共享的证据单元数（bigram 须在块内相邻出现）。"""
    seq = set()
    for k in range(len(chunk_tokens) - 1):
        seq.add((chunk_tokens[k], chunk_tokens[k + 1]))
    seq.update((t,) for t in chunk_tokens)
    return len(unit_set & seq)


def _texts_by_ids(con, chunk_ids) -> dict:
    """按 chunk_id 取 FTS 切分文本（只取候选行）。

    D-S1：旧实现每次查询整表载入 chunks_fts_content（O(规模)），
    改为按候选 ID 分批 IN 查询——候选数由 MATCH 结果界定
    （<= max(limit*20, 200)），与索引规模无关。
    """
    out = {}
    ids = list(dict.fromkeys(chunk_ids))
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        marks = ",".join("?" for _ in part)
        for cid, text in con.execute(
                "SELECT c0, c3 FROM chunks_fts_content "
                f"WHERE c0 IN ({marks})", part):
            out[cid] = text
    return out


def search_fts(root, query: str, limit: int = 10) -> list:
    con = _open_db(root)
    try:
        units = _query_units(query)
        if not units:
            return []
        unit_set = set(units)
        expr = " OR ".join(
            " ".join(f'"{t}"' for t in u) for u in units)
        rows = con.execute(
            "SELECT chunk_id, source_kind, source_id, bm25(chunks_fts) "
            "FROM chunks_fts WHERE chunks_fts MATCH ? "
            "ORDER BY bm25(chunks_fts) LIMIT ?",
            (expr, max(limit * 20, 200))).fetchall()
        if len(unit_set) <= 1:
            rows = rows[:limit]
            return [{"chunk_id": r[0], "source_kind": r[1],
                     "source_id": r[2], "score": r[3]} for r in rows]
        texts = _texts_by_ids(con, [r[0] for r in rows])
        out = []
        for r in rows:
            chunk_tokens = (texts.get(r[0]) or "").split()
            if _matched_units(unit_set, chunk_tokens) >= 2:
                out.append({"chunk_id": r[0], "source_kind": r[1],
                            "source_id": r[2], "score": r[3]})
                if len(out) >= limit:
                    break
        return out
    finally:
        con.close()


# 跨语言扩展用的停用字（与 bench 判据无关，仅剔语法字对）。
_EXPAND_STOP_CHARS = set("的了是在与及中为有个其之和或把被从向")


def expand_query(root, query: str) -> str:
    """跨语言查询扩展（伪相关反馈）：纯拉丁查询对中文语料先向量
    召回 top-8 块，从其 token 流中抽高频中文 bigram 拼回查询，
    使中文事实获得词法路与更贴合的向量表示。查询含中文时原样
    返回（不触发）；抽不到可靠 bigram（至少在 2 个块中出现）
    时也原样返回，绝不凭空造词。"""
    tokens = tokenize(query)
    if any(len(t) == 1 and "一" <= t <= "鿿" for t in tokens):
        return query
    try:
        top = search_vector(root, query, limit=8)
    except Exception:
        return query
    if not top:
        return query
    con = _open_db(root)
    try:
        texts = _texts_by_ids(con, [row["chunk_id"] for row in top])
    finally:
        con.close()
    from collections import Counter
    counts: Counter = Counter()
    for row in top:
        toks = (texts.get(row["chunk_id"]) or "").split()
        grams = set()
        for k in range(len(toks) - 1):
            a, b = toks[k], toks[k + 1]
            if len(a) == 1 and len(b) == 1 \
                    and "一" <= a <= "鿿" and "一" <= b <= "鿿" \
                    and a not in _EXPAND_STOP_CHARS \
                    and b not in _EXPAND_STOP_CHARS:
                grams.add(a + b)
        counts.update(grams)
    picked = [g for g, c in counts.most_common(6) if c >= 2]
    if not picked:
        return query
    return query + " " + " ".join(picked)


#: 向量行进程内缓存：键为索引库路径，值为（文件签名，解析后的
#: 向量行）。索引是影子派生物（可整删重建）：库文件一变（重建/
#: 替换）签名即变、缓存失效重读，结果与每次全量读完全一致；
#: 省掉的是每查一次对全部向量做 json.loads 的 O(规模) 解析（D-S1）。
_VECTOR_CACHE: dict = {}


def _vector_rows(root) -> list:
    db_path = Path(root) / INDEX_DIR / INDEX_DB
    if not db_path.exists():
        raise IndexError_(["索引不存在：先运行 index rebuild"])
    st = db_path.stat()
    sig = (st.st_mtime_ns, st.st_size)
    cached = _VECTOR_CACHE.get(str(db_path))
    if cached and cached[0] == sig:
        return cached[1]
    con = sqlite3.connect(db_path)
    try:
        raw = con.execute(
            "SELECT chunk_id, source_kind, source_id, vector FROM chunks"
        ).fetchall()
    finally:
        con.close()
    rows = [(cid, kind, sid, json.loads(vec_json))
            for cid, kind, sid, vec_json in raw]
    _VECTOR_CACHE[str(db_path)] = (sig, rows)
    return rows


def _memory_head(root):
    """只读登记头（向量路只需嵌入登记，不必整包解析；D-S1）。"""
    p = Path(root) / project_mod.FILES["memory"]
    if not p.exists():
        return None
    return load_structured(p)


def search_vector(root, query: str, limit: int = 10) -> list:
    resolved = resolve_embedder(_memory_head(root) or {})
    emb = resolved["embedder"]
    qv = getattr(emb, "embed_query", emb.embed)(query)
    scored = []
    for cid, kind, sid, vec in _vector_rows(root):
        dot = sum(a * b for a, b in zip(qv, vec))
        scored.append({"chunk_id": cid, "source_kind": kind,
                       "source_id": sid, "score": round(dot, 6)})
    scored.sort(key=lambda r: -r["score"])
    return scored[:limit]
