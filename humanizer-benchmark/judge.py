import json, sys, itertools, concurrent.futures as cf, re
from inputs import INPUTS
from run2 import call
d, model = sys.argv[1], sys.argv[2]
ld=lambda i,c: json.load(open(f"{d}/{i}.{c}.json"))["text"]
P="""You are judging two rewrites of the same source text. Source facts that must survive: {facts}

Text A:
{a}

Text B:
{b}

Answer with JSON only, no prose: {{"more_human":"A"|"B","better_overall":"A"|"B","fact_problems_A":<int: facts from the list missing/changed in A plus claims in A that are not in the facts list or common sense restatements>,"fact_problems_B":<int, same for B>}}"""
jobs=[]
for id_,g,tp,facts in INPUTS:
    t={"raw":ld(id_,"raw"),"skill":ld(id_,f"skill.{model}"),"plain":ld(id_,f"plain.{model}")}
    for x,y in (("skill","plain"),("skill","raw"),("plain","raw")):
        jobs.append((id_,x,y,t[x],t[y],facts,False)); jobs.append((id_,y,x,t[y],t[x],facts,True))  # (A-name,B-name) swapped order
def go(j):
    id_,an,bn,a,b,facts,sw=j
    res,_,_=call(P.format(facts=facts,a=a,b=b),model="sonnet")
    m=re.search(r"\{.*\}",res,re.S); r=json.loads(m.group(0))
    return dict(id=id_,A=an,B=bn,**r)
out=[]
with cf.ThreadPoolExecutor(6) as ex:
    for r in ex.map(go,jobs): out.append(r)
json.dump(out,open(f"{d}/judge.{model}.json","w"))
from collections import defaultdict
agg=defaultdict(lambda:[0,0,0,0,0])  # human wins x, wins y, overall x, overall y, n
fp=defaultdict(lambda:defaultdict(list))
for r in out:
    for q in ("more_human","better_overall"): pass
    a,b=r["A"],r["B"]
    for (nm,pa) in ((a,r["fact_problems_A"]),(b,r["fact_problems_B"])): fp[nm]["p"].append(pa)
    pair=tuple(sorted((a,b)))
    for q in ("more_human","better_overall"):
        w=a if r[q]=="A" else b
        agg[(pair,q)][ [0,1][w!=pair[0]] ]+=1
for (pair,q),v in sorted(agg.items()): print(pair,q,f"{pair[0]}={v[0]} {pair[1]}={v[1]}")
print({k:round(sum(v["p"])/len(v["p"]),2) for k,v in fp.items()}, "mean fact_problems per text")
