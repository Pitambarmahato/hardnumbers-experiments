# sd-rate-limiter

System Design pilot 4 (chapter 4, rate limiter): five Redis rate limiters, counting the most allowed requests in any 1 s span against a limit of 100.
Article: "Rate Limiter: Fixed Window vs Sliding Window vs Token Bucket" on hardnumbers.dev.

| Variant | What it does |
|---|---|
| `naive-fixed` | `GET` the window counter, `INCR` if under the limit, `EXPIRE` on first hit. Three round trips, not atomic |
| `fixed` | one Lua script: `INCR` the window counter, window id from Redis `TIME` |
| `sliding-log` | one Lua script over a sorted set of request times |
| `sliding-counter` | one Lua script, this and the previous window weighted by elapsed time |
| `token-bucket` | one Lua script, capacity 100, refill 100 per second |

Scenarios: `s1` boundary burst (100 requests 60 ms before a window edge, 100 more 10 ms after, 10 cycles), `s2` flood (100 workers, one key, 10 s), `s3` many keys (2,000 keys x 100 requests, window 3600 s, memory per key).
Truth is the decision time of each allowed request (Redis `TIME`; client clock for `naive-fixed`), not the limiter's counters. Memory is `MEMORY USAGE` summed over all keys.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install redis hiredis
./run_full.sh                      # 45 runs (3 repeats x 3 scenarios x 5 variants), about 20 min; skips finished runs
.venv/bin/python3 analyze.py       # writes results/tables.md
.venv/bin/python3 run.py --variant fixed --scenario s1 --rep 0 --quick   # one quick run -> results/quick/
```

Needs Docker (Redis 8.0 container, 2 CPUs, 1 GB, port 16379) and Python with redis-py. The driver runs on the host and talks to Redis directly (no HTTP layer).
`PREREGISTRATION.md` holds the hypotheses and amendments A1 and A2, written before the analysis. `results/full/` has the raw per-run JSON, `results/s3-first-attempt/` the first S3 set (memory method abandoned, see A2).

## Limits

One host shared by driver and Redis (the Python driver is probably the limit for the Lua variants); one Redis version; 3 repeats per cell; synthetic bursts and floods.
Not tested: leaky bucket, GCRA, Redis Cluster, replicas or failover, clock skew between hosts, Redis down.
