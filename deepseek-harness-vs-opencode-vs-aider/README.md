# DeepSeek Harness vs OpenCode vs Aider — same model, same tasks

A controlled comparison of three open-source coding-agent harnesses,
holding the model, hardware, and task suite constant and swapping only the
harness:

- **DeepSeek Harness** (`@deepseek-ai/dsh`) 0.1.2-rc.1 — released
  2026-08-13, MIT-licensed, "everything is a plugin" agent runtime.
- **OpenCode** (`opencode-ai`) 1.18.4.
- **Aider** (`aider-chat`) 0.86.2.

All three point at the same **Qwen3 14B** model (`qwen3-14b-ctx16k`,
Q4_K_M quant, `num_ctx` fixed to 16,384) served locally by Ollama — no
cloud API, no per-token billing. Every existing "harness vs harness"
comparison we found online either changed the model between harnesses or
ran everything through a cloud API. This one doesn't.

## Why a proxy sits in front of Ollama

Different harnesses call Ollama through different wire protocols: Aider's
`ollama/` model prefix uses Ollama's **native** `/api/generate` endpoint,
while OpenCode's and DeepSeek Harness's custom-provider configs use the
**OpenAI-compatible** `/v1/chat/completions` endpoint. Those two endpoints
report token usage in different shapes, and two of the three harnesses
don't print token counts at all. `proxy/server.py` is a transparent
logging reverse proxy: it forwards every request byte-for-byte, injects
`stream_options.include_usage` on OpenAI-compatible streamed requests, and
scrapes `eval_count`/`prompt_eval_count` from Ollama-native responses — so
every harness is measured the same way regardless of which protocol it
picked.

## Layout

```
Dockerfile              # shared image: Node 22 + Python 3.12, all 3 harnesses installed
entrypoint.sh            # dispatches to dsh / opencode / aider based on $HARNESS
configs/
  opencode.json          # points OpenCode's "ollama" provider at the proxy
  cordis.patch.yml        # points dsh's "ollama" provider at the proxy
proxy/
  Dockerfile
  server.py               # the logging reverse proxy described above
grader/
  Dockerfile              # pytest + mypy only, no agent tools — grades post-hoc
gen_tasks.py              # generates the 8-task pilot suite (isolated / tightly-coupled / sequential)
run_bench.py              # orchestrates one (task, harness) run: fresh repo copy, proxy + harness
                           # containers on a private network, grade, record, tear down
run_all_remaining.sh       # loops run_bench.py until every combo is done
results/
  agent_harness_pilot.json  # full 24-run results from the pilot
```

## How to run

Requires Docker and a local Ollama with the model pulled:

```bash
ollama pull qwen3:14b
cat > Modelfile <<'EOF'
FROM qwen3:14b
PARAMETER num_ctx 16384
EOF
ollama create qwen3-14b-ctx16k -f Modelfile

docker build -t harness-bench:latest .
docker build -t harness-bench-proxy:latest ./proxy
docker build -t harness-bench-grader:latest ./grader

python3 gen_tasks.py          # generates tasks/ (gitignored — regenerate, don't expect it committed)
python3 run_bench.py          # runs exactly ONE pending (task, harness) combo, then exits
# or:
./run_all_remaining.sh        # loops run_bench.py until all combos are done
```

`run_bench.py` is resumable and idempotent: it reads
`results/agent_harness_pilot.json`, finds the first `(task, harness)` pair
not yet recorded, runs it, appends the result, and exits. Safe to stop
between runs; nothing is left running on a clean stop (every run tears
down its containers and network in a
`finally` block, timeout or not).

## Results summary

24 runs (8 tasks x 3 harnesses, n=1 per cell — a pilot, not a
statistically powered benchmark):

| Harness | Pass rate | Avg. tokens/run | Avg. wall-clock |
| --- | --- | --- | --- |
| Aider 0.86.2 | 7/8 (87.5%) | 3,202 | 217s |
| OpenCode 1.18.4 | 5/8 (62.5%) | 42,269 (13.2x) | 635s (2.9x) |
| DeepSeek Harness 0.1.2-rc.1 | 4/8 (50%) | 54,900 (17.1x) | 546s (2.5x) |

Full per-run detail (per-task pass/fail, token counts, harness logs) is in
`results/agent_harness_pilot.json`.

## Caveats

- **n=1 per cell.** Every (task, harness) pair ran once. Direction and
  rough magnitude, not a statistically powered result.
- **Single model.** Everything here reflects Qwen3 14B's capability paired
  with three harnesses' scaffolding — not tested against a stronger model.
- **DeepSeek Harness's one hard failure was environmental, not a coding
  failure**: its file-write sandbox plugin requires `bubblewrap` or a
  Landlock-enforcing kernel, neither present in this minimal Debian image,
  so it refused to write a new file on one task rather than proceeding
  unsandboxed. A different container setup might not hit this at all.
- One run (`coupled_rename` x dsh) was rerun at a 2x longer timeout after
  its own reasoning log showed real, if slow, progress — every other run
  used the same 900-second default cap.

## Article

The full writeup lives at:
[hardnumbers.dev/articles/deepseek-harness-vs-opencode-vs-aider-same-model](https://hardnumbers.dev/)
