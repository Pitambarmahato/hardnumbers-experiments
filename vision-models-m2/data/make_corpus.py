"""Build the 15-image test corpus for vision model captioning benchmark.

Downloads 15 curated Wikimedia Commons images (1024px-wide thumbnails) into
data/images/, and writes data/corpus.jsonl with the source URL, local
filename, and a single hand-written reference caption per image.

The reference captions are written BEFORE running the benchmark to avoid
biasing them on the model outputs.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
IMG_DIR = ROOT / "data" / "images"
OUT = ROOT / "data" / "corpus.jsonl"

UA = {
    "User-Agent": "HardNumbers/1.0 (research; contact: ops@hardnumbers.dev)"
}


# (subject search query, reference caption)
# Captions are 1-2 sentences, simple, factual. No "A photo of" preamble.
SUBJECTS: list[tuple[str, str]] = [
    ("cat photograph", "A tabby cat sits on snow-covered ground, looking forward."),
    ("dog photograph", "A dhole, also known as an Asiatic wild dog, stands in profile."),
    ("bird photograph", "A southern masked weaver bird perches on a branch with its beak open."),
    ("car photograph sedan", "A silver Toyota Corolla sedan parked on a city street."),
    ("eiffel tower photograph", "The Eiffel Tower photographed against a clear blue sky in Paris."),
    ("mountain photograph snow", "A snow-capped mountain range under a hazy sky."),
    ("pizza photograph", "A margherita pizza topped with tomato sauce, mozzarella, and fresh basil leaves."),
    ("open book photograph", "An open hardcover book lies flat with a bookmark between its pages."),
    ("forest tree photograph", "Tall redwood trees reach upward through morning fog in a forest."),
    ("rose flower photograph", "A pink rose in full bloom photographed in close-up."),
    ("bicycle photograph", "A bicycle parked on a cobblestone street in Amsterdam."),
    ("smartphone photograph", "A modern smartphone with a dark titanium back lying on a flat surface."),
    ("coffee cup photograph", "A cup of black coffee in a white ceramic cup on a saucer."),
    ("sunset ocean photograph", "A bright orange sun setting over a calm ocean horizon."),
    ("beach photograph", "A wide sandy beach lined with palm trees under a sunny sky."),
]


def search_image(query: str, n: int = 12) -> list[str]:
    r = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srnamespace": 6,
            "srlimit": n,
        },
        headers=UA,
        timeout=15,
    )
    r.raise_for_status()
    return [h["title"] for h in r.json().get("query", {}).get("search", [])]


def get_thumb_url(title: str, width: int = 1024) -> str | None:
    r = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": width,
        },
        headers=UA,
        timeout=15,
    )
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    for p in pages.values():
        if "imageinfo" in p:
            info = p["imageinfo"][0]
            mime = info.get("mime", "")
            if mime.startswith("image/") and not mime.endswith("svg+xml"):
                return info.get("thumburl") or info.get("url")
    return None


def pick_first_photo(query: str) -> tuple[str, str] | None:
    """Return (title, thumb_url) for the first usable photo in the search."""
    candidates = search_image(query, 12)
    for title in candidates:
        low = title.lower()
        if not (low.endswith(".jpg") or low.endswith(".jpeg") or low.endswith(".png")):
            continue
        if any(bad in low for bad in ("svg", "icon", "symbol", "logo", "diagram")):
            continue
        url = get_thumb_url(title)
        if url:
            return title, url
    return None


def main() -> int:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    failures: list[str] = []

    for i, (query, caption) in enumerate(SUBJECTS, 1):
        print(f"[{i:2d}/15] {query}")
        try:
            pick = pick_first_photo(query)
        except Exception as e:
            print(f"  ERR search: {e}")
            failures.append(query)
            continue
        if not pick:
            print(f"  ERR no usable photo")
            failures.append(query)
            continue
        title, url = pick
        # Slug: id + first two words of title
        safe = "".join(c if c.isalnum() else "_" for c in title.replace("File:", ""))
        local = IMG_DIR / f"{i:02d}_{safe[:60]}.jpg"
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            local.write_bytes(r.content)
        except Exception as e:
            print(f"  ERR download: {e}")
            failures.append(query)
            continue
        size_kb = len(r.content) / 1024
        print(f"  -> {local.name}  ({size_kb:.0f} KB)")
        rows.append(
            {
                "id": f"img_{i:02d}",
                "query": query,
                "wikimedia_title": title,
                "wikimedia_url": url,
                "local_path": str(local.relative_to(ROOT)),
                "reference_caption": caption,
            }
        )
        time.sleep(0.4)

    with OUT.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    print()
    print(f"Wrote {len(rows)} entries to {OUT}")
    if failures:
        print(f"FAILED: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
