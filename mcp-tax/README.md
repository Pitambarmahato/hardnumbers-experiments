# mcp-tax — token cost of MCP servers in Claude Code

Measures how many context tokens each of 10 open-source MCP servers adds to a
Claude Code session before the user types anything, with tool search on (the
default) and off (`ENABLE_TOOL_SEARCH=false`). Run 2026-09-20 on Claude Code
2.1.278, model `claude-sonnet-5`.

Article: not yet published on hardnumbers.dev. This README will link it when
it is.

## Headline numbers

Context tokens = `input_tokens + cache_creation_input_tokens +
cache_read_input_tokens` from the JSON `usage` object. Cost of a server = its
total minus the empty-MCP-config total **in the same mode**.

| | Tool search on | Tool search off |
| --- | --- | --- |
| Empty MCP config | 22,243 | 37,211 |
| All 10 servers (108 tools) | 24,766 | 67,568 |
| Sum of the 10 single-server costs | +2,651 | +31,943 |

- With tool search on, cost fits `16.1 × tools + 0.428 × instruction_chars`
  (R² 0.99, n=10). Tool count alone: R² 0.26.
- Stacks of 2 and 5 servers add up to within 4 tokens; the 10-server stack is
  4.8% (on) and 5.0% (off) under the sum. Cause not identified.
- Full per-server table: `results/analysis.json` (`per_server`), or run
  `analyze.py`.

## Files

| Path | What it is |
| --- | --- |
| `run_matrix.py` | The runner that produced `results/`. `step0` = consistency check, `matrix` = full run. |
| `analyze.py` | Reads `results/results.jsonl` + `servers.json`, scores the hypotheses, writes `results/analysis.json`. Run from this directory. |
| `servers.json` | The 10 servers: exact version, repo, tool count, `tools/list` size, instructions size, vetting verdict and security note. |
| `results/results.jsonl` | One row per matrix run (82 measured + 1 discarded warm-up). |
| `results/raw/` | Raw `claude -p --output-format json` output for each of the 83 matrix runs. |
| `results/results_step0.jsonl`, `results/raw_step0/` | 9 setup runs (sandboxed filesystem server vs the probe). |
| `results/analysis.json`, `results/summary_firstlook.json` | Computed tables and fits. |
| `vet/` | Vetting tooling and output: `scan.py`/`scan.json` (source scan), `toolslist.py`/`toolslist.json` (`tools/list` per server), `sandbox.sb.template`. |
| `probe/` | The first feasibility probe (12 runs), which used `npx` with network access, not the sandbox. Kept for the audit trail. |
| `make_cover.py` | Renders the article cover from `analysis.json` (uses macOS Chrome headless). |

`total_cost_usd` in the raw JSON is an API-equivalent figure. These runs used
a Claude subscription, so it is not what was billed, and no analysis uses it.

## Requirements

- Claude Code 2.1.278 logged in (subscription or API key). Other versions may
  give different numbers; the built-in-tool share in particular depends on
  the version.
- macOS with `sandbox-exec` (deprecated by Apple, worked on macOS 15.0).
- `node`/`npm`, `uv`, `git`.

## How the results were produced

`run_matrix.py` expects, in the working directory: `servers/` (pinned local
copies of each server), `sandbox.sb`, `fsroot/` (an empty directory) and
`work/repo/` (an empty git repo). These were built with the commands below.
**This setup was not packaged as a script and has not been re-run from a clean
checkout.** Treat it as a record of what was done.

```bash
# npm servers: scripts disabled, one prefix per package
$ npm install --ignore-scripts --no-audit --no-fund --prefix servers/npm__modelcontextprotocol_server-filesystem @modelcontextprotocol/server-filesystem@2026.8.31
# same pattern for the others (directory name = what run_matrix.py expects):
#   npm__modelcontextprotocol_server-memory              @modelcontextprotocol/server-memory@2026.8.31
#   npm__modelcontextprotocol_server-sequential-thinking @modelcontextprotocol/server-sequential-thinking@2026.8.31
#   npm__modelcontextprotocol_server-everything          @modelcontextprotocol/server-everything@2026.8.31
#   npm__playwright_mcp                                  @playwright/mcp@0.0.82
#   npm_chrome-devtools-mcp                              chrome-devtools-mcp@1.9.0
#   npm__upstash_context7-mcp                            @upstash/context7-mcp@4.1.1

# Python servers: wheels only, so no setup.py runs
$ uv venv servers/py_mcp-server-fetch
$ uv pip install --python servers/py_mcp-server-fetch/bin/python --only-binary :all: mcp-server-fetch==2026.8.18
# same for mcp-server-time==2026.8.18 and mcp-server-git==2026.8.18

$ mkdir -p fsroot work/repo && git -C work/repo init -q
```

Then copy `vet/sandbox.sb.template` to `sandbox.sb`, replacing `<WORKDIR>` with
the absolute path of `work/` and `<HOME>` with your home directory. The
profile denies all network, denies writes outside `work/`, and denies reads of
`~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.claude`, `~/.config`, `~/.npmrc`,
`~/Library/Keychains` and `~/Desktop`.

`run_matrix.py` writes to a hardcoded `OUT` path near the top
(`/tmp/hardnumbers-experiments-staging/mcp-tax/results`). Change it before
running. It is left as-run so the file matches what produced the data.

```bash
$ python3 run_matrix.py step0    # 9 calls; must reproduce +209 / +2,955 for filesystem
$ python3 run_matrix.py matrix   # 83 calls
$ python3 analyze.py             # from this directory; regenerates results/analysis.json
```

## Deviations from this repo's reproduction standard

- **Not "no API budget".** It calls Claude through the Claude Code CLI, which
  needs a Claude subscription or API key. The runs are tiny (one short
  prompt each) but they are not local.
- **Deterministic in practice, not by construction.** `temperature` is not
  set; the measured quantity is prompt size, and every configuration returned
  identical totals on every run. That is repeatability on one version and one
  model, not a variance estimate.
- **Absolute totals are machine-specific.** They include the author's
  `CLAUDE.md`, hooks and skills. The per-server deltas are what transfer.

## Known issues

- The very first `claude -p` call of the first session read 34,610 tokens
  against 22,243 for every later baseline (cause unknown). It is in
  `probe/raw/base1.json`, was excluded, and did not recur in the 100+ runs
  after it.
- Filesystem with tool search off measured +2,953 in the probe (npx) and
  +2,955 in the sandboxed copy. The 2-token difference is unexplained.
- The 10-server stack under-shoots the sum of singles by ~5%. A bisect was
  not run.
- Not measured: cost of actually using a tool (ToolSearch fetch), HTTP
  transport servers, other versions or models, `auto:N` thresholds, latency.
