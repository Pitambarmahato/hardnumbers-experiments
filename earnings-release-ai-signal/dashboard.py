"""Read-only dashboard: writes one self-contained dashboard.html from the saved results. Research, not advice.

    python3 dashboard.py                    # tone calls per earnings release, no outcome columns
    python3 dashboard.py --with-outcomes    # adds the realised abnormal return (use ONLY after analyze.py has run)

No network calls, no order code, no broker. It reads data/sample.jsonl, data/text/ and results/results.jsonl, and shows
results/analysis.json as the "How well did it work?" panel if that file exists.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import re
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RES = os.path.join(HERE, "results")
ARMS = [("jev", "Jev"), ("qwen2.5-7b", "Local 7B"), ("rules", "Keyword rules")]
MIN_TEXT_CHARS = 500  # same exclusion rule as analyze.py


def read(path: str) -> list[dict]:
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


CONTACT = re.compile(r"@|\d{3}[\s.\-)]+\d{3}[\s.\-]+\d{4}|(?i:\b(investor relations|media contact|contact|press contact|www\.|http)\b)")
RESULTS = re.compile(r"(?i)\b(reports?|announces?|results|quarter|fiscal|earnings)\b")


def headline(text: str) -> str:
    """First line that reads like a title: not boilerplate, not contact details (no emails, phones or names of PR people)."""
    lines = [l.strip() for l in text.splitlines()[:40]]
    ok = [l for l in lines if len(l) >= 25 and not CONTACT.search(l) and not re.match(r"(?i)^(exhibit|document|for immediate release|news release)\b", l)]
    for l in ok:
        if RESULTS.search(l):
            return l[:140]
    return (ok[0] if ok else "(headline not found)")[:140]


def esc(s) -> str:
    return html.escape(str(s))


def pill(r: dict | None) -> str:
    if not r:
        return '<span class="pill none">not run</span>'
    conf = r.get("confidence")
    bar = f'<span class="bar"><i style="width:{round(conf * 100)}%"></i></span>' if conf is not None else ""
    return f'<span class="pill {esc(r["label"])}">{esc(r["label"])}</span>{bar}'


def build(with_outcomes: bool) -> str:
    sample = read(os.path.join(DATA, "sample.jsonl"))
    rows = read(os.path.join(RES, "results.jsonl"))
    by: dict[tuple[str, str], dict] = {}
    for r in rows:
        if r.get("rep", 1) == 1:
            by[(r["arm"], r["accession"])] = r
    analysis = os.path.join(RES, "analysis.json")
    stats = json.load(open(analysis))["abn"] if os.path.exists(analysis) else None
    spend = json.load(open(os.path.join(RES, "spend.json"))) if os.path.exists(os.path.join(RES, "spend.json")) else {}
    out = []
    for e in sample:
        tp = os.path.join(DATA, "text", e["accession"] + ".txt")
        if not os.path.exists(tp):
            continue
        txt = open(tp).read()
        if len(txt) < MIN_TEXT_CHARS:
            continue
        calls = {a: by.get((a, e["accession"])) for a, _ in ARMS}
        labels = [c["label"] for c in calls.values() if c]
        agree = "all agree" if len(labels) > 1 and len(set(labels)) == 1 else ("split" if len(set(labels)) > 1 else "")
        t = datetime.datetime.strptime(e["accepted"].replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=datetime.timezone.utc).astimezone(ZoneInfo("America/New_York"))
        link = f"https://www.sec.gov/Archives/edgar/data/{e['cik']}/{e['accession'].replace('-', '')}/{e['accession']}-index.html"
        cells = "".join(f"<td>{pill(calls[a])}</td>" for a, _ in ARMS)
        outc = f'<td class="num">{e["abn"] * 100:+.2f}%</td>' if with_outcomes else ""
        out.append(f'<tr data-q="{esc((e["ticker"] + " " + e["name"] + " " + headline(txt)).lower())}" data-agree="{esc(agree)}">'
                   f'<td><b>{esc(e["ticker"])}</b><br><small>{esc(e["name"])}</small></td>'
                   f'<td><small>{t:%b %d, %H:%M} ET</small></td><td class="hl">{esc(headline(txt))}<br>'
                   f'<a href="{esc(link)}" target="_blank" rel="noopener">SEC filing</a></td>{cells}<td><small>{esc(agree)}</small></td>{outc}</tr>')
    head = "".join(f"<th>{esc(n)}</th>" for _, n in ARMS)
    panel = ""
    if stats and stats.get("arms"):
        items = []
        for arm, label in ARMS + [("always_up", "Always up")]:
            s = stats["arms"].get(arm)
            if s and s["hit_rate"] is not None:
                lo, hi = s["wilson95"]
                items.append(f'<li><b>{esc(label)}</b>: {s["hit_rate"] * 100:.1f}% of {s["non_neutral"]} non-neutral calls matched the next-session direction '
                             f'(95% interval {lo * 100:.0f}-{hi * 100:.0f}%).</li>')
        oc = json.load(open(analysis))["abn_oc"]["arms"]
        after = "; ".join(f'{lab} {oc[a]["hit_rate"] * 100:.1f}%' for a, lab in ARMS if oc.get(a) and oc[a]["hit_rate"] is not None)
        items.append(f'<li><b>After the open</b> (next session, open to close): no arm beat chance ({esc(after)}). Whatever the models read was already in the price by the open.</li>')
        panel = f'<section class="card"><h2>How well did it work?</h2><ul>{"".join(items)}</ul><p class="note">First four lines: prior close to next close. One earnings season; no costs, no slippage. See the article for the full method and limits.</p></section>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Earnings Tone Board</title><style>
:root{{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--card:#fff;--line:#e7e5e4;--bull:#15803d;--bear:#b91c1c;--neu:#78716c;--acc:#2563eb}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0c0a09;--fg:#e7e5e4;--mut:#a8a29e;--card:#1c1917;--line:#292524;--bull:#4ade80;--bear:#f87171;--neu:#a8a29e;--acc:#60a5fa}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px}}h1{{font-size:1.5rem;margin:0 0 4px}}.sub{{color:var(--mut);margin:0 0 16px}}
.warn{{border:1px solid var(--bear);border-radius:8px;padding:10px 14px;margin:0 0 16px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:0 0 16px}}
.card h2{{font-size:1rem;margin:0 0 6px}}.note{{color:var(--mut);font-size:.85rem}}input{{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);margin:0 0 8px}}
.wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px}}th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{font-size:.8rem;color:var(--mut);position:sticky;top:0;background:var(--card)}}.hl{{min-width:260px}}.num{{font-variant-numeric:tabular-nums}}small{{color:var(--mut)}}a{{color:var(--acc)}}
.pill{{display:inline-block;padding:1px 8px;border-radius:99px;font-size:.8rem;border:1px solid currentColor}}.bullish{{color:var(--bull)}}.bearish{{color:var(--bear)}}.neutral,.none{{color:var(--neu)}}
.bar{{display:block;height:4px;width:60px;background:var(--line);border-radius:2px;margin-top:4px}}.bar i{{display:block;height:100%;background:var(--acc);border-radius:2px}}
</style></head><body><main>
<h1>Earnings Tone Board</h1><p class="sub">{len(out)} earnings releases (SEC 8-K Item 2.02, 2026-07-15 to 2026-08-31). Jev spend for this run: ~${spend.get("usd_est", 0):.3f}.</p>
<div class="warn"><b>Research, not advice.</b> This page shows what each model said about a press release. It does not tell anyone to buy or sell, it has no broker connection, and past results do not predict future returns.</div>
{panel}
<input id="q" type="search" placeholder="Filter by ticker, company or headline"><label><input id="split" type="checkbox" style="width:auto"> only where the arms disagree</label>
<div class="wrap"><table><thead><tr><th>Company</th><th>Filed</th><th>Headline</th>{head}<th>Agreement</th>{"<th>Next-session abnormal return</th>" if with_outcomes else ""}</tr></thead><tbody id="rows">{"".join(out)}</tbody></table></div>
</main><script>const q=document.getElementById('q'),s=document.getElementById('split'),rs=[...document.querySelectorAll('#rows tr')];
function f(){{const t=q.value.toLowerCase();rs.forEach(r=>r.style.display=(!t||r.dataset.q.includes(t))&&(!s.checked||r.dataset.agree==='split')?'':'none')}}q.oninput=f;s.onchange=f;</script></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-outcomes", action="store_true")
    a = ap.parse_args()
    path = os.path.join(HERE, "dashboard.html")
    open(path, "w").write(build(a.with_outcomes))
    print(f"wrote {path} ({os.path.getsize(path) // 1024} KB)")
