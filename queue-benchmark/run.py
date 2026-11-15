#!/usr/bin/env python3
"""Postgres vs RabbitMQ vs Redis (BullMQ) vs NATS JetStream as a job queue.

One broker at a time, one bench driver container (producers + workers). Per config:
  enqueue          50k jobs, 10 in flight, broker-confirmed          -> jobs/s
  drain            50k preloaded jobs, W = 1/4/16 workers, no-op job -> jobs/s
  latency          1000 jobs/s open loop for 30 s, W = 4             -> p50/p95/p99 ms
  crash            producer at 2000 jobs/s; SIGKILL the broker 5 s in, restart it,
                   drain what survived                                -> confirmed jobs lost
Usage: python3 run.py [--quick] [--only postgres,redis] [--repeats 3] [--out results.json]
Writes results/<out> as {"meta": {...}, "perf": [...], "crash": [...]}.
"""
import argparse, json, platform, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).parent
# config -> (compose service, adapter, url, extra bench args)
CONFIGS = {
    "postgres":            ("postgres",        "postgres", "postgres://bench:bench@postgres:5432/bench", []),
    "postgres-nosync":     ("postgres-nosync", "postgres", "postgres://bench:bench@postgres-nosync:5432/bench", []),
    "redis":               ("redis",           "redis",    "redis://redis:6379", []),
    "redis-aof":           ("redis-aof",       "redis",    "redis://redis-aof:6379", []),
    "rabbitmq-default":    ("rabbitmq",        "rabbitmq", "amqp://bench:bench@rabbitmq:5672", []),
    "rabbitmq-persistent": ("rabbitmq",        "rabbitmq", "amqp://bench:bench@rabbitmq:5672", ["--persistent"]),
    "nats":                ("nats",            "nats",     "nats://nats:4222", []),
}
DRIVER = "queue-bench-driver"


def sh(*a, check=True):
    return subprocess.run(a, cwd=HERE, check=check, text=True, capture_output=True)


def stats(*names):
    """Peak-able sample: {name: (cpu_percent_of_one_core, mem_mib)}."""
    r = sh("docker", "stats", "--no-stream", "--format", "{{.Name}} {{.CPUPerc}} {{.MemUsage}}", *names, check=False)
    out = {}
    for line in r.stdout.splitlines():
        p = line.split()
        if len(p) >= 3:
            mem = float("".join(c for c in p[2] if c.isdigit() or c == "."))
            out[p[0]] = (float(p[1].rstrip("%")), mem * (1024 if "GiB" in p[2] else 1))
    return out


def start_bench(adapter, url, extra, mode, args):
    f = tempfile.NamedTemporaryFile("w+", delete=False, suffix=".out")
    cmd = ["docker", "compose", "run", "--rm", "-T", "--name", DRIVER, "bench", "node", "bench.js", adapter, mode,
           "--url", url, *extra, *map(str, args)]
    return subprocess.Popen(cmd, cwd=HERE, stdout=f, stderr=subprocess.STDOUT, text=True), Path(f.name)


def result_line(path):
    for line in path.read_text().splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[7:])
    sys.exit(f"no RESULT in {path}:\n{path.read_text()[-2000:]}")


def run_bench(cfg, mode, args, broker):
    service, adapter, url, extra = CONFIGS[cfg]
    p, out = start_bench(adapter, url, extra, mode, args)
    peak_cpu = {"driver": 0.0, "broker": 0.0}
    peak_mem = 0.0
    while p.poll() is None:
        time.sleep(2)
        s = stats(DRIVER, broker)
        if DRIVER in s:
            peak_cpu["driver"] = max(peak_cpu["driver"], s[DRIVER][0])
        if broker in s:
            peak_cpu["broker"] = max(peak_cpu["broker"], s[broker][0])
            peak_mem = max(peak_mem, s[broker][1])
    if p.returncode != 0:
        sys.exit(f"bench {cfg} {mode} failed:\n{out.read_text()[-2000:]}")
    r = result_line(out)
    r.update(driver_cpu_pct=round(peak_cpu["driver"]), broker_cpu_pct=round(peak_cpu["broker"]), broker_mem_mib=round(peak_mem))
    return r


def wait_healthy(container, timeout=180):
    t = time.time()
    while time.time() - t < timeout:
        st = sh("docker", "inspect", "-f", "{{.State.Health.Status}}", container, check=False).stdout.strip()
        if st == "healthy":
            return
        time.sleep(2)
    sys.exit(f"{container} not healthy after {timeout}s")


def crash_run(cfg, broker, kill_after, produce_s, rate):
    service, adapter, url, extra = CONFIGS[cfg]
    p, out = start_bench(adapter, url, extra, "crash-produce", ["--rate", rate, "--seconds", produce_s])
    while "READY" not in out.read_text():
        if p.poll() is not None:
            sys.exit(f"crash-produce died:\n{out.read_text()[-2000:]}")
        time.sleep(0.1)
    time.sleep(kill_after)
    sh("docker", "kill", "-s", "KILL", broker)          # SIGKILL: no flush, no clean shutdown
    p.wait(timeout=120)
    produced = result_line(out)
    sh("docker", "start", broker)
    wait_healthy(broker)
    time.sleep(3)
    p2, out2 = start_bench(adapter, url, extra, "crash-count", ["--workers", 4])
    p2.wait(timeout=300)
    counted = result_line(out2)
    confirmed, processed = set(produced["confirmed_ids"]), set(counted["processed_ids"])
    lost = len(confirmed - processed)
    return {"confirmed": len(confirmed), "failed_after_kill": produced["failed"], "survived": len(confirmed & processed),
            "lost": lost, "lost_pct": round(100 * lost / max(1, len(confirmed)), 2),
            "processed_not_confirmed": len(processed - confirmed), "duplicates": counted["duplicates"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small smoke run: 1 repeat, 5k jobs, 5s latency, W=4 only")
    ap.add_argument("--only", default=",".join(CONFIGS))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--skip", default="", help="comma list of scenarios to skip: enqueue,drain,latency,crash")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    n, lat_s, workers, reps = (5000, 5, [4], 1) if a.quick else (50000, 30, [1, 4, 16], a.repeats)
    kill_after, produce_s, crash_rate = (3, 8, 2000) if a.quick else (5, 12, 2000)
    skip = set(filter(None, a.skip.split(",")))
    out = HERE / "results" / (a.out or ("smoke.json" if a.quick else "results.json"))
    out.parent.mkdir(exist_ok=True)

    sh("docker", "compose", "build", "bench")
    pkg = json.loads((HERE / "app" / "package.json").read_text())["dependencies"]
    meta = {"clients": pkg, "jobs": n, "latency_seconds": lat_s, "latency_rate": 1000, "repeats": reps,
            "crash": {"kill_after_s": kill_after, "rate": crash_rate, "signal": "SIGKILL"},
            "host": {"machine": platform.machine(), "docker": sh("docker", "--version").stdout.strip(),
                     "vm": sh("docker", "info", "--format", "{{.NCPU}} CPUs, {{.MemTotal}} bytes").stdout.strip()},
            "images": {}}
    perf, crash = [], []
    save = lambda: out.write_text(json.dumps({"meta": meta, "perf": perf, "crash": crash}, indent=1))

    for cfg in a.only.split(","):
        service = CONFIGS[cfg][0]
        broker = f"queue-{service}-1"
        sh("docker", "compose", "up", "-d", "--wait", service)
        meta["images"][service] = sh("docker", "inspect", broker, "--format", "{{.Config.Image}} {{.Image}}").stdout.strip()
        for rep in range(1, reps + 1):
            plan = []
            if "enqueue" not in skip: plan.append(("enqueue", ["--n", n, "--p", 10]))
            if "drain" not in skip: plan += [("drain", ["--n", n, "--workers", w]) for w in workers]
            if "latency" not in skip: plan.append(("latency", ["--rate", 1000, "--seconds", lat_s, "--workers", 4]))
            for mode, args in plan:
                r = {"config": cfg, "scenario": mode, "run": rep, **run_bench(cfg, mode, args, broker)}
                perf.append(r); save()
                print(cfg, mode, rep, {k: v for k, v in r.items() if k in ("workers", "jobs_per_s", "p50_ms", "p99_ms", "skipped")}, flush=True)
            if "crash" not in skip:
                c = {"config": cfg, "run": rep, **crash_run(cfg, broker, kill_after, produce_s, crash_rate)}
                crash.append(c); save()
                print(cfg, "crash", rep, c, flush=True)
        sh("docker", "compose", "stop", service)
    sh("docker", "compose", "down", "-v")
    print("wrote", out)


if __name__ == "__main__":
    sys.exit(main())
