"""Multi-agent coding throughput benchmark.

Runs 1, 2, 4, and 8 parallel Claude Code agents on the same task
suite and measures wall time, total tokens, cost, and success
rate. Each agent works in its own git worktree, branched from
clean main at task start.

Usage:
    export ANTHROPIC_API_KEY=...
    pip install -r requirements.txt
    python benchmark.py --parallelism 1,2,4,8 --trials 3
    python benchmark.py --parallelism 4 --trials 1 --tasks data/tasks.json

Output: writes JSON to results/multi_agent_<timestamp>.json
with the per-trial record and per-bucket summary.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Pricing (USD per 1M tokens) for Claude Sonnet 4.5
PRICE_INPUT = 3.0
PRICE_OUTPUT = 15.0

# Verifier config
VERIFIER_TIMEOUT_S = 600

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_PATH = REPO_ROOT / "multi-agent-throughput" / "data" / "tasks.json"
DEFAULT_RESULTS_DIR = REPO_ROOT / "multi-agent-throughput" / "results"


@dataclass
class TaskSpec:
    id: str
    bucket: str  # embarrassingly_parallel | loosely_coupled | tightly_coupled | sequential_dependent
    title: str
    repo: str  # path to the test repo (relative to REPO_ROOT)
    prompt: str
    verify_command: list[str]  # shell command to run for verification
    success_pattern: str  # regex that MUST match verify_command stdout for success


@dataclass
class TrialRecord:
    task_id: str
    bucket: str
    parallelism: int
    trial: int
    wall_time_s: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    success: bool
    agent_diffs: list[str]  # paths of each agent's worktree
    verifier_stdout: str
    error: str | None = None


@dataclass
class AgentHandle:
    trial_id: str
    agent_id: int
    worktree: str
    worktree_path: Path
    tokens_in: int = 0
    tokens_out: int = 0
    start_ts: float = 0.0
    end_ts: float = 0.0


def load_tasks(path: Path) -> list[TaskSpec]:
    with open(path) as f:
        raw = json.load(f)
    return [TaskSpec(**t) for t in raw]


def make_worktree(repo_path: Path, trial_id: str, agent_id: int) -> tuple[str, Path]:
    """Create a git worktree for one agent in this trial. Returns (name, path)."""
    name = f"wt-{trial_id}-a{agent_id}"
    path = repo_path.parent / name
    # Clean any prior worktree with the same name
    if path.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(path)],
            cwd=repo_path,
            check=False,
            capture_output=True,
        )
    subprocess.run(
        ["git", "worktree", "add", "-b", name, str(path), "main"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    return name, path


def remove_worktree(repo_path: Path, worktree_path: Path, branch_name: str) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo_path,
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        cwd=repo_path,
        check=False,
        capture_output=True,
    )


async def run_agent(
    client,
    model: str,
    task: TaskSpec,
    handle: AgentHandle,
    semaphore: asyncio.Semaphore,
) -> None:
    """One agent: invoke the API, stream the result into the worktree."""
    async with semaphore:
        handle.start_ts = time.monotonic()
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=8192,
                temperature=0.0,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"You are working in a git worktree at {handle.worktree_path}. "
                            f"Task:\n\n{task.prompt}\n\n"
                            "Make the changes directly to the files. "
                            "When you are done, output a one-line summary of what you changed."
                        ),
                    }
                ],
                tools=[
                    {
                        "name": "bash",
                        "description": "Run a shell command in the worktree",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "command": {"type": "string"}
                            },
                            "required": ["command"],
                        },
                    },
                    {
                        "name": "read_file",
                        "description": "Read a file from the worktree",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"}
                            },
                            "required": ["path"],
                        },
                    },
                    {
                        "name": "write_file",
                        "description": "Write a file in the worktree",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["path", "content"],
                        },
                    },
                ],
            )

            handle.tokens_in = response.usage.input_tokens
            handle.tokens_out = response.usage.output_tokens

            # Apply any tool calls to the worktree
            for block in response.content:
                if block.type == "tool_use":
                    name = block.name
                    args = block.input
                    if name == "bash":
                        subprocess.run(
                            args["command"],
                            shell=True,
                            cwd=handle.worktree_path,
                            check=False,
                            capture_output=True,
                            timeout=120,
                        )
                    elif name == "write_file":
                        p = handle.worktree_path / args["path"]
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(args["content"])
                    elif name == "read_file":
                        try:
                            (handle.worktree_path / args["path"]).read_text()
                        except FileNotFoundError:
                            pass
        except Exception as e:
            handle.tokens_in = 0
            handle.tokens_out = 0
            print(f"  ! agent {handle.agent_id} error: {e}", file=sys.stderr)
        finally:
            handle.end_ts = time.monotonic()


def verify_task(task: TaskSpec, worktrees: list[Path]) -> tuple[bool, str]:
    """Merge all agent worktrees into a clean integration branch, run verifier.

    Returns (success, stdout). The merge is the most expensive part of
    the 8-agent runs.
    """
    if not worktrees:
        return False, "no worktrees"

    repo = worktrees[0].parent / worktrees[0].name.split("-a")[0].lstrip("wt-").rstrip("-")
    # In a real harness, repo would be a real path passed via task.repo.
    # For this skeleton we use task.repo as the canonical repo.
    repo = (REPO_ROOT / task.repo).resolve()
    if not (repo / ".git").exists():
        return False, f"repo not found: {repo}"

    integration_branch = f"verify-{task.id}-{int(time.time())}"
    subprocess.run(
        ["git", "checkout", "-b", integration_branch],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    for wt in worktrees:
        # Copy changed files from the worktree into the integration branch
        diff_proc = subprocess.run(
            ["git", "diff", "--name-only", "main"],
            cwd=wt,
            check=True,
            capture_output=True,
            text=True,
        )
        for rel in diff_proc.stdout.strip().splitlines():
            if not rel:
                continue
            src = wt / rel
            dst = repo / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.copy2(src, dst)
        # Commit
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"agent {wt.name} changes"],
            cwd=repo,
            check=False,
            capture_output=True,
        )

    # Run verifier
    try:
        proc = subprocess.run(
            task.verify_command,
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=VERIFIER_TIMEOUT_S,
        )
        import re
        success = bool(re.search(task.success_pattern, proc.stdout + proc.stderr))
        return success, proc.stdout[-2000:]  # last 2KB
    except subprocess.TimeoutExpired:
        return False, "verifier timeout"
    finally:
        # Clean up integration branch
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=repo,
            check=False,
            capture_output=True,
        )
        subprocess.run(
            ["git", "branch", "-D", integration_branch],
            cwd=repo,
            check=False,
            capture_output=True,
        )


async def run_trial(
    client,
    model: str,
    task: TaskSpec,
    parallelism: int,
    trial: int,
    repo_path: Path,
) -> TrialRecord:
    """Run one (parallelism, task, trial) combination."""
    trial_id = f"{task.id}-p{parallelism}-t{trial}"

    # Spawn N agents in N worktrees
    handles: list[AgentHandle] = []
    for i in range(parallelism):
        _, wt_path = make_worktree(repo_path, trial_id, i)
        handles.append(AgentHandle(
            trial_id=trial_id,
            agent_id=i,
            worktree=f"wt-{trial_id}-a{i}",
            worktree_path=wt_path,
        ))

    # Run all agents concurrently
    wall_start = time.monotonic()
    sem = asyncio.Semaphore(parallelism)
    await asyncio.gather(*[
        run_agent(client, model, task, h, sem) for h in handles
    ])
    wall_end = time.monotonic()
    wall_time_s = wall_end - wall_start

    # Verify
    success, stdout = verify_task(task, [h.worktree_path for h in handles])

    # Cleanup
    for h in handles:
        remove_worktree(repo_path, h.worktree_path, h.worktree)

    tokens_in = sum(h.tokens_in for h in handles)
    tokens_out = sum(h.tokens_out for h in handles)
    cost = (tokens_in / 1_000_000) * PRICE_INPUT + (tokens_out / 1_000_000) * PRICE_OUTPUT

    return TrialRecord(
        task_id=task.id,
        bucket=task.bucket,
        parallelism=parallelism,
        trial=trial,
        wall_time_s=wall_time_s,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost,
        success=success,
        agent_diffs=[h.worktree for h in handles],
        verifier_stdout=stdout,
    )


def aggregate(trials: list[TrialRecord]) -> dict:
    """Compute the per-bucket and overall summary tables from trial records."""
    by_bucket: dict[str, dict[int, list[TrialRecord]]] = {}
    for tr in trials:
        by_bucket.setdefault(tr.bucket, {}).setdefault(tr.parallelism, []).append(tr)

    summary: dict = {"by_bucket": {}, "overall": {}}
    for bucket, by_p in by_bucket.items():
        summary["by_bucket"][bucket] = {}
        for p, recs in by_p.items():
            wall_med = sorted(r.wall_time_s for r in recs)[len(recs) // 2]
            cost_med = sorted(r.cost_usd for r in recs)[len(recs) // 2]
            succ_rate = sum(1 for r in recs if r.success) / len(recs)
            summary["by_bucket"][bucket][f"{p}_agents"] = {
                "wall_time_s_median": wall_med,
                "cost_usd_median": cost_med,
                "success_rate": succ_rate,
                "n_trials": len(recs),
            }

    # Compute speedups vs 1-agent
    for bucket, by_p in summary["by_bucket"].items():
        base = by_p.get("1_agents", {}).get("wall_time_s_median")
        base_cost = by_p.get("1_agents", {}).get("cost_usd_median")
        if base is None:
            continue
        for p_key, vals in by_p.items():
            vals["wall_speedup_median"] = base / vals["wall_time_s_median"] if vals["wall_time_s_median"] > 0 else None
            vals["cost_ratio_median"] = vals["cost_usd_median"] / base_cost if base_cost and base_cost > 0 else None

    # Overall
    by_p_overall: dict[int, list[TrialRecord]] = {}
    for tr in trials:
        by_p_overall.setdefault(tr.parallelism, []).append(tr)
    for p, recs in by_p_overall.items():
        wall_med = sorted(r.wall_time_s for r in recs)[len(recs) // 2]
        cost_med = sorted(r.cost_usd for r in recs)[len(recs) // 2]
        succ_rate = sum(1 for r in recs if r.success) / len(recs)
        summary["overall"][f"{p}_agents"] = {
            "wall_time_s_median": wall_med,
            "cost_usd_median": cost_med,
            "success_rate": succ_rate,
            "n_trials": len(recs),
        }
    base = summary["overall"].get("1_agents", {}).get("wall_time_s_median")
    base_cost = summary["overall"].get("1_agents", {}).get("cost_usd_median")
    for p_key, vals in summary["overall"].items():
        if base:
            vals["wall_speedup_median"] = base / vals["wall_time_s_median"] if vals["wall_time_s_median"] > 0 else None
        if base_cost:
            vals["cost_ratio_median"] = vals["cost_usd_median"] / base_cost if base_cost > 0 else None

    return summary


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parallelism", default="1,2,4,8", help="comma-separated parallelism levels")
    parser.add_argument("--trials", type=int, default=3, help="trials per (parallelism, task)")
    parser.add_argument("--model", default="claude-sonnet-4-5")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--buckets", default="", help="comma-separated buckets to run; empty = all")
    args = parser.parse_args()

    parallelism_levels = [int(p) for p in args.parallelism.split(",")]
    tasks = load_tasks(args.tasks)
    if args.buckets:
        wanted = set(args.buckets.split(","))
        tasks = [t for t in tasks if t.bucket in wanted]

    print(f"Loaded {len(tasks)} tasks across buckets: "
          f"{sorted(set(t.bucket for t in tasks))}")
    print(f"Parallelism levels: {parallelism_levels}, trials: {args.trials}")
    print(f"Total trials: {len(tasks) * len(parallelism_levels) * args.trials}")

    # Lazy-import the Anthropic client to keep --help fast
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        print("pip install anthropic", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY first", file=sys.stderr)
        sys.exit(1)

    client = AsyncAnthropic()

    all_trials: list[TrialRecord] = []
    for task in tasks:
        repo_path = (REPO_ROOT / task.repo).resolve()
        if not (repo_path / ".git").exists():
            print(f"  ! skipping {task.id}: repo {repo_path} not a git repo")
            continue
        for p in parallelism_levels:
            for trial in range(args.trials):
                print(f"  · {task.id} p={p} t={trial+1}/{args.trials} ...", end="", flush=True)
                rec = await run_trial(client, args.model, task, p, trial, repo_path)
                all_trials.append(rec)
                print(f"  wall={rec.wall_time_s:.1f}s cost=${rec.cost_usd:.2f} {'OK' if rec.success else 'FAIL'}")

    summary = aggregate(all_trials)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"multi_agent_{ts}.json"
    with open(out_path, "w") as f:
        json.dump({
            "model": args.model,
            "trials_per_config": args.trials,
            "timestamp": ts,
            "results": [asdict(r) for r in all_trials],
            "summary": summary,
        }, f, indent=2)
    print(f"\nWrote {out_path}")
    print(json.dumps(summary["overall"], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
