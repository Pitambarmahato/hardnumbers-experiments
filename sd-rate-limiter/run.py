#!/usr/bin/env python3
"""Run one (variant, scenario, repeat). Variants: naive-fixed | fixed | sliding-log | sliding-counter | token-bucket.
Scenarios: s1 boundary burst, s2 flood, s3 many keys (see docs/kw-sd-rate-limiter.md). Truth is the decision time of each ALLOWED request
(Redis TIME for the Lua variants, the client clock for naive-fixed), not the limiter's own counters. Usage: .venv/bin/python3 run.py --variant fixed --scenario s1 --rep 0 [--quick]"""
import argparse, asyncio, json, math, platform, random, statistics as st, sys, time
from collections import Counter
from pathlib import Path
import redis.asyncio as aioredis
import redis as redis_pkg

HERE = Path(__file__).parent
URL = "redis://127.0.0.1:16379/0"
VARIANTS = ("naive-fixed", "fixed", "sliding-log", "sliding-counter", "token-bucket")
L, W = 100, 1  # requests per window, window seconds (s3 uses W = 3600)

HEAD = """local t = redis.call('TIME'); local now = t[1] * 1000000 + t[2]
local limit = tonumber(ARGV[1]); local w = tonumber(ARGV[2]); local wus = w * 1000000
"""
LUA = {
    "fixed": HEAD + """local k = KEYS[1] .. ':' .. math.floor(now / wus)
local c = redis.call('INCR', k)
if c == 1 then redis.call('EXPIRE', k, w) end
if c <= limit then return {1, now} end
return {0, now}""",
    "sliding-log": HEAD + """redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - wus)
if redis.call('ZCARD', KEYS[1]) < limit then
  redis.call('ZADD', KEYS[1], now, ARGV[3]); redis.call('EXPIRE', KEYS[1], w); return {1, now}
end
return {0, now}""",
    "sliding-counter": HEAD + """local win = math.floor(now / wus)
local cur_k = KEYS[1] .. ':' .. win
local prev = tonumber(redis.call('GET', KEYS[1] .. ':' .. (win - 1))) or 0
local cur = tonumber(redis.call('GET', cur_k)) or 0
local elapsed = (now - win * wus) / wus
if prev * (1 - elapsed) + cur < limit then
  redis.call('INCR', cur_k); redis.call('EXPIRE', cur_k, 2 * w); return {1, now}
end
return {0, now}""",
    "token-bucket": HEAD + """local h = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(h[1]); local ts = tonumber(h[2])
if tokens == nil then tokens = limit; ts = now end
tokens = math.min(limit, tokens + (now - ts) / 1000000 * (limit / w))
local ok = 0
if tokens >= 1 then tokens = tokens - 1; ok = 1 end
redis.call('HSET', KEYS[1], 'tokens', string.format('%.6f', tokens), 'ts', string.format('%.0f', now))
redis.call('EXPIRE', KEYS[1], w + 1)
return {ok, now}""",
}


def make_check(variant, r, w):
    seq = iter(range(10**12))
    if variant == "naive-fixed":
        async def check(key):  # read, decide, write: three round trips, nothing atomic
            win = int(time.time() // w)
            k = f"{key}:{win}"
            c = int(await r.get(k) or 0)
            decided = time.time()  # the moment the client decides
            if c >= L: return 0, decided, win
            if await r.incr(k) == 1: await r.expire(k, w)
            return 1, decided, win
        return check
    script = r.register_script(LUA[variant])

    async def check(key):
        ok, us = await script(keys=[key], args=[L, w, next(seq)])
        return ok, us / 1e6, int(us // (w * 1_000_000))  # time and window as Redis saw them
    return check


def span_max(ts, w):
    """Most timestamps in any half-open span [t, t + w) that starts at one of them."""
    best, j = 0, 0
    for i, t in enumerate(ts):
        while ts[j] <= t - w: j += 1
        best = max(best, i - j + 1)
    return best



async def one(check, key, rec):
    t0 = time.perf_counter()
    try:
        ok, when, win = await check(key)
        rec["lat"].append((time.perf_counter() - t0) * 1000)
        if ok: rec["allowed"].append(when); rec["wins"][win] += 1
        else: rec["denied"] += 1
    except Exception as e:  # noqa: BLE001
        rec["errors"] += 1; rec["err_kinds"][type(e).__name__] += 1


async def s1(check, quick, rec):
    cycles = 3 if quick else 10
    start = math.ceil(time.time()) + 3
    for i in range(cycles):
        b = start + 3 * i  # a window boundary (integer second)
        for at in (b - 0.06, b + 0.01):
            while (d := at - time.time()) > 0: await asyncio.sleep(min(d, 0.005))
            await asyncio.gather(*[one(check, "k", rec) for _ in range(100)])


async def s2(check, quick, rec):
    end = time.perf_counter() + (3 if quick else 10)
    async def worker():
        while time.perf_counter() < end: await one(check, "k", rec)
    await asyncio.gather(*[worker() for _ in range(100)])


async def s3(check, quick, rec, seed):
    keys = 200 if quick else 2000
    order = [f"u{i}" for i in range(keys) for _ in range(100)]
    random.Random(seed).shuffle(order)
    it = iter(order)
    async def worker():
        for k in it: await one(check, k, rec)
    await asyncio.gather(*[worker() for _ in range(100)])
    return keys


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, choices=VARIANTS); ap.add_argument("--scenario", required=True, choices=("s1", "s2", "s3"))
    ap.add_argument("--rep", type=int, default=0); ap.add_argument("--quick", action="store_true"); ap.add_argument("--dump", action="store_true")
    a = ap.parse_args()
    w = 3600 if a.scenario == "s3" else W
    r = aioredis.from_url(URL, max_connections=120)
    await r.flushall()
    await asyncio.gather(*[r.ping() for _ in range(100)])  # open the connections before timing
    base_mem = (await r.info("memory"))["used_memory"]
    check = make_check(a.variant, r, w)
    if a.variant != "naive-fixed": await check("warmup"); await r.flushall(); base_mem = (await r.info("memory"))["used_memory"]
    rec = {"wins": Counter(), "allowed": [], "denied": 0, "errors": 0, "err_kinds": Counter(), "lat": []}
    t0 = time.time()
    keys = None
    if a.scenario == "s1": await s1(check, a.quick, rec)
    elif a.scenario == "s2": await s2(check, a.quick, rec)
    else: keys = await s3(check, a.quick, rec, a.rep)
    t1 = time.time()
    ts = sorted(rec["allowed"])
    lat = sorted(rec["lat"])
    n = len(lat)
    out = {"variant": a.variant, "scenario": a.scenario, "rep": a.rep, "quick": a.quick, "limit": L, "window_s": w,
           "attempts": n + rec["errors"], "allowed": len(ts), "denied": rec["denied"], "errors": rec["errors"], "error_kinds": dict(rec["err_kinds"]),
           "duration_s": round(t1 - t0, 2), "throughput_per_s": round(n / max(t1 - t0, 1e-9), 1),
           "p50_ms": round(st.median(lat), 2) if lat else None, "p99_ms": round(lat[int(n * 0.99) - 1], 2) if n else None}
    if a.scenario in ("s1", "s2"):
        out["max_sliding"] = span_max(ts, w)
        out["max_aligned"] = max(rec["wins"].values()) if ts else 0
        late = [t for t in ts if t >= t0 + 2]
        out["max_sliding_after2s"] = span_max(late, w) if a.scenario == "s2" else None
    else:
        # MEMORY USAGE per key (key name + value + overhead). The first attempt diffed used_memory and went negative.
        names = [k async for k in r.scan_iter(count=1000)]
        pipe = r.pipeline(transaction=False)
        for k in names: pipe.memory_usage(k)
        sizes = await pipe.execute()
        out["keys"] = keys; out["redis_keys"] = len(names); out["mem_per_key_bytes"] = round(sum(sizes) / keys)
    if a.dump: (HERE / "dump.json").write_text(json.dumps([round(t - t0, 4) for t in ts]))
    out.update(redis=(await r.info("server"))["redis_version"], redis_py=redis_pkg.__version__, python=platform.python_version(), platform=platform.platform())
    d = HERE / "results" / ("quick" if a.quick else "full"); d.mkdir(parents=True, exist_ok=True)
    (d / f"{a.scenario}-{a.variant}-r{a.rep}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("redis", "redis_py", "python", "platform")}))
    await r.aclose()

asyncio.run(main())
