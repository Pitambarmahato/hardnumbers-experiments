"""Render the article cover from results/full: attempts per second in the hot-room test (S2), per variant, with double bookings and deadlocks.
Output: cover.html -> cover.png (2752x1536). Usage: python3 make_cover.py [out.png]"""
import json, glob, os, statistics as st, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
def med(sc, v, key):
    return st.median(json.load(open(f))[key] for f in glob.glob(f"{here}/results/full/{sc}-{v}-r[0-9].json"))  # not r*: "exclusion-r*" also matches exclusion-retry
V = [("naive", "plain check", "#ff5d5d"), ("pessimistic", "FOR UPDATE", "#34d399"), ("optimistic", "version column", "#60a5fa"),
     ("exclusion", "exclusion constraint", "#fbbf24"), ("exclusion-retry", "exclusion + retry", "#f59e0b")]
H, top = 200, max(med("s2", v, "throughput_per_s") for v, _, _ in V)
groups = ""
for v, name, c in V:
    rate, dbl, dl = med("s2", v, "throughput_per_s"), med("s2", v, "double_bookings"), med("s2", v, "pg_deadlocks")
    note = f"{dbl:.0f} double" if dbl else (f"{dl:.0f} deadlocks" if dl else "0 double")
    groups += (f'<div class="grp"><div class="val">{rate:,.0f}/s</div><div class="bars"><div class="b" style="height:{max(3, rate/top*H):.0f}px;background:{c}"></div></div>'
               f'<div class="nm">{name}</div><div class="nt">{note}</div></div>')
big = f"{med('s2', 'exclusion', 'pg_deadlocks'):.0f}"
html = f"""<!doctype html><meta charset=utf-8><style>
html,body{{margin:0;width:1376px;height:768px;background:linear-gradient(160deg,#0d1226,#161b33);font-family:ui-monospace,Menlo,'SF Mono',monospace;color:#cfd8ee;overflow:hidden}}
.wrap{{padding:44px 64px 0 64px}}.brand{{font-size:20px;letter-spacing:.32em;color:#6f7ba0}}
h1{{margin:14px 0 0 0;font-size:37px;line-height:1.05;color:#eef2ff;font-weight:700;max-width:900px}}
.big{{margin-top:16px;display:flex;align-items:baseline;gap:18px}}.n{{font-size:96px;font-weight:800;line-height:1;color:#fbbf24}}
.cap{{font-size:22px;color:#9aa6c8;line-height:1.35}}
.foot{{position:absolute;right:64px;top:50px;font-size:16px;color:#6f7ba0;text-align:right;line-height:1.5}}
.chart{{position:absolute;left:64px;right:64px;bottom:40px;display:flex;gap:28px;border-bottom:1px solid #2a3355}}
.grp{{flex:1;text-align:center}}.bars{{display:flex;align-items:flex-end;justify-content:center;height:{H}px}}
.b{{width:110px;border-radius:4px 4px 0 0}}.val{{font-size:19px;color:#eef2ff;font-weight:700;margin-bottom:6px}}
.nm{{margin-top:10px;font-size:17px;color:#cfd8ee}}.nt{{margin:2px 0 10px;font-size:16px;color:#9aa6c8}}
</style><div class=wrap><div class=brand>HARD NUMBERS</div><h1>SELECT FOR UPDATE vs Exclusion Constraint</h1>
<div class=big><div class=n>{big}</div><div class=cap>deadlocks per run when overlapping inserts<br>hit an exclusion constraint on hot rooms</div></div></div>
<div class=foot>45 runs · Postgres 16.4<br>truth = audit over the table<br>bars: attempts/s, 10 hot rooms</div>
<div class=chart>{groups}</div>"""
open(f"{here}/cover.html", "w").write(html)
out = sys.argv[1] if len(sys.argv) > 1 else f"{here}/cover.png"
subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                "--window-size=1376,768", f"--screenshot={out}", "file://" + f"{here}/cover.html"], capture_output=True, timeout=90)
print("wrote", out)
