"""Minimal connectivity test: call Ollama with gpt-oss:20b (fastest
local model) and a tiny token budget. Just proves the pipeline works.
"""
import asyncio
import os
import time

import httpx
from openai import AsyncOpenAI


async def smoke_test():
    base = os.environ.get("OLLAMA_BASE", "http://localhost:11434/v1")
    # Use the fastest local model from the previous benchmarks
    model = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")

    r = httpx.get(f"{base.rstrip('/v1')}/api/tags", timeout=5)
    models = [m["name"] for m in r.json().get("models", [])]
    print(f"Available: {models}")
    print(f"Using: {model} @ {base}")
    print()

    client = AsyncOpenAI(base_url=base, api_key="ollama")

    # 1. Pure connectivity test
    print("=== Test 1: connectivity (10 token budget) ===")
    wall = time.monotonic()
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                max_tokens=10,
                temperature=0.0,
                messages=[{"role": "user", "content": "Reply with one word: ok"}],
            ),
            timeout=30,
        )
        text = resp.choices[0].message.content
        elapsed = time.monotonic() - wall
        print(f"  OK in {elapsed:.2f}s: {text!r}")
    except Exception as e:
        print(f"  FAIL: {e}")
        return

    # 2. Code-gen test (the real workload) with 500 token budget
    print("\n=== Test 2: small code-gen (500 token budget) ===")
    prompt = (
        "Add a one-line Python docstring to: "
        "def add(a, b): return a + b\n"
        "Output just the modified function. No explanation."
    )
    wall = time.monotonic()
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                max_tokens=500,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=120,
        )
        text = resp.choices[0].message.content
        elapsed = time.monotonic() - wall
        tokens_in = resp.usage.prompt_tokens if resp.usage else 0
        tokens_out = resp.usage.completion_tokens if resp.usage else 0
        print(f"  OK in {elapsed:.2f}s ({tokens_in} in, {tokens_out} out)")
        print(f"  Response:\n{text}")
    except Exception as e:
        print(f"  FAIL: {e}")
        return

    print("\n=== Pipeline verified ===")
    print("Ollama + gpt-oss:20b can serve the benchmark workload.")
    print("For real cloud providers, we need API keys.")


if __name__ == "__main__":
    asyncio.run(smoke_test())
