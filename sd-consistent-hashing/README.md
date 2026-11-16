# sd-consistent-hashing

System Design pilot 1: consistent hashing, tested. Plan: `docs/plan-system-design-notes-tutorials.md`.
Pre-registered scenarios and hypotheses: `PREREGISTRATION.md` (copy of `docs/kw-sd-consistent-hashing.md` in the site repo).

## Status

| Part | Status |
|---|---|
| **S0 offline** (`run_s0.py`): keys moved and load balance, no servers | done 2026-11-15, gate passed |
| **S1-S4 online** (`online.py`, `run_online.sh`, `analyze_online.py`; 3-4 Redis nodes + Postgres) | done 2026-11-15: 48 runs (4 schemes x 4 scenarios x 3 repeats), 0 failed, 0 wrong values |

## Run S0

Standard library only (Python 3.13 used). Takes about 11 seconds.

```bash
python3 run_s0.py                    # 100,000 keys, 50 ring layouts per config -> results/s0.json
```

Deterministic: keys are `key:0`..`key:99999`, hash is 64-bit BLAKE2b, ring layouts use salts `t0`..`t49`.
The script also asserts that on a ring every key that moves on an add moves to the new node, and that
a removal only moves the removed node's keys.

## S0 results (full tables: `results/s0_tables.md`)

Keys moved, 100,000 keys; ring rows are the median over 50 layouts:

| Scheme | Add a node (3 to 4) | Remove a node (3 to 2) | Load CV at 4 nodes | Peak/avg at 4 nodes |
|---|---|---|---|---|
| mod-N | 75.2% | 66.5% | 0.28% | 1.002 |
| ring, V=1 | 21.0% (0.7-82.6%) | 26.4% | 70.3% | 1.88 |
| ring, V=10 | 26.2% | 33.9% | 23.9% | 1.33 |
| ring, V=150 | 25.1% (21.5-28.9%) | 33.4% | 7.0% | 1.10 |
| ring, V=500 | 25.1% | 33.5% | 3.7% | 1.04 |

Against the pre-registered hypotheses: H1, H2 and H6 held. H3 held on its first half (a ring with V=1 balances far
worse than mod-N) and was refuted on its second half: V=150 is not "close to mod-N" (CV 7.0% vs 0.28%, about 25x;
busiest node 10% above the mean at the median, 18% at the worst layout).

Two findings the explainers do not state:

- **The ring's "about 1/N" is an average.** With V=1 the share of keys that moved ranged from 0.7% to 82.6% across
  layouts; the worst layout moved more keys than mod-N. The spread narrows as V grows (V=150: 21.5-28.9%).
- **The ring gives up balance to buy stability.** mod-N balances almost perfectly because the hash is uniform; the
  ring needs V of about 150 to bring the busiest node within roughly 10-18% of the mean.

## Limits of S0

Offline only: it counts which node owns a key, not what a cache miss costs. One hash function, sequential key
names, 3-to-4 and 3-to-2 only, 50 layouts per config. It says nothing about hot keys or latency; those are S1-S4.

## Run the online part (S1-S4)

Needs Docker and a venv with `redis[hiredis]==6.4.0` and `asyncpg==0.30.0` (driver runs on the host; Python 3.14 used).

```bash
python3 -m venv .venv && .venv/bin/pip install "redis[hiredis]==6.4.0" asyncpg==0.30.0
docker compose up -d                 # r0-r3 (redis:8.0, 1 CPU each) + pg (postgres:16.4, 2 CPUs)
./run_online.sh                      # 48 runs, about 55 min, resumable -> results/online/*.json
.venv/bin/python3 analyze_online.py  # -> results/online_tables.md
```

Parameters were fixed in amendment A2 before the full run (`docs/kw-sd-consistent-hashing.md`): 3,000 req/s open loop, 100,000 keys of 1 KB, ring layout salt `t<repeat>`, 5 s failure-detection delay.

## Online results (median, min-max over 3 repeats; full tables: `results/online_tables.md`)

| Scheme | S2 lowest hit rate | S2 peak Postgres q/s | S2 extra Postgres queries (60 s) | S3 lowest hit rate | S3 extra queries (60 s) | S3 busiest survivor | S4 busiest node share |
|---|---|---|---|---|---|---|---|
| mod-N | 25.4% | 2,238 | 62,742 | 36.8% | 58,791 | 50.1% | 41.6% |
| ring V=1 | 87.8% (87.2-88.5) | 365 | 10,111 | 46.1% (43.1-68.0) | 50,869 (29,500-53,938) | 79.3% (63.1-92.5) | 55.5% (45.7-56.3) |
| ring V=10 | 73.9% (62.2-84.7) | 782 | 21,841 (13,006-32,714) | 64.0% | 33,378 | 53.4% | 38.4% (36.9-45.1) |
| ring V=150 | 73.9% (73.8-75.7) | 784 | 21,730 (20,536-22,352) | 65.0% | 32,843 | 52.9% | 43.2% (39.5-47.0) |

Uniform traffic (S1): every scheme 100% hit (warm cache); busiest node 33.7% (mod-N), 36.6% (V=150), 52.8% (V=1).

Against the pre-registered hypotheses:

- **H5 held.** Adding a node: mod-N fell to 25% hit rate and sent 62.7k extra queries to Postgres in 60 s; the ring (V=150) fell to 74% and sent 21.7k (2.9x fewer). Peak Postgres load 2,238 vs 784 q/s. After 60 s mod-N was still at 88% (never recovered); V=150 reached 95% after about 56 s. Peak p99 latency is NOT clearly different (mod-N 196-767 ms, V=150 106-431 ms: ranges overlap).
- **H4 held (not refuted).** Zipf traffic raised the busiest node from 33.7% to 41.6% under mod-N and to 43.2% under V=150. The ring did not reduce it. V=10 was lower (38.4%) but its range overlaps mod-N's. The hot key (13.5% of all requests, computed from the Zipf weights) lands on one node whatever the scheme. No latency cost was visible: that node served about 1,300 req/s, far below saturation.
- **Layout luck (new, online).** Ring V=1 had the smallest dip in S2 (87.8%) because those 3 layouts happened to give the new node a small share, and the worst S3 survivor imbalance (one survivor took 79%, up to 92.5%). A ring with few virtual nodes is a lottery.
- **S3 kill:** mod-N lowest hit 36.8% vs 65% for V=150; extra Postgres queries 58.8k vs 32.8k (1.8x fewer). Survivors split 50.1% (mod-N) vs 52.9% (V=150).

## Limits of the online part

Single host, Docker Desktop on a Mac: latency spikes of 100-200 ms appear in single 1-second buckets, so latency claims need the repeats. 3 repeats and 3 ring layouts per V, so ring V=1 and V=10 ranges are wide. The cache is fully warm at the start, so the baseline hit rate is trivially 100%. One request rate (3,000/s), one key count, Zipf s=1.1 only, no TTL, no eviction. Postgres is never the bottleneck at baseline and the driver is a single Python process (baseline p99 is about 7 ms). The ring moves keys but not data: the new node starts cold.
