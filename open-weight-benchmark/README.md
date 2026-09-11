# Open-Weight LLM Head-to-Head

A reproducible benchmark comparing three Apache 2.0 open-weight language models in
the 20-30B parameter class:

- **gpt-oss-20B** — OpenAI's first open-weight model since GPT-2 (Apache 2.0, MXFP4 native)
- **Qwen3-30B-A3B-Instruct-2507** — Alibaba's MoE with 30B total / 3B active params (Apache 2.0)
- **Mistral-Small-24B-Instruct-2501** — Mistral's strongest 24B-class model (Apache 2.0)

All three are commercially usable, all three run on a single 24 GB consumer device,
and all three were released within the last 18 months. They are the three biggest
open-weight model families that can plausibly replace a paid API for local
inference.

## What this benchmark measures

| Task       | Items | What it tests                                  |
|------------|-------|------------------------------------------------|
| MMLU dev   | 50    | Multiple-choice general knowledge (10 subjects)|
| GSM8K test | 30    | Grade-school math word problems                |
| HumanEval+ | 20    | Python function synthesis (pass@1)             |
| IFEval     | 20    | Verifiable instruction-following constraints   |
| Speed      | 9 runs| tok/s at short / medium / long prompts         |

Total: 387 data points. Every prompt, every validator, every result is in this
repository. Nothing is hand-scored or "vibes-based."

## Layout

```
.
├── benchmark.py        # orchestrator: runs all tasks, saves results
├── data/
│   ├── mmlu_50.jsonl   # multiple-choice questions
│   ├── gsm8k_30.jsonl  # math word problems
│   ├── humaneval_20.jsonl  # code problems
│   └── ifeval_20.jsonl # instruction-following prompts + validators
├── results/            # one JSON per run, timestamped
└── README.md
```

## How to reproduce

Prerequisites: a machine with at least 24 GB of unified memory, Ollama 0.12+,
Python 3.10+.

```bash
# 1. Pull the three models (~47 GB total)
ollama pull gpt-oss:20b
ollama pull qwen3:30b-a3b-instruct-2507-q4_K_M
ollama pull mistral-small:24b-instruct-2501-q4_K_M

# 2. Run the full benchmark (~2.5 hours on M2 24GB)
python3 benchmark.py run

# 3. Or run a single task / model
python3 benchmark.py run --task mmlu
python3 benchmark.py run --model gpt-oss:20b
```

Every run writes to `results/results_<UTC-timestamp>.json`. The JSON contains the
exact prompt sent, the exact response received, the parsed answer, and the
correctness verdict for every item.

## Why these three (and not others)

- **gpt-oss-20B**: the news. Apache 2.0 from OpenAI on 2025-08-05, MXFP4 native,
  runs on 16 GB. The "is OpenAI's open release any good?" question.
- **Qwen3-30B-A3B**: the incumbent. Apache 2.0 from Alibaba, MoE architecture with
  3 B active parameters, ~18 GB on disk. The strongest 30 B-class open weight on
  most public leaderboards.
- **Mistral-Small-24B**: the European alternative. Apache 2.0, dense 24 B, ~14 GB.
  Best-in-class from Mistral.

We deliberately did not include the larger gpt-oss-120B (won't fit on 24 GB), the
Qwen3-235B flagship (won't fit on 24 GB), or any closed-weights model (the
question we are answering is "what can I run locally?").

## Limitations

- **50 / 30 / 20 / 20 / 9 is small.** Real leaderboards use 14 000 / 1 300 / 164 /
  500 / full sweep. Our subset has high variance: a 1-question swing moves MMLU
  by 2 percentage points. Treat per-task numbers as rough orderings, not exact
  gaps.
- **1 trial for accuracy, 3 trials for speed.** Accuracy is deterministic at
  temperature 0, so additional trials are wasted compute. Speed has thermal and
  scheduling noise, so we report 3 trials.
- **Hardware-specific speed.** Tokens/sec numbers are tied to the specific GPU /
  NPU / memory configuration we ran on. The *ranking* generalizes, the absolute
  numbers do not.
- **English only.** No multilingual evaluation.
- **No tool calling.** Tool-calling accuracy gets its own article.

## See also

Companion article on this site: "gpt-oss-20B vs Qwen3-30B vs Mistral-Small-24B:
A Real Benchmark of Apache 2.0 Open-Weight Models."

Other experiments in this repo:

- `m2-benchmark/` — single-model speed tests on M2 24 GB
- `tool-calling-benchmark/` — tool-calling accuracy for local LLMs
- `mlx-vs-llama-cpp/` — engine comparison on identical hardware

## License

Code: MIT. Data files retain their original licenses — MMLU and GSM8K are
research-only; HumanEval+ is Apache 2.0; IFEval prompts in this repo are
original.
