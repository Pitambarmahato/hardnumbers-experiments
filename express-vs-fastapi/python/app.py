import asyncio
import hashlib
import os
import random
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from pydantic import BaseModel, Field


class Body(BaseModel):
    name: str = Field(min_length=1)
    age: int = Field(ge=0, le=150)
    tags: list[str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        os.environ["PG_URL"], min_size=1, max_size=int(os.environ.get("PG_POOL", "10"))
    )
    yield
    await app.state.pool.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/json")
async def json_ep():
    return {"message": "ok", "n": 42}


@app.post("/validate")
async def validate(body: Body):
    return {"ok": True, "name": body.name, "tags": len(body.tags)}


@app.get("/db")
async def db():
    i = random.randint(1, 1000)
    row = await app.state.pool.fetchrow("SELECT id, name, value FROM items WHERE id = $1", i)
    return dict(row)


# Identical across all stacks: 20k chained sha256 rounds. Plain `def` runs in the threadpool.
@app.get("/cpu")
def cpu():
    h = b"hard-numbers"
    for _ in range(20000):
        h = hashlib.sha256(h).digest()
    return {"hash": h.hex()}


@app.get("/io")
async def io():
    await asyncio.sleep(0.05)
    return {"ok": True}
