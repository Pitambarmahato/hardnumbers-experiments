"""Render the article cover from results/analysis.json. Output: cover.html -> cover.png (2752x1536).

    python3 make_cover.py results/analysis.json

Dot-and-whisker chart: hit rate with its 95% Wilson interval for each arm, in two windows, against the 50% line.
Every plotted number comes from analysis.json; nothing is typed in by hand.
"""
import json
import os
import subprocess
import sys

A = json.load(open(sys.argv[1]))
P, S = A["abn"]["arms"], A["abn_oc"]["arms"]
ARMS = [("jev", "Jev"), ("qwen2.5-7b", "Local 7B"), ("rules", "Keyword rules"), ("always_up", "Always up")]
LO, HI = 0.40, 0.65
X0, X1 = 330, 1250  # plot area in px inside the 1376-wide canvas
STEP = 66           # vertical space per arm
PLOT_TOP = 432


def x(v):
    return X0 + (v - LO) / (HI - LO) * (X1 - X0)


rows = ""
y = 0
for key, name in ARMS:
    rows += f'<div class="lab" style="top:{y + 12}px">{name}</div>'
    for off, (stats, cls) in enumerate(((P[key], "c1"), (S[key], "c2"))):
        lo, hi = stats["wilson95"]
        yy = y + 4 + off * 26
        rows += (f'<div class="w {cls}" style="top:{yy + 7}px;left:{x(lo):.0f}px;width:{x(hi) - x(lo):.0f}px"></div>'
                 f'<div class="d {cls}" style="top:{yy}px;left:{x(stats["hit_rate"]) - 7:.0f}px"></div>'
                 f'<div class="v {cls}" style="top:{yy - 2}px;left:{x(hi) + 12:.0f}px">{stats["hit_rate"] * 100:.1f}%</div>')
    y += STEP
H = y
ticks = "".join(f'<div class="tk" style="left:{x(t / 100):.0f}px"><i></i>{t}%</div>' for t in (40, 45, 50, 55, 60, 65))
j, jo = P["jev"], S["jev"]
html = f"""<!doctype html><meta charset=utf-8><style>
html,body{{margin:0;width:1376px;height:768px;background:linear-gradient(160deg,#0d1226,#161b33);font-family:ui-monospace,Menlo,'SF Mono',monospace;color:#cfd8ee;overflow:hidden;position:relative}}
.brand{{position:absolute;left:64px;top:36px;font-size:20px;letter-spacing:.32em;color:#6f7ba0}}
h1{{position:absolute;left:64px;top:68px;margin:0;font-size:50px;line-height:1.06;letter-spacing:-.01em;color:#eef2ff;font-weight:700}}
.big{{position:absolute;left:64px;top:196px;display:flex;align-items:baseline;gap:20px}}
.n{{font-size:96px;font-weight:800;line-height:1;letter-spacing:-.03em}}.n1{{color:#4cc9f0}}.n2{{color:#f5a623}}.vs{{font-size:28px;color:#6f7ba0}}
.cap{{position:absolute;left:64px;top:312px;font-size:20px;color:#9aa6c8;line-height:1.4}}
.leg{{position:absolute;left:800px;top:222px;font-size:19px;line-height:2}}.leg i{{display:inline-block;width:14px;height:14px;margin-right:10px;border-radius:50%}}
.plot{{position:absolute;left:0;top:{PLOT_TOP}px;width:1376px;height:{H}px}}
.lab{{position:absolute;left:{X0 - 260}px;width:230px;text-align:right;font-size:19px;color:#eef2ff}}
.w{{position:absolute;height:2px}}.d{{position:absolute;width:14px;height:14px;border-radius:50%}}.v{{position:absolute;font-size:16px}}
.w.c1,.d.c1{{background:#4cc9f0}}.w.c2,.d.c2{{background:#f5a623}}.v.c1{{color:#4cc9f0}}.v.c2{{color:#f5a623}}
.base{{position:absolute;left:{x(0.5):.0f}px;top:-6px;height:{H + 6}px;border-left:2px dashed #6f7ba0}}
.axis{{position:absolute;left:0;top:{H + 4}px;width:1376px}}.tk{{position:absolute;top:0;font-size:15px;color:#6f7ba0;transform:translateX(-50%);text-align:center}}.tk i{{display:block;width:1px;height:8px;background:#2a3355;margin:0 auto 4px}}
.foot{{position:absolute;right:64px;top:42px;font-size:16px;color:#6f7ba0;text-align:right;line-height:1.5}}
</style>
<div class=brand>HARD NUMBERS</div><h1>Jev AI vs a local 7B model<br>on 476 earnings releases</h1>
<div class=big><div class="n n1">{j['hit_rate'] * 100:.1f}%</div><div class=vs>then</div><div class="n n2">{jo['hit_rate'] * 100:.1f}%</div></div>
<div class=cap>Jev's hit rate on next-session direction,<br>before the open vs after it</div>
<div class=leg><div><i style="background:#4cc9f0"></i>prior close to next close</div><div><i style="background:#f5a623"></i>next open to next close</div></div>
<div class=foot>hit rate with 95% interval<br>dashed line = 50%<br>one earnings season</div>
<div class=plot><div class=base></div>{rows}<div class=axis>{ticks}</div></div>"""
open("cover.html", "w").write(html)
subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=2", "--window-size=1376,768", "--screenshot=cover.png", "file://" + os.path.abspath("cover.html")],
               capture_output=True, timeout=90)
print("wrote cover.png", os.path.getsize("cover.png") // 1024, "KB")
