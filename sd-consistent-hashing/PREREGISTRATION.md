# Keyword brief: consistent hashing, tested (System Design pilot 1)

Date: 2026-11-15. Process: `docs/KEYWORD-RESEARCH.md`. Plan: `docs/plan-system-design-notes-tutorials.md`
(Pilot 1, chapter 5). Pillar: `system-design`. Format: naive vs designed, see the plan.

## Step 1: Topic + keyword variants

- **Broad:** consistent hashing
- **Specific:** consistent hashing vs modulo hashing / consistent hashing virtual nodes
- **Long tail:** how many keys move when you add a node with consistent hashing / how many virtual nodes do you need

## Step 2: Search volume signal

Three web searches (standard mode, 2026-11-15). The head term is saturated with 2026
interview-prep pages: [AlgoMaster](https://algomaster.io/learn/system-design/consistent-hashing),
[Interview Cake](https://www.interviewcake.com/concept/consistent-hashing),
[Exponent](https://www.tryexponent.com/courses/system-design-interviews/consistent-hashing),
[DesignGurus](https://www.designgurus.io/blog/consistent-hashing-vs-traditional-hashing),
[techinterview.org](https://www.techinterview.org/post/3233474137/system-design-consistent-hashing-virtual-nodes-hash-ring-load-balancing-distributed-cache-dynamo-cassandra/),
and more. **HIGH volume** on the head term. These URLs come from search results; the pages were not opened.
No Reddit or HN threads surfaced, so community interest is inferred from blog volume only.

## Step 3: Competition scan

- **Direct competitors (same test, same method): 0 found.** The search turned up no controlled
  experiment that counts moved keys against virtual-node count. One summary said as much: "you'd need
  to run a simulation... I didn't find published results of that kind."
- **Adjacent (many):** explainers repeating the same claims: about 75% of keys move for mod-N from
  3 to 4 nodes, about 1/N for a ring, virtual nodes for evenness. These are the SEO competition for the head term.
- **Reference material:** Jump Hash (Lamping and Veach, 2014), multi-probe consistent hashing
  ([arXiv 1505.00062](https://arxiv.org/pdf/1505.00062.pdf)), bounded-load / rendezvous work
  ([arXiv 2512.23434](https://arxiv.org/pdf/2512.23434)). Cite, do not compete.
- **A claim we can check:** one widely copied table puts load standard deviation near 57% at 1 virtual
  node and about 4% at 150 for 3 servers, but the search summary said it sits on a tutorial site
  with no sourced benchmark. Our run produces our own figures for the same question.

**Honest read:** we cannot win the head term "consistent hashing" against interview-prep sites.
The winnable queries are the long tails ("how many keys move", "how many virtual nodes",
"consistent hashing vs modulo, measured"), where measured numbers are what is missing.

## Step 4: Counter-intuitive angle

**Expected (what every explainer says):** consistent hashing fixes rehashing; add a node and only
about 1/N of keys move; virtual nodes make it even.

**Our angle:** consistent hashing buys *stability* and gives up *balance*. With few virtual nodes
the ring balances load worse than plain mod-N, and no setting fixes a hot key.

### Pre-registered scenarios and hypotheses (written 2026-11-15, before any run)

App: a key-lookup service. 3 Redis cache nodes in front of Postgres; 4th node added in S2.
100,000 keys, ~1 KB values, cache warmed before measuring. Naive = `hash(key) mod N`.
Designed = hash ring with V virtual nodes per node, V in {1, 10, 150}.

| Scenario | What we measure |
|---|---|
| S0 offline | Hash all 100,000 keys: share that change owner going 3 to 4 nodes; share of keys per node; load std dev, for mod-N and V in {1, 10, 150}. No servers needed. |
| S1 steady, uniform keys | cache hit rate, p50/p99, Postgres queries/s |
| S2 add the 4th node mid-run | hit-rate dip (depth, recovery time), peak Postgres queries/s, p99 |
| S3 `docker kill` one of 3 nodes mid-run | same as S2, plus load on the survivors |
| S4 skewed (Zipf) traffic with one hot key | share of requests on the busiest node |

| # | Hypothesis (not yet measured) | Would be refuted by |
|---|---|---|
| H1 | mod-N moves about 75% of keys going 3 to 4 nodes (theory: exactly 3/4 for a uniform hash) | measured outside 70-80% |
| H2 | A ring with V=150 moves about 25% (theory: 1/4) | measured outside 20-30% |
| H3 | A ring with V=1 balances load worse than mod-N. V=150 is close to mod-N | V=1 load std dev not clearly above mod-N |
| H4 | The hot key leaves the busiest node's share unchanged by the ring | busiest-node share drops with the ring |
| H5 | In S2, mod-N causes a larger hit-rate dip and a larger Postgres spike than the ring | no clear difference |

### Amendment A1 (2026-11-15, written BEFORE the first S0 run)

S0 is extended in three ways. Nothing has been run yet.

- **Virtual-node sweep:** V in {1, 10, 50, 150, 500} (adds 50 and 500 to draw the balance curve).
- **Removal case:** also hash 3 to 2 nodes (one node removed). New hypothesis:
  **H6** mod-N moves about 67% of keys going from 3 to 2 nodes (theory: 2/3); a ring with V=150 moves
  about 33% (the removed node's share). Refuted if mod-N is outside 62-72% or the ring outside 28-38%.
- **Many ring layouts, not one.** A ring's balance depends on where its points land, so a single run
  can look lucky or unlucky. S0 repeats each ring configuration over 50 different node-name salts
  (`t0`..`t49`) and reports min / median / max. mod-N has no layout, so it is one value.
- **Metrics:** keys moved (share of 100,000), and per-node load as coefficient of variation
  (std / mean of keys per node, in %) and peak-to-average (max / mean). Keys are `key:0`..`key:99999`;
  hash is 64-bit BLAKE2b; fully deterministic, so the run is exactly reproducible.
- **Self-check:** on a ring, every key that moves when a node is added must move *to the new node*.

**Quick gate** (before any full run): S0 shows mod-N moving more than 50% and V=150 fewer than 35%
(a check on the hashing code, cheap and offline), and an online `--quick` S2 run shows a visible
hit-rate dip for mod-N. If either fails, stop and rethink before the full run.

### S0 outcome (recorded 2026-11-15, after the run; results in `experiments/sd-consistent-hashing/`)

Gate passed (mod-N 75.2%, ring V=150 25.1%). H1, H2, H6 held. H3: first half held (V=1 CV 70.3% vs mod-N 0.28%);
second half **refuted** (V=150 CV 7.0%, about 25x mod-N, not "close"). New finding: with V=1 the share of keys
moved ranged 0.7%-82.6% across layouts, so the ring's "about 1/N" is an average and a bad layout can move more
keys than mod-N. H4 and H5 are online (S2/S4) and untested.

### Amendment A2 (2026-11-15, written BEFORE the full online run; quick gate already passed)

Quick gate (single runs, `results/online-quick/`): S2 mod-N hit rate fell 100% -> 27% in the first seconds after the 4th node joined;
ring V=150 fell to 74%. Kill and hot-key paths run end to end, 0 wrong values. Parameters fixed for the full run:

- **Load:** open loop, 3,000 requests/s, 100,000 keys, 1 KB values, latency measured from the scheduled start (queueing counts). Driver on the host, nodes in Docker (1 CPU each; Postgres 2 CPUs, 256 MB shared_buffers); same for every scheme.
- **Schemes:** mod-N, ring V=1, V=10, V=150. Repeats 0-2; ring layout salt `t<rep>`; the request stream is identical across schemes for a given repeat.
- **S1** 30 s uniform steady. **S2** 70 s: nodes 0-2 warm, node 3 (empty) joins routing at t=10 s. **S3** 70 s: `docker kill` node 2 at t=10 s; requests to it fail and fall through to Postgres; the client drops node 2 from routing at t=15 s (5 s detection delay, set before seeing results). **S4** 30 s Zipf (s=1.1) over the same 100,000 keys, hot keys scattered by a seeded shuffle.
- **Cache:** cache-aside, no TTL, no eviction, no persistence. Warm-up writes each key to its owner under the 3-node layout directly, not through traffic. Old copies on previous owners stay (as in production).
- **Metrics:** baseline = mean of t=2..9 s. Dip = lowest 1-second hit rate after the change. Peak Postgres queries/s (client count). Peak 1-second p99. **Extra Postgres queries over the 60 s after the change** (total cost). Recovery time is reported only if hit rate returns to within 5 points of baseline inside the window; with uniform traffic over 100,000 keys at 3,000 req/s a key is requested about once per 33 s, so most runs are expected NOT to recover inside 60 s, and that is reported as is.
- **S4 / H4:** busiest node's share of requests, compared with the uniform S1 share and with the other schemes. H4 is refuted only if the ring's busiest share is clearly below mod-N's.
- **Known noise:** Docker Desktop on a Mac adds latency spikes (single 1-second buckets with p99 100-200 ms appear in the quick ring run). Medians across 3 repeats; an effect that is not larger than the run-to-run spread is reported as no difference.

### Online outcome (recorded 2026-11-15, after the full run; `experiments/sd-consistent-hashing/results/online_tables.md`)

48 runs, 0 failed, 0 wrong values. **H5 held:** S2 lowest hit rate mod-N 25% vs ring V=150 74%; extra Postgres queries in 60 s 62.7k vs 21.7k; peak p99 NOT clearly different (ranges overlap). **H4 held (not refuted):** busiest node share under Zipf 41.6% mod-N vs 43.2% V=150; the ring did not help. New: ring V=1 is a layout lottery (best S2 dip, worst S3 survivor imbalance 79%, range 63-93%). Hot key costs no latency at this rate.

**Where the designed version is expected to still fail (goes in the article):** the hot key (H4);
low V (H3); data is not moved by the ring itself, so a new node starts cold.

## Step 5: Title + slug + meta

- Title: **Consistent Hashing Tested: mod N vs Ring vs Virtual Nodes** (57 chars)
- Slug: `consistent-hashing-tested-mod-n-vs-ring-vs-virtual-nodes` (56 chars)
- Meta: written after the run; it must carry one measured number and the phrase "consistent hashing".
- No M2 / Mac in title or meta.

## Step 6: Decision

**Green for the long-tail measured angle, red for the head term.** 0 direct competitors on the
measured version, a clear and falsifiable hypothesis set, and a cheap offline first gate (S0).
The risk is SEO, not feasibility: expect little traffic from "consistent hashing" itself. The
article still serves the series (a spoke for the hub) and the numbers are reusable.

## Not in this pilot (candidates for a follow-up)

Jump hash, rendezvous hashing, multi-probe and bounded-load variants. Adding them turns the pilot
into a comparison of five algorithms; the plan's format is naive vs designed.
