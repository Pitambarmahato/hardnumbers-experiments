# quant-speed-test

Q4_K_M vs MXFP4 inference speed test on Apple M2 silicon.

## What this tests

Two local LLMs (Qwen3-14B at Q4_K_M, gpt-oss-20B at MXFP4) on the
same 263-character code-completion prompt, 3 trials each. The result:
Q4_K_M is ~1.8x faster than MXFP4 on M2 (warm cache, both models
resident in unified memory).

## How to run

```bash
# Install Ollama from https://ollama.com, then:
ollama pull qwen3:14b
ollama pull gpt-oss:20b

# Set up venv
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run
.venv/bin/python src/benchmark.py
```

The 6-run benchmark takes about 6 minutes on an M2 24GB Mac. Results
written to `results/local_llm_speed_<timestamp>.json`.

## Method

Single-prompt code-completion test, max 200 output tokens, temperature 0.
First trial of each model is the cold-load control. Trials 2 and 3 are
the warm-cache apples-to-apples comparison. Timing source: Ollama's
`/api/chat total_duration` field.

## Article

The full writeup is at https://hardnumbers.dev/articles/q4-vs-mxfp4-on-m2-which-quant-is-faster
