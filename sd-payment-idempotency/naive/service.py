"""NAIVE charge service: what a competent developer writes first. Check-then-act by order id, no unique constraint,
no key sent to the provider. POST /charges {order_id, amount}. The Idempotency-Key header is ignored."""
import asyncio, os
import aiohttp, asyncpg
from aiohttp import web

PROVIDER = os.environ["PROVIDER_URL"]


async def charges(req):
    body, pool = await req.json(), req.app["pool"]
    oid, amount = body["order_id"], body["amount"]
    if await pool.fetchval("SELECT 1 FROM charges WHERE order_id = $1 AND status = 'succeeded'", oid):
        return web.json_response({"status": "succeeded", "replay": True})      # already paid: return it
    cid = await pool.fetchval("INSERT INTO charges(order_id, amount, status) VALUES ($1, $2, 'pending') RETURNING id", oid, amount)
    try:
        async with req.app["http"].post(f"{PROVIDER}/charge", json={"order_id": oid, "amount": amount}) as r:
            if r.status != 200:
                raise RuntimeError(r.status)
    except Exception:
        await pool.execute("UPDATE charges SET status = 'failed' WHERE id = $1", cid)
        return web.json_response({"status": "failed"}, status=502)
    await pool.execute("UPDATE charges SET status = 'succeeded' WHERE id = $1", cid)
    return web.json_response({"status": "succeeded"})


async def reset(req):
    await req.app["pool"].execute("TRUNCATE charges RESTART IDENTITY"); return web.json_response({"ok": True})


async def init(app):
    for _ in range(30):
        try:
            app["pool"] = await asyncpg.create_pool(os.environ["DSN"], min_size=5, max_size=40); break
        except Exception:
            await asyncio.sleep(1)
    app["http"] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5), connector=aiohttp.TCPConnector(limit=300))
    await app["pool"].execute("""CREATE TABLE IF NOT EXISTS charges (
        id bigserial PRIMARY KEY, order_id text NOT NULL, amount int NOT NULL, status text NOT NULL, created timestamptz DEFAULT now())""")
    await app["pool"].execute("CREATE INDEX IF NOT EXISTS charges_order ON charges(order_id)")   # a plain index, NOT unique


app = web.Application()
app.on_startup.append(init)
app.add_routes([web.post("/charges", charges), web.post("/admin/reset", reset), web.get("/health", lambda r: web.json_response({"ok": True}))])
web.run_app(app, port=8080, print=None)
