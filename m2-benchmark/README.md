# Apple Silicon M2 Inference Benchmark

Reproducible benchmark of two local LLMs (Qwen3 14B and Llama 3.2 3B) on an
Apple M2 laptop. Compares throughput, latency, and accuracy on a small set of
real reasoning, math, code, and instruction-following tasks.

Companion to the Hard Numbers article:
**[Qwen3 14B vs Llama 3.2 3B on Apple Silicon M2: An Honest Benchmark](https://hardnumbers.dev/articles/qwen3-14b-vs-llama-3-2-3b-on-apple-silicon-m2-an-honest-benc)**

## What this measures

- Tokens/sec throughput per model (gen time only)
- Wall-clock latency per prompt
- Accuracy on a 8-task suite: reasoning, math, code (write + fix), instruction
  following (constrained outputs and translation)

## Hardware

- Apple M2 (8 cores: 4 performance + 4 efficiency)
- 24 GB unified memory
- macOS 15, Metal 3
- Local Ollama install (`localhost:11434`)

## Models tested

| Model              | Ollama tag          | Quant | Params  | On-disk |
| ------------------ | ------------------- | ----- | ------- | ------- |
| Qwen3 14B          | `qwen3:14b`         | Q4_K_M| 14.8 B  | 9.3 GB  |
| Llama 3.2 3B       | `llama3.2:latest`   | Q4_0  | 3.2 B   | 2.0 GB  |

## Headline numbers (from `results.json`, Aug 2026)

| Metric                      | Qwen3 14B | Llama 3.2 3B |
| --------------------------- | --------- | ------------ |
| Median tokens/sec           | 8.25      | 27.3         |
| Median wall time per prompt | 31 s      | 9.7 s        |
| Accuracy (8-task suite)     | 5/8       | 7/8          |

The 3B is ~3.3× faster on tokens/sec. The 14B is a "thinking" model that
burns its output budget on chain-of-thought; with the 256-token `num_predict`
cap used here, it often gets cut off mid-thought. For latency-sensitive local
work on M2, the 3B is the better pick. See the article for the full discussion.

## How to reproduce

```bash
# 1. Install Ollama and pull both models
brew install ollama
ollama serve &
ollama pull qwen3:14b
ollama pull llama3.2:latest

# 2. Run the benchmark (takes ~10-15 min)
python3 benchmark.py
# → writes a fresh m2_benchmark_<timestamp>.json into ./experiments/runs/
```

The benchmark uses `temperature=0` for determinism, `num_predict=256`, and
includes a warmup pass so the first-prompt model-load latency doesn't poison
the numbers.

## Files

- `benchmark.py` — the experiment driver (Ollama HTTP client + keyword scoring)
- `results.json` — the exact run that the article's tables cite
