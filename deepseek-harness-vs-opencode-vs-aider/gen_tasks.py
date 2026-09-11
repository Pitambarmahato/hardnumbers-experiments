"""Generates the 8-task pilot suite for the harness benchmark.

Each task gets its own git-initialized repo under tasks/<id>/repo/, a
prompt.txt (the exact text handed to the harness), and a check.py that exits
0 if the task was done correctly (run against the harness's output repo,
never shipped to the harness itself).

Categories, matching multi-agent-coding-1-vs-4-vs-8's framework:
- isolated (3): single-file, self-contained fix
- tightly_coupled (3): change spans 2-3 files with shared state
- sequential (2): implement-then-test, later step depends on earlier step
"""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent / "tasks"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=repo,
        check=True,
    )


TASKS = {}


def task(task_id, category, prompt, files, check):
    TASKS[task_id] = dict(category=category, prompt=prompt, files=files, check=check)


# ---------------------------------------------------------------- isolated --

task(
    "isolated_offbyone",
    "isolated",
    "Fix the bug in stats.py so that test_stats.py passes. Do not modify test_stats.py.",
    {
        "stats.py": (
            "def last_n(items, n):\n"
            "    # bug: off-by-one, drops the final element\n"
            "    return items[-n:-1]\n"
        ),
        "test_stats.py": (
            "from stats import last_n\n\n"
            "def test_last_n():\n"
            "    assert last_n([1, 2, 3, 4, 5], 3) == [3, 4, 5]\n"
        ),
    },
    "pytest -q test_stats.py",
)

task(
    "isolated_validation",
    "isolated",
    "Add input validation to divide() in mathops.py: raise ValueError if the "
    "divisor is zero. Make test_mathops.py pass. Do not modify test_mathops.py.",
    {
        "mathops.py": (
            "def divide(a, b):\n"
            "    return a / b\n"
        ),
        "test_mathops.py": (
            "import pytest\n"
            "from mathops import divide\n\n"
            "def test_divide():\n"
            "    assert divide(10, 2) == 5\n\n"
            "def test_divide_by_zero():\n"
            "    with pytest.raises(ValueError):\n"
            "        divide(1, 0)\n"
        ),
    },
    "pytest -q test_mathops.py",
)

task(
    "isolated_typehints",
    "isolated",
    "Add type hints to every function in strutil.py (parameters and return "
    "types). Do not change behavior. Make test_strutil.py pass, and it must "
    "still pass mypy --strict on strutil.py.",
    {
        "strutil.py": (
            "def slugify(text):\n"
            "    return text.strip().lower().replace(' ', '-')\n\n"
            "def truncate(text, length):\n"
            "    return text if len(text) <= length else text[:length] + '...'\n"
        ),
        "test_strutil.py": (
            "from strutil import slugify, truncate\n\n"
            "def test_slugify():\n"
            "    assert slugify('  Hard Numbers ') == 'hard-numbers'\n\n"
            "def test_truncate():\n"
            "    assert truncate('hello world', 5) == 'hello...'\n"
        ),
    },
    "pytest -q test_strutil.py && python3 -m mypy --strict strutil.py",
)

# ----------------------------------------------------------- tightly_coupled --

task(
    "coupled_rename",
    "tightly_coupled",
    "Rename the function compute_total to compute_order_total everywhere it "
    "is defined or called across the repo (order.py, receipt.py, and the "
    "test file), keeping behavior identical. Make test_order.py pass.",
    {
        "order.py": (
            "def compute_total(items):\n"
            "    return sum(i['price'] * i['qty'] for i in items)\n"
        ),
        "receipt.py": (
            "from order import compute_total\n\n"
            "def format_receipt(items):\n"
            "    total = compute_total(items)\n"
            "    return f'Total: ${total:.2f}'\n"
        ),
        "test_order.py": (
            "from order import compute_order_total\n"
            "from receipt import format_receipt\n\n"
            "def test_compute_order_total():\n"
            "    items = [{'price': 2.0, 'qty': 3}]\n"
            "    assert compute_order_total(items) == 6.0\n\n"
            "def test_format_receipt():\n"
            "    items = [{'price': 2.0, 'qty': 3}]\n"
            "    assert format_receipt(items) == 'Total: $6.00'\n"
        ),
    },
    "pytest -q test_order.py",
)

task(
    "coupled_new_field",
    "tightly_coupled",
    "Add a 'discount_pct' field (default 0) to the Order dataclass in "
    "models.py. Update total() in models.py to apply the discount, and "
    "update the caller in checkout.py to pass discount_pct through from its "
    "own 'discount' argument. Make test_checkout.py pass, without modifying it.",
    {
        "models.py": (
            "from dataclasses import dataclass\n\n"
            "@dataclass\n"
            "class Order:\n"
            "    subtotal: float\n\n"
            "    def total(self):\n"
            "        return self.subtotal\n"
        ),
        "checkout.py": (
            "from models import Order\n\n"
            "def checkout(subtotal, discount=0):\n"
            "    order = Order(subtotal=subtotal)\n"
            "    return order.total()\n"
        ),
        "test_checkout.py": (
            "from checkout import checkout\n\n"
            "def test_checkout_no_discount():\n"
            "    assert checkout(100) == 100\n\n"
            "def test_checkout_with_discount():\n"
            "    assert checkout(100, discount=10) == 90\n"
        ),
    },
    "pytest -q test_checkout.py",
)

task(
    "coupled_shared_constant",
    "tightly_coupled",
    "The retry limit '3' is hardcoded separately in client.py and worker.py. "
    "Extract it into a single MAX_RETRIES constant in config.py and import it "
    "in both files. Make test_retry.py pass.",
    {
        "config.py": "# shared configuration constants\n",
        "client.py": (
            "def fetch_with_retry(fn):\n"
            "    for attempt in range(3):\n"
            "        try:\n"
            "            return fn()\n"
            "        except Exception:\n"
            "            continue\n"
            "    raise RuntimeError('failed after retries')\n"
        ),
        "worker.py": (
            "def run_with_retry(fn):\n"
            "    for attempt in range(3):\n"
            "        try:\n"
            "            return fn()\n"
            "        except Exception:\n"
            "            continue\n"
            "    raise RuntimeError('failed after retries')\n"
        ),
        "test_retry.py": (
            "import config\n"
            "import client, worker\n\n"
            "def test_max_retries_constant():\n"
            "    assert config.MAX_RETRIES == 3\n\n"
            "def test_client_uses_constant():\n"
            "    assert 'config.MAX_RETRIES' in open('client.py').read()\n\n"
            "def test_worker_uses_constant():\n"
            "    assert 'config.MAX_RETRIES' in open('worker.py').read()\n"
        ),
    },
    "pytest -q test_retry.py",
)

# --------------------------------------------------------------- sequential --

task(
    "sequential_feature_then_test",
    "sequential",
    "Implement a function `is_palindrome(s)` in palindrome.py that returns "
    "True if s reads the same forwards and backwards, ignoring case and "
    "spaces. Then write test_palindrome.py with at least 3 test cases "
    "(including one true, one false, and one with mixed case/spaces) and "
    "make sure they pass.",
    {
        "palindrome.py": "# implement is_palindrome here\n",
    },
    "pytest -q test_palindrome.py",
)

task(
    "sequential_migrate_then_update",
    "sequential",
    "In schema.py, add a new 'email' field (string, required) to the User "
    "namedtuple/class. Then update every place in seed.py that constructs a "
    "User to pass an email value, and update test_seed.py's assertions to "
    "check the new field. Make test_seed.py pass.",
    {
        "schema.py": (
            "from dataclasses import dataclass\n\n"
            "@dataclass\n"
            "class User:\n"
            "    name: str\n"
        ),
        "seed.py": (
            "from schema import User\n\n"
            "def seed_users():\n"
            "    return [User(name='Ada'), User(name='Grace')]\n"
        ),
        "test_seed.py": (
            "from seed import seed_users\n\n"
            "def test_seed_users():\n"
            "    users = seed_users()\n"
            "    assert len(users) == 2\n"
            "    assert users[0].name == 'Ada'\n"
            "    assert '@' in users[0].email\n"
            "    assert '@' in users[1].email\n"
        ),
    },
    "pytest -q test_seed.py",
)


def main():
    for task_id, spec in TASKS.items():
        repo = ROOT / task_id / "repo"
        for filename, content in spec["files"].items():
            write(repo / filename, content)
        git_init(repo)
        write(ROOT / task_id / "prompt.txt", spec["prompt"])
        write(ROOT / task_id / "check.sh", f"#!/usr/bin/env bash\nset -e\n{spec['check']}\n")
        os.chmod(ROOT / task_id / "check.sh", 0o755)
        write(ROOT / task_id / "category.txt", spec["category"])
        print(f"  + {task_id} ({spec['category']})")


if __name__ == "__main__":
    main()
