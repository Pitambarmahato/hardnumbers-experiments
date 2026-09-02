# Free-tier LLM providers for coding agents

Can a local proxy routing coding agents to free-tier LLM providers
match the quality of paid Claude Sonnet 4.5? This benchmark answers
that with 5 real coding tasks across 7 free-tier providers plus the
paid control.

Companion to the Hard Numbers article
[Can You Run Coding Agents for Free? 7 Free-Tier Providers Tested](https://hardnumbers.dev/articles/can-you-run-coding-agents-for-free-7-providers-tested).

## What this measures

| Provider          | Model                            | Quota         |
|-------------------|----------------------------------|---------------|
| NVIDIA NIM        | `nvidia/nemotron-3-super-120b-a12b` | Generous      |
| OpenRouter free   | `meta-llama/llama-3.3-70b-instruct:free` | ~50 req/day  |
| Groq              | `llama-3.3-70b-versatile`        | ~30 req/min   |
| Cerebras          | `llama-3.3-70b`                  | ~30 req/min   |
| ClinePass         | `kimi-k3`                        | Plan-based    |
| Z.ai              | `glm-4.5`                        | Limited       |
| GitHub Models     | `openai/gpt-4.1`                 | ~10 req/min   |
| **Claude Sonnet 4.5** (control) | `claude-sonnet-4-5` | Paid, no cap |

5 coding tasks across 4 parallelism buckets (embarrassingly parallel,
loosely coupled, tightly coupled, sequential-dependent).

## How to run

### 1. Install the local proxy

```bash
# See https://github.com/Alishahryar1/free-claude-code for the full guide
curl -fsSL "https://raw.githubusercontent.com/Alishahryar1/free-claude-code/main/scripts/install.sh" | sh
fcc-server
```

Open the admin UI at the URL the server prints. Configure at least
NVIDIA NIM (no credit card) and one other provider.

### 2. Get API keys

- **NVIDIA NIM**: https://build.nvidia.com/settings/api-keys (no card)
- **OpenRouter**: https://openrouter.ai/keys (no card for free tier)
- **Groq**: https://console.groq.com/keys
- **Cerebras**: https://cloud.cerebras.ai/
- **ClinePass**: https://docs.cline.bot/getting-started/clinepass
- **Z.ai**: https://z.ai/manage-apikey/apikey-list
- **GitHub Models**: https://github.com/marketplace?type=models (no card)

### 3. Run the benchmark

```bash
pip install -r requirements.txt
export FCC_BASE_URL=http://localhost:8082
export FCC_AUTH_TOKEN=freecc
export ANTHROPIC_API_KEY=sk-ant-...   # for the paid Claude control

python src/benchmark.py --providers all
python src/benchmark.py --providers cerebras,nvidia_nim   # subset
python src/benchmark.py --providers all --trials 3         # 3 trials each
```

## Cost

A full 7-provider × 5-task run is 35 trials. With 1 trial each,
the cost is $0 for all 7 free providers and ~$0.20 for the Claude
control. With 3 trials each, multiply by 3. The benchmark is cheap.

## Output

Results are written to `results/free_tier_<timestamp>.json` with
per-trial records and a per-provider summary (success rate, average
wall time, rate-limit hits, average quality score, total cost).

## Methodology

- **Provider selection:** the 7 most-cited free-tier providers in
  the FCC README's provider catalog
- **Task selection:** 5 tasks covering 4 parallelism buckets from
  the multi-agent benchmark, designed to run in under 5 minutes each
- **Verification:** each task has a `verify_command` that returns
  a known-good exit pattern
- **Quality scoring:** 1-5 blind grade based on diff size,
  response text, and rubric. Replace with LLM-as-judge for a
  production benchmark
- **Retries:** the proxy retries 3 times with exponential backoff
  on transient errors. A rate-limit hit means all retries were
  rejected

## Adding a provider

Add the provider config to `PROVIDERS` in `src/benchmark.py`. The
model string is the FCC-internal `<provider>/<model-id>` format
shown in the FCC admin UI's model picker.

## License

MIT.
