# local-embeddings-m2

Benchmark of three local embedding models (Nomic Embed, mxbai-embed-large,
BGE-M3) on a 20-chunk RAG corpus drawn from Hard Numbers published articles.

The question: which small open-weights embedding model is the right default
for a RAG pipeline on a 24 GB Apple Silicon machine, and does the published
MTEB leaderboard order match what happens on a real workload?

## TL;DR

Counter-intuitive result: Nomic Embed (274 MB, the smallest) won on every
metric. 100% hit@1, 23.7 ms per chunk, 8.6 ms per query. mxbai-embed-large
(669 MB) got 87% hit@1. BGE-M3 (1.2 GB) got 93% but was 2x slower.

| Model | Size | Chunk ms | Query ms | hit@1 | hit@3 | MRR |
|-------|------|----------|----------|-------|-------|-----|
| Nomic | 274 MB | 23.7 | 8.6 | **100%** | 100% | 1.000 |
| mxbai | 669 MB | 43.8 | 16.3 | 86.7% | 93.3% | 0.917 |
| BGE-M3 | 1.2 GB | 49.7 | 23.8 | 93.3% | 100% | 0.967 |

15 hand-curated queries against 20 chunks. All three models run via Ollama
on the same M2 24 GB machine. Full per-query results in
`results/embeddings_benchmark.json`.

## Why this matters

The published MTEB leaderboard has mxbai-embed-large at 64.68 and Nomic
at 62.39. On this corpus, the order flipped. The smallest, fastest model
won. This is a real-world counter-example to the "use the best MTEB score"
default and worth documenting.

## Quick start

```bash
# Pull the three models
ollama pull nomic-embed-text
ollama pull mxbai-embed-large
ollama pull bge-m3

# Run the benchmark (stdlib only, no extra deps)
python3 src/benchmark.py
```

The script runs each model, measures embedding throughput, computes cosine
similarity, scores hit@1/hit@3/MRR, and writes `results/embeddings_benchmark.json`.

## What I did not test

- **Larger corpora.** 20 chunks is small. The 100% hit@1 is partly a
  function of the test being easy. Re-test with 1,000+ chunks before
  generalizing.
- **Multilingual.** BGE-M3 is explicitly multilingual; the others are
  primarily English. Unfair to BGE-M3 in this benchmark.
- **Hybrid retrieval.** BGE-M3 emits dense + sparse + multi-vector
  outputs; this benchmark only used dense.
- **Reranking.** A cross-encoder reranker on top of any of these would
  likely equalize retrieval quality.
- **Other models.** Qwen3-Embedding-8B is the obvious omission but
  doesn't fit on a 24 GB machine alongside a 14 B LLM.
