"""Score the 3 TTS engines with Whisper transcription WER + summary stats.

Uses the small.en Whisper model (~460MB) for reasonable WER quality.
If disk is tight, falls back to tiny.en (~75MB).

Reads:
  results/benchmark_piper_kokoro.json
  results/benchmark_xtts.json

Writes:
  results/summary.json
  results/transcriptions.json (raw whisper output for inspection)

Run:
  /tmp/tts-m2-venv/bin/python3 src/score.py
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
from test_sentences import SENTENCES  # noqa: E402

WAV_DIR = ROOT / "results" / "wav"
OUT = ROOT / "results" / "summary.json"
RAW = ROOT / "results" / "transcriptions.json"

# Try small.en, fall back to tiny.en
MODEL_NAME = "small.en"


def normalize(text: str) -> str:
    """Normalize text for WER: lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def wer(reference: str, hypothesis: str) -> tuple[int, int]:
    """Word error rate = (substitutions + deletions + insertions) / reference_words.
    Returns (errors, ref_words)."""
    ref_words = normalize(reference).split()
    hyp_words = normalize(hypothesis).split()
    if not ref_words:
        return (0, 0)
    # Levenshtein
    n, m = len(ref_words), len(hyp_words)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[n][m], n


def main() -> int:
    import whisper

    piper_kokoro = json.loads((ROOT / "results" / "benchmark_piper_kokoro.json").read_text())
    xtts = json.loads((ROOT / "results" / "benchmark_xtts.json").read_text())
    sentences_by_id = {s["id"]: s["text"] for s in SENTENCES}

    print(f"Loading whisper {MODEL_NAME} ...", flush=True)
    t0 = time.perf_counter()
    model = whisper.load_model(MODEL_NAME)
    t1 = time.perf_counter()
    print(f"  loaded in {t1 - t0:.1f}s", flush=True)

    # Transcribe every wav file
    raw: dict = {}
    wav_files = sorted(WAV_DIR.glob("*.wav"))
    print(f"Transcribing {len(wav_files)} wav files ...", flush=True)
    for i, wav in enumerate(wav_files, 1):
        # Filename format: {model}_{sentence_id}.wav
        parts = wav.stem.split("_", 1)
        engine = parts[0]
        sentence_id = parts[1]
        key = f"{engine}_{sentence_id}"
        print(f"  [{i:2d}/{len(wav_files)}] {key} ...", end=" ", flush=True)
        t0 = time.perf_counter()
        r = model.transcribe(str(wav), language="en", fp16=False)
        t1 = time.perf_counter()
        raw[key] = {
            "engine": engine,
            "sentence_id": sentence_id,
            "whisper_text": r["text"].strip(),
            "transcribe_seconds": t1 - t0,
        }
        print(f"{t1 - t0:.1f}s: {r['text'].strip()[:60]}...", flush=True)

    RAW.write_text(json.dumps(raw, indent=2))
    print(f"Wrote {RAW}")

    # Score per model
    by_engine: dict = {"piper": [], "kokoro": [], "xtts": []}
    for key, t in raw.items():
        engine = t["engine"]
        if engine not in by_engine:
            continue
        ref = sentences_by_id[t["sentence_id"]]
        errors, ref_n = wer(ref, t["whisper_text"])
        wer_pct = (errors / ref_n) if ref_n else 0
        by_engine[engine].append(
            {
                "sentence_id": t["sentence_id"],
                "reference": ref,
                "hypothesis": t["whisper_text"],
                "wer": wer_pct,
                "errors": errors,
                "ref_words": ref_n,
            }
        )

    # Combine timing data
    timing: dict = {"piper": {}, "kokoro": {}, "xtts": {}}
    for r in piper_kokoro["models"].get("piper", []):
        if "error" in r:
            continue
        timing["piper"][r["sentence_id"]] = {
            "wall_seconds": r["wall_seconds"],
            "audio_duration_seconds": r["audio_duration_seconds"],
            "real_time_factor": r["real_time_factor"],
            "peak_rss_mb": r["peak_rss_mb"],
        }
    for r in piper_kokoro["models"].get("kokoro", []):
        if "error" in r:
            continue
        timing["kokoro"][r["sentence_id"]] = {
            "wall_seconds": r["wall_seconds"],
            "audio_duration_seconds": r["audio_duration_seconds"],
            "real_time_factor": r["real_time_factor"],
            "peak_rss_mb": r["peak_rss_mb"],
        }
    for r in xtts["models"].get("xtts_v2", []):
        if "error" in r:
            continue
        timing["xtts"][r["sentence_id"]] = {
            "wall_seconds": r["wall_seconds"],
            "audio_duration_seconds": r["audio_duration_seconds"],
            "real_time_factor": r["real_time_factor"],
            "peak_rss_mb": r["peak_rss_mb"],
        }

    summary: dict = {"models": {}}
    for engine, scores in by_engine.items():
        if not scores:
            continue
        engine_timing = timing.get(engine, {})
        wer_vals = [s["wer"] for s in scores]
        rtfs = [t["real_time_factor"] for t in engine_timing.values()]
        walls = [t["wall_seconds"] for t in engine_timing.values()]
        rss_vals = [t["peak_rss_mb"] for t in engine_timing.values()]
        summary["models"][engine] = {
            "median_wer": statistics.median(wer_vals),
            "mean_wer": statistics.mean(wer_vals),
            "median_real_time_factor": statistics.median(rtfs) if rtfs else 0,
            "mean_real_time_factor": statistics.mean(rtfs) if rtfs else 0,
            "median_wall_seconds": statistics.median(walls) if walls else 0,
            "median_peak_rss_mb": statistics.median(rss_vals) if rss_vals else 0,
            "per_sentence": [
                {
                    **s,
                    **({"timing": engine_timing.get(s["sentence_id"])} if s["sentence_id"] in engine_timing else {}),
                }
                for s in scores
            ],
        }

    OUT.write_text(json.dumps(summary, indent=2))

    # Print headline
    print()
    print("=" * 80)
    print(f"{'Model':<14s} {'Median WER':>12s} {'Mean WER':>11s} {'RTF':>10s} {'Wall s':>10s} {'RSS MB':>10s}")
    print("=" * 80)
    for engine, s in summary["models"].items():
        print(
            f"{engine:<14s} "
            f"{s['median_wer']*100:>11.1f}% "
            f"{s['mean_wer']*100:>10.1f}% "
            f"{s['median_real_time_factor']:>10.3f} "
            f"{s['median_wall_seconds']:>10.2f} "
            f"{s['median_peak_rss_mb']:>10.0f}"
        )
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
