# Multi-agent coding throughput benchmark

How much wall-time speedup, cost overhead, and success-rate change
do you actually get from running 1, 2, 4, and 8 parallel Claude Code
agents on the same coding task set?

Companion to the Hard Numbers article
[Multi-Agent Coding: 1 vs 4 vs 8 Parallel Agents, A Real Benchmark](https://hardnumbers.dev/articles/multi-agent-coding-1-vs-4-vs-8-parallel-agents-a-real-benchmark).

## What this measures

| Bucket                  | Tasks | Description                                          |
|-------------------------|------:|------------------------------------------------------|
| Embarrassingly parallel |    12 | Independent files, no shared state                   |
| Loosely coupled         |    15 | Independent files, common reviewer at the end        |
| Tightly coupled         |    12 | Files depend on each other, later work builds on earlier |
| Sequential-dependent    |     8 | Each step is a prerequisite for the next             |
| **Total**               |  **47** |                                                  |

For each of the 4 buckets, every (parallelism, task) pair runs 3 trials.
564 trials total. Each agent works in its own git worktree, branched
from clean `main` at task start.

## How to run

```bash
# Requires Python 3.10+ and an Anthropic API key
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python src/benchmark.py --parallelism 1,2,4,8 --trials 3
```

To run a quick smoke test (1 trial, 1 parallelism level):

```bash
python src/benchmark.py --parallelism 4 --trials 1
```

To run only the embarrassing-parallel bucket:

```bash
python src/benchmark.py --buckets embarrassingly_parallel --parallelism 1,4,8
```

## Cost

A full run (1+2+4+8 × 3 trials × 47 tasks = 564 trials) costs about
$80-120 in API fees at Claude Sonnet 4.5 pricing. Subset runs
(parallelism-only or bucket-only) are proportionally cheaper.

## Output

Results are written to `results/multi_agent_<timestamp>.json` with
the per-trial record and per-bucket summary. Schema:

```json
{
  "model": "claude-sonnet-4-5",
  "trials_per_config": 3,
  "timestamp": "20260901_...",
  "results": [TrialRecord, ...],
  "summary": {
    "by_bucket": {...},
    "overall": {...}
  }
}
```

The summary includes wall-time median, cost median, success rate,
wall-time speedup vs 1-agent baseline, and cost ratio vs 1-agent
baseline — for every (bucket, parallelism) cell.

## Methodology

- **Model:** Claude Sonnet 4.5 only. Held constant to isolate the
  parallelism effect.
- **API:** Anthropic Messages API. Tools (bash, read_file, write_file)
  are provided so the agent can apply changes directly to its worktree.
- **Isolation:** git worktree per agent, branched from clean main.
- **Retry policy:** none. A trial that fails the verifier is a failure.
- **Verifier:** the project's own test suite (or task-specific bash
  assertion), run from a clean state against the merged diff.
- **Wall time:** measured from the moment all agents in a trial are
  spawned to the moment the last one finishes.

See the article for the full results and the analysis.

## Adding a task

Each task in `data/tasks.json` has:

- `id` — unique string
- `bucket` — one of the four buckets above
- `title` — short human description
- `repo` — path to a real git repo the agent can work in
- `prompt` — the user message sent to the agent
- `verify_command` — shell command that validates the agent's work
- `success_pattern` — regex that must match verify output for success

The `verify_command` is run after all parallel agents finish, on a
clean integration branch that merges their diffs. The `success_pattern`
is checked against the verifier's combined stdout+stderr.

The harder part is the `repo`: each task references a real git repo
under `experiments/test-repos/` that the agent can explore and modify.
The benchmark harness checks out a worktree, runs the agent, then
verifies the diff.

For the published article, the task suite was run against throwaway
test repos with known correct answers (e.g. "this script should
output 5 files"). The repo is not bundled with the benchmark code
because the test repos are the user's data, not the benchmark.

## License

MIT.
