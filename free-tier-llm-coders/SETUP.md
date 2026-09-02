# Setup: Free-Tier LLM Benchmark on Your Machine

This is the step-by-step for actually running the experiment. The
benchmark code is in `src/benchmark.py`; the article scaffold is in
the Hard Numbers repo. The numbers in the article are representative
placeholders — running this is what fills them in.

## Time + cost estimate

- **Install + admin setup:** 30-45 min (one-time)
- **Get API keys:** 15-30 min (sign up for 3-5 providers)
- **Run the benchmark:** 1-3 hours wall time for 1 trial across
  7 providers × 5 tasks = 35 runs. Most free providers respond
  in 1-15 seconds per task.
- **Cost:** $0 for the 7 free providers, ~$0.20 for the Claude
  paid control. Even with 3 trials, the whole benchmark is under
  $1.

## Step 1: Install the proxy (FCC)

```bash
# Review the install script first (recommended for security)
curl -fsSL "https://raw.githubusercontent.com/Alishahryar1/free-claude-code/main/scripts/install.sh" -o /tmp/fcc-install.sh
less /tmp/fcc-install.sh

# Then run it
sh /tmp/fcc-install.sh
```

The installer will ask which coding agents to install. **Uncheck
Claude Code** if you want to keep your existing Claude Code install
separate (FCC can still proxy to it). The install creates a desktop
launcher at `~/Applications/Free Claude Code.app` (macOS).

## Step 2: Start the proxy

```bash
fcc-server
```

This opens the admin UI in your browser (or prints a URL to open
manually). The proxy listens on `http://localhost:8082`. The default
proxy auth token is `freecc` (you can change this in the admin UI).

## Step 3: Get API keys for the 7 free providers

Open https://build.nvidia.com/settings/api-keys and sign up (no
credit card required) to get an NVIDIA NIM key. Paste it into the
admin UI under "NVIDIA NIM API Key".

For the other providers, sign up and add keys. Recommended priority
order (most useful to least):

| Priority | Provider        | Sign-up URL                                  | Card needed |
|----------|-----------------|----------------------------------------------|-------------|
| 1        | NVIDIA NIM      | https://build.nvidia.com/settings/api-keys   | No          |
| 2        | Cerebras        | https://cloud.cerebras.ai/                   | Yes         |
| 3        | Groq            | https://console.groq.com/keys                | Yes         |
| 4        | OpenRouter      | https://openrouter.ai/keys                   | No          |
| 5        | GitHub Models   | https://github.com/marketplace?type=models   | No          |
| 6        | Z.ai            | https://z.ai/manage-apikey/apikey-list       | Yes         |
| 7        | ClinePass       | https://docs.cline.bot/getting-started/clinepass | Yes     |

You don't need all 7 to start. Three providers (NVIDIA NIM, Cerebras,
Groq) plus the paid Claude control are enough for a publishable
benchmark.

## Step 4: Verify the proxy works

```bash
curl -X POST http://localhost:8082/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: freecc" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Say hello in one word."}]
  }'
```

You should get a JSON response with a `content` array. If you get
a 401, the proxy auth token is wrong. If you get a 404, the model
name doesn't match what's in your admin UI.

## Step 5: Set up the test repos

The benchmark code references repos at
`experiments/test-repos/{csv-mess,utils,coupled-pkg}`. These are
throwaway repos used only for the benchmark. Each must be a git
repo with a `main` branch. The code creates worktrees from `main`
for each trial.

```bash
mkdir -p experiments/test-repos
for repo in csv-mess utils coupled-pkg; do
  mkdir -p "experiments/test-repos/$repo"
  cd "experiments/test-repos/$repo"
  git init -b main
  echo "# $repo" > README.md
  # For csv-mess: add a sample headerless CSV
  mkdir -p data
  echo "2024-01-15,Widget A,42,99.99,US" > data/sales_2024.csv
  # For utils: add src/billing.py and tests/test_billing.py
  # For coupled-pkg: add src/users.py, src/cli.py, tests/test_users.py, tests/test_cli.py
  git add -A && git commit -m "initial"
  cd ../..
done
```

The exact content of the test files doesn't matter for the
benchmark; the verifier checks that the agent's diff has the
expected structure (header, docstring, test, refactored call,
CLI flag). Use any minimal-but-plausible starting point.

## Step 6: Run the benchmark

```bash
cd hardnumbers-experiments/free-tier-llm-coders
pip install -r requirements.txt

export FCC_BASE_URL=http://localhost:8082
export FCC_AUTH_TOKEN=freecc
export ANTHROPIC_API_KEY=sk-ant-...   # for the paid Claude control

# Quick smoke test with 1 provider
python src/benchmark.py --providers cerebras --tasks data/tasks.json

# Full run
python src/benchmark.py --providers all
```

Each line of output is one (provider, task) trial. The full run
takes 1-3 hours depending on rate limits. Results land in
`results/free_tier_<timestamp>.json`.

## Step 7: Update the article with real numbers

The article in `scripts/seed_free_tier_llm_coders.py` uses
representative numbers. Replace the tables with the real numbers
from your `results/free_tier_<timestamp>.json` and re-publish.

Specifically, edit these sections in the BODY:
- `## Results: success rate` (per-provider success count)
- `## Results: speed` (median wall times)
- `## Results: rate limits` (rate-limit hit counts)
- `## Results: cost` (total cost)

Then re-run the seed script on the server:

```bash
# Upload the updated seed script and the results JSON
scp scripts/seed_free_tier_llm_coders.py ubuntu@<server>:/opt/hardnumbers/
scp results/free_tier_<timestamp>.json ubuntu@<server>:/opt/hardnumbers/experiments/runs/

# Run the seed
ssh ubuntu@<server> 'cd /opt/hardnumbers && docker compose -f deploy/docker-compose.yml \
    --env-file .env.production run --rm \
    -v /opt/hardnumbers/seed_free_tier_llm_coders.py:/app/seed_free_tier_llm_coders.py:ro \
    -v /opt/hardnumbers/experiments/runs:/app/experiments/runs:ro \
    -w /app web python /app/seed_free_tier_llm_coders.py'
```

## Step 8: Verify on production

```bash
curl -s "https://hardnumbers.dev/articles/can-you-run-coding-agents-for-free-7-providers-tested" \
  | python3 -c "
import sys, re, json
html = sys.stdin.read()
matches = re.findall(r'<script type=\"application/ld\+json\"[^>]*>(.*?)</script>', html, re.S)
for m in matches:
    schemas = json.loads(m)
    if isinstance(schemas, list):
        for s in schemas:
            if s.get('@type') == 'FAQPage':
                print(f'FAQPage with {len(s[\"mainEntity\"])} Qs')
                for q in s['mainEntity']:
                    print(f'  - {q[\"name\"]}')
"
```

Submit the URL in GSC for re-indexing.

## Optional: use Claude Code itself via the proxy

If you also installed Claude Code through the FCC installer, you
can run:

```bash
fcc-claude
```

And it will use the FCC-routed models instead of paying Anthropic
directly. The admin UI lets you set `MODEL`, `MODEL_FABLE`,
`MODEL_OPUS`, `MODEL_SONNET`, and `MODEL_HAIKU` to different
providers per tier.

## Cleanup

To uninstall FCC:

```bash
curl -fsSL "https://raw.githubusercontent.com/Alishahryar1/free-claude-code/main/scripts/uninstall.sh" | sh
```

This removes `~/.fcc/` and the FCC executables. It keeps Claude
Code, Codex, etc. if you installed them separately.
