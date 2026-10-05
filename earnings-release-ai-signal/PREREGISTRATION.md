# Pre-registration: earnings-release-ai-signal

**Timing, stated plainly.** These hypotheses were written in a working plan dated 2026-10-03, before any Jev, Haiku or local
model call and before any return was compared with a label. This file was committed to the repository on 2026-10-05, after
the run, so a git timestamp cannot prove the order of events. The dates are our record.

## Question

1. Does any arm predict the sign of the next-session abnormal return better than a coin flip?
2. Does Jev beat a free local model on the same task?
3. Is Jev's confidence score informative?

## Design (locked)

- Events: SEC EDGAR 8-K filings with Item 2.02 accepted 2026-07-15 to 2026-08-31; Nasdaq/NYSE tickers; entry close at or
  above $5; one row per filing; seeded random sample of 500 (seed 1); exhibit 99.1 text.
- Arms: Jev, a local model (Ollama, thinking off, temperature 0, schema-constrained label), a keyword-rule baseline whose word
  lists were fixed before any outcome was examined, and an always-up control.
- Outcome: sign of the abnormal return (stock minus SPY). Primary window: last regular-session close at or before acceptance
  to the close of the first session that starts after acceptance. Secondary (descriptive only): next session open to close.
  Neutral calls are excluded from hit rates; exactly-zero abnormal returns are dropped.
- Statistics: Wilson 95% intervals; exact two-sided binomial test against 50%; three model arms on one primary window, so
  "beats chance" means a lower bound above 50% **and** p below 0.05 / 3 = 0.0167; Spearman correlation of signed score
  (direction times confidence; 1 where an arm has none) with the abnormal return.

## Hypotheses (locked 2026-10-03)

| ID | Statement | Falsified if |
| --- | --- | --- |
| H1 | No arm has a hit rate whose Wilson lower bound exceeds 50% | Any arm beats the corrected threshold |
| H2 | Jev and the local model are within 3 points | Gap is 5 points or more |
| H3 | Jev's top-confidence third beats its bottom third by 5 points or more | Gap is under 2 points |
| H4 | Best Spearman correlation is 0.10 or lower | Correlation is 0.15 or higher with p under 0.01 |

## Changes made after the lock and before any outcome was scored

1. Text per release cut from 12,000 to 6,000 characters for every arm (the local model needed 30 to 35 s per longer prompt).
2. Local model changed from Qwen3-14B to Qwen2.5-7B, for the same reason. The hypotheses name "the local model", so their
   thresholds are unchanged.
3. Releases with under 500 characters of text excluded for every arm (3 near-empty exhibits).
4. One filing per row, by a rule that ignores returns (no hyphen in the ticker, then the shorter ticker).
5. The local run's stop rule moved from swap growth to measured latency after the first attempt showed swap growth did not
   slow inference. This affects when a run stops, not which events are scored.

## Results

H1 holds narrowly (Jev p = 0.0175 against the 0.0167 line). H2 falsified (gap 5.7 points). H3 neither supported nor
falsified (gap 3.8 points, between the 2 and 5 point thresholds). H4 falsified (Jev's correlation 0.224). Full tables:
`results/analysis.json`. Observations made after scoring (for example Jev's bearish calls) were **not** pre-registered and are
labelled post-hoc wherever they appear.
