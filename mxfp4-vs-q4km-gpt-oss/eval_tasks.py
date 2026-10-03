"""Run tasks.json against a GGUF via llama-server (greedy, seed 0, reasoning effort low). Usage: eval_tasks.py <gguf> <out.json>"""
import json, re, subprocess, sys, time, urllib.request

gguf, out = sys.argv[1], sys.argv[2]
PORT = 8089
srv = subprocess.Popen(
    ["llama-server", "-m", gguf, "-c", "4096", "-ngl", "99", "--port", str(PORT), "-np", "1",
     "--chat-template-kwargs", '{"reasoning_effort":"low"}', "--seed", "0"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(300):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2)
            break
        except Exception:
            time.sleep(2)
    else:
        sys.exit("server did not start")

    import os
    tasks = json.load(open("tasks.json"))
    if os.environ.get("IDS"):
        tasks = [t for t in tasks if t["id"] in os.environ["IDS"].split(",")]
    results = []
    for t in tasks:
        body = json.dumps({"messages": [{"role": "user", "content": t["prompt"]}],
                           "temperature": 0, "seed": 0, "max_tokens": 2048}).encode()
        t0 = time.time()
        r = json.load(urllib.request.urlopen(urllib.request.Request(
            f"http://127.0.0.1:{PORT}/v1/chat/completions", body, {"Content-Type": "application/json"}), timeout=600))
        msg = r["choices"][0]["message"]
        text = (msg.get("content") or "")
        m = re.findall(r"FINAL:\s*`?\s*(.+?)\s*`?\s*$", text, re.M)
        got = m[-1].strip().strip("`*\"'. ") if m else None
        ok = got is not None and got.replace(",", "") == t["answer"]
        lines = [l for l in text.strip().splitlines() if l.strip()]
        lenient = got if got is not None else (lines[-1].strip().strip("`*\"'. ") if lines else None)
        ok_lenient = lenient is not None and lenient.replace(",", "") == t["answer"]
        results.append({"id": t["id"], "cat": t["cat"], "answer": t["answer"], "got": got, "ok": ok, "got_lenient": lenient, "ok_lenient": ok_lenient,
                        "completion_tokens": r["usage"]["completion_tokens"], "secs": round(time.time() - t0, 1),
                        "finish": r["choices"][0].get("finish_reason"), "content": text,
                        "reasoning": (msg.get("reasoning_content") or "")[:500]})
        print(t["id"], "OK" if ok else f"X got={got} want={t['answer']}", flush=True)
    json.dump({"gguf": gguf, "results": results}, open(out, "w"), indent=1)
    n = sum(x["ok"] for x in results)
    print(f"ACCURACY strict {n}/{len(results)} lenient {sum(x['ok_lenient'] for x in results)}/{len(results)}")
finally:
    srv.terminate()
