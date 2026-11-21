# Keyword brief: hotel double booking, tested (System Design pilot 3)

Date: 2026-11-20. Process: `docs/KEYWORD-RESEARCH.md`. Plan: `docs/plan-system-design-notes-tutorials.md`
(chapter 22, Hotel Reservation). Coverage tracker: `docs/system-design-coverage.md`. Pillar: `system-design`.
Pilot 1 was a performance failure (cache misses), pilot 2 a correctness failure (money charged twice). This one is a
**correctness failure under contention** (a room sold twice) plus the **throughput cost of each fix**.

## Step 1: Topic + keyword variants

- **Broad:** prevent double booking
- **Specific:** postgres double booking / select for update vs optimistic locking
- **Long tail:** does select for update prevent double booking / postgres exclusion constraint vs select for update

## Step 2: Search volume signal

Two web searches (standard mode, 2026-11-20). Many practitioner write-ups on the head term:
[DEV: exclusion constraints for double bookings](https://dev.to/ripazocom/preventing-double-bookings-with-postgresql-exclusion-constraints-5efn),
[DEV: the bug behind double bookings](https://dev.to/vjrngn/the-bug-behind-double-bookings-3g20),
[DEV: hotel booking schema comparison](https://dev.to/sumedhbala/hotel-booking-schema-design-comparison-g3h),
[DEV: exclude constraints vs serializable](https://dev.to/franckpachot/postgresql-exclude-constraints-for-better-concurrency-than-serializable-pob),
[DEV: six OTAs case study](https://dev.to/adamo_software/building-a-real-time-hotel-booking-engine-how-we-solved-double-booking-across-6-otas-3g7o),
[Pessimistic vs optimistic locking in PostgreSQL](https://samowolabi.substack.com/p/optimistic-vs-pessimistic-locking).
**HIGH volume** on the head term. These URLs come from search results; the pages were not opened.
No Reddit or HN thread was checked; interest is inferred from blog volume only.

## Step 3: Competition scan

- **Direct competitors (a controlled test counting double bookings per approach under the same load): 0 found.** The
  search summaries said the same: "none provides a controlled benchmark comparing the two under the same load".
- **Adjacent (many):** design guides ("pessimistic is safer, optimistic suits low contention, use an exclusion
  constraint for ranges"), one vendor case study with unverified figures (collision rate 0.2-0.4%, pool exhaustion
  with `SELECT FOR UPDATE`), and one anecdote of a hot row at 127 ms vs 6 ms.
- **Claims we can check:** (a) check-then-insert double-books under concurrency; (b) `SELECT FOR UPDATE` on the room
  prevents it; (c) optimistic locking prevents it but gives up under contention; (d) an exclusion constraint
  prevents it with one statement; (e) the locking approaches run out of connections under load.

**Honest read:** the head term is saturated, so the winnable queries are the measured long tails ("select for update vs
exclusion constraint"). Risk is SEO, not feasibility.

## Step 4: Counter-intuitive angle

**Expected (what every guide says):** lock the row or add a constraint and double booking is solved. The only open
question is which is fastest.

**Our angle:** count the double bookings of the unprotected version first, then check whether each fix is *actually* free
of them, and what each costs in failed requests and tail latency when everyone wants the same room.

### Pre-registered design (written 2026-11-20, before any code or run)

Postgres 16.4 only. The driver issues transactions directly through asyncpg from the host (no HTTP layer); say so in the
article. Truth = an audit query run after each scenario that counts bookings overlapping another booking on the same
room, not the driver's own success counter. Every variant writes to the same `bookings(room_id, stay daterange)` table.

| Variant | What it does |
|---|---|
| `naive` | READ COMMITTED. `SELECT` overlapping bookings for the room; if none, `INSERT`. No lock, no constraint. |
| `pessimistic` | `SELECT ... FROM rooms WHERE id = $1 FOR UPDATE`, then check overlap, then `INSERT`, one transaction. |
| `optimistic` | `rooms.version` column. Read version, check overlap, `INSERT`, `UPDATE rooms SET version = version + 1 WHERE id = $1 AND version = $read`; zero rows updated rolls back and retries (up to 5 tries, no backoff beyond 5 ms jitter). After 5 failures the request returns an error. |
| `exclusion` | `EXCLUDE USING gist (room_id WITH =, stay WITH &&)` (`btree_gist`). Plain `INSERT`; error 23P01 means the room is taken. No explicit check, no lock. |

Not tested: SERIALIZABLE isolation, per-night unique rows, advisory locks, holds with expiry, multi-room bookings.

| Scenario | Setup | What we count |
|---|---|---|
| S1 spread | 10,000 attempts, stays of 1-5 nights, 200 rooms, 60-night window, concurrency 50 (low contention) | double bookings; accepted; sold out; errors; throughput; p50/p99 |
| S2 hot | 2,000 attempts, stays of 1-3 nights, 10 rooms, 5-night window, concurrency 100 (everyone wants the same rooms) | same |
| S3 pool pressure | S2's workload with concurrency 400 and a client pool of 20 connections, acquire timeout 5 s | same, plus timeouts |

Per scenario: 3 repeats, 4 variants = 36 runs (45 after amendment A1 adds a fifth variant). Same seeded attempt list for every variant at a given repeat.
Each attempt is one request: success, `sold_out` (a clean refusal), or `error` (gave up, timeout or other failure).

| # | Hypothesis (not yet measured) | Refuted by |
|---|---|---|
| H1 | `naive` double-books in S2: at least 10% of its accepted bookings overlap another | under 2% |
| H2 | `naive` double-books in S1 too, but under 1% of attempts | zero in all 3 repeats, or 1% or more |
| H3 | `pessimistic`, `optimistic` and `exclusion` have 0 double bookings in every scenario | any overlap |
| H4 | `optimistic` returns `error` (5 retries exhausted) for at least 1% of attempts in S2 | under 1% |
| H5 | S1: the three safe variants' throughput is within 25% of each other | a spread of 25% or more |
| H6 | S2: `exclusion` throughput is at least 20% higher than `pessimistic` | under 20% |
| H7 | S3: `pessimistic` p99 is at least 2x `exclusion` p99 | under 2x |

**Quick gate:** one `--quick` S2 run of `naive` shows at least one double booking. If not, stop and change the scenario
before the full run.

### Amendment A1 (2026-11-20, written BEFORE the full run; the quick gate has already run)

Quick gate (`experiments/sd-hotel-double-booking/results/quick/`, 400-2,000 attempts per run): `naive` S2 produced 80 double
bookings (47 room-nights sold twice), so the gate passed. Every variant and scenario ran once. The quick runs showed
something no hypothesis covered: `exclusion` returned `DeadlockDetectedError` (11 of 400 attempts in S2, 3 of 2,000 in S1)
and stalled for about 1 s per deadlock, so its throughput and p99 were far worse than predicted. Changes made after
seeing the quick results, all before the full run:

- **New variant `exclusion-retry`:** the same constraint and `INSERT`, plus up to 5 retries on a deadlock (5 ms jitter),
  the way `optimistic` retries. `exclusion` stays exactly as registered, with no retry, so both are reported. Without it
  the comparison would punish one design for a failure the others are allowed to retry.
- **New metric `pg_deadlocks`:** the change in Postgres's own `pg_stat_database.deadlocks` counter over the run.
- **New hypothesis H8 (formed after the quick runs, so it is a replication, not a blind prediction):** `exclusion`
  returns at least one deadlock error in S2 in all 3 repeats. Refuted by any repeat with zero.
- **H6 is evaluated as registered, for `exclusion`.** We also report it for `exclusion-retry`, labelled as added.
- Everything else is as registered: 3 scenarios x 5 variants x 3 repeats = **45 runs**, same seeded attempt list for
  every variant at a given repeat. `deadlock_timeout` stays at the Postgres default of 1 s; tuning it is not tested.

### Outcome (recorded 2026-11-20, after the full run; `experiments/sd-hotel-double-booking/results/tables.md`)

45 runs, no rerun, no discarded run. **H1, H2, H3, H8 held. H4, H5, H6, H7 were refuted** (4 and 4).

- **H1 held.** `naive` S2: 81 of its 102 accepted bookings overlapped another (73-83 across repeats). **H2 held:** S1 gave 21-27 double
  bookings in 10,000 attempts (0.21-0.27%), with 50 clients and 200 rooms, not a hot spot. S3: 13 double bookings.
- **H3 held.** `pessimistic`, `optimistic`, `exclusion` and `exclusion-retry` had 0 double bookings and 0 oversold room-nights in all 45 runs.
- **H4 refuted.** `optimistic` returned 0 errors in S2 (124 retries over 2,000 attempts, none exhausted its 5 tries).
- **H5 refuted.** S1 attempts/s: `pessimistic` 4,363, `optimistic` 3,836, `exclusion` 7,737 (a spread of 2x, not 25%).
- **H6 refuted, in the opposite direction.** S2 `exclusion` ran at 22 attempts/s against 3,478 for `pessimistic`. Cause: **225 deadlocks** (178-231)
  per run, each costing about 1 s (`deadlock_timeout`). **H8 held** (deadlock errors in 3 of 3 S2 repeats).
- **H7 refuted on medians:** S3 `pessimistic` p99 224 ms vs `exclusion` 132 ms (1.7x). One `exclusion` repeat had 20 deadlocks and 425 pool timeouts (p99 9 s).
- **Not in any hypothesis, found in the repeats:** the exclusion variants are bimodal. With no deadlock a run takes about 0.2 s (8,000-9,000
  attempts/s, the fastest of all designs); with deadlocks it takes 60-268 s. `exclusion-retry` S2: 0 deadlocks in one repeat (0.24 s), 953 in
  another (268 s, p99 158 s). Three repeats cannot give a deadlock probability. Retrying did not remove the problem: it exhausted its
  5 tries for 171 attempts in one S2 repeat and timed out 1,257 pool requests in one S3 repeat.

**Where the designed version is expected to still fail (goes in the article):** a hold that spans a slow step
(a payment call inside the transaction keeps the lock or the version window open; not tested, stated as a limit);
optimistic retries exhausted under a hot room; one database only, no replicas; a constraint that depends on the
table design (a booking model without a range column cannot use it).

## Step 5: Title + slug + meta

- Working title: **Select For Update vs Exclusion Constraint: Double Bookings Tested** (decide after results; slug must
  stay at or under 80 characters).
- Meta: written after the run; it must carry one measured number and the phrase "double booking".
- No M2 / Mac in title or meta. No hardware named.

## Step 6: Decision

**Green for the measured long tail, red for the head term.** 0 direct competitors on a measured version, falsifiable
hypotheses, a cheap harness (Postgres only), and a correctness result that guides do not give.

## Not in this pilot

SERIALIZABLE, advisory locks, per-night unique rows, hold-and-expire flows, payments, overbooking policies, multi-region.
