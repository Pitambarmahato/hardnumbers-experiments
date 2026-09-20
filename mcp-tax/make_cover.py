"""Render the MCP-tax article cover from analysis.json. Output: cover.html -> cover.png (2752x1536)."""
import json, subprocess, sys
A = json.load(open(sys.argv[1])); ps = A["per_server"]
order = sorted(ps, key=lambda n: ps[n]["tools"])
on_total = sum(v["default_delta"] for v in ps.values()); off_total = sum(v["off_delta"] for v in ps.values())
stack_on = A["built_in_share_stack10"]["default_total"] - A["baseline_default"]; stack_off = A["built_in_share_stack10"]["off_total"] - A["baseline_off"]
H = 250; mx = max(v["off_delta"] for v in ps.values())
cols = ""
for n in order:
    v = ps[n]; ho = max(2, v["off_delta"]/mx*H); hd = max(2, v["default_delta"]/mx*H)
    cols += f'<div class="col"><div class="bars"><div class="b bon" style="height:{hd:.1f}px"></div><div class="b boff" style="height:{ho:.1f}px"></div></div><div class="nm">{n.replace("sequential-thinking","seq-thinking").replace("chrome-devtools","chrome-dt")}</div><div class="tl">{v["tools"]} {"tool" if v["tools"]==1 else "tools"}</div></div>'
html = f"""<!doctype html><meta charset=utf-8><style>
html,body{{margin:0;width:1376px;height:768px;background:linear-gradient(160deg,#0d1226,#161b33);font-family:ui-monospace,Menlo,'SF Mono',monospace;color:#cfd8ee;overflow:hidden}}
.wrap{{padding:44px 64px 0 64px}}
.brand{{font-size:20px;letter-spacing:.32em;color:#6f7ba0}}
h1{{margin:14px 0 0 0;font-size:54px;line-height:1.05;letter-spacing:-.01em;color:#eef2ff;font-weight:700}}
.big{{margin-top:22px;display:flex;align-items:baseline;gap:22px}}
.n{{font-size:112px;font-weight:800;line-height:1;letter-spacing:-.03em}}
.n.on{{color:#4cc9f0}}.n.off{{color:#f5a623}}.vs{{font-size:34px;color:#6f7ba0}}
.cap{{font-size:22px;color:#9aa6c8;margin-top:8px}}
.leg{{margin-top:6px;font-size:20px;display:flex;gap:34px}}
.leg i{{display:inline-block;width:14px;height:14px;margin-right:9px;border-radius:2px}}
.chart{{position:absolute;left:64px;right:64px;bottom:64px;height:{H+62}px;display:flex;gap:14px;align-items:flex-end;border-bottom:1px solid #2a3355}}
.col{{flex:1;text-align:center}}.bars{{display:flex;gap:4px;align-items:flex-end;justify-content:center;height:{H}px}}
.b{{width:20px;border-radius:2px 2px 0 0}}.bon{{background:#4cc9f0}}.boff{{background:#f5a623}}
.nm{{margin-top:8px;font-size:15px;color:#cfd8ee}}.tl{{font-size:13px;color:#6f7ba0;margin-bottom:10px}}
.foot{{position:absolute;right:64px;top:50px;font-size:16px;color:#6f7ba0;text-align:right;line-height:1.5}}
</style><div class=wrap><div class=brand>HARD NUMBERS</div><h1>MCP server token cost<br>in Claude Code</h1>
<div class=big><div class="n on">{stack_on:,}</div><div class=vs>vs</div><div class="n off">{stack_off:,}</div></div>
<div class=cap>tokens added by 10 MCP servers (108 tools)</div>
<div class=leg><span><i style="background:#4cc9f0"></i>tool search on (default)</span><span><i style="background:#f5a623"></i>tool search off</span></div></div>
<div class=foot>per-server cost<br>Claude Code 2.1.278<br>83 runs · 10 servers</div>
<div class=chart>{cols}</div>"""
open("cover.html", "w").write(html)
subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                "--window-size=1376,768", "--screenshot=cover.png", "file://" + __import__("os").path.abspath("cover.html")], capture_output=True, timeout=90)
