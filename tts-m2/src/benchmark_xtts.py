"""Run XTTS v2 in the 3.11 venv (Coqui TTS only supports Python <=3.12).

Same 15 sentences as benchmark_piper_kokoro.py. Uses the Kokoro output
of the first sentence as the reference speaker (XTTS v2 needs a 6+
second reference clip for voice cloning).

Output: results/benchmark_xtts.json (will be merged with the other
benchmark files in score.py).

Run:
  COQUI_TOS_AGREED=1 /tmp/tts-xtts-venv/bin/python3 src/benchmark_xtts.py
"""

from __future__ import annotations

import json
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
from test_sentences import SENTENCES  # noqa: E402

OUT = ROOT / "results" / "benchmark_xtts.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

# Use a Kokoro-generated reference (long enough for XTTS v2 to clone)
REF_WAV = str(ROOT / "results" / "wav" / "kokoro_long_01.wav")


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024


def wav_duration(path: str) -> float:
    import wave as _w
    with _w.open(path, "rb") as f:
        return f.getnframes() / f.getframerate()


def main() -> int:
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    from TTS.api import TTS as CoquiTTS

    print("Loading XTTS v2 (one-time) ...", flush=True)
    t0 = time.perf_counter()
    tts = CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
    t1 = time.perf_counter()
    print(f"  loaded in {t1-t0:.1f}s", flush=True)

    if not Path(REF_WAV).exists():
        print(f"ERROR: reference wav not found at {REF_WAV}")
        print("Run the kokoro benchmark first to generate the reference.")
        return 1

    data: dict = {"models": {}}
    if OUT.exists():
        data = json.loads(OUT.read_text())

    for sentence in SENTENCES:
        sid = sentence["id"]
        text = sentence["text"]
        if any(r.get("sentence_id") == sid for r in data["models"].get("xtts_v2", [])):
            print(f"  {sid} already done, skip")
            continue
        out_path = str(ROOT / "results" / "wav" / f"xtts_{sid}.wav")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        print(f"=== {sid} (words={len(text.split())}) ===", flush=True)
        rss_before = peak_rss_mb()
        t0 = time.perf_counter()
        try:
            tts.tts_to_file(
                text=text,
                file_path=out_path,
                speaker_wav=REF_WAV,
                language="en",
            )
        except Exception as e:
            print(f"  ERR {e}")
            data["models"].setdefault("xtts_v2", []).append(
                {"sentence_id": sid, "error": str(e)}
            )
            OUT.write_text(json.dumps(data, indent=2))
            continue
        t1 = time.perf_counter()
        rss_after = peak_rss_mb()
        dur = wav_duration(out_path)
        wall = t1 - t0
        r = {
            "sentence_id": sid,
            "category": sentence["category"],
            "wall_seconds": wall,
            "audio_duration_seconds": dur,
            "real_time_factor": wall / dur if dur > 0 else 0,
            "peak_rss_mb": rss_after,
            "rss_delta_mb": rss_after - rss_before,
        }
        data["models"].setdefault("xtts_v2", []).append(r)
        print(
            f"  xtts: wall={wall:.1f}s, rtf={r['real_time_factor']:.3f}, audio={dur:.2f}s",
            flush=True,
        )
        OUT.write_text(json.dumps(data, indent=2))

    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
