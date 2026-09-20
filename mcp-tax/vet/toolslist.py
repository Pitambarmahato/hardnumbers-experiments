import json, os, subprocess, sys, time, threading, queue
S = os.getcwd()
N = lambda n, b: f"{S}/servers/npm_{n}/node_modules/.bin/{b}"
P = lambda n, b: f"{S}/servers/py_{n}/bin/{b}"
SERVERS = {
 "filesystem":[[N("_modelcontextprotocol_server-filesystem","mcp-server-filesystem"), f"{S}/fsroot"],{}],
 "memory":[[N("_modelcontextprotocol_server-memory","mcp-server-memory")],{"MEMORY_FILE_PATH":f"{S}/work/memory.json"}],
 "sequential-thinking":[[N("_modelcontextprotocol_server-sequential-thinking","mcp-server-sequential-thinking")],{}],
 "everything":[[N("_modelcontextprotocol_server-everything","mcp-server-everything"),"stdio"],{}],
 "playwright":[[N("_playwright_mcp","playwright-mcp")],{}],
 "chrome-devtools":[[N("chrome-devtools-mcp","chrome-devtools-mcp"),"--no-usage-statistics","--no-performance-crux"],{"CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS":"1"}],
 "context7":[[N("_upstash_context7-mcp","context7-mcp"),"--transport","stdio"],{}],
 "fetch":[[P("mcp-server-fetch","mcp-server-fetch")],{}],
 "time":[[P("mcp-server-time","mcp-server-time")],{}],
 "git":[[P("mcp-server-git","mcp-server-git"),"--repository",f"{S}/work/repo"],{}],
}
def rpc(p, q, i, method, params=None, timeout=90):
    msg = {"jsonrpc":"2.0","method":method}
    if i is not None: msg["id"] = i
    if params is not None: msg["params"] = params
    p.stdin.write((json.dumps(msg)+"\n").encode()); p.stdin.flush()
    if i is None: return None
    end = time.time()+timeout
    while time.time() < end:
        try: line = q.get(timeout=1)
        except queue.Empty: continue
        try: d = json.loads(line)
        except Exception: continue
        if d.get("id") == i: return d
    raise TimeoutError(method)
results = {}
only = sys.argv[1:] or list(SERVERS)
for name in only:
    cmd, extra = SERVERS[name]
    env = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], **extra}
    t0 = time.time()
    p = subprocess.Popen(["sandbox-exec","-f",f"{S}/sandbox.sb",*cmd], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=f"{S}/work")
    q = queue.Queue(); threading.Thread(target=lambda: [q.put(l) for l in p.stdout], daemon=True).start()
    err = []; threading.Thread(target=lambda: [err.append(l.decode(errors="ignore")) for l in p.stderr], daemon=True).start()
    try:
        init = rpc(p, q, 1, "initialize", {"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"mcp-tax-probe","version":"0"}})
        rpc(p, q, None, "notifications/initialized")
        tools, cur, k = [], None, 2
        while True:
            r = rpc(p, q, k, "tools/list", {"cursor":cur} if cur else {}); k += 1
            tools += r["result"]["tools"]; cur = r["result"].get("nextCursor")
            if not cur: break
        res = init["result"]
        results[name] = {"ok":True,"server":res.get("serverInfo"),"protocol":res.get("protocolVersion"),
            "instructions_chars":len(res.get("instructions") or ""),"tool_count":len(tools),
            "tools_json_chars":len(json.dumps(tools,separators=(",",":"))),"tool_names":[t["name"] for t in tools],
            "startup_s":round(time.time()-t0,1)}
        print(f"OK   {name:20} tools={len(tools):3} json_chars={results[name]['tools_json_chars']:6} instr_chars={results[name]['instructions_chars']:5} {results[name]['server']} {results[name]['startup_s']}s")
    except Exception as e:
        results[name] = {"ok":False,"error":repr(e),"stderr":"".join(err)[:400]}
        print(f"FAIL {name:20} {e!r} | stderr: {''.join(err)[:300]}")
    finally:
        p.kill()
json.dump(results, open("toolslist.json","w"), indent=1)
