"""Collect earnings-release events (8-K Item 2.02) from SEC EDGAR. No Jev, no paid API.

    python3 collect.py events [--sample N] [--seed 1]   # sample tickers, find Item 2.02 8-Ks in the window
    python3 collect.py text                             # fetch exhibit 99.1 for each event, convert to plain text

SEC fair access: declared User-Agent, at most 5 requests/second, every response cached on disk and never re-fetched.
Raw filing text lives in data/ (gitignored). The repo commits only accession numbers and derived results.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "cache")
UA = os.environ.get("SEC_USER_AGENT", "")
if not UA:
    raise SystemExit("SEC fair access requires a contact in the User-Agent. Set it first, e.g.\n"
                     "  export SEC_USER_AGENT='Your Name your.email@example.com'")
WINDOW = ("2026-07-15", "2026-08-31")  # fixed in the plan before data collection
MIN_INTERVAL = 0.2  # 5 requests per second
_last = [0.0]


def get(url: str) -> bytes:
    """Cached, throttled GET. Raises on HTTP errors (stop rule: no blind retries)."""
    os.makedirs(CACHE, exist_ok=True)
    key = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9._-]", "_", url)[-180:])
    if os.path.exists(key):
        return open(key, "rb").read()
    wait = MIN_INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    _last[0] = time.time()
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    open(key, "wb").write(body)
    return body


def events(sample: int, seed: int) -> None:
    tk = json.loads(get("https://www.sec.gov/files/company_tickers_exchange.json"))
    fields = tk["fields"]
    rows = [dict(zip(fields, r)) for r in tk["data"]]
    listed = [r for r in rows if r.get("exchange") in ("Nasdaq", "NYSE") and r.get("ticker")]
    print(f"tickers: {len(rows)} total, {len(listed)} on Nasdaq/NYSE")
    random.Random(seed).shuffle(listed)
    out, errors, checked = [], 0, 0
    for r in listed[:sample]:
        cik = int(r["cik"])
        try:
            sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
        except (urllib.error.URLError, TimeoutError) as e:
            errors += 1
            print(f"  error {r['ticker']}: {e!r}")
            if errors > 10:
                sys.exit("STOP: more than 10 fetch errors")
            continue
        checked += 1
        rec = sub["filings"]["recent"]
        for i, form in enumerate(rec["form"]):
            if form != "8-K" or "2.02" not in rec["items"][i].split(","):
                continue
            if not (WINDOW[0] <= rec["filingDate"][i] <= WINDOW[1]):
                continue
            out.append({"ticker": r["ticker"], "cik": cik, "name": r["name"], "exchange": r["exchange"],
                        "accession": rec["accessionNumber"][i], "filing_date": rec["filingDate"][i],
                        "accepted": rec["acceptanceDateTime"][i], "items": rec["items"][i],
                        "primary_doc": rec["primaryDocument"][i]})
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "events.jsonl"), "w") as f:
        for e in out:
            f.write(json.dumps(e) + "\n")
    print(f"checked {checked} companies ({errors} errors): {len(out)} Item 2.02 8-Ks in {WINDOW[0]}..{WINDOW[1]}"
          f" -> {len(out) / max(checked, 1):.2f} per company")


def strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in raw.splitlines()]
    lines = [l for l in lines if l and l != "​"]
    while lines and re.fullmatch(r"EX-99\.1|\d{1,2}|\S+\.html?", lines[0], re.I):  # SEC header artifact
        lines.pop(0)
    return "\n".join(lines)


def exhibit_url(e: dict) -> str | None:
    """Find the document typed EX-99.1 in the filing's -index.html table (file names are not reliable)."""
    acc = e["accession"].replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{e['cik']}/{acc}/"
    page = get(f"{base}{e['accession']}-index.html").decode("utf-8", "replace")
    for row in re.findall(r"(?is)<tr[^>]*>.*?</tr>", page):
        if re.search(r">\s*EX-99\.1\s*<", row):
            m = re.search(r'href="([^"]+\.(?:htm|html|txt))"', row, re.I)
            if m:
                href = m.group(1).replace("/ix?doc=", "")
                return "https://www.sec.gov" + href if href.startswith("/") else base + href
    return None


def texts(limit: int | None) -> None:
    sample = os.path.join(DATA, "sample.jsonl")  # fetch only sampled events when a sample exists
    path = sample if os.path.exists(sample) else os.path.join(DATA, "events.jsonl")
    evs = [json.loads(l) for l in open(path)]
    os.makedirs(os.path.join(DATA, "text"), exist_ok=True)
    ok = missing = failed = 0
    for e in evs[:limit]:
        dest = os.path.join(DATA, "text", e["accession"] + ".txt")
        if os.path.exists(dest):
            ok += 1
            continue
        try:
            url = exhibit_url(e)
            if not url:
                missing += 1
                continue
            text = strip_html(get(url).decode("utf-8", "replace"))
        except (urllib.error.URLError, TimeoutError) as ex:  # counted and reported; a rerun picks it up from the cache
            failed += 1
            print(f"  fetch failed {e['ticker']} {e['accession']}: {ex!r}")
            continue
        open(dest, "w").write(text)
        ok += 1
    print(f"exhibit text: {ok} saved, {missing} without an EX-99.1, {failed} fetch failures (of {len(evs[:limit])})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["events", "text"])
    ap.add_argument("--sample", type=int, default=1100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    events(a.sample, a.seed) if a.cmd == "events" else texts(a.limit)
