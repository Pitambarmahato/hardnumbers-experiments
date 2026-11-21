"""Render the article cover from results/full: most allowed in any 1 s span (limit 100), boundary burst S1, per variant.
Output: cover.html -> cover.png (2752x1536). Usage: python3 make_cover.py [out.png]"""
import json, glob, os, statistics as st, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
def med(sc, v, key):
    return st.median(json.load(open(f))[key] for f in glob.glob(f"{here}/results/full/{sc}-{v}-r[0-9].json"))
V = [("naive-fixed", "fixed, 3 calls", "#ff5d5d"), ("fixed", "fixed, 1 script", "#f59e0b"), ("sliding-log", "sliding log", "#34d399"),
     ("sliding-counter", "sliding counter", "#60a5fa"), ("token-bucket", "token bucket", "#a78bfa")]
H = 200
top = max(med("s1", v, "max_sliding") for v, _, _ in V)
groups = ""
for v, name, c in V:
    n = med("s1", v, "max_sliding")
    groups += (f'<div class="grp"><div class="val">{n:.0f}</div><div class="bars"><div class="b" style="height:{n/top*H:.0f}px;background:{c}"></div></div>'
               f'<div class="nm">{name}</div></div>')
limit_y = 100 / top * H
html = f"""<!doctype html><meta charset=utf-8><style>
html,body{{margin:0;width:1376px;height:768px;background:linear-gradient(160deg,#0d1226,#161b33);font-family:ui-monospace,Menlo,'SF Mono',monospace;color:#cfd8ee;overflow:hidden}}
.wrap{{padding:44px 64px 0 64px}}.brand{{font-size:20px;letter-spacing:.32em;color:#6f7ba0}}
h1{{margin:14px 0 0 0;font-size:37px;line-height:1.05;color:#eef2ff;font-weight:700;max-width:900px}}
.big{{margin-top:16px;display:flex;align-items:baseline;gap:18px}}.n{{font-size:96px;font-weight:800;line-height:1;color:#ff5d5d}}
.cap{{font-size:22px;color:#9aa6c8;line-height:1.35}}
.foot{{position:absolute;right:64px;top:50px;font-size:16px;color:#6f7ba0;text-align:right;line-height:1.5}}
.chart{{position:absolute;left:64px;right:64px;bottom:40px;display:flex;gap:28px;border-bottom:1px solid #2a3355}}
.grp{{flex:1;text-align:center}}.bars{{display:flex;align-items:flex-end;justify-content:center;height:{H}px;position:relative}}
.b{{width:110px;border-radius:4px 4px 0 0}}.val{{font-size:19px;color:#eef2ff;font-weight:700;margin-bottom:6px}}
.nm{{margin:10px 0 10px;font-size:17px;color:#cfd8ee}}
.lim{{position:absolute;left:64px;right:64px;bottom:{80 + limit_y:.0f}px;border-top:2px dashed #6f7ba0;color:#9aa6c8;font-size:15px;text-align:right}}
</style><div class=wrap><div class=brand>HARD NUMBERS</div><h1>Rate Limiter: Fixed Window vs Sliding Window vs Token Bucket</h1>
<div class=big><div class=n>200</div><div class=cap>requests let through in one second<br>when the limit is 100 (fixed window, edge burst)</div></div></div>
<div class=foot>45 runs · Redis 8.0<br>truth = decision time of allowed requests<br>bars: most allowed in any 1 s span</div>
<div class=chart>{groups}</div><div class=lim><span style="position:absolute;left:56%;bottom:6px;white-space:nowrap">limit = 100</span></div>"""
open(f"{here}/cover.html", "w").write(html)
out = sys.argv[1] if len(sys.argv) > 1 else f"{here}/cover.png"
subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                "--window-size=1376,768", f"--screenshot={out}", "file://" + f"{here}/cover.html"], capture_output=True, timeout=90)
print("wrote", out)
