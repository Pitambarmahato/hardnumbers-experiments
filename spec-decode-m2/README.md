# spec-decode-m2

Speculative decoding on an M2-class Mac with 24 GB of unified memory.

The question: does pairing a small draft model with a larger target model
actually speed up inference on Apple Silicon? Published benchmarks on
discrete GPUs report 1.5-2.0x speedup. M2 has different memory-bandwidth
characteristics, so we ran the test ourselves.

## TL;DR

It did not help. With Ollama 0.12.8, qwen3:14b at Q4_K_M, and a qwen2.5
draft model (either 0.5B or 1.5B), speculative decoding **slowed down**
inference by 5-10%:

| Config | Median tok/s | vs baseline |
|---|---|---|
| No draft (baseline) | 4.0 | 1.00x |
| Draft: qwen2.5:0.5b | 3.8 | **0.95x** |
| Draft: qwen2.5:1.5b | 3.6 | **0.90x** |

The smaller draft was less harmful than the larger one, but neither was a
speedup. 5 trials per config, deterministic settings, same prompt. Full
numbers in `results/spec_decode.json`.

## Why this matters

Speculative decoding is the recommended pattern for fast local LLM serving
in 2026. Most write-ups assume it always helps, or at minimum doesn't hurt.
The data on M2 24GB says otherwise: the draft model's overhead is not
amortized by enough acceptance to beat the baseline.

## Quick start

```bash
# Pull the target and draft models
ollama pull qwen3:14b
ollama pull qwen2.5:0.5b
ollama pull qwen2.5:1.5b

# Start Ollama (it should already be running)
ollama serve &

# Run the benchmark
python3 src/benchmark.py
```

The script runs 5 trials per config, prints per-trial results, and writes
`results/spec_decode.json` with the full per-trial numbers.

## Hardware

- Apple M2 (10-core GPU, 16-core Neural Engine)
- 24 GB unified memory, macOS 15
- Ollama 0.12.8, Metal backend
- No other significant load during the test

## Caveats

- Single-batch inference. Speculative decoding's biggest wins are
  high-throughput batched serving, which is not what a single user on a
  laptop does. The numbers here are the *interactive* use case.
- Different acceptance rate target. We measured end-to-end tok/s, not
  acceptance rate. A high acceptance rate on a different prompt could
  change the result.
- Different draft. A draft model from the same family (Qwen 3 1.7B)
  would likely have a higher acceptance rate than Qwen 2.5 0.5B and
  could turn the result around. We didn't have one installed.
- Newer Ollama. v0.32.6 (Aug 2026) added MTP-based automatic
  speculative decoding that doesn't need a separate draft model. This
  benchmark uses 0.12.8 with manual draft model.
