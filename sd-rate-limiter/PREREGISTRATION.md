# Keyword brief: rate limiter algorithms, tested (System Design pilot 4)

Date: 2026-11-21. Process: `docs/KEYWORD-RESEARCH.md`. Plan: `docs/plan-system-design-notes-tutorials.md`
(chapter 4, Rate Limiter). Coverage tracker: `docs/system-design-coverage.md`. Pillar: `system-design`.
Pilots so far: cache misses (performance), duplicate charges (correctness), double bookings (correctness plus cost of each fix).
This one is a **limit that does not hold**: how many requests get through that should not, per algorithm.

## Step 1: Topic + keyword variants

- **Broad:** rate limiter
- **Specific:** redis rate limiter / fixed window vs sliding window vs token bucket
- **Long tail:** does fixed window rate limiting allow double the limit / redis rate limiter race condition

## Step 2: Search volume signal

Two web searches (standard mode, 2026-11-21). Many tutorials and guides on the head term:
[Redis: build 5 rate limiters](https://redis.io/tutorials/howtos/ratelimiting/), [Redis patterns (antirez)](https://redis.antirez.com/fundamental/rate-limiting.html),
[DEV: 4 algorithms, 4 trade-offs](https://dev.to/gabrielanhaia/design-a-rate-limiter-4-algorithms-4-trade-offs-eoi),
[DEV: token bucket vs sliding window](https://dev.to/roni_das_b1b76c5ee6583027/designing-a-rate-limiter-token-bucket-vs-sliding-window-and-making-it-distributed-1lh5),
[Percona: strategies with Valkey/Redis](https://www.percona.com/blog/rate-limiting-strategies-with-valkey-redis/),
[arXiv 2602.11741 (rolling window design paper)](https://arxiv.org/html/2602.11741).
**HIGH volume** on the head term. These URLs come from search results; the pages were not opened.
No Reddit or HN thread was checked; interest is inferred from blog volume only.

## Step 3: Competition scan

- **Direct competitors (a controlled test counting requests that exceed the limit, per algorithm, under the same load): 0 found.**
  Both searches said so: "no head-to-head benchmark", "none ran a head-to-head benchmark".
- **Adjacent (many):** guides that agree on the same claims. We can check them:
  (a) fixed window lets up to 2x the limit through at a window edge; (b) the sliding-window log is exact, at a memory cost;
  (c) the sliding-window counter is an approximation; (d) token bucket allows bursts up to its capacity;
  (e) a read-check-write sequence races unless it runs atomically (Lua).
  Nobody quantified (a), (c) or (e) in what we found.

**Honest read:** head term saturated; winnable queries are the measured long tails ("fixed window 2x limit", "redis rate limiter race").
Risk is SEO, not feasibility.

## Step 4: Counter-intuitive angle

**Expected (what every guide says):** pick an algorithm, run it in Redis, and the limit holds. The only question is smooth vs bursty.

**Our angle:** measure the truth from outside. Record when each *allowed* request arrived and count the most any one
second ever held. Compare to the limit. The race (non-atomic) version and the boundary (fixed window) version both
leak, but by different amounts, and one "correct" algorithm may leak by design.

### Pre-registered design (written 2026-11-21, before any code or run)

Redis 8.0 (one instance, `--appendonly no`). Driver on the host, asyncio with redis-py, talks to Redis directly (no HTTP layer; say so).
Limit L = 100 requests per window W = 1 s per key (S3 uses W = 3600 s). Truth = timestamps of **allowed** requests (see amendment A1: decision time); the metric is the most allowed requests in any sliding 1 s span (`max_sliding`), and the most in any clock-aligned 1 s window (`max_aligned`).

| Variant | What it does |
|---|---|
| `naive-fixed` | `GET` the window counter; if under L, `INCR`, and `EXPIRE` on the first hit. Three round trips, no atomicity. Window id from the client clock. |
| `fixed` | One Lua script: window id from Redis `TIME`, `INCR`, `EXPIRE` on first hit, allow if count <= L. |
| `sliding-log` | One Lua script, sorted set of request times: drop entries older than W, allow if the set has fewer than L, then add this one. |
| `sliding-counter` | One Lua script: this and the previous window's counters; allow if `prev * (1 - elapsed_fraction) + current < L`. |
| `token-bucket` | One Lua script: capacity L, refill L/W per second from Redis `TIME`; allow if a token is available. |

Not tested: leaky bucket, GCRA, Redis Cluster (key slots), replicas or failover, clock skew between hosts, fail-open behaviour when Redis is down.

| Scenario | Setup | What we count |
|---|---|---|
| S1 boundary burst | one key; 10 cycles; each cycle sends a burst of 100 simultaneous requests 60 ms before a window boundary and another 100 10 ms after it, then idles 2 s | `max_sliding`, `max_aligned`, allowed in total |
| S2 flood | one key; 100 workers send as fast as they can for 10 s | `max_sliding`, `max_aligned` (overall, and after the first 2 s), allowed in total |
| S3 many keys | 2,000 keys x 100 requests each (all within the limit, W = 3600 s), concurrency 100 | requests/s, p50 and p99 latency, Redis memory used per key (`used_memory` delta after `FLUSHALL`) |

Per scenario: 3 repeats, 5 variants = 45 runs. Same seeded key order at a given repeat.

| # | Hypothesis (not yet measured) | Refuted by |
|---|---|---|
| H1 | S2: `naive-fixed` lets through more than the limit in at least one aligned window, `max_aligned` at least 1.1x L in every repeat | any repeat under 1.1x |
| H2 | S1: `fixed` shows `max_sliding` of at least 1.8x L in every repeat | any repeat under 1.5x |
| H3 | S1 and S2: `sliding-log` never exceeds L in any sliding 1 s span (`max_sliding` <= L in all repeats) | any value above L |
| H4 | S1: `sliding-counter` exceeds L by no more than 10% (`max_sliding` <= 1.1 x L) | above 1.1x |
| H5 | S2: `token-bucket` `max_sliding` is at least 1.5x L because a full bucket also refills (about 2L in the first second) | under 1.5x |
| H6 | S3: `fixed` has the highest requests/s and `sliding-log` the lowest of the five | any other order at the median |
| H7 | S3: `sliding-log` uses at least 10x the memory per key of `fixed` | under 10x |

**Quick gate:** one `--quick` S2 run of `naive-fixed` shows `max_aligned` above L. If not, stop and change the scenario before the full run.

**Where the designed version is expected to still fail (goes in the article):** the sliding counter is an estimate, so it
leaks a little; the token bucket exceeds a naive "L per window" reading by design; one Redis means a single point and one
core for every check; multi-instance clocks and Cluster slots are not tested.

### Amendment A1 (2026-11-21, written BEFORE the full run; the quick gate has already run)

Quick gate (`experiments/sd-rate-limiter/results/quick/`, 3 s floods, 3 burst cycles, 200 keys): `naive-fixed` S2 reached `max_aligned` 111 against a limit of 100, so the gate passed.
One change after seeing the quick runs, made before the full run:

- **Truth timestamp is the decision time, not the reply time.** With reply times, `sliding-log` in a flood showed `max_sliding` 141, which
  cannot be right for an exact log. Cause: allowed requests are admitted in a burst of about 100 within 7 ms, and a couple of
  milliseconds of reply jitter put some of the next burst inside the span. The Lua variants now return Redis `TIME` with the verdict, and
  `naive-fixed` stamps the moment its `GET` reply is read. `max_aligned` counts allowed requests per window id the limiter itself used.
  Rerun of the quick gate with decision time: `sliding-log` S2 `max_sliding` 100.
- Hypotheses, variants, scenarios and run counts are unchanged. 45 runs.
- The earlier line "Reply-time jitter is about a millisecond" no longer applies; the remaining method limit is that `naive-fixed` uses the
  client clock, which is the same host as Redis.

### Amendment A2 (2026-11-21, written AFTER the first S3 results and before they were analysed)

The first S3 set measured memory as the change in Redis `used_memory`. It came out **negative** for four of five variants (about -690 bytes per key), so the method was wrong
(connection buffers and the flush distorted the baseline). Memory is now the sum of `MEMORY USAGE` over every key divided by the 2,000 users, and all 15 S3 runs were repeated.
The first S3 set is kept in `results/s3-first-attempt/`. H6 and H7 are evaluated on the repeated set. S1 and S2 were not rerun.

### Outcome (recorded 2026-11-21, after the full run; `experiments/sd-rate-limiter/results/tables.md`)

45 runs, S3 repeated once (A2), no S1 or S2 run discarded. **H2, H3, H4, H5, H7 held. H1 and H6 were refuted** (5 and 2).

- **H1 refuted by the registered rule, narrowly.** `naive-fixed` S2 `max_aligned` was 160, 107 and 140 (median 140): over the limit in all three repeats, but one repeat was under the 1.1x bar (107).
  Its `max_sliding` reached 204-259. In S1 it did not overshoot (100 per window), because the bursts were exactly the limit.
- **H2 held.** `fixed` S1 `max_sliding` 200 in all 3 repeats (2.0x). In S2 it was 200 too, and 133-152 after the first 2 s.
- **H3 held.** `sliding-log` `max_sliding` 100 in every S1 and S2 repeat.
- **H4 held.** `sliding-counter` S1 `max_sliding` 102-103 (3% over). **Not covered by H4:** in S2 it reached 106-147 (one repeat 47% over).
- **H5 held.** `token-bucket` S2 `max_sliding` 199 in all 3 repeats (first second), 101-105 after the first 2 s. Its `max_aligned` was 128-163.
- **H6 refuted.** S3 requests/s: `token-bucket` 23,995 (highest), `fixed` 23,727, `sliding-counter` 23,700, `sliding-log` 23,385 (lowest), all within 3% of each other; `naive-fixed` 13,040 (three round trips). The Python driver is probably the limit for the four Lua variants ([Inferred]).
- **H7 held.** Bytes per key: `sliding-log` 1,584 vs `fixed` 56 (28x); `sliding-counter` 56, `token-bucket` 88, `naive-fixed` 56.

**Where the designed version still fails (goes in the article):** `sliding-counter` leaks in a flood (up to 147); `token-bucket` passes up to 2x in its first second by design;
`sliding-log` is exact but costs 28x the memory per key; one Redis, one clock; Cluster, replicas and Redis down not tested.

## Step 5: Title + slug + meta

- Working title: **Fixed Window vs Sliding Window vs Token Bucket, Tested** (decide after results; slug at or under 80 characters).
- Meta: written after the run; it must carry one measured number and the phrase "rate limiter".
- No M2 / Mac in title or meta. No hardware named.

## Step 6: Decision

**Green for the measured long tail, red for the head term.** 0 direct competitors on a measured version, falsifiable
hypotheses, cheap harness (one Redis container), and a result that guides state but do not quantify.
