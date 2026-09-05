"""Run Piper and Kokoro in the 3.13 venv (which has whisper too).

For each of 15 sentences, run Piper and Kokoro and record:
  - wall_seconds: total time to produce the wav
  - time_to_first_byte_seconds: streaming latency (not always available)
  - audio_duration_seconds: output wav length
  - real_time_factor: wall_seconds / audio_duration_seconds
  - peak_rss_mb: peak resident set during this call
  - output_wav: path to saved wav file

XTTS v2 is run separately in src/benchmark_xtts.py because it lives in
a different venv.

Run:
  /tmp/tts-m2-venv/bin/python3 src/benchmark_piper_kokoro.py
"""

from __future__ import annotations

import json
import os
import resource
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))
from test_sentences import SENTENCES  # noqa: E402

OUT = ROOT / "results" / "benchmark_piper_kokoro.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

PIPER_VOICE = str(ROOT / "voices" / "piper.onnx")
PIPER_CONFIG = str(ROOT / "voices" / "piper.onnx.json")
KOKORO_ONNX = str(ROOT / "voices" / "kokoro.onnx")
KOKORO_VOICES = str(ROOT / "voices" / "kokoro-voices.bin")
KOKORO_VOICE_NAME = "af_bella"  # American English, female


def peak_rss_mb() -> float:
    # On macOS, ru_maxrss is in bytes.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / w.getframerate()


def run_piper(text: str, out_path: str) -> dict:
    from piper import PiperVoice

    v = PiperVoice.load(PIPER_VOICE, PIPER_CONFIG)
    rss_before = peak_rss_mb()
    t0 = time.perf_counter()
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(v.config.sample_rate)
        for chunk in v.synthesize(text):
            w.writeframes(chunk.audio_int16_bytes)
    t1 = time.perf_counter()
    rss_after = peak_rss_mb()
    return {
        "wall_seconds": t1 - t0,
        "audio_duration_seconds": wav_duration(out_path),
        "real_time_factor": (t1 - t0) / wav_duration(out_path),
        "peak_rss_mb": rss_after,
        "rss_delta_mb": rss_after - rss_before,
    }


def run_kokoro(text: str, out_path: str) -> dict:
    from kokoro_onnx import Kokoro
    import soundfile as sf

    k = Kokoro(KOKORO_ONNX, KOKORO_VOICES)
    rss_before = peak_rss_mb()
    t0 = time.perf_counter()
    samples, sr = k.create(text, voice=KOKORO_VOICE_NAME, speed=1.0, lang="en-us")
    t1 = time.perf_counter()
    sf.write(out_path, samples, sr)
    rss_after = peak_rss_mb()
    dur = len(samples) / sr
    return {
        "wall_seconds": t1 - t0,
        "audio_duration_seconds": dur,
        "real_time_factor": (t1 - t0) / dur,
        "peak_rss_mb": rss_after,
        "rss_delta_mb": rss_after - rss_before,
    }


def main() -> int:
    data: dict = {"models": {}}
    if OUT.exists():
        data = json.loads(OUT.read_text())

    for sentence in SENTENCES:
        sid = sentence["id"]
        text = sentence["text"]
        print(f"=== {sid} (category={sentence['category']}, words={len(text.split())}) ===")

        # Piper
        if (
            "piper" not in data["models"]
            or not any(r.get("sentence_id") == sid for r in data["models"].get("piper", []))
        ):
            out_path = str(ROOT / "results" / "wav" / f"piper_{sid}.wav")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            print("  piper ...", end=" ", flush=True)
            try:
                r = run_piper(text, out_path)
                r["sentence_id"] = sid
                r["category"] = sentence["category"]
                data["models"].setdefault("piper", []).append(r)
                print(
                    f"wall={r['wall_seconds']:.2f}s, rtf={r['real_time_factor']:.3f}, "
                    f"audio={r['audio_duration_seconds']:.2f}s"
                )
            except Exception as e:
                print(f"ERR {e}")
                data["models"].setdefault("piper", []).append(
                    {"sentence_id": sid, "error": str(e)}
                )
            OUT.write_text(json.dumps(data, indent=2))

        # Kokoro
        if (
            "kokoro" not in data["models"]
            or not any(r.get("sentence_id") == sid for r in data["models"].get("kokoro", []))
        ):
            out_path = str(ROOT / "results" / "wav" / f"kokoro_{sid}.wav")
            print("  kokoro ...", end=" ", flush=True)
            try:
                r = run_kokoro(text, out_path)
                r["sentence_id"] = sid
                r["category"] = sentence["category"]
                data["models"].setdefault("kokoro", []).append(r)
                print(
                    f"wall={r['wall_seconds']:.2f}s, rtf={r['real_time_factor']:.3f}, "
                    f"audio={r['audio_duration_seconds']:.2f}s"
                )
            except Exception as e:
                print(f"ERR {e}")
                data["models"].setdefault("kokoro", []).append(
                    {"sentence_id": sid, "error": str(e)}
                )
            OUT.write_text(json.dumps(data, indent=2))

    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
