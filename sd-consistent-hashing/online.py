#!/usr/bin/env python3
"""Online scenarios S1-S4: cache-aside lookups over 3-4 Redis nodes in front of Postgres.

Routing schemes: modn | ring1 | ring10 | ring150 (ring V=1/10/150). One run = one (scheme, scenario, repeat).
Open-loop load at a fixed request rate (latency counts from the scheduled start, so queueing shows up).
Results: results/online/<scenario>-<scheme>-r<repeat>.json (1-second buckets). Pre-registration: docs/kw-sd-consistent-hashing.md (A1, A2).
Driver runs on the host; the only hard dependencies are redis-py 6.4.0 + asyncpg 0.30.0 (see README).
"""
import argparse, asyncio, json, platform, random, subprocess, sys, time
from bisect import bisect_left
from pathlib import Path
import asyncpg, redis.asyncio as aioredis
from run_s0 import h64, ring

HERE = Path(__file__).parent
NKEYS, VSIZE = 100_000, 1024
PORTS = {0: 16380, 1: 16381, 2: 16382, 3: 16383}
PG = dict(host="127.0.0.1", port=15432, user="bench", password="bench", database="bench")
RATE, DETECT_S = 3000, 5          # requests/s (A2); seconds from kill to the client dropping the node (A2)
ZIPF_S = 1.1


def value(i):
    return i.to_bytes(8, "big") * (VSIZE // 8)


def owners(scheme, nodes, kh, salt):
    """owner node id per key id, for a node set."""
    if scheme == "modn":
        return [nodes[h % len(nodes)] for h in kh]
    pts, own = ring(nodes, int(scheme[4:]), salt)
    n = len(pts)
    return [own[bisect_left(pts, h) % n] for h in kh]


async def sh(*cmd):
    p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await p.communicate()
    return p.returncode, out.decode()


async def wait_ready(nodes):
    for n in nodes:
        for _ in range(60):
            try:
                c = aioredis.Redis(port=PORTS[n]); await c.ping(); await c.aclose(); break
            except Exception:
                await asyncio.sleep(0.5)
        else:
            raise RuntimeError(f"r{n} not ready")


async def seed_pg(pool):
    if await pool.fetchval("SELECT to_regclass('kv') IS NOT NULL") and await pool.fetchval("SELECT count(*) FROM kv") == NKEYS:
        return
    await pool.execute("DROP TABLE IF EXISTS kv; CREATE TABLE kv (id int PRIMARY KEY, val bytea NOT NULL)")
    await pool.executemany("INSERT INTO kv VALUES ($1, $2)", [(i, value(i)) for i in range(NKEYS)])
    await pool.execute("VACUUM ANALYZE kv")


def key_stream(kind, n, seed):
    rng = random.Random(seed)
    if kind == "uniform":
        return [rng.randrange(NKEYS) for _ in range(n)]
    # zipf: rank r has weight 1/r^s; ranks map to key ids through a seeded shuffle so the hot keys are not sequential
    perm = list(range(NKEYS)); random.Random(seed + 1).shuffle(perm)
    cum, t = [], 0.0
    for r in range(1, NKEYS + 1):
        t += 1 / r ** ZIPF_S; cum.append(t)
    return [perm[r] for r in rng.choices(range(NKEYS), cum_weights=cum, k=n)]


async def run(scenario, scheme, rep, secs, rate, quick):
    kh = [h64(f"key:{i}") for i in range(NKEYS)]
    salt = f"t{rep}"
    own3 = owners(scheme, [0, 1, 2], kh, salt)
    own4 = owners(scheme, [0, 1, 2, 3], kh, salt)
    own2 = owners(scheme, [0, 1], kh, salt)                     # after r2 is removed (S3)
    nodes = [0, 1, 2, 3]
    await sh("docker", "compose", "start", "r0", "r1", "r2", "r3", "pg")
    await wait_ready(nodes)
    rc = {n: aioredis.Redis(port=PORTS[n], socket_connect_timeout=0.3, socket_timeout=0.5, max_connections=64) for n in nodes}
    for c in rc.values():
        await c.flushall()
    pool = await asyncpg.create_pool(**PG, min_size=16, max_size=16)
    await seed_pg(pool)
    # warm: every key in its owner under the 3-node layout. Done directly, not through traffic.
    for n in (0, 1, 2):
        async with rc[n].pipeline(transaction=False) as p:
            for i in range(NKEYS):
                if own3[i] == n:
                    p.set(f"key:{i}", value(i))
            await p.execute()

    switch_at = 10 if scenario in ("s2", "s3") else None
    total = secs
    nreq = int(rate * total)
    keys = key_stream("zipf" if scenario == "s4" else "uniform", nreq, seed=1000 + rep)   # same stream for every scheme at a given repeat
    nb = total + 1
    B = lambda: dict(n=0, hit=0, miss=0, err=0, wrong=0, db=0, lat=[], node=[0, 0, 0, 0])
    buckets = [B() for _ in range(nb)]
    state = dict(own=own3, up={0, 1, 2}, routed=[0, 1, 2], events=[])
    sem = asyncio.Semaphore(400)
    t_start = time.perf_counter() + 0.5

    async def one(i, sched):
        async with sem:
            key = keys[i]
            node = state["own"][key]
            b = buckets[min(int(sched - t_start), nb - 1)]
            b["node"][node] += 1
            try:
                v = await rc[node].get(f"key:{key}")
            except Exception:
                v = None; b["err"] += 1
                cache_ok = False
            else:
                cache_ok = True
            if v is None:
                b["miss"] += 1
                v = await pool.fetchval("SELECT val FROM kv WHERE id = $1", key)
                b["db"] += 1
                if cache_ok:
                    try: await rc[node].set(f"key:{key}", v)
                    except Exception: b["err"] += 1
            else:
                b["hit"] += 1
            if v != value(key):
                b["wrong"] += 1
            b["n"] += 1
            b["lat"].append((time.perf_counter() - sched) * 1000)

    async def control():
        if switch_at is None:
            return
        await asyncio.sleep(max(0, t_start + switch_at - time.perf_counter()))
        if scenario == "s2":
            state["own"] = own4; state["events"].append(("add_r3", time.perf_counter() - t_start))
        else:
            await sh("docker", "kill", "sdch-r2-1"); state["events"].append(("kill_r2", time.perf_counter() - t_start))
            await asyncio.sleep(DETECT_S)
            state["own"] = own2; state["events"].append(("route_drop_r2", time.perf_counter() - t_start))

    tasks, ctl = [], asyncio.create_task(control())
    i, tick = 0, 0.01
    while i < nreq:
        now = time.perf_counter()
        due = min(nreq, int((now - t_start) / tick + 1) * int(rate * tick)) if now >= t_start else 0
        while i < due:
            tasks.append(asyncio.create_task(one(i, t_start + i / rate))); i += 1
        await asyncio.sleep(tick / 2)
    await asyncio.gather(*tasks); await ctl
    wall = time.perf_counter() - t_start
    for c in rc.values():
        await c.aclose()
    await pool.close()
    if scenario == "s3":
        await sh("docker", "compose", "start", "r2")

    def summ(b):
        l = sorted(b["lat"]); q = lambda p: l[min(len(l) - 1, int(p * len(l)))] if l else None
        return dict(n=b["n"], hit=b["hit"], miss=b["miss"], err=b["err"], wrong=b["wrong"], db=b["db"], node=b["node"], p50=q(.5), p99=q(.99))
    out = dict(meta=dict(scenario=scenario, scheme=scheme, rep=rep, salt=salt, secs=total, rate=rate, nkeys=NKEYS, vsize=VSIZE, switch_at=switch_at,
                         detect_s=DETECT_S, wall_s=round(wall, 2), quick=quick, python=platform.python_version(), events=state["events"]),
               buckets=[summ(b) for b in buckets[:total]])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=["s1", "s2", "s3", "s4"], required=True)
    ap.add_argument("--scheme", choices=["modn", "ring1", "ring10", "ring150"], required=True)
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--secs", type=int, default=None)
    ap.add_argument("--rate", type=int, default=RATE)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    secs = a.secs or {"s1": 30, "s2": 70, "s3": 70, "s4": 30}[a.scenario]
    out = asyncio.run(run(a.scenario, a.scheme, a.rep, secs, a.rate, a.quick))
    d = HERE / "results" / ("online-quick" if a.quick else "online"); d.mkdir(parents=True, exist_ok=True)
    p = d / f"{a.scenario}-{a.scheme}-r{a.rep}.json"; p.write_text(json.dumps(out))
    bs = out["buckets"]
    for t in range(0, len(bs), 5):
        b = bs[t]; print(f"t={t:>3}s n={b['n']:>5} hit={b['hit']/max(1,b['n']):.1%} db={b['db']:>5} err={b['err']:>4} p50={b['p50'] or 0:.1f} p99={b['p99'] or 0:.1f}")
    print("wrong values:", sum(b["wrong"] for b in bs), "| wall", out["meta"]["wall_s"], "s |", p)


if __name__ == "__main__":
    main()
