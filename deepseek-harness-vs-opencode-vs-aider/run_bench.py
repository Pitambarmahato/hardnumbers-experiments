"""Runs the full harness-vs-harness pilot: every task x every harness, once
each, serially (one Ollama instance on this machine, no point contending).

For each (harness, task) pair:
  1. copy the task's pristine repo to a scratch dir
  2. start a fresh logging proxy container (tags every request with
     harness/task) on a private network
  3. run the harness container against the scratch repo copy
  4. grade the result with the grader container running the task's check.sh
  5. sum tokens/duration from the proxy's JSONL log
  6. tear down the proxy + network, record the result

Writes incrementally to results/agent_harness_pilot.json so a crash
partway through doesn't lose completed runs.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
TASKS_DIR = ROOT / "tasks"
SCRATCH = Path("/tmp/hn_harness_bench_scratch")
RUNS_DIR = ROOT / "results"
HARNESSES = ["aider", "opencode", "dsh"]
TASK_TIMEOUT_S = int(__import__("os").environ.get("TASK_TIMEOUT_S", 900))  # hard cap per run


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def run_one(task_id: str, category: str, prompt: str, harness: str) -> dict:
    run_id = f"{task_id}__{harness}__{uuid.uuid4().hex[:6]}"
    net = f"hb-net-{run_id}"
    proxy_name = f"hb-proxy-{run_id}"
    harness_name = f"hb-run-{run_id}"
    scratch_repo = SCRATCH / run_id / "repo"
    log_dir = SCRATCH / run_id / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(TASKS_DIR / task_id / "repo", scratch_repo)

    timed_out = False
    try:
        sh(["docker", "network", "create", net])
        sh([
            "docker", "run", "-d", "--rm", "--name", proxy_name,
            "--network", net, "--network-alias", "ollama-proxy",
            "-e", f"HARNESS={harness}", "-e", f"TASK_ID={task_id}",
            "-v", f"{log_dir}:/logs",
            "harness-bench-proxy:latest",
        ])
        time.sleep(1)

        started = time.time()
        try:
            sh(
                [
                    "docker", "run", "--rm", "--name", harness_name,
                    "--network", net,
                    "-v", f"{scratch_repo}:/workspace",
                    "-e", f"HARNESS={harness}",
                    "-e", f"TASK_PROMPT={prompt}",
                    "harness-bench:latest",
                ],
                timeout=TASK_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            timed_out = True
        harness_wall_s = time.time() - started
    finally:
        # Killing the local `docker run` CLI on timeout does NOT stop the
        # container on the daemon - always force-remove both containers and
        # the network, whether we succeeded, failed, or timed out.
        sh(["docker", "rm", "-f", harness_name])
        sh(["docker", "rm", "-f", proxy_name])
        sh(["docker", "network", "rm", net])

    exit_code_file = scratch_repo / "out" / "exit_code"
    duration_file = scratch_repo / "out" / "duration_seconds"
    harness_exit = exit_code_file.read_text().strip() if exit_code_file.exists() else None
    harness_duration = float(duration_file.read_text().strip()) if duration_file.exists() else None

    # Grade whatever's on disk even after a timeout kill - the mounted
    # volume survives the container, so a fix that landed before the harness
    # got stuck is still visible and worth recording.
    grade = sh([
        "docker", "run", "--rm",
        "-v", f"{scratch_repo}:/workspace",
        "-v", f"{TASKS_DIR / task_id / 'check.sh'}:/workspace/check.sh",
        "harness-bench-grader:latest",
    ])
    passed = grade.returncode == 0

    proxy_log_path = log_dir / "proxy.jsonl"
    calls = []
    if proxy_log_path.exists():
        for line in proxy_log_path.read_text().splitlines():
            if line.strip():
                try:
                    calls.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    total_prompt_tokens = sum(
        c["usage"]["prompt_tokens"] or 0 for c in calls if c.get("usage") and c["usage"].get("prompt_tokens")
    )
    total_completion_tokens = sum(
        c["usage"]["completion_tokens"] or 0 for c in calls if c.get("usage") and c["usage"].get("completion_tokens")
    )
    dropped_calls = sum(1 for c in calls if c.get("error"))

    return {
        "run_id": run_id,
        "task_id": task_id,
        "category": category,
        "harness": harness,
        "passed": passed,
        "timed_out": timed_out,
        "harness_exit_code": harness_exit,
        "harness_wall_seconds": round(harness_wall_s, 1),
        "harness_reported_duration_seconds": harness_duration,
        "model_calls": len(calls),
        "dropped_calls": dropped_calls,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "grader_stdout_tail": grade.stdout[-2000:],
        "harness_log_tail": (scratch_repo / "out" / "log.txt").read_text()[-2000:]
        if (scratch_repo / "out" / "log.txt").exists()
        else "",
    }


PERSISTENT_RESULTS = RUNS_DIR / "agent_harness_pilot.json"


def load_tasks():
    tasks = []
    for d in sorted(TASKS_DIR.iterdir()):
        if not d.is_dir():
            continue
        prompt = (d / "prompt.txt").read_text().strip()
        category = (d / "category.txt").read_text().strip()
        tasks.append((d.name, category, prompt))
    return tasks


def load_results():
    if PERSISTENT_RESULTS.exists():
        return json.loads(PERSISTENT_RESULTS.read_text())
    return {
        "started_at": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "machine": "MacBook Pro M2 24GB",
        "model": "qwen3-14b-ctx16k",
        "runs": [],
    }


def next_pending(tasks, results):
    done = {(r["task_id"], r["harness"]) for r in results["runs"] if r.get("passed") is not None}
    for task_id, category, prompt in tasks:
        for harness in HARNESSES:
            if (task_id, harness) not in done:
                return task_id, category, prompt, harness
    return None


def main():
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks()
    results = load_results()
    total = len(tasks) * len(HARNESSES)
    done_count = len({(r["task_id"], r["harness"]) for r in results["runs"] if r.get("passed") is not None})

    pending = next_pending(tasks, results)
    if pending is None:
        print(f"All {total}/{total} runs complete. Results: {PERSISTENT_RESULTS}")
        return

    task_id, category, prompt, harness = pending
    print(f"[{done_count + 1}/{total}] {task_id} x {harness} ...", flush=True)
    result = run_one(task_id, category, prompt, harness)
    print(f"    -> passed={result.get('passed')} timed_out={result.get('timed_out')} "
          f"tokens={result.get('total_tokens')} "
          f"wall={result.get('harness_wall_seconds')}s", flush=True)

    results["runs"] = [
        r for r in results["runs"] if (r["task_id"], r["harness"]) != (task_id, harness)
    ]
    results["runs"].append(result)
    PERSISTENT_RESULTS.write_text(json.dumps(results, indent=2))
    print(f"\n{done_count + 1}/{total} done. Results: {PERSISTENT_RESULTS}")


if __name__ == "__main__":
    main()
