import json, subprocess, sys, os, concurrent.futures as cf
from inputs import INPUTS
def call(prompt, skill=False, model=None, system=None):
    cmd = ["claude","-p",prompt,"--no-session-persistence","--output-format","json"]
    if model: cmd += ["--model",model]
    if skill: cmd += ["--setting-sources","project","--tools","Skill"]
    else: cmd += ["--setting-sources","","--tools","","--disable-slash-commands"]
    for _ in range(3):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        try:
            j = json.loads(r.stdout); return j["result"], j.get("total_cost_usd",0), j
        except Exception: pass
    raise RuntimeError(r.stderr[:300])
HARD = "Write a {g} of about 180 words about {t}. Use these facts: {f}. Write it in the voice of a typical enthusiastic AI chatbot or marketing copywriter. Output only the text."
def gen(i):
    return call(HARD.format(g=i[1],t=i[2],f=i[3]), model="haiku")
def cond(a):
    id_,c,draft,model,d = a
    if c=="skill": return call(f"/humanizer Return only the final humanized version, no critique or notes.\n\n{draft}", skill=True, model=model)
    return call(f"Rewrite this so it does not sound AI-written. Keep every fact. Return only the rewritten text.\n\n{draft}", model=model)
if __name__=="__main__":
    stage, d = sys.argv[1], sys.argv[2]; os.makedirs(d, exist_ok=True)
    if stage=="gen":
        with cf.ThreadPoolExecutor(4) as ex:
            for i,(res,cost,_) in zip(INPUTS, ex.map(gen, INPUTS)):
                json.dump({"id":i[0],"text":res,"cost":cost}, open(f"{d}/{i[0]}.raw.json","w")); print(i[0],len(res.split()),flush=True)
    else:
        model=sys.argv[3]; jobs=[(i[0],c,json.load(open(f"{d}/{i[0]}.raw.json"))["text"],model,d) for i in INPUTS for c in ("skill","plain")]
        with cf.ThreadPoolExecutor(4) as ex:
            for j,(res,cost,full) in zip(jobs, ex.map(cond, jobs)):
                json.dump({"id":j[0],"cond":j[1],"text":res,"cost":cost}, open(f"{d}/{j[0]}.{j[1]}.{model}.json","w")); print(j[0],j[1],model,len(res.split()),flush=True)
