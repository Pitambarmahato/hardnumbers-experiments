# sd-payment-idempotency

System Design pilot 2: payment idempotency, tested. Plan: `docs/plan-system-design-notes-tutorials.md` (site repo).
Pre-registered scenarios and hypotheses: `PREREGISTRATION.md` (copy of `docs/kw-sd-payment-idempotency.md` in the site repo; amendment A1 was written before the full run).

Three variants of a charge service call a **mock** payment provider (no real provider is ever contacted):

| Variant | Behaviour |
|---|---|
| `naive` | Check-then-act by order id, no unique constraint, no key sent to the provider |
| `idem-local` | Idempotency key + request hash + unique key + 3 s lease, key NOT sent to the provider |
| `idem-e2e` | As `idem-local`, and the key is sent to the provider, which dedupes on it |

Truth is the provider's own ledger (`provider_charges`), not the service's tables. The provider commits a charge before its artificial delay,
so a client that times out has still been charged.

## Run

Docker and a venv with `aiohttp==3.14.5` (Python 3.14 on the host, python:3.13-slim in the containers, asyncpg 0.30.0, postgres:16.4).

```bash
python3 -m venv .venv && .venv/bin/pip install aiohttp==3.14.5
docker compose build
.venv/bin/python3 run.py --variant naive --scenario s2 --rep 0 --quick   # one run, 10% size
./run_full.sh                                                            # 45 runs, about 45 min, resumable -> results/full/*.json
.venv/bin/python3 analyze.py                                             # -> results/tables.md
```

Scenarios: S1 happy path; S2 provider slower than the client timeout; S3 `docker kill` of the service mid-load; S4 each order sent twice at once;
S5 same key with a different amount. Client retries timeouts, connection errors, 5xx and 409 (10 tries, 0.4 s backoff) with the same key and body.

## Status

| Part | Status |
|---|---|
| Quick gate (naive S2 shows duplicates) | passed 2026-11-17 (199 of 200 orders charged twice) |
| Full run (45 runs: 3 variants x 5 scenarios x 3 repeats) | done 2026-11-17, 0 reruns, no run discarded. Tables: `results/tables.md` |

## Results (median, min-max over 3 repeats; full tables `results/tables.md`)

Orders charged twice or more, counted from the provider's own ledger:

| Scenario | naive | idem-local (key not sent to provider) | idem-e2e (key sent to provider) |
|---|---|---|---|
| S2 slow provider, 2,000 orders | 1,988 (1,934-1,988) | 0 | 0 |
| S3 service killed mid-load, 1,000 orders | 100 (100-100) | 100 (98-100) | 0 |
| S4 double click, 2,000 orders | 2,000 (1,999-2,000) | 0 | 0 |
| S5 same key, different amount, 500 orders: second request rejected | 0 (all 500 accepted) | 500 | 500 |
| S1 happy path, 10,000 orders: duplicates | 0 | 0 | 0 |

Cost of the design: S1 median latency 56.0 ms (naive) vs 54.7 and 54.6 ms; throughput ranges overlap (naive 744/s, designed 840 and 835/s).
S3 p99 latency: 2,508 ms (naive), 4,349 ms (idem-local), 4,641 ms (idem-e2e): a retry has to wait out the 3 s lease before it can take a dead request over.
No client gave up and no order went uncharged in any run (10 tries cover the restart).

Against the pre-registered hypotheses: **H1-H8 all held** (H1 99.4% duplicates in S2; H2 100 in S3; H3 100% in S4; H4 0; H5 100 in S3 for idem-local;
H6 0; H7 500 of 500; H8 -2.4% median latency). The surprise is H5: the version with a unique-constrained key, request hash and lease
duplicated exactly as many charges in a crash as the naive version: every order that was in flight (100 at concurrency 100).

## Limits

The provider is our own mock (a row per charge, optional dedupe on `Idempotency-Key`); real providers differ. One Postgres, one service
instance, one kill timing (2 s into the load), simultaneous double sends (the worst case for a race), 10 client retries, keys that never expire,
no webhooks and no outbox. Throughput differences are within run-to-run spread.
