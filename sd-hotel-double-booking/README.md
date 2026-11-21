# sd-hotel-double-booking

System Design pilot 3 (chapter 22, hotel reservation): five ways to book a room in Postgres, counting bookings that overlap another booking on the same room.
Article: "SELECT FOR UPDATE vs Exclusion Constraint: Double Bookings" on hardnumbers.dev.

| Variant | What it does |
|---|---|
| `naive` | READ COMMITTED, `SELECT` overlap then `INSERT`. No lock, no constraint |
| `pessimistic` | `SELECT ... FOR UPDATE` on the room row, then the same check and `INSERT` |
| `optimistic` | `rooms.version` compare-and-bump, up to 5 tries |
| `exclusion` | `EXCLUDE USING gist (room_id WITH =, stay WITH &&)`, plain `INSERT`, no retry |
| `exclusion-retry` | the same, retrying deadlocks up to 5 tries (added by amendment A1, before the full run) |

Scenarios: `s1` spread (10,000 attempts, 200 rooms, 50 clients), `s2` hot rooms (2,000 attempts, 10 rooms, 100 clients), `s3` pool pressure (S2 workload, 400 clients, pool of 20).
Truth is an audit query over the `bookings` table after each run. `pg_deadlocks` is the change in Postgres's own `pg_stat_database.deadlocks`.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install asyncpg==0.32.0
./run_full.sh                      # 45 runs (3 repeats x 3 scenarios x 5 variants), about 25 min; skips finished runs
.venv/bin/python3 analyze.py       # writes results/tables.md
.venv/bin/python3 run.py --variant naive --scenario s2 --rep 0 --quick   # one quick run -> results/quick/
```

Needs Docker (Postgres 16.4 container, 2 CPUs, 2 GB, port 15433) and a Python with asyncpg. The driver runs on the host and talks to Postgres directly (no HTTP layer).
`PREREGISTRATION.md` holds the hypotheses and amendment A1, both written before the full run. `results/full/` has the raw per-run JSON, `results/full.log` the run log.

## Limits

One host shared by driver and database; one Postgres version; default `deadlock_timeout` (1 s), `max_connections=200` and isolation level; 3 repeats per cell; synthetic uniform workload.
Not tested: SERIALIZABLE, advisory locks, per-night unique rows, holds that expire, payments inside the transaction, replicas.
