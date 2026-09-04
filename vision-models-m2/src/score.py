"""Score the benchmark results with sacrebleu BLEU-4 + summary stats."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import sacrebleu

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "results" / "benchmark.json"
OUT = ROOT / "results" / "summary.json"


def main() -> int:
    data = json.loads(IN.read_text())
    summary: dict = {"models": {}}

    for model, rows in data["models"].items():
        per_image_bleu: list[dict] = []
        refs: list[str] = []
        hyps: list[str] = []
        walls: list[float] = []
        tps: list[float] = []
        rss: list[float] = []
        out_tok: list[int] = []
        for r in rows:
            if "error" in r:
                continue
            ref = r["reference_caption"]
            hyp = r["output_text"]
            refs.append(ref)
            hyps.append(hyp)
            walls.append(r["wall_seconds"])
            tps.append(r["tokens_per_second"])
            rss.append(r["peak_rss_mb"])
            out_tok.append(r["output_tokens"])
            bleu = sacrebleu.sentence_bleu(hyp, [ref], smooth_method="exp").score
            per_image_bleu.append(
                {
                    "image_id": r["image_id"],
                    "reference": ref,
                    "hypothesis": hyp,
                    "bleu4": bleu,
                }
            )

        if not hyps:
            continue
        corpus_bleu = sacrebleu.corpus_bleu(hyps, [refs]).score
        bleu_scores = [x["bleu4"] for x in per_image_bleu]

        summary["models"][model] = {
            "corpus_bleu4": corpus_bleu,
            "mean_sentence_bleu4": statistics.mean(bleu_scores),
            "median_sentence_bleu4": statistics.median(bleu_scores),
            "median_wall_seconds": statistics.median(walls),
            "median_tokens_per_second": statistics.median(tps),
            "median_peak_rss_mb": statistics.median(rss),
            "median_output_tokens": statistics.median(out_tok),
            "total_wall_seconds": sum(walls),
            "per_image": per_image_bleu,
        }

    OUT.write_text(json.dumps(summary, indent=2))

    # Print headline table
    print("=" * 80)
    print(f"{'Model':<22s} {'Corpus BLEU4':>14s} {'Mean s-BLEU4':>14s} {'Wall s':>10s} {'tok/s':>10s} {'RSS MB':>10s}")
    print("=" * 80)
    for m, s in summary["models"].items():
        print(
            f"{m:<22s} "
            f"{s['corpus_bleu4']:>14.2f} "
            f"{s['mean_sentence_bleu4']:>14.2f} "
            f"{s['median_wall_seconds']:>10.2f} "
            f"{s['median_tokens_per_second']:>10.1f} "
            f"{s['median_peak_rss_mb']:>10.0f}"
        )
    print("=" * 80)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
