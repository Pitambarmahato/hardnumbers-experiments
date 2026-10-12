import json, subprocess, sys, os, concurrent.futures as cf
from inputs import INPUTS
os.makedirs("out", exist_ok=True)
def call(prompt, skill=False):
    cmd = ["claude","-p",prompt,"--no-session-persistence","--output-format","json"]
    if skill: cmd += ["--setting-sources","project","--tools","Skill"]
    else: cmd += ["--setting-sources","","--tools","","--disable-slash-commands"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    j = json.loads(r.stdout)
    return j["result"], j.get("total_cost_usd",0), j
def gen(i):
    id_,g,t,f = i
    p = f"Write a {g} of about 180 words about {t}. Use these facts: {f}. Output only the text."
    return call(p)
def cond(args):
    id_, cname, draft = args
    if cname=="skill":
        p = f"/humanizer Return only the final humanized version, no critique or notes.\n\n{draft}"
        return call(p, skill=True)
    p = f"Rewrite this so it does not sound AI-written. Keep every fact. Return only the rewritten text.\n\n{draft}"
    return call(p)
if __name__=="__main__":
    stage, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv)>2 else 99
    items = INPUTS[:n]
    if stage=="gen":
        with cf.ThreadPoolExecutor(4) as ex:
            for i,(res,cost,_) in zip(items, ex.map(gen, items)):
                json.dump({"id":i[0],"text":res,"cost":cost}, open(f"out/{i[0]}.raw.json","w"))
                print(i[0], len(res.split()), cost, flush=True)
    else:
        jobs=[]
        for i in items:
            d=json.load(open(f"out/{i[0]}.raw.json"))["text"]
            for c in ("skill","plain"): jobs.append((i[0],c,d))
        with cf.ThreadPoolExecutor(4) as ex:
            for j,(res,cost,full) in zip(jobs, ex.map(cond, jobs)):
                json.dump({"id":j[0],"cond":j[1],"text":res,"cost":cost,"turns":full.get("num_turns"),"denials":full.get("permission_denials")}, open(f"out/{j[0]}.{j[1]}.json","w"))
                print(j[0], j[1], len(res.split()), cost, flush=True)
