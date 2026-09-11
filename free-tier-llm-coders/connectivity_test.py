"""Connectivity test: hit each provider with a 50-token 'ok' request.
Prints the result and any error so we can see which providers are reachable.
"""
import asyncio
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load .env from the experiment directory
load_dotenv(Path(__file__).parent / ".env")

# (label, base_url, model, api_key_env)
TARGETS = [
    ("NVIDIA NIM", "https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3-super-120b-a12b", "NVIDIA_NIM_API_KEY"),
    ("OpenRouter free", "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free", "OPENROUTER_API_KEY"),
    ("Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    ("Cerebras", "https://api.cerebras.ai/v1", "llama-3.3-70b", "CEREBRAS_API_KEY"),
    # ClinePass: try the OpenAI-compatible endpoint first
    ("ClinePass", "https://api.cline.bot/v1", "anthropic/claude-sonnet-4.5", "CLINEPASS_API_KEY"),
]


async def hit_one(label, base_url, model, key):
    api_key = os.environ.get(key, "")
    if not api_key:
        return f"{label:20s}  SKIP (no key)"
    client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=30)
    t = time.monotonic()
    try:
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=20,
            temperature=0.0,
            messages=[{"role": "user", "content": "Reply with one word: ok"}],
        )
        dt = time.monotonic() - t
        text = (resp.choices[0].message.content or "").strip()
        return f"{label:20s}  OK   {dt:5.1f}s  model={resp.model}  text={text!r}"
    except Exception as e:
        dt = time.monotonic() - t
        err = str(e).splitlines()[0][:120] if str(e) else "(empty error)"
        return f"{label:20s}  FAIL {dt:5.1f}s  {type(e).__name__}: {err}"


async def main():
    print("== Connectivity test (parallel) ==")
    results = await asyncio.gather(*[hit_one(*t) for t in TARGETS])
    for r in results:
        print(r)
    print()
    print("== Sequential retry for any FAILs ==")
    for label, base, model, key in TARGETS:
        api_key = os.environ.get(key, "")
        if not api_key:
            continue
        client = AsyncOpenAI(base_url=base, api_key=api_key, timeout=30)
        try:
            resp = await client.chat.completions.create(
                model=model, max_tokens=20, temperature=0.0,
                messages=[{"role": "user", "content": "Reply with one word: ok"}],
            )
            print(f"  retry {label}: OK (text={resp.choices[0].message.content!r})")
        except Exception as e:
            print(f"  retry {label}: {type(e).__name__}: {str(e)[:400]}")


if __name__ == "__main__":
    asyncio.run(main())
