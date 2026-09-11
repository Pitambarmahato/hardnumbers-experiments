"""Quick Python test of OpenRouter cohere to see if it's curl-specific."""
import asyncio
import os
import time
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()


async def main():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=60)
    for model in [
        "cohere/north-mini-code:free",
        "minimax/minimax-m3:free",
        "google/gemma-4-31b-it:free",
    ]:
        print(f"\n=== {model} ===")
        t = time.monotonic()
        try:
            resp = await client.chat.completions.create(
                model=model,
                max_tokens=80,
                temperature=0.0,
                messages=[{
                    "role": "user",
                    "content": "Add a Python docstring to: def add(a,b): return a+b. Output just the modified function.",
                }],
            )
            dt = time.monotonic() - t
            text = (resp.choices[0].message.content or "").strip()
            print(f"  OK {dt:.1f}s: {text[:200]!r}")
        except Exception as e:
            dt = time.monotonic() - t
            print(f"  FAIL {dt:.1f}s: {type(e).__name__}: {str(e)[:300]}")


if __name__ == "__main__":
    asyncio.run(main())
