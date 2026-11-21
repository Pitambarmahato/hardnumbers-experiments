# Results: 45 runs (median of 3 repeats; min-max in brackets when repeats differ). Limit = 100 per 1 s window.

## S1 boundary burst: 100 requests 60 ms before a window edge and 100 10 ms after it, 10 cycles

| Variant | max_sliding | max_aligned | allowed | denied | errors |
|---|---|---|---|---|---|
| naive-fixed | 200 | 100 | 2,000 | 0 | 0 |
| fixed | 200 | 100 | 2,000 (1,937-2,000) | 0 (0-63) | 0 |
| sliding-log | 100 | 100 | 1,000 | 1,000 | 0 |
| sliding-counter | 103 (102-103) | 100 | 1,020 (1,020-1,021) | 980 (979-980) | 0 |
| token-bucket | 108 (107-108) | 100 | 1,071 (1,070-1,072) | 929 (928-930) | 0 |

## S2 flood: 100 workers on one key for 10 s

| Variant | max_sliding | max_sliding_after2s | max_aligned | allowed | errors | throughput_per_s |
|---|---|---|---|---|---|---|
| naive-fixed | 223 (204-259) | 197 (138-259) | 140 (107-160) | 1,191 (1,131-1,235) | 0 | 27,357 (27,236.4-27,834.7) |
| fixed | 200 | 146 (133-152) | 100 | 1,100 | 0 | 24,118 (23,455.2-24,508.4) |
| sliding-log | 100 | 100 | 100 | 1,000 (1,000-1,001) | 0 | 23,713 (23,307.4-24,416.6) |
| sliding-counter | 114 (106-147) | 106 (103-106) | 100 | 1,014 (1,006-1,047) | 0 | 23,248 (23,147.5-23,931.0) |
| token-bucket | 199 | 103 (101-105) | 154 (128-163) | 1,099 | 0 | 23,282 (22,981.9-23,565.1) |

## S3 many keys: 2,000 keys x 100 requests, window 3600 s, concurrency 100

| Variant | Requests/s | p50 ms | p99 ms | Bytes per key | Allowed (of 200,000) | Errors |
|---|---|---|---|---|---|---|
| naive-fixed | 13,040 (11,488.0-14,050.0) | 7.25 | 15.4 | 56 | 200,000 | 0 |
| fixed | 23,727 (23,287.6-23,876.1) | 4.06 | 6.0 | 56 | 200,000 | 0 |
| sliding-log | 23,385 (23,280.8-23,911.1) | 4.08 | 6.5 | 1,584 | 200,000 | 0 |
| sliding-counter | 23,700 (23,660.7-24,258.7) | 4.06 | 6.2 | 56 | 200,000 | 0 |
| token-bucket | 23,995 (23,812.7-24,178.7) | 4.06 | 6.0 | 88 | 200,000 | 0 |

Environment: Redis 8.0.6, redis-py 8.1.0, Python 3.14.6, macOS-15.0-arm64-arm-64bit-Mach-O.
