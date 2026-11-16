"""Render the article cover from results/online/s2-*.json: lowest cache hit rate after a 4th node joins, per routing scheme.
Output: cover.html -> cover.png (2752x1536). Usage: python3 make_cover.py [out.png]"""
import json, os, statistics as st, sys, glob, subprocess

here = os.path.dirname(os.path.abspath(__file__))
def low(sch):
    v = []
    for f in sorted(glob.glob(f"{here}/results/online/s2-{sch}-r*.json")):
        b = json.load(open(f))["buckets"][10:]; v.append(min(x["hit"] / x["n"] for x in b))
    return st.median(v)
order = [("modn", "mod N"), ("ring1", "ring<br>1 virtual node"), ("ring10", "ring<br>10"), ("ring150", "ring<br>150")]
H, cols = 230, ""
for k, name in order:
    h = low(k); color = "#ff5d5d" if k == "modn" else "#34d399"
    cols += (f'<div class="col"><div class="val">{h:.0%}</div><div class="bars"><div class="b" style="height:{h*H:.1f}px;background:{color}"></div></div>'
             f'<div class="nm">{name}</div></div>')
big = f"{low('modn'):.0%} vs {low('ring150'):.0%}"
html = f"""<!doctype html><meta charset=utf-8><style>
html,body{{margin:0;width:1376px;height:768px;background:linear-gradient(160deg,#0d1226,#161b33);font-family:ui-monospace,Menlo,'SF Mono',monospace;color:#cfd8ee;overflow:hidden}}
.wrap{{padding:44px 64px 0 64px}}
.brand{{font-size:20px;letter-spacing:.32em;color:#6f7ba0}}
h1{{margin:14px 0 0 0;font-size:50px;line-height:1.05;letter-spacing:-.01em;color:#eef2ff;font-weight:700}}
.big{{margin-top:18px;display:flex;align-items:baseline;gap:18px}}
.n{{font-size:96px;font-weight:800;line-height:1;letter-spacing:-.03em;color:#ff5d5d}}
.cap{{font-size:22px;color:#9aa6c8;margin-top:6px;line-height:1.35}}
.foot{{position:absolute;right:64px;top:50px;font-size:16px;color:#6f7ba0;text-align:right;line-height:1.5}}
.chart{{position:absolute;left:64px;right:64px;bottom:50px;height:{H+110}px;display:flex;gap:40px;align-items:flex-end;border-bottom:1px solid #2a3355}}
.col{{flex:1;text-align:center}}
.bars{{display:flex;align-items:flex-end;justify-content:center;height:{H}px}}
.b{{width:130px;border-radius:4px 4px 0 0}}
.val{{font-size:24px;color:#eef2ff;font-weight:700;margin-bottom:8px}}
.nm{{margin-top:10px;font-size:18px;color:#cfd8ee;line-height:1.25;height:48px}}
</style><div class=wrap><div class=brand>HARD NUMBERS</div>
<h1>Consistent Hashing Tested</h1>
<div class=big><div class="n">{big}</div><div class=cap>lowest cache hit rate after a 4th node joins<br>mod N vs ring with 150 virtual nodes</div></div></div>
<div class=foot>100,000 keys · 4 Redis nodes + Postgres<br>3,000 req/s · median of 3 runs<br>bars: lowest 1-second hit rate</div>
<div class=chart>{cols}</div>"""
open(f"{here}/cover.html", "w").write(html)
out = sys.argv[1] if len(sys.argv) > 1 else f"{here}/cover.png"
subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=2", "--window-size=1376,768", f"--screenshot={out}", "file://" + f"{here}/cover.html"], capture_output=True, timeout=90)
print("wrote", out)
