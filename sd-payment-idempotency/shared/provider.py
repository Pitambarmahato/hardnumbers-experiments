"""Mock payment provider. Every accepted /charge is a row in provider_charges: that ledger is the ground truth.
With an Idempotency-Key header it dedupes on the key (one row per key, same response); without one every call is a new charge.
The row is committed BEFORE the artificial delay, so a client that times out has still been charged (as with a real provider)."""
import asyncio, os
import asyncpg
from aiohttp import web

CFG = {"delay_ms": 50}


async def charge(req):
    body, key = await req.json(), req.headers.get("Idempotency-Key")
    pool = req.app["pool"]
    row = await pool.fetchrow(
        "INSERT INTO provider_charges(order_id, amount, idem_key) VALUES ($1, $2, $3) ON CONFLICT (idem_key) DO NOTHING RETURNING id",
        body["order_id"], body["amount"], key)
    if row is None:  # key seen before: replay, no new charge
        row = await pool.fetchrow("SELECT id FROM provider_charges WHERE idem_key = $1", key)
    await asyncio.sleep(CFG["delay_ms"] / 1000)
    return web.json_response({"id": row["id"], "status": "charged"})


async def config(req):
    CFG.update(await req.json()); return web.json_response(CFG)


async def reset(req):
    await req.app["pool"].execute("TRUNCATE provider_charges RESTART IDENTITY"); return web.json_response({"ok": True})


async def orders(req):  # order_id -> number of charges the provider recorded
    rows = await req.app["pool"].fetch("SELECT order_id, count(*) AS n FROM provider_charges GROUP BY order_id")
    return web.json_response({r["order_id"]: r["n"] for r in rows})


async def init(app):
    for _ in range(30):
        try:
            app["pool"] = await asyncpg.create_pool(os.environ["DSN"], min_size=5, max_size=40); break
        except Exception:
            await asyncio.sleep(1)
    await app["pool"].execute("""CREATE TABLE IF NOT EXISTS provider_charges (
        id bigserial PRIMARY KEY, order_id text NOT NULL, amount int NOT NULL, idem_key text UNIQUE, created timestamptz DEFAULT now())""")


app = web.Application()
app.on_startup.append(init)
app.add_routes([web.post("/charge", charge), web.post("/admin/config", config), web.post("/admin/reset", reset),
                web.get("/admin/orders", orders), web.get("/health", lambda r: web.json_response({"ok": True}))])
web.run_app(app, port=8081, print=None)
