"""Run the vision captioning benchmark: 3 models x 15 images.

For each model:
  1. Warm up with one dummy image (not timed)
  2. For each test image, time the full request, record:
     - wall_seconds: end-to-end latency
     - time_to_first_token_seconds: streaming first byte
     - output_tokens: eval_count
     - prompt_tokens: prompt_eval_count
     - peak_rss_mb: peak resident set size during this single request
  3. Save the model output (caption) verbatim

Output: results/benchmark.json with per-model, per-image metrics and captions.
"""

from __future__ import annotations

import json
import os
import resource
import time
from pathlib import Path

import ollama

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus.jsonl"
OUT = ROOT / "results" / "benchmark.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

MODELS: list[str] = [
    "moondream",
    "gemma3:4b",
    "qwen2.5vl:7b",
]

PROMPT = (
    "Describe this image in one or two short sentences. "
    "Be specific about what is visible. Do not start with phrases like "
    "'The image', 'This image', or 'Shown here'. Just describe the subject."
)


def load_corpus() -> list[dict]:
    return [json.loads(l) for l in CORPUS.read_text().splitlines() if l.strip()]


def peak_rss_mb() -> float:
    # ru_maxrss is in KB on macOS
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def run_image(model: str, image_path: str) -> dict:
    """Run a single image through the model, returning timing + output."""
    # Warm cache: do a tiny first call so the model file is loaded
    # (Not timed; serves as the first pass that loads the model into RAM)

    # Mark baseline RSS for delta measurement
    rss_before = peak_rss_mb()
    t_start = time.perf_counter()
    first_token_at: float | None = None
    chunks: list[str] = []
    prompt_tokens = 0
    output_tokens = 0
    total_duration_ns = 0

    stream = ollama.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": PROMPT,
                "images": [image_path],
            }
        ],
        stream=True,
    )
    final_chunk = None
    for chunk in stream:
        if first_token_at is None and chunk.get("message", {}).get("content"):
            first_token_at = time.perf_counter()
        content = chunk.get("message", {}).get("content") or ""
        chunks.append(content)
        final_chunk = chunk
    t_end = time.perf_counter()
    rss_after = peak_rss_mb()

    text = "".join(chunks).strip()
    # Final chunk has the eval stats
    if final_chunk:
        output_tokens = final_chunk.get("eval_count", 0) or 0
        prompt_tokens = final_chunk.get("prompt_eval_count", 0) or 0
        total_duration_ns = final_chunk.get("total_duration", 0) or 0

    return {
        "wall_seconds": t_end - t_start,
        "time_to_first_token_seconds": (
            (first_token_at - t_start) if first_token_at else None
        ),
        "output_tokens": output_tokens,
        "prompt_tokens": prompt_tokens,
        "ollama_total_duration_seconds": total_duration_ns / 1e9,
        "tokens_per_second": (
            output_tokens / (t_end - t_start) if (t_end - t_start) > 0 else 0
        ),
        "peak_rss_mb": rss_after,
        "rss_delta_mb": rss_after - rss_before,
        "output_text": text,
    }


def warmup(model: str, image_path: str) -> None:
    """One untimed pass to load the model."""
    try:
        ollama.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": "Describe briefly.",
                    "images": [image_path],
                }
            ],
            stream=False,
        )
    except Exception as e:
        print(f"  warmup failed: {e}")


def main() -> int:
    corpus = load_corpus()
    print(f"Loaded {len(corpus)} images from {CORPUS.name}")
    print(f"Models: {MODELS}")
    print(f"Prompt: {PROMPT!r}")
    print()

    all_results: dict = {"models": {}}

    for m in MODELS:
        print(f"=== {m} ===")
        # First image is the warmup target
        warmup_path = str(ROOT / corpus[0]["local_path"])
        print(f"  warmup with {warmup_path}")
        warmup(m, warmup_path)
        m_results: list[dict] = []
        for entry in corpus:
            img_path = str(ROOT / entry["local_path"])
            print(f"  {entry['id']}: {Path(img_path).name} ...", end=" ", flush=True)
            try:
                r = run_image(m, img_path)
            except Exception as e:
                print(f"ERR {e}")
                r = {"error": str(e)}
            r["image_id"] = entry["id"]
            r["reference_caption"] = entry["reference_caption"]
            m_results.append(r)
            if "error" not in r:
                print(
                    f"{r['wall_seconds']:.2f}s "
                    f"({r['output_tokens']} tok, "
                    f"{r['tokens_per_second']:.1f} tok/s, "
                    f"RSS {r['peak_rss_mb']:.0f}MB)"
                )
        all_results["models"][m] = m_results
        # write per-model checkpoint in case something dies
        OUT.write_text(json.dumps(all_results, indent=2))
        print()
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
