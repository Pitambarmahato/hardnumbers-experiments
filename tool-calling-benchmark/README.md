# Local LLM Tool-Calling Benchmark

Reproducible benchmark of two local LLMs (Qwen3 14B and Llama 3.2 3B) on the
core task an AI agent LLM has to get right: produce a valid, schema-correct
JSON tool call when offered a small set of plausible productivity tools.

Companion to the Hard Numbers article:
**[Local LLM Tool Calling for AI Agents: Qwen3 14B vs Llama 3.2 3B on Apple Silicon](https://hardnumbers.dev/articles/local-llm-tool-calling-for-ai-agents-qwen3-14b-vs-llama-3-2-3b-on-apple-silicon)**

## What this measures

Three independent pass/fail signals per (model, prompt) pair:

- **Parse rate** — % of calls where the model output was extractable as JSON
  (handles raw JSON, ` ```json ` fences, free-text containing a `{...}` block,
  and `<think>` stripping for Qwen3)
- **Schema-valid rate** — % where the JSON is a `{name, arguments}` object
  and `name` is in the offered toolset and `arguments` satisfy required fields,
  types, and enums
- **Tool-correct rate** — % of schema-valid calls that picked the *expected*
  tool (the one a reasonable human would pick for the prompt). Catches the
  failure mode where the model picks a valid but wrong tool — the worst kind,
  because the JSON parses and the agent happily calls the wrong function

Plus wall-clock latency and tokens/sec throughput.

## Hardware

- Apple M2 (8 cores)
- 24 GB unified memory
- macOS 15
- Local Ollama install (`localhost:11434`)

## Models tested

| Model              | Ollama tag          | Quant | Params  |
| ------------------ | ------------------- | ----- | ------- |
| Qwen3 14B          | `qwen3:14b`         | Q4_K_M| 14.8 B  |
| Llama 3.2 3B       | `llama3.2:latest`   | Q4_0  | 3.2 B   |

## Tools offered

Six plausible productivity-agent tools in OpenAI function-calling JSON schema
style (Ollama accepts the same format):

| Tool            | Purpose                          |
| --------------- | -------------------------------- |
| `get_weather`   | Current weather for a city       |
| `search_articles`| Search the publication archive   |
| `create_task`   | Add a to-do item                 |
| `send_email`    | Email a recipient                |
| `lookup_user`   | Find a user by email             |
| `book_meeting`  | Book a calendar event            |

Each tool has a real JSON schema with `required` fields, enums where
appropriate (e.g. `priority: ["low","medium","high"]`), and type constraints
(string / integer / array).

## Workload

Ten prompts that should each trigger exactly one tool call. Mix of one-shot
("what's the weather in Tokyo") and more complex ("book a 30-minute design
review tomorrow at 2pm with sam@ and jordan@"). Each prompt has a hand-scored
expected tool.

## Headline numbers (from `results.json`, Aug 2026)

| Metric              | Qwen3 14B | Llama 3.2 3B |
| ------------------- | --------- | ------------ |
| **Parse rate**      | 90% (9/10)| 90% (9/10)   |
| **Schema-valid rate**| 90% (9/10)| 60% (6/10)   |
| **Tool-correct rate**| **90% (9/10)** | **50% (5/10)** |
| Wall time, median   | 27.8 s    | **1.1 s**    |
| Tokens/sec, median  | 6.7       | **26.6**     |

The 3B is ~25× faster wall-time on the median task, but its tool correctness
is a coin flip. The 14B picks the right tool 9/10. For an unsupervised agent
loop, the 14B is the one you can ship; the 3B needs retries and a fallback
strategy. See the article for the failure-by-failure breakdown and the
specific schema-violation patterns the 3B repeats.

## How to reproduce

```bash
# 1. Install Ollama and pull both models
brew install ollama
ollama serve &
ollama pull qwen3:14b
ollama pull llama3.2:latest

# 2. Install the one Python dep
pip install httpx

# 3. Run the benchmark (takes ~5-8 min)
python3 benchmark.py
# → writes a fresh tool_calling_<timestamp>.json into ./experiments/runs/
```

The benchmark uses `temperature=0` for determinism, `num_predict=512`, and
handles both the `tool_calls` structured path and the raw-JSON-in-content
path that smaller models tend to emit.

## Files

- `benchmark.py` — the experiment driver (Ollama chat API + JSON extraction
  + schema validator)
- `results.json` — the exact run that the article's tables cite
