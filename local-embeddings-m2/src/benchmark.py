"""Local embeddings benchmark: Nomic vs mxbai vs BGE-M3 on M2 24GB.

Embeds a 20-chunk corpus (drawn from Hard Numbers published articles) and
runs 15 queries against each model, measuring:

- Embedding throughput (ms per chunk, ms per query)
- Retrieval quality: hit@1, hit@3, MRR

Three models, all via Ollama's /api/embeddings endpoint. The corpus is
deliberately small and the queries are hand-curated with known-correct
chunks, so the retrieval-quality numbers are not noise-immune; the point
is to see which model handles the same workload best.
"""
import json
import statistics
import time
import urllib.request
from pathlib import Path

URL = "http://localhost:11434/api/embed"
ROOT = Path(__file__).parent.parent
CORPUS = ROOT / "data" / "corpus.jsonl"
QUERIES = ROOT / "data" / "queries.json"
OUT = ROOT / "results" / "embeddings_benchmark.json"

MODELS = [
    "nomic-embed-text",
    "mxbai-embed-large",
    "bge-m3",
]


def load_corpus() -> list[dict]:
    rows = []
    with open(CORPUS) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_queries() -> list[dict]:
    return json.loads(QUERIES.read_text())["queries"]


def embed(texts: list[str], model: str) -> tuple[list[list[float]], float]:
    """Embed a batch of texts. Returns (vectors, total_wall_seconds)."""
    body = json.dumps({"model": model, "input": texts}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    wall = time.perf_counter() - t0
    return data["embeddings"], wall


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def evaluate(model: str, corpus: list[dict], queries: list[dict]) -> dict:
    """Embed everything for one model and compute retrieval quality + timing."""
    # Warmup: a single dummy embed so the model is loaded into memory
    embed(["warmup"], model)
    time.sleep(0.5)

    # Embed corpus
    texts = [c["text"] for c in corpus]
    chunk_vecs, chunk_wall = embed(texts, model)
    chunk_ms = (chunk_wall / len(texts)) * 1000

    # Embed queries
    qtexts = [q["text"] for q in queries]
    q_vecs, q_wall = embed(qtexts, model)
    q_ms = (q_wall / len(qtexts)) * 1000

    # Score retrieval
    hit1 = 0
    hit3 = 0
    mrr_sum = 0.0
    per_query = []
    for q, qv in zip(queries, q_vecs):
        scored = [(cosine(qv, cv), c["id"]) for cv, c in zip(chunk_vecs, corpus)]
        scored.sort(key=lambda x: -x[0])
        top_ids = [sid for _, sid in scored[:10]]
        if top_ids[0] in q["expected"]:
            hit1 += 1
        if any(t in q["expected"] for t in top_ids[:3]):
            hit3 += 1
        # MRR: first position where an expected id appears
        for rank, sid in enumerate(top_ids, 1):
            if sid in q["expected"]:
                mrr_sum += 1.0 / rank
                break
        per_query.append({"q": q["id"], "top1": top_ids[0], "top3": top_ids[:3]})

    n = len(queries)
    return {
        "model": model,
        "corpus_chunks": len(corpus),
        "queries": n,
        "chunk_embed_total_s": round(chunk_wall, 3),
        "chunk_embed_ms_each": round(chunk_ms, 1),
        "query_embed_total_s": round(q_wall, 3),
        "query_embed_ms_each": round(q_ms, 1),
        "hit_at_1": round(hit1 / n, 3),
        "hit_at_3": round(hit3 / n, 3),
        "mrr": round(mrr_sum / n, 3),
        "per_query": per_query,
    }


def main():
    corpus = load_corpus()
    queries = load_queries()
    print(f"Corpus: {len(corpus)} chunks from Hard Numbers articles")
    print(f"Queries: {len(queries)} hand-curated with known-correct chunks\n")

    all_results = []
    for model in MODELS:
        print(f"=== {model} ===")
        t0 = time.perf_counter()
        r = evaluate(model, corpus, queries)
        wall = time.perf_counter() - t0
        r["total_wall_s"] = round(wall, 2)
        all_results.append(r)
        print(f"  chunk embed:  {r['chunk_embed_ms_each']} ms/chunk ({r['chunk_embed_total_s']}s total)")
        print(f"  query embed:  {r['query_embed_ms_each']} ms/query")
        print(f"  hit@1:        {r['hit_at_1']:.1%}  ({int(r['hit_at_1']*len(queries))}/{len(queries)})")
        print(f"  hit@3:        {r['hit_at_3']:.1%}")
        print(f"  MRR:          {r['mrr']:.3f}")
        print(f"  total wall:   {r['total_wall_s']}s\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "experiment": "local-embeddings-m2",
        "description": "Nomic vs mxbai vs BGE-M3 for RAG retrieval, 20-chunk Hard Numbers corpus",
        "corpus_chunks": len(corpus),
        "queries": len(queries),
        "results": all_results,
    }, indent=2))
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
