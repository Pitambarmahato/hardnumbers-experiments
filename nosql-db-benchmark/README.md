# nosql-db-benchmark

Redis vs Valkey vs MongoDB vs Postgres JSONB, measured behind the same
Node (Fastify) app. Only the store changes between runs. The Postgres
JSONB run is the baseline for "do you need a separate document database
at all?"

The full writeup is at
https://hardnumbers.dev/articles/redis-vs-valkey-vs-mongodb-vs-postgres-jsonb-benchmark

## What this tests

One Fastify app, four stores, five operations:

- `read` — fetch one document by id
- `write` — replace one whole document by id (upsert)
- `mixed` — 80% read / 20% write
- `incr` — add 1 to one field of a document
- `query` — fetch 10 documents with a given category, ordered by id

10,000 documents of ~1 KB each; the whole set fits in memory on every
store, so this measures the in-memory path only.

## Stores and how each implements the tasks

| Store | Storage | `incr` | `query` |
| --- | --- | --- | --- |
| Postgres 16.4 | `jsonb` column, PK on id | `jsonb_set` in one `UPDATE` | expression index on `(doc->>'category')::int, id` |
| MongoDB 8.0 | collection, `_id` = id | `$inc` | compound index on `category, _id` |
| Redis 8.0 / Valkey 8.0 | one JSON string per key, no module | Lua `GET`/decode/+1/encode/`SET` | sorted set per category, then `MGET` |

The Redis/Valkey secondary index is maintained by the app. See
`app/adapters.js` for the exact code per store.

## Fairness notes

- Each store: 2 CPUs / 2 GB. App: 2 CPUs / 1 GB. Load generator (oha):
  2 CPUs. One store + its app up at a time. Drivers: pg 8.13.1,
  mongodb 6.12.0, ioredis 5.4.2, all pool of 10 (ioredis one
  auto-pipelined connection).
- Durability differs by default: Redis/Valkey run `--appendonly yes
  --appendfsync everysec` (flush ~1×/s); Postgres flushes on every
  commit. The `postgres-nosync` service (`synchronous_commit=off`)
  reruns the write/incr tasks with a comparable once-a-second
  guarantee. Results in `results/postgres_nosync.json`.

## How to run

Requires Docker.

```bash
python3 run.py --quick                 # smoke test, ~10 min
python3 run.py                         # full matrix, ~70 min -> results/results.json
python3 run.py --only postgres-nosync --tasks write,incr \
  --concurrency 50 --out postgres_nosync.json   # durability-fair rerun
python3 analyze.py > results/tables.md
```

Image digests for every store and for oha are recorded in the `meta`
block of each results file.

## Method

Concurrency 10 / 50 / 200. Each cell: 10 s warmup (discarded), then 3
measured runs of 20 s. Reported: median requests/s across the 3 runs
(min-max in `results/tables.md`), plus p50/p95/p99 latency, error rate,
and store container memory. 4 stores × 5 tasks × 3 concurrency × 3 runs
= 180 runs. All 180 finished with zero failed requests.
