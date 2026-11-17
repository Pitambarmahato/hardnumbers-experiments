# Keyword brief: payment idempotency, tested (System Design pilot 2)

Date: 2026-11-17. Process: `docs/KEYWORD-RESEARCH.md`. Plan: `docs/plan-system-design-notes-tutorials.md`
(Pilot 2, chapter 26). Pillar: `system-design`. Format: naive vs designed, see the plan.
Pilot 1 (consistent hashing) was a performance failure; this one is a **correctness** failure (money charged twice).

## Step 1: Topic + keyword variants

- **Broad:** idempotency key
- **Specific:** idempotency key payment API / idempotency key vs unique constraint
- **Long tail:** how many duplicate charges does a retry cause / does an idempotency key prevent double charge under concurrency

## Step 2: Search volume signal

Three web searches (standard mode, 2026-11-17). The head term is saturated with practitioner write-ups (2026 dates
on many): [Zackius on Substack](https://zackius.substack.com/p/67a), [DEV: what most tutorials don't tell you](https://dev.to/highflyer910/idempotency-keys-what-most-tutorials-dont-tell-you-1ncc),
[Dodo Payments](https://dodopayments.com/blogs/idempotency-keys-payment-api/), [OneUptime: concurrent idempotency keys](https://oneuptime.com/blog/post/2026-09-13-concurrent-idempotency-key-wait-replay-conflict/markdown),
[DEV: exactly-once money movement](https://dev.to/dannstorm/exactly-once-money-movement-surviving-retries-and-duplicate-webhooks-3laa),
[Brandur's reference article](https://brandur.org/idempotency-keys), [QA Skills: testing concurrent requests](https://qaskills.sh/blog/testing-idempotency-key-concurrent-requests).
**HIGH volume** on the head term. These URLs come from search results; the pages were not opened.
No Reddit or HN threads surfaced; community interest is inferred from blog volume only.

## Step 3: Competition scan

- **Direct competitors (a controlled test that counts duplicate charges per scenario): 0 found.** All three searches
  said so in their own words: "no actual benchmark numbers", "none of the results measured latency, throughput, or failure
  rates", "no published benchmark or controlled experiment".
- **Adjacent (many):** design guides repeating the same advice: claim the key with an atomic insert behind a unique
  constraint before charging; store the key in the same transaction as the side effect; return 409 for an in-flight
  duplicate; hash the request and return 422 when a key is reused with a different body.
- **Claims we can check:** (a) check-then-insert always races; (b) a unique constraint on the key stops concurrent
  duplicates; (c) the constraint does not undo a charge that happened before the losing insert; (d) the key protects the
  inbound request but not the outgoing provider call; (e) the in-flight window needs explicit handling.
  Source summaries said (c) and (d) are known limits; nobody counted what they cost.

**Honest read:** we cannot win "idempotency key" against practitioner blogs and the reference articles. The winnable
queries are measured long tails ("idempotency key vs unique constraint", "does an idempotency key prevent double
charges"). Risk is SEO, not feasibility.

## Step 4: Counter-intuitive angle

**Expected (what every guide says):** add an idempotency key and a unique constraint and retries are safe.

**Our angle:** the constraint makes *your own database* exactly-once, not the charge. Whether a retry charges twice
depends on one more thing: whether the key reaches the provider. Test three versions and count duplicates.

### Pre-registered design (written 2026-11-17, before any code or run)

Mock payment provider only; never a real one. Truth = the provider's own ledger (rows it recorded), not the service's tables.

| Variant | What it does |
|---|---|
| `naive` | Check-then-act by order id: SELECT a succeeded charge for the order (return it if found), else INSERT a pending row (no unique constraint), call the provider with no key, UPDATE to succeeded. What a competent developer writes first. |
| `idem-local` | Idempotency key + request hash in a table with a unique key. Claim with `INSERT ... ON CONFLICT DO NOTHING`; `in_progress` rows carry a 3 s lease; duplicate while leased gets 409; stored result replayed; key reused with a different hash gets 422; an expired lease can be taken over. The provider call carries **no** key. |
| `idem-e2e` | Same as `idem-local`, and the key is also sent to the provider, which dedupes on it (Stripe-style semantics, implemented in our mock). |

Stack: Postgres 16.4 (service DB and provider ledger as separate databases), mock provider and service as small Python
(aiohttp, asyncpg) containers; load driver on the host. Orders are distinct; the client sends the same key and body on
every retry, retries on timeout, connection error, 5xx and 409 (up to 10 tries, 0.4 s backoff).

| Scenario | Setup | What we count |
|---|---|---|
| S1 happy path | 2,000 orders, 50 concurrent, provider 50 ms, client timeout 2 s | throughput, p50 and p99 latency, duplicates (expected 0) |
| S2 slow provider | 2,000 orders, 100 concurrent; provider records the charge at once, answers after 1.5 s; client timeout 1.0 s | orders charged twice or more; extra charges; orders the client gave up on |
| S3 crash | 1,000 orders, 100 concurrent, provider delay 1 s, client timeout 2 s; `docker kill` the service 2 s into the load, restart it right away | orders charged twice or more; orders never charged; orders the client gave up on |
| S4 concurrent duplicate | 2,000 orders, each sent twice at the same instant (double click), provider 50 ms | orders charged twice or more |
| S5 key reuse | 500 orders: same key, second request has a different amount | requests rejected (4xx) vs silently accepted; extra charges |

Per scenario: 3 repeats, 3 variants. Same seeds and orders for every variant at a given repeat.

| # | Hypothesis (not yet measured) | Refuted by |
|---|---|---|
| H1 | `naive` charges at least 50% of orders twice in S2 (the retry arrives before the first call finishes) | under 10% |
| H2 | `naive` charges some orders twice in S3 | zero duplicates in all 3 repeats |
| H3 | `naive` charges at least 50% of orders twice in S4 | under 10% |
| H4 | `idem-local` has 0 duplicates in S2 and S4 | any duplicate |
| H5 | `idem-local` has duplicates in S3 (lease takeover calls the provider again with no key). Expected "designed still fails" case | zero duplicates in all 3 repeats |
| H6 | `idem-e2e` has 0 duplicates in S2, S3 and S4 | any duplicate |
| H7 | S5: `idem-*` rejects 100% of mismatched reuse; `naive` accepts 100% and returns success for the wrong amount | any other result |
| H8 | S1: the design adds less than 25% to median latency compared with `naive` | 25% or more |

**Quick gate:** one `--quick` S2 run of `naive` shows at least one duplicate. If not, stop and change the scenario before the full run.

### Amendment A1 (2026-11-17, written BEFORE the full run; the quick gate has already run)

Quick gate (`experiments/sd-payment-idempotency/results/quick/`, 100-500 orders per run): `naive` S2 charged 199 of 200 orders twice, so the gate passed.
The quick runs also exercised every variant and scenario once. Nothing in them changes a hypothesis. Changes made after seeing quick results,
all before the full run:

- **S1 size:** 2,000 orders finish in about a second, which makes throughput noisy. S1 now uses **10,000 orders** (concurrency 50).
- **S3 validity:** a quick S3 run with 100 orders finished before the kill at 2 s, so no crash was tested. The driver now records `kill_during_load`;
  a run where the kill landed after the load ended is discarded and repeated. Full S3 (1,000 orders, 100 concurrent, 1 s provider delay) runs about 10 s, so the kill lands mid-load.
- **Quick S3 size** is 500 orders (was 100). Not used for conclusions.
- **Metrics added:** `charged_but_client_gave_up` (customer charged but told it failed) and `orders_never_charged`.
- Everything else is as pre-registered: 3 variants x 5 scenarios x 3 repeats = 45 runs, same seeds per repeat.

**Where the designed version is expected to still fail (goes in the article):** a provider with no idempotency support
(H5); keys that expire (not tested; stated as a limit); a client that gives up before the lease ends; the in-flight
window needs a 409 and a client that retries, so a client that does not retry sees an error instead of a duplicate.

## Step 5: Title + slug + meta

- Working title: **Idempotency Key vs Unique Constraint: Duplicate Charges Tested** (decide after results)
- Meta: written after the run; it must carry one measured number and the phrase "idempotency key".
- No M2 / Mac in title or meta.

## Step 6: Decision

**Green for the measured long tail, red for the head term.** 0 direct competitors on a measured version, falsifiable
hypotheses, a cheap harness (Postgres + a mock provider), and a correctness result readers do not get from guides.

## Not in this pilot

Redis `SET NX` as the key store, advisory locks, outbox pattern, webhooks, double-entry ledgers (chapter 27), real
providers. Each could be a follow-up; adding them here turns a three-variant test into a survey.
