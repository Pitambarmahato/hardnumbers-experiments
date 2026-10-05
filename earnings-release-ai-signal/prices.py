"""Compute next-session abnormal returns for each earnings event. No Jev, no paid API.

    python3 prices.py fetch     # download daily bars (Yahoo chart endpoint, unofficial) for event tickers + SPY
    python3 prices.py returns   # write data/returns.jsonl from cached bars
    python3 prices.py selftest  # offline checks of the timing rules

Outcome windows (fixed in the plan before data):
  entry = close of the last regular session at or before the filing's acceptance time
  exit  = close of the first session that STARTS after acceptance
  primary    : abnormal = stock return - SPY return over entry-close -> exit-close
  secondary  : same, over the exit session's open -> close (what a reader could still capture)
Acceptance time comes from EDGAR (UTC) and is converted to America/New_York. Raw prices stay in data/ (gitignored):
the feed is unofficial, so it is not redistributed.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
PRICES = os.path.join(DATA, "prices")
NY = ZoneInfo("America/New_York")
OPEN_T, CLOSE_T = dt.time(9, 30), dt.time(16, 0)
MIN_PRICE = 5.0  # entry close filter, fixed in the plan


def fetch_bars(sym: str) -> dict:
    os.makedirs(PRICES, exist_ok=True)
    path = os.path.join(PRICES, sym.replace("/", "_") + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    p1 = int(dt.datetime(2026, 6, 20, tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime(2026, 9, 12, tzinfo=dt.timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.load(r)["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    bars = {}
    for i, t in enumerate(res.get("timestamp") or []):
        o, c = q["open"][i], q["close"][i]
        if o is None or c is None:
            continue
        day = dt.datetime.fromtimestamp(t, NY).strftime("%Y-%m-%d")
        bars[day] = {"o": o, "c": c}
    json.dump(bars, open(path, "w"))
    time.sleep(0.5)  # at most ~2 requests/second
    return bars


def windows(accepted_utc: str, days: list[str]) -> tuple[str, str] | None:
    """Return (entry_day, exit_day) trading dates from an EDGAR acceptance time and sorted trading days."""
    t = dt.datetime.strptime(accepted_utc.replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=dt.timezone.utc).astimezone(NY)
    d = t.strftime("%Y-%m-%d")
    is_day = d in days
    if is_day and t.time() >= CLOSE_T:
        entry = d                                     # accepted after the close: that day's close is the last one
    else:
        prev = [x for x in days if x < d]             # before the open, during the session, or a non-trading day
        entry = prev[-1] if prev else None
    if is_day and t.time() < OPEN_T:
        exit_ = d                                     # accepted before the open: today's session starts after acceptance
    else:
        nxt = [x for x in days if x > d]
        exit_ = nxt[0] if nxt else None
    return (entry, exit_) if entry and exit_ else None


def build_returns() -> None:
    evs = [json.loads(l) for l in open(os.path.join(DATA, "events.jsonl"))]
    spy = fetch_bars("SPY")
    spy_days = sorted(spy)
    out, drop = [], {}
    def skip(why: str) -> None:
        drop[why] = drop.get(why, 0) + 1
    for e in evs:
        try:
            bars = fetch_bars(e["ticker"])
        except Exception:  # noqa: BLE001 - counted below, never retried blindly
            skip("no price data")
            continue
        w = windows(e["accepted"], sorted(set(bars) & set(spy_days)))
        if not w:
            skip("no window")
            continue
        entry, ex = w
        if bars[entry]["c"] < MIN_PRICE:
            skip(f"entry close < ${MIN_PRICE:g}")
            continue
        r = bars[ex]["c"] / bars[entry]["c"] - 1
        m = spy[ex]["c"] / spy[entry]["c"] - 1
        ro = bars[ex]["c"] / bars[ex]["o"] - 1
        mo = spy[ex]["c"] / spy[ex]["o"] - 1
        out.append({"accession": e["accession"], "ticker": e["ticker"], "accepted": e["accepted"], "entry": entry,
                    "exit": ex, "ret": r, "spy": m, "abn": r - m, "abn_oc": ro - mo})
    with open(os.path.join(DATA, "returns.jsonl"), "w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    print(f"{len(out)} events with returns of {len(evs)}; dropped: {drop}")


def selftest() -> None:
    days = ["2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03"]
    cases = {
        "after close Thu 20:30 ET -> entry Thu, exit Fri": ("2026-07-31T00:30:28.000Z", ("2026-07-30", "2026-07-31")),
        "before open Fri 07:00 ET -> entry Thu, exit Fri": ("2026-07-31T11:00:00.000Z", ("2026-07-30", "2026-07-31")),
        "during session Thu 12:00 ET -> entry Wed, exit Fri": ("2026-07-30T16:00:00.000Z", ("2026-07-29", "2026-07-31")),
        "after close Fri -> entry Fri, exit Mon": ("2026-07-31T21:00:00.000Z", ("2026-07-31", "2026-08-03")),
        "Saturday -> entry Fri, exit Mon": ("2026-08-01T15:00:00.000Z", ("2026-07-31", "2026-08-03")),
    }
    ok = True
    for name, (ts, want) in cases.items():
        got = windows(ts, days)
        ok &= got == want
        print(f"  {'PASS' if got == want else 'FAIL'}  {name}: {got}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "fetch":
        evs = [json.loads(l) for l in open(os.path.join(DATA, "events.jsonl"))]
        syms = ["SPY"] + sorted({e["ticker"] for e in evs})
        bad = 0
        for s in syms:
            try:
                fetch_bars(s)
            except Exception as ex:  # noqa: BLE001
                bad += 1
                print(f"  no data {s}: {ex!r}")
        print(f"fetched {len(syms) - bad}/{len(syms)} symbols")
    elif cmd == "returns":
        build_returns()
    else:
        sys.exit(__doc__)
