# humanizer-benchmark

Does the [blader/humanizer](https://github.com/blader/humanizer) skill (v3.1.0, commit `225a6f3`, MIT) beat a one-line rewrite prompt, and does it remove claims the source never supported?

Article: not yet published.

## Design

- 24 inputs (`inputs.py`): 13 genres, each with 3-4 concrete facts.
- **Round 1** (`out/`): clean drafts written by Claude Opus 5.5 from a neutral prompt.
- **Round 2** (`hard/`): tell-heavy drafts written by Haiku "in the voice of a typical enthusiastic AI chatbot or marketing copywriter".
- Conditions per draft: raw, `/humanizer` skill, and a one-line control: "Rewrite this so it does not sound AI-written. Keep every fact. Return only the rewritten text."
- Rewriters: Opus 5.5 and Sonnet 5.5 (round 2); Opus 5.5 (round 1). Judge and claim extractor: Sonnet 5.5.
- Everything ran through Claude Code 2.1.296 headless (`claude -p`), 2026-10-11 and 2026-10-12. No API key, no AI detector.

## Files

| File | Purpose |
| --- | --- |
| `inputs.py` | the 24 inputs and their facts |
| `run.py` | round 1: generate drafts, then skill / control rewrites |
| `run2.py` | round 2: hype-toned drafts, rewrites on a chosen model |
| `metrics.py`, `metrics2.py` | regex tell density, fact (number) retention, length |
| `judge.py` | blind pairwise judge, both orders, "more human" / "better overall" |
| `invent.py` | unsupported-claim extraction and carryover into rewrites |
| `SKILL.v3.1.0.md` | the exact skill file used |
| `out/`, `hard/` | every raw draft, rewrite, judge output, and cost |

## Reproduce

```bash
mkdir -p .claude/skills/humanizer && cp SKILL.v3.1.0.md .claude/skills/humanizer/SKILL.md
python3 run.py gen && python3 run.py rewrite          # round 1 -> out/
python3 run2.py gen hard                              # round 2 drafts -> hard/
python3 run2.py rewrite hard opus && python3 run2.py rewrite hard sonnet
python3 metrics.py; python3 metrics2.py hard opus; python3 metrics2.py hard sonnet
python3 judge.py hard opus; python3 invent.py
```

Run from this directory, with Claude Code logged in. List-price cost was about $10 in total.

## Caveats

- **Not deterministic.** `claude -p` exposes no temperature setting, so reruns will differ. This does not follow this repo's usual `temperature=0` standard; the raw outputs are included so the numbers can be audited instead.
- One run per cell, n=24 short synthetic texts.
- The judge and claim extractor are Claude models and may favor Claude-style prose. Extracted claims were not hand-audited and mix concrete details with soft claims.
- Results are specific to skill v3.1.0 and the model versions above.
