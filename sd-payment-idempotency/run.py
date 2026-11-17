#!/usr/bin/env python3
"""Run one (variant, scenario, repeat). Variants: naive | idem-local | idem-e2e. Scenarios: s1..s5 (see docs/kw-sd-payment-idempotency.md).
Truth is the mock provider's own ledger (how many charges it recorded per order), not anything the service says.
Usage: .venv/bin/python3 run.py --variant naive --scenario s2 --rep 0 [--quick]"""
import argparse, asyncio, json, os, platform, random, statistics as st, subprocess, time
from pathlib import Path
import aiohttp

HERE = Path(__file__).parent
SVC, PROV = "http://127.0.0.1:18080", "http://127.0.0.1:18081"
VARIANTS = {"naive": ("naive", "0"), "idem-local": ("designed", "0"), "idem-e2e": ("designed", "1")}
TRIES, BACKOFF = 10, 0.4
# orders, concurrent orders, provider delay ms, client timeout s
SCEN = {"s1": (10000, 50, 50, 2.0), "s2": (2000, 100, 1500, 1.0), "s3": (1000, 100, 1000, 2.0),
        "s4": (2000, 100, 50, 2.0), "s5": (500, 50, 50, 2.0)}
KILL_AT_S = 2.0


async def sh(*cmd, env=None):
    p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env={**os.environ, **(env or {})}, cwd=HERE)
    out, _ = await p.communicate()
    return p.returncode, out.decode()


async def wait_health(s, url, secs=60):
    for _ in range(secs * 2):
        try:
            async with s.get(url + "/health", timeout=aiohttp.ClientTimeout(total=1)) as r:
                if r.status == 200: return
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError(f"{url} not healthy")


async def place(s, rng, oid, amount, timeout, key=None):
    """One client: same key and body on every retry; retries timeouts, connection errors, 5xx and 409."""
    t0, statuses = time.perf_counter(), []
    for attempt in range(1, TRIES + 1):
        try:
            async with s.post(SVC + "/charges", json={"order_id": oid, "amount": amount}, headers={"Idempotency-Key": key or f"key-{oid}"},
                              timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                await r.read(); status = r.status
        except (asyncio.TimeoutError, aiohttp.ClientError):
            status = 0                                        # 0 = timeout or connection error
        statuses.append(status)
        if status == 200 or status in (400, 422):
            break
        await asyncio.sleep(BACKOFF + rng.random() * 0.1)
    return {"ok": statuses[-1] == 200, "last": statuses[-1], "attempts": len(statuses), "ms": (time.perf_counter() - t0) * 1000, "statuses": statuses}


async def run(variant, scen, rep, quick):
    n, conc, delay, timeout = SCEN[scen]
    if quick: n = 500 if scen == "s3" else max(100, n // 10)   # s3 needs enough load to still be running when the kill lands
    vdir, pk = VARIANTS[variant]
    await sh("docker", "compose", "up", "-d", "--wait", "pg", "provider")
    rc, out = await sh("docker", "compose", "up", "-d", "--force-recreate", "--no-deps", "svc", env={"VARIANT": vdir, "PASS_KEY": pk})
    conn = aiohttp.TCPConnector(limit=600)
    async with aiohttp.ClientSession(connector=conn) as s:
        await wait_health(s, SVC); await wait_health(s, PROV)
        for u in (SVC, PROV):
            await s.post(u + "/admin/reset")
        await s.post(PROV + "/admin/config", json={"delay_ms": delay})
        rng, sem = random.Random(7000 + rep), asyncio.Semaphore(conc)
        events, results = [], {}

        async def order(i):
            oid, amount = f"o{rep}-{i}", 1000 + i % 97
            async with sem:
                if scen == "s4":                              # double click: two requests at the same instant
                    a, b = await asyncio.gather(place(s, random.Random(i), oid, amount, timeout), place(s, random.Random(i + 1), oid, amount, timeout))
                    r = {"ok": a["ok"] or b["ok"], "last": a["last"], "attempts": a["attempts"] + b["attempts"], "ms": max(a["ms"], b["ms"]), "statuses": a["statuses"] + b["statuses"]}
                elif scen == "s5":                            # same key, second request carries a different amount
                    a = await place(s, rng, oid, amount, timeout)
                    b = await place(s, rng, oid, amount + 500, timeout, key=f"key-{oid}")
                    r = {**a, "second": b["last"], "second_ok": b["ok"]}
                else:
                    r = await place(s, rng, oid, amount, timeout)
            results[oid] = r

        async def killer():
            await asyncio.sleep(KILL_AT_S)
            await sh("docker", "kill", "sdidem-svc-1"); events.append(("kill", round(time.perf_counter() - t_start, 2)))
            await sh("docker", "start", "sdidem-svc-1"); await wait_health(s, SVC); events.append(("restarted", round(time.perf_counter() - t_start, 2)))

        t_start = time.perf_counter()
        kt = asyncio.create_task(killer()) if scen == "s3" else None
        await asyncio.gather(*(order(i) for i in range(n)))
        wall = time.perf_counter() - t_start
        if kt: await kt
        async with s.get(PROV + "/admin/orders") as r:
            ledger = await r.json()

    mine = {o: ledger.get(o, 0) for o in results}
    ms = sorted(r["ms"] for r in results.values()); q = lambda p: ms[min(len(ms) - 1, int(p * len(ms)))]
    out = {"meta": {"variant": variant, "scenario": scen, "rep": rep, "orders": n, "concurrency": conc, "provider_delay_ms": delay, "client_timeout_s": timeout,
                    "tries": TRIES, "backoff_s": BACKOFF, "wall_s": round(wall, 2), "quick": quick, "events": events, "python": platform.python_version()},
           "orders_charged_twice_or_more": sum(c >= 2 for c in mine.values()),
           "extra_charges": sum(max(0, c - 1) for c in mine.values()),
           "orders_never_charged": sum(c == 0 for c in mine.values()),
           "client_gave_up": sum(not r["ok"] for r in results.values()),
           "charged_but_client_gave_up": sum((not r["ok"]) and mine[o] >= 1 for o, r in results.items()),
           "orders_per_s": round(n / wall, 1), "p50_ms": round(q(.5), 1), "p99_ms": round(q(.99), 1),
           "mean_attempts": round(st.mean(r["attempts"] for r in results.values()), 2),
           "http_requests": sum(r["attempts"] for r in results.values()),
           "ledger_total": sum(ledger.get(o, 0) for o in results)}
    if scen == "s3":
        kill_t = next((t for e, t in events if e == "kill"), None)
        out["kill_during_load"] = kill_t is not None and kill_t < wall      # False = the run is invalid, discard it
    if scen == "s5":
        out["s5_second_rejected"] = sum(r["second"] in (409, 422, 400) for r in results.values())
        out["s5_second_accepted_200"] = sum(r["second"] == 200 for r in results.values())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=list(VARIANTS), required=True)
    ap.add_argument("--scenario", choices=list(SCEN), required=True)
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    out = asyncio.run(run(a.variant, a.scenario, a.rep, a.quick))
    d = HERE / "results" / ("quick" if a.quick else "full"); d.mkdir(parents=True, exist_ok=True)
    p = d / f"{a.scenario}-{a.variant}-r{a.rep}.json"; p.write_text(json.dumps(out, indent=1))
    keys = ["orders_charged_twice_or_more", "extra_charges", "orders_never_charged", "client_gave_up", "charged_but_client_gave_up", "orders_per_s", "p50_ms", "p99_ms", "mean_attempts"]
    print(f"{a.scenario} {a.variant} r{a.rep} n={out['meta']['orders']} wall={out['meta']['wall_s']}s | " + " ".join(f"{k}={out[k]}" for k in keys), out["meta"]["events"], "kill_during_load=" + str(out.get("kill_during_load")) if a.scenario == "s3" else "")
    if a.scenario == "s5": print("  s5:", out["s5_second_rejected"], "rejected,", out["s5_second_accepted_200"], "accepted")


if __name__ == "__main__":
    main()
