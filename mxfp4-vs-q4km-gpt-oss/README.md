# MXFP4 vs Q4_K_M on gpt-oss-20B (what is actually inside the files)

Companion to the Hard Numbers article "MXFP4 vs Q4_K_M: 93% of gpt-oss Weights Are Identical".
Machine: Apple M2, 24 GB. llama.cpp 0.5.0 (Homebrew, build 7fe450e19). Date: 2026-10-03.
Files: bartowski/openai_gpt-oss-20b-GGUF `Q4_K_M` and `MXFP4`.

| File | Purpose |
|---|---|
| `tensor_anatomy.py` | bytes per tensor kind and storage type (needs `pip install gguf`) |
| `results/anatomy_*.txt` | its output for the Q4_K_M, MXFP4 and bf16 files |
| `results/hash_*.txt` | `llama-gguf-hash --sha256` per tensor, both files (398 of 459 identical) |
| `run_bench.sh`, `results/bench.log` | llama-bench pp512 / tg128, 3 reps |
| `run_ppl.sh`, `results/ppl.log` | WikiText-2 perplexity, 60 x 512 tokens (needs `wiki.test.raw` from Salesforce/wikitext, wikitext-2-raw-v1 test split) |
| `make_tasks.py`, `tasks.json` | 60 seeded, code-graded tasks (seed 7) |
| `eval_tasks.py`, `results/tasks_*.json`, `results/eval_*.log` | llama-server runner and per-task raw replies (120 runs) |
| `results/requantize_fallback.txt` | evidence that Q4_K_M requantization of the experts falls back to Q5_0/Q8_0 |

Not included: the GGUF files, the WikiText file, and the KL-divergence run (stopped, see article).
Known limits: one seed, temperature 0, reasoning effort requested low, 60 tasks.
