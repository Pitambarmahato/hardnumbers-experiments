### S0: keys moved (100,000 keys; ring rows = median over 50 layouts, min-max in brackets)

| Scheme | Add a node (3 to 4) | Remove a node (3 to 2) |
|---|---|---|
| mod-N | 75.2% | 66.5% |
| ring, V=1 | 21.0% (0.7%-82.6%) | 26.4% (0.6%-89.7%) |
| ring, V=10 | 26.2% (11.4%-49.5%) | 33.9% (15.2%-49.8%) |
| ring, V=50 | 24.7% (17.2%-31.8%) | 32.1% (25.3%-41.0%) |
| ring, V=150 | 25.1% (21.5%-28.9%) | 33.4% (26.2%-39.8%) |
| ring, V=500 | 25.1% (22.4%-27.4%) | 33.5% (30.9%-36.0%) |
| theory (uniform hash) | mod-N 75.0%, ideal ring 25.0% | mod-N 66.7%, ideal ring 33.3% |

### S0: load balance with 4 nodes (CV = std/mean of keys per node; peak/avg = busiest node / mean)

| Scheme | CV % (median, min-max) | Peak/avg (median, max) |
|---|---|---|
| mod-N | 0.28 | 1.002 |
| ring, V=1 | 70.3 (16.9-139.9) | 1.88 (max 3.41) |
| ring, V=10 | 23.9 (7.4-57.2) | 1.33 (max 1.98) |
| ring, V=50 | 10.3 (4.2-23.7) | 1.13 (max 1.32) |
| ring, V=150 | 7.0 (1.4-12.7) | 1.10 (max 1.18) |
| ring, V=500 | 3.7 (0.5-6.9) | 1.04 (max 1.10) |

mod-N with 3 nodes: CV 0.63%, peak/avg 1.008

### Hypotheses (pre-registered in docs/kw-sd-consistent-hashing.md)

- H1 mod-N add ~75% (70-80%): 75.2% -> HELD
- H2 ring V=150 add ~25% (20-30%): median 25.1% -> HELD
- H3 ring V=1 balances worse than mod-N: CV 70.3% vs 0.28% -> HELD;  V=150 'close to mod-N': CV 7.0% vs 0.28% (ratio 25x)
- H6 mod-N remove ~67% (62-72%): 66.5% -> HELD;  ring V=150 ~33% (28-38%): median 33.4% -> HELD
