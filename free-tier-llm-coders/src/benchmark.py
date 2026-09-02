"""Free-tier LLM provider benchmark for coding agents (v2).

Calls 4 LLM APIs (3 free + 1 paid control) directly via OpenAI-compatible
protocol. For each task, asks the model to rewrite the target file(s)
completely, writes the new content, then runs the task's verify_command.

Usage:

    pip install -r requirements.txt
    # Put keys in .env (chmod 600, gitignored)
    python src/benchmark.py --providers all
    python src/benchmark.py --providers nvidia_nim,groq,cline --trials 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load .env from the experiment directory
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_PATH = REPO_ROOT / "free-tier-llm-coders" / "data" / "tasks.json"
DEFAULT_RESULTS_DIR = REPO_ROOT / "free-tier-llm-coders" / "results"
DEFAULT_WORKTREES_DIR = REPO_ROOT / "free-tier-llm-coders" / "worktrees"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # exponential backoff
DEFAULT_TRIALS = 1
MAX_TOKENS = 4096

# Provider -> (base_url, model, key env var, label, free?)
PROVIDERS = {
    "nvidia_nim": {
        "label": "NVIDIA NIM (Nemotron 120B, free)",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "key_env": "NVIDIA_NIM_API_KEY",
        "is_free": True,
    },
    "openrouter_minimax_m3": {
        "label": "OpenRouter MiniMax M3 (free)",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "minimax/minimax-m3:free",
        "key_env": "OPENROUTER_API_KEY",
        "is_free": True,
    },
    "groq": {
        "label": "Groq Qwen 3.6 27B (free)",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "qwen/qwen3.6-27b",
        "key_env": "GROQ_API_KEY",
        "is_free": True,
    },
    "cline_claude": {
        "label": "Cline API Claude fable 5.1 (paid control)",
        "base_url": "https://api.cline.bot/api/v1",
        "model": "anthropic/claude-fable-5.1",
        "key_env": "CLINEPASS_API_KEY",
        "is_free": False,
    },
}


@dataclass
class TaskSpec:
    id: str
    bucket: str
    title: str
    repo: str
    files: list[str]
    context_chars: int
    prompt: str
    verify_command: list[str]
    success_pattern: str
    quality_rubric: str


@dataclass
class TrialRecord:
    provider: str
    provider_label: str
    task_id: str
    bucket: str
    trial: int
    wall_time_s: float
    time_to_first_token_s: float
    tokens_in: int
    tokens_out: int
    tokens_per_s: float
    success: bool
    rate_limited: bool
    error: str | None = None
    diff_lines: int = 0
    response_excerpt: str = ""


def load_tasks(path: Path) -> list[TaskSpec]:
    with open(path) as f:
        return [TaskSpec(**t) for t in json.load(f)]


def make_worktree(repo_path: Path, name: str) -> Path:
    """Create a git worktree branched from main. Returns the worktree path."""
    path = DEFAULT_WORKTREES_DIR / name
    if path.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(path)],
            cwd=repo_path, check=False, capture_output=True,
        )
    DEFAULT_WORKTREES_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "-b", name, str(path), "main"],
        cwd=repo_path, check=True, capture_output=True,
    )
    return path


def remove_worktree(repo_path: Path, worktree_path: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo_path, check=False, capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-D", worktree_path.name],
        cwd=repo_path, check=False, capture_output=True,
    )


def build_prompt(task: TaskSpec, worktree: Path, file_contents: dict[str, str]) -> str:
    """Build the prompt with file context + the task + clear output format."""
    parts = [
        f"You are editing files in a git worktree at {worktree}.",
        "",
        f"Task: {task.title}",
        "",
    ]
    for path, content in file_contents.items():
        ext = Path(path).suffix.lstrip(".") or "txt"
        # truncate if needed
        if len(content) > task.context_chars:
            content = content[: task.context_chars] + "\n... (truncated)"
        parts.append(f"=== CURRENT FILE: {path} ===")
        parts.append(f"```{ext}")
        parts.append(content)
        parts.append("```")
        parts.append("")
    parts.append("=== YOUR TASK ===")
    parts.append(task.prompt)
    parts.append("")
    parts.append("=== OUTPUT FORMAT ===")
    parts.append(
        "For EACH file you need to change, output a code block in this exact format:"
    )
    parts.append("")
    parts.append("```file:path/to/file.ext")
    parts.append("<complete new file content>")
    parts.append("```")
    parts.append("")
    parts.append(
        "If a file doesn't need changes, skip it. Do not include any prose, "
        "explanation, or commentary outside the code blocks."
    )
    return "\n".join(parts)


# Regex: ```file:path\ncontent\n``` (greedy across newlines)
FILE_BLOCK_RE = re.compile(
    r"```(?:file:)?([^\s`]+)\s*\n(.*?)```",
    re.DOTALL,
)


def parse_file_rewrites(response: str) -> dict[str, str]:
    """Extract file path -> new content from the model's response."""
    rewrites: dict[str, str] = {}
    for match in FILE_BLOCK_RE.finditer(response):
        path = match.group(1).strip().lstrip("./")
        content = match.group(2)
        # Strip leading "file:" if present
        if path.startswith("file:"):
            path = path[5:]
        # Skip if "path" looks like a language identifier (e.g., "python")
        if path in ("python", "py", "javascript", "js", "ts", "tsx", "json", "bash", "sh", "text", "txt", "yaml", "yml", "diff", ""):
            continue
        rewrites[path] = content.rstrip("\n") + "\n"
    return rewrites


def apply_rewrites(worktree: Path, rewrites: dict[str, str]) -> tuple[int, int]:
    """Write each file to the worktree. Returns (files_written, lines_changed)."""
    written = 0
    diff_lines = 0
    for rel_path, content in rewrites.items():
        # Strip leading src/ if present (worktree is the repo root)
        if rel_path.startswith("/"):
            rel_path = rel_path[1:]
        target = worktree / rel_path
        if not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        old = target.read_text() if target.exists() else ""
        target.write_text(content)
        written += 1
        diff_lines += abs(len(content.splitlines()) - len(old.splitlines()))
    return written, diff_lines


def count_diff_lines(worktree: Path) -> int:
    """Count lines changed in the worktree vs main."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--stat", "main"],
            cwd=worktree, check=True, capture_output=True, text=True,
        )
        # Sum insertions + deletions from --stat output
        total = 0
        for line in proc.stdout.splitlines():
            m = re.search(r"(\d+) insertion|\d+ insertion.*?(\d+) deletion", line)
            if m:
                for g in m.groups():
                    if g:
                        total += int(g)
        return total
    except Exception:
        return 0


def verify_task(task: TaskSpec, worktree: Path) -> tuple[bool, str]:
    """Run the task's verify_command. Returns (success, output_tail).

    Success = exit code 0 AND (if success_pattern set) pattern found in output.
    Uses the venv's python3 so pytest is available.
    """
    # Rewrite the verify command to use the venv's python3 instead of bare `python`
    cmd = list(task.verify_command)
    if cmd and cmd[0] == "bash":
        venv_py = str(Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python3")
        # Inject into the bash -c string
        bash_c_idx = next((i for i, c in enumerate(cmd) if c == "-c"), None)
        if bash_c_idx is not None and bash_c_idx + 1 < len(cmd):
            original = cmd[bash_c_idx + 1]
            # Replace leading "python " and "python -m" with the venv python
            rewritten = re.sub(r"\bpython(\s+)", f"{venv_py}\\1", original)
            cmd[bash_c_idx + 1] = rewritten
    env = os.environ.copy()
    env["PATH"] = str(Path(__file__).resolve().parent.parent / ".venv" / "bin") + ":" + env.get("PATH", "")
    try:
        proc = subprocess.run(
            cmd,
            cwd=worktree, check=False, capture_output=True, text=True, timeout=120, env=env,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return False, output[-1500:]
        if task.success_pattern and task.success_pattern != ".":
            if not re.search(task.success_pattern, output):
                return False, f"pattern not found: {output[-500:]}"
        return True, output[-500:]
    except subprocess.TimeoutExpired:
        return False, "verifier timeout"
    except Exception as e:
        return False, f"verifier error: {e}"


async def call_provider(
    client: AsyncOpenAI,
    model: str,
    prompt: str,
) -> tuple[str, int, int, float, float, bool, str | None]:
    """Call the model. Returns (text, in, out, wall_s, ttft_s, rate_limited, error)."""
    wall_start = time.monotonic()
    rate_limited = False
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            ttft = None
            text_chunks: list[str] = []
            stream = await client.chat.completions.create(
                model=model,
                max_tokens=MAX_TOKENS,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                stream_options={"include_usage": True},
            )
            usage_in = usage_out = 0
            async for chunk in stream:
                if ttft is None and chunk.choices and chunk.choices[0].delta.content:
                    ttft = time.monotonic() - wall_start
                if chunk.choices and chunk.choices[0].delta.content:
                    text_chunks.append(chunk.choices[0].delta.content)
                if chunk.usage:
                    usage_in = chunk.usage.prompt_tokens or 0
                    usage_out = chunk.usage.completion_tokens or 0
            wall_s = time.monotonic() - wall_start
            text = "".join(text_chunks)
            return text, usage_in, usage_out, wall_s, ttft or wall_s, rate_limited, None
        except Exception as e:
            err_str = str(e)
            last_error = err_str
            if "429" in err_str or "rate_limit" in err_str.lower():
                rate_limited = True
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                    continue
            if "503" in err_str or "overloaded" in err_str.lower() or "502" in err_str:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                    continue
            break
    wall_s = time.monotonic() - wall_start
    return "", 0, 0, wall_s, 0.0, rate_limited, last_error


async def run_trial(
    client: AsyncOpenAI,
    provider_id: str,
    provider_cfg: dict,
    task: TaskSpec,
    trial: int,
) -> TrialRecord:
    repo_path = (REPO_ROOT / task.repo).resolve()
    if not (repo_path / ".git").exists():
        return TrialRecord(
            provider=provider_id,
            provider_label=provider_cfg["label"],
            task_id=task.id,
            bucket=task.bucket,
            trial=trial,
            wall_time_s=0.0,
            time_to_first_token_s=0.0,
            tokens_in=0,
            tokens_out=0,
            tokens_per_s=0.0,
            success=False,
            rate_limited=False,
            error=f"repo not found: {repo_path}",
        )

    name = f"wt-{provider_id}-{task.id}-t{trial}"
    worktree = make_worktree(repo_path, name)

    try:
        # Read file contents
        file_contents = {}
        for rel in task.files:
            full = worktree / rel
            if full.exists():
                file_contents[rel] = full.read_text()

        prompt = build_prompt(task, worktree, file_contents)
        text, tok_in, tok_out, wall_s, ttft, rate_limited, error = await call_provider(
            client, provider_cfg["model"], prompt
        )

        if error:
            return TrialRecord(
                provider=provider_id,
                provider_label=provider_cfg["label"],
                task_id=task.id,
                bucket=task.bucket,
                trial=trial,
                wall_time_s=round(wall_s, 2),
                time_to_first_token_s=round(ttft, 2),
                tokens_in=tok_in,
                tokens_out=tok_out,
                tokens_per_s=0.0,
                success=False,
                rate_limited=rate_limited,
                error=error[:500],
                response_excerpt=text[:500],
            )

        # Parse and apply file rewrites
        rewrites = parse_file_rewrites(text)
        if not rewrites:
            error = "no file blocks found in response"
        else:
            apply_rewrites(worktree, rewrites)

        success, _ = verify_task(task, worktree)
        diff_lines = count_diff_lines(worktree)
        gen_time = max(wall_s - ttft, 0.01)
        tok_per_s = round(tok_out / gen_time, 2) if tok_out else 0.0

        return TrialRecord(
            provider=provider_id,
            provider_label=provider_cfg["label"],
            task_id=task.id,
            bucket=task.bucket,
            trial=trial,
            wall_time_s=round(wall_s, 2),
            time_to_first_token_s=round(ttft, 2),
            tokens_in=tok_in,
            tokens_out=tok_out,
            tokens_per_s=tok_per_s,
            success=success,
            rate_limited=rate_limited,
            error=error,
            diff_lines=diff_lines,
            response_excerpt=text[:300],
        )
    finally:
        remove_worktree(repo_path, worktree)


def get_client(provider_cfg: dict) -> AsyncOpenAI:
    api_key = os.environ.get(provider_cfg["key_env"], "")
    if not api_key:
        raise RuntimeError(f"missing API key env var: {provider_cfg['key_env']}")
    return AsyncOpenAI(base_url=provider_cfg["base_url"], api_key=api_key, timeout=180)


async def run_benchmark(providers: list[str], trials: int, tasks: list[TaskSpec]):
    # Warm up: ensure all repos are on a clean main
    for t in tasks:
        repo = (REPO_ROOT / t.repo).resolve()
        if (repo / ".git").exists():
            subprocess.run(["git", "checkout", "main"], cwd=repo, check=False, capture_output=True)

    all_records: list[TrialRecord] = []
    for provider_id in providers:
        cfg = PROVIDERS[provider_id]
        print(f"\n--- {cfg['label']} ---", flush=True)
        try:
            client = get_client(cfg)
        except Exception as e:
            print(f"  SKIP: {e}")
            continue
        for task in tasks:
            for trial in range(trials):
                rec = await run_trial(client, provider_id, cfg, task, trial)
                tag = "✓" if rec.success else "✗"
                rate = " [rate-limited]" if rec.rate_limited else ""
                err = f" err={rec.error[:80]}" if rec.error else ""
                print(
                    f"  {tag} {task.id:24s} {rec.wall_time_s:6.1f}s "
                    f"ttft={rec.time_to_first_token_s:5.1f}s "
                    f"tok/s={rec.tokens_per_s:5.1f} "
                    f"Δ={rec.diff_lines:4d}{rate}{err}",
                    flush=True,
                )
                all_records.append(rec)

    # Save results
    DEFAULT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = DEFAULT_RESULTS_DIR / f"benchmark_{ts}.json"
    with open(out_path, "w") as f:
        json.dump([asdict(r) for r in all_records], f, indent=2)
    print(f"\nResults written to {out_path}")
    return all_records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--providers",
        default="all",
        help="comma-separated provider ids, or 'all' (default)",
    )
    ap.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    ap.add_argument("--tasks", default=None, help="comma-separated task ids, or 'all'")
    args = ap.parse_args()

    if args.providers == "all":
        providers = list(PROVIDERS.keys())
    else:
        providers = [p.strip() for p in args.providers.split(",")]

    all_tasks = load_tasks(DEFAULT_TASKS_PATH)
    if args.tasks and args.tasks != "all":
        wanted = {t.strip() for t in args.tasks.split(",")}
        all_tasks = [t for t in all_tasks if t.id in wanted]

    print(f"Providers: {providers}")
    print(f"Tasks: {[t.id for t in all_tasks]}")
    print(f"Trials per (provider, task): {args.trials}")
    print(f"Total runs: {len(providers) * len(all_tasks) * args.trials}")
    print()

    asyncio.run(run_benchmark(providers, args.trials, all_tasks))


if __name__ == "__main__":
    main()
