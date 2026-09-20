import json, os, subprocess, sys, time
cfg, mode, tag = sys.argv[1], sys.argv[2], sys.argv[3]
env = dict(os.environ)
if mode == "false": env["ENABLE_TOOL_SEARCH"] = "false"
t = time.time()
p = subprocess.run(["claude","-p","Reply with the single word: ok","--output-format","json","--strict-mcp-config","--mcp-config",cfg,"--no-session-persistence"],capture_output=True,text=True,env=env,timeout=400)
open(f"{tag}.json","w").write(p.stdout)
try:
    d = json.loads(p.stdout); u = d["usage"]
    tot = u["input_tokens"]+u["cache_creation_input_tokens"]+u["cache_read_input_tokens"]
    print(f"{tag:14} mode={mode:7} total={tot:6} in={u['input_tokens']} create={u['cache_creation_input_tokens']} read={u['cache_read_input_tokens']} turns={d['num_turns']} err={d['is_error']} {time.time()-t:.0f}s", flush=True)
except Exception as e:
    print(tag, "FAILED", e, p.stdout[:200], p.stderr[:300], flush=True)
