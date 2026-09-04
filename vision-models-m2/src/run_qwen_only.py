"""Run ONLY the Qwen2.5-VL 7B benchmark (others are already done).

Moondream and Gemma 3 4B ran in ~3 min and ~10 min respectively. Qwen
is larger (7B) and may take longer. Run in the background and check.
"""

from __future__ import annotations

import json
import resource
import time
from pathlib import Path

import ollama

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus.jsonl"
OUT = ROOT / "results" / "benchmark.json"

MODEL = "qwen2.5vl:7b"
PROMPT = (
    "Describe this image in one or two short sentences. "
    "Be specific about what is visible. Do not start with phrases like "
    "'The image', 'This image', or 'Shown here'. Just describe the subject."
)


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main() -> int:
    corpus = [json.loads(l) for l in CORPUS.read_text().splitlines() if l.strip()]
    data = json.loads(OUT.read_text()) if OUT.exists() else {"models": {}}
    if MODEL in data["models"] and len(data["models"][MODEL]) == len(corpus):
        print(f"{MODEL} already complete, skipping")
        return 0
    data["models"].setdefault(MODEL, [])
    print(f"Starting {MODEL} on {len(corpus)} images")

    # Warmup
    print("warmup...", flush=True)
    warmup_path = str(ROOT / corpus[0]["local_path"])
    ollama.chat(
        model=MODEL,
        messages=[
            {"role": "user", "content": "Describe briefly.", "images": [warmup_path]}
        ],
        stream=False,
    )

    for entry in corpus:
        # Skip if already done
        if any(r.get("image_id") == entry["id"] for r in data["models"][MODEL]):
            print(f"  {entry['id']} already done, skip")
            continue
        img_path = str(ROOT / entry["local_path"])
        print(f"  {entry['id']}: {Path(img_path).name} ...", end=" ", flush=True)
        rss_before = peak_rss_mb()
        t0 = time.perf_counter()
        first_token_at = None
        chunks: list[str] = []
        final_chunk = None
        try:
            for chunk in ollama.chat(
                model=MODEL,
                messages=[
                    {"role": "user", "content": PROMPT, "images": [img_path]}
                ],
                stream=True,
            ):
                if first_token_at is None and chunk.get("message", {}).get("content"):
                    first_token_at = time.perf_counter()
                chunks.append(chunk.get("message", {}).get("content") or "")
                final_chunk = chunk
            t1 = time.perf_counter()
        except Exception as e:
            print(f"ERR {e}")
            data["models"][MODEL].append(
                {"image_id": entry["id"], "error": str(e), "reference_caption": entry["reference_caption"]}
            )
            OUT.write_text(json.dumps(data, indent=2))
            continue
        text = "".join(chunks).strip()
        rss_after = peak_rss_mb()
        wall = t1 - t0
        out_tokens = (final_chunk or {}).get("eval_count", 0) or 0
        prompt_tokens = (final_chunk or {}).get("prompt_eval_count", 0) or 0
        print(
            f"{wall:.2f}s, {out_tokens} tok, {out_tokens/wall if wall else 0:.1f} tok/s, "
            f"ttft={(first_token_at-t0) if first_token_at else 0:.2f}s, RSS {rss_after:.0f}MB"
        )
        data["models"][MODEL].append(
            {
                "image_id": entry["id"],
                "wall_seconds": wall,
                "time_to_first_token_seconds": (first_token_at - t0) if first_token_at else None,
                "output_tokens": out_tokens,
                "prompt_tokens": prompt_tokens,
                "tokens_per_second": out_tokens / wall if wall else 0,
                "peak_rss_mb": rss_after,
                "rss_delta_mb": rss_after - rss_before,
                "output_text": text,
                "reference_caption": entry["reference_caption"],
            }
        )
        OUT.write_text(json.dumps(data, indent=2))
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
