import json, re, statistics as st, sys
import metrics as M
from inputs import INPUTS
HYPE=r"\b(wow|exciting|excited|thrilled|supercharg\w*|unlock\w*|dive|journey|game-?chang\w*|revolution\w*|amazing|incredible|powerful|effortless\w*|seamless\w*|boost\w*|fly|flies|truly|ultimate|elevate|transform\w*|imagine|buckle|grab a coffee|let'?s be honest)\b"
def tells(t):
    d=M.tells(t); w=len(t.split()) or 1
    d["excl"]=t.count("!"); d["hype"]=len(re.findall(HYPE,t,re.I))
    d["total"]+=d["excl"]+d["hype"]; d["per100"]=100*d["total"]/w; return d
def run(d, model):
    rows=[]
    ld=lambda i,c: json.load(open(f"{d}/{i}.{c}.json"))["text"]
    for id_,g,tp,facts in INPUTS:
        raw=ld(id_,"raw"); fn=M.nums(facts)
        for c,t in (("raw",raw),("skill",ld(id_,f"skill.{model}")),("plain",ld(id_,f"plain.{model}"))):
            n=M.nums(t); tl=tells(t)
            rows.append(dict(cond=c,words=len(t.split()),ratio=len(t.split())/len(raw.split()),retained=len(fn&n)/len(fn),**tl))
    return rows
if __name__=="__main__":
    d,model=sys.argv[1],sys.argv[2]; rows=run(d,model)
    keys=["words","ratio","per100","excl","hype","emdash","not_x_but_y","triads","ai_words","bold","closer","staged","retained"]
    print(f"[{d} / rewriter={model}]"); print("cond  "+" ".join(f"{k:>9}" for k in keys))
    for c in ("raw","skill","plain"):
        rs=[r for r in rows if r["cond"]==c]; print(f"{c:6}"+" ".join(f"{st.mean(r[k] for r in rs):9.2f}" for k in keys))
