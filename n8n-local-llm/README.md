# n8n + Local LLM Size Benchmark

**Question:** What's the smallest local LLM size that gives acceptable accuracy on common n8n workflows (classification, extraction, summarization, RAG Q&A, tool-calling) on Apple Silicon M2?

**Short answer:** The 3B model matches or beats the 14B model on 4 of 5 workflow types at 5-9x the speed. The 1.5B model is the right pick for tool-calling-heavy pipelines. The 14B model is only the right pick for complex multi-step tool-calling where reasoning matters more than latency.

**Counter-intuitive finding:** The 14B model is *slower* AND *worse* than the 3B on extraction (0.87 vs 1.00 accuracy, 9x slower). The 14B's only accuracy win is tool-calling, and even there the 1.5B beats it (1.00 vs 0.80 at 14x the speed).

See the full article at [hardnumbers.dev/articles/5-local-llm-sizes-in-n8n-which-one-do-you-actually-need](https://hardnumbers.dev/articles/5-local-llm-sizes-in-n8n-which-one-do-you-actually-need).

## What this benchmark tests

5 model sizes from the Qwen2.5 family × 5 n8n workflows × multiple runs per cell:

| Model | Parameters | Disk size |
|---|---:|---:|
| `qwen2.5:0.5b` | 0.5B | 397 MB |
| `qwen2.5:1.5b` | 1.5B | 986 MB |
| `qwen2.5:3b`   | 3.1B | 1.9 GB |
| `qwen2.5:7b`   | 7.6B | 4.4 GB |
| `qwen2.5:14b`  | 14.8B | 8.9 GB |

Workflows:
1. **classification** — categorize a support email as billing / technical / other
2. **extraction** — pull total, currency, date from an invoice as JSON
3. **summarization** — 500-word meeting transcript → 3 bullet points
4. **rag_qa** — answer a question using only provided document excerpts
5. **tool_calling** — pick the right tool from a list with the right arguments

## What this directory contains

- `data/test_workflows.json` — the 5 workflows with system prompts and test inputs
- `src/run_ollama.py` — direct Ollama benchmark runner
- `src/run_n8n.py` — n8n webhook benchmark runner
- `src/create_n8n_workflows.py` — creates the 5 n8n workflows via API
- `n8n_workflow_urls.json` — the created workflow IDs and webhook URLs
- `results/ollama_qwen2.5_*.json` — per-run direct Ollama results
- `results/ollama_qwen2.5_*_summary.json` — per-workflow medians
- `results/n8n_qwen2.5_*.json` — per-run n8n results
- `results/n8n_qwen2.5_*_summary.json` — per-workflow medians

## How to run

```bash
# 1. Install Ollama from https://ollama.com
ollama pull qwen2.5:0.5b
ollama pull qwen2.5:1.5b
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b
ollama pull qwen2.5:14b

# 2. (Optional) Install n8n via Docker
docker run -d --name n8n \
  -p 5678:5678 \
  -v n8n_data:/home/node/.n8n \
  docker.n8n.io/n8nio/n8n

# 3. Set up venv and dependencies
python -m venv .venv
.venv/bin/pip install requests

# 4. Run the direct-Ollama benchmark (no n8n needed)
.venv/bin/python src/run_ollama.py all

# 5. (Optional) Build the 5 n8n workflows via API
#    First: log into n8n at http://localhost:5678 and create an owner account
#    Then: extract the n8n-auth cookie and save to /tmp/n8n-cookies.txt
.venv/bin/python src/create_n8n_workflows.py

# 6. (Optional) Run the n8n benchmark
.venv/bin/python src/run_n8n.py all --runs 3
```

Total time on M2 24GB: ~45 minutes for direct Ollama, ~30 minutes for n8n.

## Hardware

- Apple M2, 24 GB unified memory
- macOS Tahoe 26.0
- Ollama 0.12.8
- n8n latest (1.x), Docker image `docker.n8n.io/n8nio/n8n`

## Limitations

- n=5 runs per cell (direct Ollama), n=3 (n8n). Wide confidence intervals on medians; rankings are robust, specific accuracy differences in 0.05-0.10 range are not.
- One model family (Qwen2.5). Pattern likely generalizes to Llama 3.2, Gemma 2, Phi-3.5.
- One n8n version.
- One OS (macOS Tahoe 26.0 on M2).
- No streaming.
- Summarization is fragile — all models fail equally on the specific-bullet task.
