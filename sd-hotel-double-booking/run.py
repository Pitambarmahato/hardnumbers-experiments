#!/usr/bin/env python3
"""Run one (variant, scenario, repeat). Variants: naive | pessimistic | optimistic | exclusion | exclusion-retry. Scenarios: s1 s2 s3
(see docs/kw-sd-hotel-double-booking.md). Truth is an audit query over the bookings table after the run, not the
driver's own counters. Usage: .venv/bin/python3 run.py --variant naive --scenario s2 --rep 0 [--quick]"""
import argparse, asyncio, datetime as dt, json, platform, random, statistics as st, subprocess, sys, time
from pathlib import Path
import asyncpg

HERE = Path(__file__).parent
DSN = "postgresql://bench:bench@127.0.0.1:15433/bench"
VARIANTS = ("naive", "pessimistic", "optimistic", "exclusion", "exclusion-retry")
# attempts, concurrency, pool size, rooms, window nights, min stay, max stay
SCEN = {"s1": (10000, 50, 50, 200, 60, 1, 5),
        "s2": (2000, 100, 100, 10, 5, 1, 3),
        "s3": (2000, 400, 20, 10, 5, 1, 3)}
MAX_TRIES, JITTER_S, ACQUIRE_TIMEOUT_S = 5, 0.005, 5.0
BASE = dt.date(2027, 1, 1)

OVERLAP = "SELECT 1 FROM bookings WHERE room_id = $1 AND stay && daterange($2::date, $3::date) LIMIT 1"
INSERT = "INSERT INTO bookings (room_id, stay) VALUES ($1, daterange($2::date, $3::date))"


async def reset(variant, rooms):
    c = await asyncpg.connect(DSN)
    await c.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    await c.execute("DROP TABLE IF EXISTS bookings; DROP TABLE IF EXISTS rooms")
    await c.execute("CREATE TABLE rooms (id int PRIMARY KEY, version int NOT NULL DEFAULT 0)")
    await c.execute("CREATE TABLE bookings (id bigserial PRIMARY KEY, room_id int NOT NULL, stay daterange NOT NULL)")
    if variant.startswith("exclusion"):
        await c.execute("ALTER TABLE bookings ADD CONSTRAINT no_overlap EXCLUDE USING gist (room_id WITH =, stay WITH &&)")
    else:  # the same index the constraint would create, so every variant pays for one
        await c.execute("CREATE INDEX bookings_room_stay ON bookings USING gist (room_id, stay)")
    await c.executemany("INSERT INTO rooms (id) VALUES ($1)", [(i,) for i in range(rooms)])
    await c.execute("VACUUM ANALYZE")
    ver = await c.fetchval("SHOW server_version")
    await c.close()
    return ver


async def book(variant, conn, room, a, b):
    """Returns ('ok'|'sold_out', retries). Raises on any other failure."""
    if variant == "naive":
        async with conn.transaction():
            if await conn.fetchval(OVERLAP, room, a, b): return "sold_out", 0
            await conn.execute(INSERT, room, a, b)
        return "ok", 0
    if variant == "pessimistic":
        async with conn.transaction():
            await conn.fetchval("SELECT 1 FROM rooms WHERE id = $1 FOR UPDATE", room)
            if await conn.fetchval(OVERLAP, room, a, b): return "sold_out", 0
            await conn.execute(INSERT, room, a, b)
        return "ok", 0
    if variant == "exclusion":
        try:
            await conn.execute(INSERT, room, a, b)
        except asyncpg.ExclusionViolationError:
            return "sold_out", 0
        return "ok", 0
    if variant == "exclusion-retry":  # same, but a deadlock (Postgres aborts one of two waiting inserts) is retried like optimistic does
        for tries in range(MAX_TRIES):
            try:
                await conn.execute(INSERT, room, a, b)
                return "ok", tries
            except asyncpg.ExclusionViolationError:
                return "sold_out", tries
            except asyncpg.DeadlockDetectedError:
                await asyncio.sleep(random.random() * JITTER_S)
        raise RuntimeError("retries_exhausted")
    # optimistic: rooms.version; a lost race (0 rows updated) rolls back and retries
    for tries in range(MAX_TRIES):
        tr = conn.transaction(); await tr.start()
        try:
            v = await conn.fetchval("SELECT version FROM rooms WHERE id = $1", room)
            if await conn.fetchval(OVERLAP, room, a, b):
                await tr.rollback(); return "sold_out", tries
            await conn.execute(INSERT, room, a, b)
            res = await conn.execute("UPDATE rooms SET version = version + 1 WHERE id = $1 AND version = $2", room, v)
            if res == "UPDATE 1":
                await tr.commit(); return "ok", tries
            await tr.rollback()
        except BaseException:
            await tr.rollback(); raise
        await asyncio.sleep(random.random() * JITTER_S)
    raise RuntimeError("retries_exhausted")


def make_attempts(n, rooms, window, lo, hi, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        nights = rng.randint(lo, hi)
        start = rng.randint(0, window - nights)
        out.append((rng.randrange(rooms), BASE + dt.timedelta(days=start), BASE + dt.timedelta(days=start + nights)))
    return out


async def run(args):
    n, conc, pool_size, rooms, window, lo, hi = SCEN[args.scenario]
    if args.quick: n = max(conc * 2, n // 5)
    attempts = make_attempts(n, rooms, window, lo, hi, seed=1000 * args.rep + int(args.scenario[1:]))
    pgver = await reset(args.variant, rooms)
    DL = "SELECT deadlocks FROM pg_stat_database WHERE datname = 'bench'"   # Postgres's own count, not ours
    c0 = await asyncpg.connect(DSN); dl0 = await c0.fetchval(DL); await c0.close()
    pool = await asyncpg.create_pool(DSN, min_size=pool_size, max_size=pool_size)
    sem, lat, kinds, retries = asyncio.Semaphore(conc), [], {}, 0
    counts = {"ok": 0, "sold_out": 0, "error": 0}

    async def one(room, a, b):
        nonlocal retries
        async with sem:
            t0 = time.perf_counter()
            try:
                async with pool.acquire(timeout=ACQUIRE_TIMEOUT_S) as conn:
                    status, r = await book(args.variant, conn, room, a, b)
                retries += r
            except Exception as e:
                status = "error"; k = "acquire_timeout" if isinstance(e, asyncio.TimeoutError) else (str(e) if isinstance(e, RuntimeError) else type(e).__name__)
                kinds[k] = kinds.get(k, 0) + 1
            lat.append((time.perf_counter() - t0) * 1000)
            counts[status] += 1

    t0 = time.perf_counter()
    await asyncio.gather(*(one(*x) for x in attempts))
    elapsed = time.perf_counter() - t0
    await pool.close()

    await asyncio.sleep(1.5)                                                 # stats are flushed lazily
    c = await asyncpg.connect(DSN)
    pg_deadlocks = await c.fetchval(DL) - dl0
    rows = await c.fetchval("SELECT count(*) FROM bookings")
    dbl = await c.fetchval("SELECT count(DISTINCT b.id) FROM bookings a JOIN bookings b ON a.room_id = b.room_id AND a.id < b.id AND a.stay && b.stay")
    over = await c.fetchval("""SELECT count(*) FROM (SELECT room_id, d FROM bookings, generate_series(lower(stay), upper(stay) - 1, interval '1 day') d
                               GROUP BY 1, 2 HAVING count(*) > 1) x""")
    await c.close()
    lat.sort()
    res = {"variant": args.variant, "scenario": args.scenario, "rep": args.rep, "quick": args.quick, "attempts": n, "concurrency": conc,
           "pool": pool_size, "rooms": rooms, "window_nights": window, "stay_nights": [lo, hi],
           "elapsed_s": round(elapsed, 3), "throughput_per_s": round(n / elapsed, 1),
           "accepted": counts["ok"], "sold_out": counts["sold_out"], "errors": counts["error"], "error_kinds": kinds,
           "retries_total": retries, "pg_deadlocks": pg_deadlocks, "rows_in_table": rows, "double_bookings": dbl, "nights_oversold": over,
           "p50_ms": round(st.median(lat), 2), "p99_ms": round(lat[int(len(lat) * 0.99) - 1], 2),
           "postgres": pgver, "asyncpg": asyncpg.__version__, "python": sys.version.split()[0], "platform": platform.platform()}
    out = HERE / "results" / ("quick" if args.quick else "full"); out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.scenario}-{args.variant}-r{args.rep}.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("variant", "scenario", "rep", "attempts", "accepted", "sold_out", "errors", "double_bookings",
                                           "nights_oversold", "throughput_per_s", "p50_ms", "p99_ms", "retries_total", "pg_deadlocks")}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, choices=VARIANTS)
    ap.add_argument("--scenario", required=True, choices=sorted(SCEN))
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--quick", action="store_true")
    asyncio.run(run(ap.parse_args()))
