# Results: 45 runs (median of 3 repeats; counts show min-max in brackets when the repeats differ)

## S1 spread: 10,000 attempts, 200 rooms, concurrency 50

| Variant | Double bookings | Room-nights oversold | Accepted | Errors | Deadlocks (Postgres) | Retries | Attempts/s | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| naive | 23 (21-27) | 43 (42-48) | 3,252 (3,250-3,264) | 0 | 0 | 0 | 5,846 | 6.7 | 42 |
| pessimistic | 0 | 0 | 3,243 (3,233-3,249) | 0 | 0 | 0 | 4,363 | 9.1 | 43 |
| optimistic | 0 | 0 | 3,241 (3,231-3,248) | 0 | 0 | 324 (323-343) | 3,836 | 8.7 | 58 |
| exclusion | 0 | 0 | 3,242 (3,232-3,247) | 0 | 0 | 0 | 7,737 | 4.0 | 56 |
| exclusion-retry | 0 | 0 | 3,242 (3,232-3,248) | 0 | 0 | 0 | 7,395 | 4.1 | 57 |

## S2 hot: 2,000 attempts, 10 rooms, 5 nights, concurrency 100

| Variant | Double bookings | Room-nights oversold | Accepted | Errors | Deadlocks (Postgres) | Retries | Attempts/s | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| naive | 81 (73-83) | 44 (42-47) | 102 (89-104) | 0 | 0 | 0 | 7,264 | 11.0 | 51 |
| pessimistic | 0 | 0 | 32 (30-37) | 0 | 0 | 0 | 3,478 | 21.3 | 85 |
| optimistic | 0 | 0 | 32 (29-38) | 0 | 0 | 124 (122-136) | 4,042 | 14.4 | 115 |
| exclusion | 0 | 0 | 32 (30-42) | 225 (178-231) | 225 (178-231) | 0 | 22 | 1.9 | 52,138 |
| exclusion-retry | 0 | 0 | 32 (30-37) | 32 (0-171) | 213 (0-953) | 53 (0-98) | 33 | 5.0 | 46,222 |

## S3 pool pressure: S2 workload, concurrency 400, pool of 20

| Variant | Double bookings | Room-nights oversold | Accepted | Errors | Deadlocks (Postgres) | Retries | Attempts/s | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| naive | 13 (12-14) | 16 (15-18) | 41 (40-42) | 0 | 0 | 0 | 6,384 | 60.3 | 178 |
| pessimistic | 0 | 0 | 33 (31-33) | 0 | 0 | 0 | 3,514 | 106.7 | 224 |
| optimistic | 0 | 0 | 32 (31-32) | 0 | 0 | 22 (19-23) | 5,436 | 68.5 | 202 |
| exclusion | 0 | 0 | 32 (29-37) | 0 (0-445) | 0 (0-20) | 0 | 8,918 | 41.1 | 132 |
| exclusion-retry | 0 | 0 | 32 (31-33) | 0 (0-1,272) | 19 (0-89) | 14 (0-19) | 163 | 40.6 | 201 |

## Error kinds (summed over repeats)

| Scenario | Variant | Kinds |
|---|---|---|
| s2 | exclusion | DeadlockDetectedError: 634 |
| s2 | exclusion-retry | retries_exhausted: 203 |
| s3 | exclusion | DeadlockDetectedError: 20, acquire_timeout: 425 |
| s3 | exclusion-retry | acquire_timeout: 1257, retries_exhausted: 15 |

Environment: Postgres 16.4 (Debian 16.4-1.pgdg120+2), asyncpg 0.32.0, Python 3.14.6, macOS-15.0-arm64-arm-64bit-Mach-O. deadlock_timeout = Postgres default (1 s).
