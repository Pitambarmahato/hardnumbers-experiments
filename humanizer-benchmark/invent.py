import json, re, sys, concurrent.futures as cf
from inputs import INPUTS
from run2 import call
ld=lambda i,c: json.load(open(f"hard/{i}.{c}.json"))["text"]
def js(res):
    return json.loads(re.search(r"[\{\[].*[\}\]]",res,re.S).group(0))
P1="""Source facts: {facts}
Topic: {topic}

Draft:
{raw}

List every specific factual claim in the draft that is NOT among the source facts and is not trivially implied by them (e.g. named steps, features, causes, outcomes, people, commitments, apologies, audiences). Ignore tone, hype, opinions, greetings, hashtags. JSON only: {{"unsupported":["short claim", ...]}}"""
P2="""Source facts: {facts}

Unsupported claims found in the original draft:
{lst}

Rewrite:
{rw}

JSON only: {{"kept":[indices (0-based) of the listed claims that still appear in the rewrite, even reworded],"new":["specific factual claims in the rewrite that are in neither the source facts nor the listed claims, excluding tone/opinion"]}}"""
def s1(i):
    r,_,_=call(P1.format(facts=i[3],topic=i[2],raw=ld(i[0],"raw")),model="sonnet"); return i[0],js(r)["unsupported"]
with cf.ThreadPoolExecutor(6) as ex: uns=dict(ex.map(s1,INPUTS))
def s2(a):
    i,c=a; lst=uns[i[0]]
    if not lst: return (i[0],c,[],js(call(P2.format(facts=i[3],lst="(none)",rw=ld(i[0],f"{c}.opus")),model="sonnet")[0])["new"])
    r=js(call(P2.format(facts=i[3],lst="\n".join(f"{n}: {x}" for n,x in enumerate(lst)),rw=ld(i[0],f"{c}.opus")),model="sonnet")[0])
    return i[0],c,r["kept"],r["new"]
jobs=[(i,c) for i in INPUTS for c in ("skill","plain")]
with cf.ThreadPoolExecutor(6) as ex: res=list(ex.map(s2,jobs))
json.dump({"unsupported_in_raw":uns,"rewrites":res},open("hard/invent.opus.json","w"))
tot=sum(len(v) for v in uns.values()); print("drafts with >=1 unsupported:",sum(1 for v in uns.values() if v),"/24; total claims",tot)
for c in ("skill","plain"):
    rs=[r for r in res if r[1]==c]
    print(c,"kept",sum(len(r[2]) for r in rs),"of",tot,"| new claims added",sum(len(r[3]) for r in rs),"in",sum(1 for r in rs if r[3]),"texts")
