"""Formal analysis for the MCP tax experiment. Reads results/results.jsonl + servers.json."""
import json, statistics as st
rows = [json.loads(l) for l in open("results/results.jsonl") if json.loads(l)["label"] != "warmup_discard"]
T = {(r["config"], r["mode"]): r["total_context"] for r in rows}
runs = {}
for r in rows: runs.setdefault((r["config"], r["mode"]), []).append(r["total_context"])
srv = {s["name"]: s for s in json.load(open("servers.json"))["servers"]}
bd, bf = T[("empty","default")], T[("empty","false")]
D = {n: T[(n,"default")] - bd for n in srv}; F = {n: T[(n,"false")] - bf for n in srv}
out = {"baseline_default": bd, "baseline_off": bf, "zero_mcp_gap": bf - bd,
       "runs_identical": all(len(set(v)) == 1 for v in runs.values()), "config_modes": len(runs),
       "total_runs": len(rows)}
# --- H1
small = [n for n in srv if srv[n]["tool_count"] < 10]
out["H1"] = {"max_default_delta_servers_lt10_tools": max(D[n] for n in small), "server": max(small, key=lambda n: D[n]),
             "all_lt_1000": all(D[n] < 1000 for n in small),
             "tokens_per_tool_no_instructions": {n: round(D[n]/srv[n]["tool_count"],1) for n in srv if srv[n]["instructions_chars"] == 0}}
pt = list(out["H1"]["tokens_per_tool_no_instructions"].values())
out["H1"]["per_tool_range"] = [min(pt), max(pt)]; out["H1"]["per_tool_median"] = st.median(pt)
# --- H2
out["H2"] = {"gap": bf - bd, "meets_ge_10000": bf - bd >= 10000, "off_baseline_runs": runs[("empty","false")], "default_baseline_runs": runs[("empty","default")]}
# --- H3
ratio = {n: F[n]/D[n] for n in srv}
out["H3"] = {"ratio": {n: round(v,1) for n, v in ratio.items()}, "n_ge_10x": sum(v >= 10 for v in ratio.values()), "falsified_as_written": not all(v >= 10 for v in ratio.values()),
             "below_10x": [n for n, v in ratio.items() if v < 10]}
# --- H4
stacks = {"stack2":["filesystem","memory"],"stack5":["filesystem","memory","git","time","fetch"],"stack2_big":["playwright","chrome-devtools"],"stack10":list(srv)}
h4 = {}
for s, mem in stacks.items():
    for m, b, X in (("default", bd, D), ("false", bf, F)):
        meas = T[(s,m)] - b; exp = sum(X[x] for x in mem); h4[f"{s}/{m}"] = {"measured": meas, "sum_of_singles": exp, "diff": meas-exp, "pct": round((meas/exp-1)*100, 2)}
out["H4"] = {"per_stack": h4, "all_within_5pct": all(abs(v["pct"]) <= 5 for v in h4.values()), "worst_pct": min(v["pct"] for v in h4.values())}
# --- cost model, default mode: delta = a*tools + b*instr_chars (least squares, no intercept)
def lstsq2(X1, X2, y):
    s11=sum(a*a for a in X1); s22=sum(b*b for b in X2); s12=sum(a*b for a,b in zip(X1,X2)); r1=sum(a*c for a,c in zip(X1,y)); r2=sum(b*c for b,c in zip(X2,y))
    det=s11*s22-s12*s12; return ((r1*s22-r2*s12)/det, (s11*r2-s12*r1)/det)
names = list(srv); tools = [srv[n]["tool_count"] for n in names]; ins = [srv[n]["instructions_chars"] for n in names]; y = [D[n] for n in names]
a, b = lstsq2(tools, ins, y); pred = [a*t+b*i for t,i in zip(tools,ins)]
ss_res = sum((p-v)**2 for p,v in zip(pred,y)); ss_tot = sum((v-st.mean(y))**2 for v in y)
out["model_default"] = {"tokens_per_tool": round(a,2), "tokens_per_instruction_char": round(b,3), "r2": round(1-ss_res/ss_tot,4),
                        "residuals": {n: round(v-p,1) for n, v, p in zip(names, y, pred)}}
# tools-only fit for comparison
a1 = sum(t*v for t,v in zip(tools,y))/sum(t*t for t in tools); pred1=[a1*t for t in tools]
out["model_default"]["r2_tools_only"] = round(1 - sum((p-v)**2 for p,v in zip(pred1,y))/ss_tot, 4)
# off mode: delta = k*json_chars
ch = [srv[n]["tools_json_chars"] for n in names]; yo = [F[n] for n in names]
k = sum(c*v for c,v in zip(ch,yo))/sum(c*c for c in ch); predo=[k*c for c in ch]
ss_o = sum((v-st.mean(yo))**2 for v in yo)
out["model_off"] = {"tokens_per_json_char": round(k,3), "chars_per_token": round(1/k,2), "r2_chars": round(1-sum((p-v)**2 for p,v in zip(predo,yo))/ss_o,4)}
kt = sum(t*v for t,v in zip(tools,yo))/sum(t*t for t in tools)
out["model_off"]["tokens_per_tool"] = round(kt,1); out["model_off"]["r2_tools"] = round(1-sum((kt*t-v)**2 for t,v in zip(tools,yo))/ss_o,4)
out["model_off"]["chars_per_token_by_server"] = {n: round(srv[n]["tools_json_chars"]/F[n],2) for n in names}
# built-in share
sd, sf = T[("stack10","default")], T[("stack10","false")]
out["built_in_share_stack10"] = {"default_total": sd, "off_total": sf, "tool_search_saves": sf-sd, "built_in_part": bf-bd, "mcp_part": (sf-bf)-(sd-bd), "built_in_pct": round((bf-bd)/(sf-sd)*100,1)}
out["stack10_total_tools"] = sum(tools)
out["per_server"] = {n: {"tools": srv[n]["tool_count"], "json_chars": srv[n]["tools_json_chars"], "instr_chars": srv[n]["instructions_chars"], "default_delta": D[n], "off_delta": F[n]} for n in names}
json.dump(out, open("results/analysis.json","w"), indent=1)
print(json.dumps({k: out[k] for k in ("H1","H2","H3","H4","model_default","model_off","built_in_share_stack10")}, indent=1))
