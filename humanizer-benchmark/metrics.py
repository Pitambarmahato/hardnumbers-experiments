import json, re, statistics as st
from inputs import INPUTS
W2N={w:str(i) for i,w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
def nums(t):
    t=t.lower()
    t=re.sub(r"\b("+"|".join(W2N)+r")\b",lambda m:W2N[m.group(1)],t)
    t=re.sub(r"(?<=\d),(?=\d{3})","",t)
    t=re.sub(r"(\d+)k\b",lambda m:str(int(m.group(1))*1000),t)
    return set(re.findall(r"\d+(?:\.\d+)?",t))
AI=r"\b(delve|leverag\w*|tapestry|pivotal|testament|landscape|seamless\w*|robust|crucial|vital|underscore\w*|showcas\w*|foster\w*|intricate|vibrant|realm|navigat\w*|journey|game-?chang\w*|transformative|elevate|streamlin\w*|empower\w*|cutting-edge|comprehensive|ensur\w*)\b"
def tells(t):
    w=len(t.split()) or 1
    paras=[p for p in t.split("\n\n") if p.strip()]
    d={}
    d["emdash"]=t.count("—")+t.count(" – ")
    d["not_x_but_y"]=len(re.findall(r"\bnot (just|only|merely|simply)\b|\bisn'?t (just|only|about)\b|\bnot (a|an|the)? ?\w+[,;]? (but|it'?s|—)",t,re.I))
    d["triads"]=len(re.findall(r"\b[\w-]+(?: [\w-]+)?, [\w-]+(?: [\w-]+)?,? (?:and|or) [\w-]+",t))
    d["ai_words"]=len(re.findall(AI,t,re.I))
    d["bold"]=t.count("**")//2
    d["curly"]=sum(t.count(c) for c in "“”’")
    d["closer"]=int(len(paras)>0 and len(paras[-1].split())<=10 and len(paras)>1)
    d["staged"]=len(re.findall(r"\b(in this (post|article|guide)|let'?s (dive|explore)|here'?s the thing|the (result|truth|reality)\?)",t,re.I))
    d["total"]=sum(d[k] for k in ("emdash","not_x_but_y","triads","ai_words","bold","curly","closer","staged"))
    d["per100"]=100*d["total"]/w
    return d
def load(id_,c):
    return json.load(open(f"out/{id_}.{c}.json"))["text"]
rows=[]
for id_,g,tp,facts in INPUTS:
    try: raw=load(id_,"raw"); sk=load(id_,"skill"); pl=load(id_,"plain")
    except FileNotFoundError: continue
    fn=nums(facts)
    for c,t in (("raw",raw),("skill",sk),("plain",pl)):
        n=nums(t); tl=tells(t)
        rows.append(dict(id=id_,cond=c,words=len(t.split()),ratio=len(t.split())/len(raw.split()),
          retained=len(fn&n)/len(fn),new_nums=len(n-nums(raw)-fn),**tl))
if __name__=="__main__":
    keys=["words","ratio","per100","emdash","not_x_but_y","triads","ai_words","bold","closer","staged","retained","new_nums"]
    print("n inputs:",len(rows)//3)
    print("cond  "+"  ".join(f"{k:>11}" for k in keys))
    for c in ("raw","skill","plain"):
        rs=[r for r in rows if r["cond"]==c]
        print(f"{c:6}"+"  ".join(f"{st.mean(r[k] for r in rs):11.2f}" for k in keys))
