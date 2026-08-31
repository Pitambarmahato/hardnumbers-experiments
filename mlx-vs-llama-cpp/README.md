# MLX vs llama.cpp on Apple Silicon M2

A real, reproducible benchmark of two local-LLM inference runtimes running
the **same Qwen3 14B Instruct model** on the **same MacBook Pro M2 (24 GB)**.

- **Engine A: Ollama 0.12.8** (which wraps `llama.cpp` + Metal backend), serving the GGUF Q4_K_M weights via the local HTTP API.
- **Engine B: mlx-lm 0.31.3** (Apple's MLX + Metal), serving the 4-bit MLX weights in-process from Python.

Both run the same prompts, same fixed seed, same `temperature: 0`, same
`max_tokens` budget. Three workloads × three trials per engine, plus a cold-load
measurement each.

## What it measures

- `wall_ms` — total request latency (the user-visible number)
- `gen_tok_s` (Ollama) — pure decode throughput (output tokens / eval duration)
- `gen_tok_s` (MLX) — total throughput (prefill + decode combined) — `mlx_lm.generate` doesn't expose prefill timing separately
- `prompt_tokens`, `gen_tokens` — actual counts per trial
- `cold_load` — first-request time including model load

## Workloads

| Workload | Input (target) | Output (max) | What it stresses |
|---|---|---|---|
| `short_chat` | ~20 tokens | 256 tokens | Realistic chat: prompt-eval is small, decode dominates |
| `long_context_rag` | ~3,000 tokens | 256 tokens | RAG / doc-Q&A: prompt-eval dominates |
| `long_generation_code` | ~80 tokens | 1,024 tokens | Code generation: decode dominates with longer output |

## How to run

```bash
# Install deps (one-time, on Apple Silicon)
pip3 install --user --break-system-packages mlx mlx-lm

# Pull the Ollama model (one-time, ~9.3 GB)
ollama pull qwen3:14b

# Download the MLX model into ./model (one-time, ~8.3 GB)
huggingface-cli download mlx-community/Qwen3-14B-4bit \
    --local-dir ./model

# Run the full benchmark (both engines, ~1 hour total)
python3 benchmark.py

# Or run engines separately (resume-safe):
python3 benchmark.py --engine mlx
python3 benchmark.py --engine ollama
```

## Results

The full numbers are in
[`mlx_vs_llamacpp_20260831_013128.json`](./mlx_vs_llamacpp_20260831_013128.json).
Headline wall-time medians (3 trials each) below.

| Workload | Ollama wall | MLX wall | MLX speedup |
|---|---|---|---|
| `short_chat` (256 in, 256 out) | 44.1 s | 31.1 s | **1.42× faster** |
| `long_context_rag` (3 000 in, 256 out) | 42.9 s | 75.0 s | 0.57× (Ollama faster) |
| `long_generation_code` (80 in, 1 024 out) | 166.4 s | 24.7 s* | **6.74× faster** |
| Cold load (first request) | 6.5 s | 3.7 s | **1.73× faster** |

\* `MLX` stopped at 220 tokens on the code workload (hit EOS after
producing the function), Ollama went to 1 024. So the wall-time comparison
there is partly a "how much did the model write" effect, not pure speed.

## TL;DR

- **MLX is faster for chat, agents, and code generation** — anywhere decode dominates.
- **Ollama (llama.cpp) is faster for long-context RAG** — its prompt-eval is dramatically faster (15-20k tok/s after warmup vs ~90 tok/s for MLX's prefill path).
- **MLX cold-loads in about half the time** — it's just a Python library, no HTTP server to start.
- **Pick Ollama if** your agent pipeline is RAG-heavy (large prompts, short answers).
- **Pick MLX if** your agent pipeline is chat/code-heavy (small prompts, longer answers), or if you want one Python process without a server in the middle.

## Caveats

- **Qwen3-Instruct's thinking mode is on by default** — the model emits a hidden thinking block before the answer. This is the same on both engines, so the relative comparison is fair, but the absolute `gen_tok_s` numbers reflect "thinking + answer" combined, not just answer.
- The `mlx_lm` Python API does not expose prefill timing separately, so the article reports total throughput for MLX and decode-only throughput for Ollama. Wall time is the apples-to-apples comparison.
- The `long_generation_code` workload was unfair: MLX's output was 220 tokens, Ollama's was 1 024, because the model on MLX wrote a more concise function and hit EOS. The wall-time number there should be read as "MLX finished a code task in 25 s; Ollama wrote longer output in 166 s", not "MLX is 6.7× faster at the same work".
- Both engines run on the same M2 with 24 GB unified memory. MLX weights are ~8.3 GB; the Ollama qwen3:14b image is ~9.3 GB. They live in the same physical memory; nothing changes between trials.

## Reproduction

The exact `benchmark.py` in this directory is the script that generated the
JSON. Re-run on any M-series Mac and the numbers will land within the same
ballpark — same models, same prompts, same scoring logic.

## Article

The full writeup of these results lives at:
[hardnumbers.dev/articles/mlx-vs-llama-cpp-on-apple-silicon](https://hardnumbers.dev/)
