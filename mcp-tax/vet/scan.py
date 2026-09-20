import json, os, re, subprocess, sys, tarfile, zipfile, urllib.request, glob, collections
NPM = {"memory":("@modelcontextprotocol/server-memory","2026.8.31"),
       "sequential-thinking":("@modelcontextprotocol/server-sequential-thinking","2026.8.31"),
       "everything":("@modelcontextprotocol/server-everything","2026.8.31"),
       "playwright":("@playwright/mcp","0.0.82"),
       "chrome-devtools":("chrome-devtools-mcp","1.9.0"),
       "context7":("@upstash/context7-mcp","4.1.1")}
PY = {"fetch":"mcp-server-fetch","time":"mcp-server-time","git":"mcp-server-git"}
PAT = collections.OrderedDict([("proc", r"child_process|\bspawn\(|\bexecSync\(|\bexec\(|subprocess|os\.system|Popen"),
      ("net", r"\bfetch\(|https?\.request|\bhttpx\b|\brequests\.|urlopen|undici|XMLHttpRequest|WebSocket"),
      ("env", r"process\.env|os\.environ|os\.getenv"),
      ("dyn", r"\beval\(|new Function\(|\bexec\(|__import__")])
def scan(root, exts):
    hits = collections.Counter(); urls = collections.Counter(); files = 0; loc = 0
    for dp, dn, fn in os.walk(root):
        if "node_modules" in dp: continue
        for f in fn:
            if f.endswith(exts):
                files += 1
                t = open(os.path.join(dp, f), errors="ignore").read(); loc += t.count("\n")
                for k, p in PAT.items(): hits[k] += len(re.findall(p, t))
                for u in re.findall(r"https?://[A-Za-z0-9.\-]+(?:/[A-Za-z0-9._/\-]*)?", t): urls[u.rstrip('/.')] += 1
    return files, loc, dict(hits), [u for u, _ in urls.most_common(6)]
out = {}
for name, (pkg, ver) in NPM.items():
    subprocess.run(["npm","pack",f"{pkg}@{ver}","--ignore-scripts","--silent","--pack-destination","."],capture_output=True,text=True)
    tgz = glob.glob(pkg.replace("@","").replace("/","-")+f"-{ver}.tgz")[0]
    d = f"x_{name}"; os.makedirs(d, exist_ok=True)
    with tarfile.open(tgz) as t: t.extractall(d, filter="data")
    pj = json.load(open(f"{d}/package/package.json"))
    sc = pj.get("scripts", {})
    out[name] = {"pkg": f"{pkg}@{ver}", "install_hooks": {k: sc[k] for k in ("preinstall","install","postinstall","prepare") if k in sc},
                 "deps": sorted(pj.get("dependencies", {})), "bin": pj.get("bin"), "size_kb": round(os.path.getsize(tgz)/1024)}
    out[name]["scan"] = scan(f"{d}/package", (".js",".mjs",".cjs"))
for name, pkg in PY.items():
    j = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{pkg}/json"))
    w = [u for u in j["urls"] if u["packagetype"] == "bdist_wheel"][0]
    fn = w["url"].split("/")[-1]; urllib.request.urlretrieve(w["url"], fn)
    d = f"x_{name}"; zipfile.ZipFile(fn).extractall(d)
    out[name] = {"pkg": f"{pkg}=={j['info']['version']}", "install_hooks": "wheel (no setup.py run)", "deps": [r.split(";")[0] for r in (j["info"].get("requires_dist") or [])],
                 "size_kb": round(os.path.getsize(fn)/1024), "scan": scan(d, (".py",))}
json.dump(out, open("scan.json","w"), indent=1)
for k, v in out.items():
    f, loc, h, u = v["scan"]
    print(f"\n## {k}  {v['pkg']}  ({v['size_kb']} KB, {f} files, {loc} lines)\n hooks: {v['install_hooks']}\n hits: {h}\n urls: {u}\n deps: {v['deps']}")
