# vision-models-m2

Benchmark of 3 local vision-language models on M2 24GB for image captioning.

## The question

Does the "king of local VLMs" (Qwen2.5-VL 7B) actually produce better captions
on a real-world image set than a tiny 2B model (Moondream 2)? And does Google's
Gemma 3 4B sit between them in both quality and speed, as the benchmarks
suggest?

## Models

| Model        | Params | Ollama tag        | Size Q4 | Source                                                                 |
|--------------|--------|-------------------|---------|------------------------------------------------------------------------|
| Moondream 2  | 1.8B   | `moondream`       | ~2.5GB  | [docs.moondream.ai](https://docs.moondream.ai/)                        |
| Gemma 3 4B   | 4.3B   | `gemma3:4b`       | ~2.6GB  | [ollama.com/library/gemma3](https://ollama.com/library/gemma3)         |
| Qwen2.5-VL 7B| 7B     | `qwen2.5vl:7b`    | ~6.0GB  | [ollama.com/library/qwen2.5vl](https://ollama.com/library/qwen2.5vl)   |

All three run through Ollama on the same M2 24GB Mac.

## Test set

15 hand-curated images from Wikimedia Commons covering: cat, dog, bird, car,
Eiffel Tower, snow mountain, pizza, open book, redwood forest, rose, bicycle,
smartphone, coffee, sunset, beach. One reference caption per image,
written before any model output was seen.

## Metric

- **BLEU-4** vs the single reference caption (sacrebleu, smoothed)
- **Wall time per image** (s) from request to final token
- **Tokens per second** (output only)
- **Peak RSS** (MB) during the run

## How to reproduce

```bash
# 1. Pull models
ollama pull moondream
ollama pull gemma3:4b
ollama pull qwen2.5vl:7b

# 2. Set up venv and install deps
python3 -m venv /tmp/vision-m2-venv
/tmp/vision-m2-venv/bin/pip install ollama sacrebleu requests Pillow

# 3. Build the test corpus (downloads 15 images from Wikimedia)
cd /tmp/hardnumbers-experiments-staging/vision-models-m2
/tmp/vision-m2-venv/bin/python3 data/make_corpus.py

# 4. Run the benchmark
/tmp/vision-m2-venv/bin/python3 src/benchmark.py

# 5. Score captions with BLEU
/tmp/vision-m2-venv/bin/python3 src/score.py
```

## Results

See `results/benchmark.json` for raw per-image timings, model outputs, and
BLEU scores. The summary table is in the Hard Numbers article:
[hardnumbers.dev/articles/3-vision-models-tested-moondream-vs-gemma3-vs-qwen-vl](https://hardnumbers.dev/articles/3-vision-models-tested-moondream-vs-gemma3-vs-qwen-vl)
