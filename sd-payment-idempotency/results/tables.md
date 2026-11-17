# Results (median, min-max across 3 repeats)

## S1 happy path, 10,000 orders
| Variant | runs | orders/s | p50 ms | p99 ms | charged twice |
|---|---|---|---|---|---|
| naive | 3 | 743.9 (700.6-798.3) | 56.0 (55.9-57.3) | 307.2 (168.9-464.4) | 0 (0-0) |
| idem-local | 3 | 840.2 (696.1-856.6) | 54.7 (54.3-57.5) | 122.9 (96.7-401.8) | 0 (0-0) |
| idem-e2e | 3 | 834.5 (834.3-857.1) | 54.6 (54.3-54.8) | 143.7 (93.0-158.7) | 0 (0-0) |

## S2 slow provider (answers in 1.5 s, client times out at 1.0 s), 2,000 orders
| Variant | runs | orders charged twice+ | extra charges | client gave up | charged but client gave up | mean attempts | p50 ms |
|---|---|---|---|---|---|---|---|
| naive | 3 | 1,988 (1,934-1,988) | 1,988 (1,934-1,988) | 0 (0-0) | 0 (0-0) | 3.0 (3.0-3.0) | 2,906 (2,906-2,911) |
| idem-local | 3 | 0 (0-0) | 0 (0-0) | 0 (0-0) | 0 (0-0) | 3.0 (2.9-3.0) | 1,913 (1,908-1,913) |
| idem-e2e | 3 | 0 (0-0) | 0 (0-0) | 0 (0-0) | 0 (0-0) | 3.0 (3.0-3.0) | 1,911 (1,909-1,912) |

## S3 service killed mid-load, 1,000 orders
| Variant | runs | orders charged twice+ | never charged | client gave up | charged but client gave up | p99 ms | kill during load |
|---|---|---|---|---|---|---|---|
| naive | 3 | 100 (100-100) | 0 (0-0) | 0 (0-0) | 0 (0-0) | 2,508 (2,416-2,721) | True (True-True) |
| idem-local | 3 | 100 (98-100) | 0 (0-0) | 0 (0-0) | 0 (0-0) | 4,349 (4,329-4,464) | True (True-True) |
| idem-e2e | 3 | 0 (0-0) | 0 (0-0) | 0 (0-0) | 0 (0-0) | 4,641 (4,417-4,756) | True (True-True) |

## S4 double click (each order sent twice at once), 2,000 orders
| Variant | runs | orders charged twice+ | extra charges | client gave up | mean attempts |
|---|---|---|---|---|---|
| naive | 3 | 2,000 (1,999-2,000) | 2,000 (1,999-2,000) | 0 (0-0) | 2.0 (2.0-2.0) |
| idem-local | 3 | 0 (0-0) | 0 (0-0) | 0 (0-0) | 3.0 (3.0-3.0) |
| idem-e2e | 3 | 0 (0-0) | 0 (0-0) | 0 (0-0) | 3.0 (3.0-3.0) |

## S5 same key, different amount, 500 orders
| Variant | runs | second request rejected | second accepted (200) | extra charges |
|---|---|---|---|---|
| naive | 3 | 0 (0-0) | 500 (500-500) | 0 (0-0) |
| idem-local | 3 | 500 (500-500) | 0 (0-0) | 0 (0-0) |
| idem-e2e | 3 | 500 (500-500) | 0 (0-0) | 0 (0-0) |
