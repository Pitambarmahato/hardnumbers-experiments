# Hard Numbers — Experiments

Reproducible code and raw results for every benchmark published on
[hardnumbers.dev](https://hardnumbers.dev).

One directory per published article. Each one contains the exact benchmark
script and the exact results JSON that the article's tables cite, so a
reader can either rerun the experiment on their own machine or audit the
underlying numbers without having to trust the writeup.

## Index

| Article | Experiment dir | What it measures |
| ------- | -------------- | ---------------- |
| [Qwen3 14B vs Llama 3.2 3B on Apple Silicon M2: An Honest Benchmark](https://hardnumbers.dev/articles/qwen3-14b-vs-llama-3-2-3b-on-apple-silicon-m2-an-honest-benc) | [`m2-benchmark/`](./m2-benchmark/) | Throughput, latency, accuracy on a small reasoning / math / code / instruction suite |
| [Local LLM Tool Calling for AI Agents: Qwen3 14B vs Llama 3.2 3B on Apple Silicon](https://hardnumbers.dev/articles/local-llm-tool-calling-for-ai-agents-qwen3-14b-vs-llama-3-2-3b-on-apple-silicon) | [`tool-calling-benchmark/`](./tool-calling-benchmark/) | JSON tool-call reliability (parse, schema-valid, tool-correct) on a 10-prompt agent suite |

## How to read this repo

- The **article** is on hardnumbers.dev — that's the human-readable writeup
  with the framing, the methodology summary, and the conclusions
- The **directory** here is the underlying evidence: the script that ran
  the experiment, and the raw JSON output that fed the tables in the article
- A new article on hardnumbers.dev is matched to a new directory here. If
  you can't find one, ping us — the article is misconfigured

## Reproduction standard

Every experiment in this repo:

1. **Runs locally** on a single consumer laptop. No cluster, no API budget.
2. **Deterministic** — `temperature=0`, fixed model versions, fixed prompts.
3. **Self-contained** — the script, the results, and a README are all in
   the same directory. No external data files.
4. **Honest** — if a model failed a task, the failure is in the JSON. We
   don't edit the output to make the numbers prettier.

## Hardware baseline

The first two experiments were both run on:

- Apple M2, 24 GB unified memory, macOS 15
- Ollama for model serving
- Python 3.12

If your hardware is meaningfully different, expect different throughput
numbers but the same correctness ranking in most cases.
