"""DESIGNED charge service: idempotency key + request hash behind a unique key, a 3 s lease on in-flight work,
409 for a live duplicate, 422 for key reuse with a different body, stored result replayed.
PASS_KEY=1 also sends the key to the provider (idem-e2e); PASS_KEY=0 does not (idem-local)."""
import asyncio, hashlib, json, os
import aiohttp, asyncpg
from aiohttp import web

PROVIDER, PASS_KEY, LEASE_S = os.environ["PROVIDER_URL"], os.environ.get("PASS_KEY") == "1", 3


async def charges(req):
    key = req.headers.get("Idempotency-Key")
    if not key:
        return web.json_response({"error": "Idempotency-Key required"}, status=400)
    body, pool = await req.json(), req.app["pool"]
    h = hashlib.sha256(json.dumps([body["order_id"], body["amount"]]).encode()).hexdigest()
    # claim the key atomically; the unique key decides which concurrent request wins
    won = await pool.fetchrow(
        "INSERT INTO idem(key, request_hash, status, lease_until) VALUES ($1, $2, 'in_progress', now() + $3 * interval '1 second') "
        "ON CONFLICT (key) DO NOTHING RETURNING key", key, h, LEASE_S)
    if won is None:
        cur = await pool.fetchrow("SELECT request_hash, status, response, lease_until < now() AS expired FROM idem WHERE key = $1", key)
        if cur["request_hash"] != h:
            return web.json_response({"error": "key reused with a different request"}, status=422)
        if cur["status"] == "succeeded":
            return web.json_response(json.loads(cur["response"]) | {"replay": True})
        if not cur["expired"]:
            return web.json_response({"error": "in progress"}, status=409)
        took = await pool.fetchrow(   # lease ran out (the worker probably died): take the key over
            "UPDATE idem SET lease_until = now() + $2 * interval '1 second' WHERE key = $1 AND status = 'in_progress' "
            "AND lease_until < now() RETURNING key", key, LEASE_S)
        if took is None:
            return web.json_response({"error": "in progress"}, status=409)
    try:
        async with req.app["http"].post(f"{PROVIDER}/charge", json={"order_id": body["order_id"], "amount": body["amount"]},
                                        headers={"Idempotency-Key": key} if PASS_KEY else {}) as r:
            if r.status != 200:
                raise RuntimeError(r.status)
    except Exception:
        return web.json_response({"status": "failed"}, status=502)    # key stays in_progress; it can be taken over after the lease
    resp = {"status": "succeeded"}
    await pool.execute("UPDATE idem SET status = 'succeeded', response = $2 WHERE key = $1", key, json.dumps(resp))
    return web.json_response(resp)


async def reset(req):
    await req.app["pool"].execute("TRUNCATE idem"); return web.json_response({"ok": True})


async def init(app):
    for _ in range(30):
        try:
            app["pool"] = await asyncpg.create_pool(os.environ["DSN"], min_size=5, max_size=40); break
        except Exception:
            await asyncio.sleep(1)
    app["http"] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5), connector=aiohttp.TCPConnector(limit=300))
    await app["pool"].execute("""CREATE TABLE IF NOT EXISTS idem (
        key text PRIMARY KEY, request_hash text NOT NULL, status text NOT NULL, response text, lease_until timestamptz NOT NULL)""")


app = web.Application()
app.on_startup.append(init)
app.add_routes([web.post("/charges", charges), web.post("/admin/reset", reset), web.get("/health", lambda r: web.json_response({"ok": True}))])
web.run_app(app, port=8080, print=None)
