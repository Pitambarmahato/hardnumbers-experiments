"""MCP tax runner. usage: python3 run_matrix.py step0 | matrix
Measures context tokens of `claude -p` with one MCP config at a time, in two modes."""
import datetime, json, os, random, subprocess, sys, time
S = os.getcwd(); HOME = os.environ["HOME"]
OUT = "/tmp/hardnumbers-experiments-staging/mcp-tax/results"; os.makedirs(f"{OUT}/raw", exist_ok=True); os.makedirs(f"{S}/cfgs", exist_ok=True)
PATHV = "/usr/bin:/bin:/opt/homebrew/bin"
N = lambda n, b: f"{S}/servers/npm_{n}/node_modules/.bin/{b}"
P = lambda n, b: f"{S}/servers/py_{n}/bin/{b}"
SERVERS = {
 "filesystem":([N("_modelcontextprotocol_server-filesystem","mcp-server-filesystem"), f"{S}/fsroot"],{}),
 "memory":([N("_modelcontextprotocol_server-memory","mcp-server-memory")],{"MEMORY_FILE_PATH":f"{S}/work/memory.json"}),
 "sequential-thinking":([N("_modelcontextprotocol_server-sequential-thinking","mcp-server-sequential-thinking")],{}),
 "everything":([N("_modelcontextprotocol_server-everything","mcp-server-everything"),"stdio"],{}),
 "playwright":([N("_playwright_mcp","playwright-mcp")],{}),
 "chrome-devtools":([N("chrome-devtools-mcp","chrome-devtools-mcp"),"--no-usage-statistics","--no-performance-crux"],{"CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS":"1"}),
 "context7":([N("_upstash_context7-mcp","context7-mcp"),"--transport","stdio"],{}),
 "fetch":([P("mcp-server-fetch","mcp-server-fetch")],{}),
 "time":([P("mcp-server-time","mcp-server-time")],{}),
 "git":([P("mcp-server-git","mcp-server-git"),"--repository",f"{S}/work/repo"],{}),
}
STACKS = {"stack2":["filesystem","memory"], "stack5":["filesystem","memory","git","time","fetch"],
          "stack2_big":["playwright","chrome-devtools"], "stack10":list(SERVERS)}
def cfg_path(name):
    members = [] if name == "empty" else STACKS.get(name, [name])
    servers = {}
    for m in members:
        cmd, extra = SERVERS[m]
        servers[m] = {"command":"sandbox-exec","args":["-f",f"{S}/sandbox.sb","/usr/bin/env","-i",f"PATH={PATH_V}",f"HOME={HOME}",*[f"{k}={v}" for k,v in extra.items()],*cmd]}
    p = f"{S}/cfgs/{name}.json"; json.dump({"mcpServers":servers}, open(p,"w"), indent=1); return p
PATH_V = PATHV
VERSION = subprocess.run(["claude","--version"],capture_output=True,text=True).stdout.strip()
idx = [0]
def call(cfg, mode, rnd, label=None):
    env = dict(os.environ); env.pop("ENABLE_TOOL_SEARCH", None)
    if mode == "false": env["ENABLE_TOOL_SEARCH"] = "false"
    idx[0] += 1; i = idx[0]; t0 = time.time()
    p = subprocess.run(["claude","-p","Reply with the single word: ok","--output-format","json","--strict-mcp-config","--mcp-config",cfg_path(cfg),"--no-session-persistence"],capture_output=True,text=True,env=env,timeout=300)
    d = json.loads(p.stdout); u = d["usage"]
    row = {"i":i,"label":label or "run","config":cfg,"mode":mode,"round":rnd,"ts":datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "input":u["input_tokens"],"cache_creation":u["cache_creation_input_tokens"],"cache_read":u["cache_read_input_tokens"],"output":u["output_tokens"],
           "total_context":u["input_tokens"]+u["cache_creation_input_tokens"]+u["cache_read_input_tokens"],"turns":d["num_turns"],"is_error":d["is_error"],
           "subtype":d["subtype"],"duration_ms":d["duration_ms"],"claude_version":VERSION,"n_members":len(json.load(open(cfg_path(cfg)))["mcpServers"])}
    json.dump(d, open(f"{OUT}/raw/{i:03d}_{cfg}_{mode}_r{rnd}.json","w"))
    open(f"{OUT}/results.jsonl","a").write(json.dumps(row)+"\n")
    print(f"{i:3} {cfg:18} {mode:7} r{rnd} total={row['total_context']:6} turns={row['turns']} {time.time()-t0:4.0f}s {'ERR' if row['is_error'] else ''}", flush=True)
    bad = p.returncode != 0 or row["is_error"] or row["subtype"] != "success" or row["turns"] != 1 or any(w in (p.stderr+p.stdout).lower() for w in ("rate limit","usage limit","quota","limit reached"))
    if bad: print("STOP: abnormal run:", p.stderr[:300], d.get("result","")[:200]); sys.exit(2)
    return row["total_context"]
if sys.argv[1] == "step0":
    call("empty","default",0,"warmup_discard")
    res = {}
    for r in (1,2):
        for cfg in ("empty","filesystem"):
            for mode in ("default","false"): res.setdefault((cfg,mode),[]).append(call(cfg,mode,r,"step0"))
    probe = {("empty","default"):22243,("filesystem","default"):22452,("empty","false"):37211,("filesystem","false"):40164}
    ok = True
    for k,v in res.items():
        dev = (max(v)/probe[k]-1)*100; flag = "OK" if len(set(v))==1 and abs(dev)<1 else "MISMATCH"; ok &= flag=="OK"
        print(f"{k[0]:11} {k[1]:8} runs={v} probe={probe[k]} dev={dev:+.2f}% {flag}")
    for m in ("default","false"): print(f"filesystem delta [{m}]: {res[('filesystem',m)][0]-res[('empty',m)][0]:+d}  (probe: {'+209' if m=='default' else '+2953'})")
    print("STEP0", "PASSED" if ok else "FAILED")
else:
    call("empty","default",0,"warmup_discard")
    singles = ["empty"]+list(SERVERS); rounds = {c:(3 if c in singles else 2) for c in singles+list(STACKS)}
    rnd_rng = random.Random(1)
    for r in (1,2,3):
        todo = [(c,m) for c in rounds if rounds[c] >= r for m in ("default","false")]; rnd_rng.shuffle(todo)
        for c,m in todo: call(c,m,r)
    print("MATRIX DONE")
