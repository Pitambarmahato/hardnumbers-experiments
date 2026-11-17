"""Render the article cover from results/full: share of orders charged twice per scenario and variant.
Output: cover.html -> cover.png (2752x1536). Usage: python3 make_cover.py [out.png]"""
import json, glob, os, statistics as st, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
def share(sc, v):
    runs = [json.load(open(f)) for f in glob.glob(f"{here}/results/full/{sc}-{v}-r*.json")]
    return st.median(r["orders_charged_twice_or_more"] / r["meta"]["orders"] for r in runs)
V = [("naive", "naive", "#ff5d5d"), ("idem-local", "key kept local", "#fbbf24"), ("idem-e2e", "key sent to provider", "#34d399")]
S = [("s2", "slow provider"), ("s4", "double click"), ("s3", "crash")]
H, groups = 230, ""
for sc, name in S:
    bars = "".join(f'<div class="bar"><div class="val">{share(sc, v):.0%}</div><div class="b" style="height:{max(3, share(sc, v)*H):.0f}px;background:{c}"></div></div>' for v, _, c in V)
    groups += f'<div class="grp"><div class="bars">{bars}</div><div class="nm">{name}</div></div>'
key = "".join(f'<span class="k" style="background:{c}"></span>{l}<br>' for _, l, c in V)
big = f"{share('s3', 'idem-local'):.0%}"
html = f"""<!doctype html><meta charset=utf-8><style>
html,body{{margin:0;width:1376px;height:768px;background:linear-gradient(160deg,#0d1226,#161b33);font-family:ui-monospace,Menlo,'SF Mono',monospace;color:#cfd8ee;overflow:hidden}}
.wrap{{padding:44px 64px 0 64px}}.brand{{font-size:20px;letter-spacing:.32em;color:#6f7ba0}}
h1{{margin:14px 0 0 0;font-size:39px;line-height:1.05;color:#eef2ff;font-weight:700}}
.big{{margin-top:18px;display:flex;align-items:baseline;gap:18px}}.n{{font-size:96px;font-weight:800;line-height:1;color:#fbbf24}}
.cap{{font-size:22px;color:#9aa6c8;line-height:1.35}}
.foot{{position:absolute;right:64px;top:50px;font-size:16px;color:#6f7ba0;text-align:right;line-height:1.5}}
.key{{position:absolute;right:64px;top:190px;font-size:17px;color:#9aa6c8;text-align:right;line-height:1.9}}
.k{{display:inline-block;width:12px;height:12px;border-radius:2px;margin:0 8px 0 0}}
.chart{{position:absolute;left:64px;right:64px;bottom:44px;display:flex;gap:70px;border-bottom:1px solid #2a3355}}
.grp{{flex:1;text-align:center}}.bars{{display:flex;gap:16px;align-items:flex-end;justify-content:center;height:{H+30}px}}
.bar{{width:90px}}.b{{border-radius:4px 4px 0 0}}.val{{font-size:20px;color:#eef2ff;font-weight:700;margin-bottom:6px}}
.nm{{margin:10px 0;font-size:19px;color:#cfd8ee}}
</style><div class=wrap><div class=brand>HARD NUMBERS</div><h1>Idempotency Key vs Unique Constraint</h1>
<div class=big><div class=n>{big}</div><div class=cap>of orders still charged twice after a crash<br>with a key + unique constraint, key kept local</div></div></div>
<div class=foot>45 runs · mock payment provider<br>truth = provider's own ledger<br>bars: share of orders charged twice</div>
<div class=key>{key}</div><div class=chart>{groups}</div>"""
open(f"{here}/cover.html", "w").write(html)
out = sys.argv[1] if len(sys.argv) > 1 else f"{here}/cover.png"
subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                "--window-size=1376,768", f"--screenshot={out}", "file://" + f"{here}/cover.html"], capture_output=True, timeout=90)
print("wrote", out)
