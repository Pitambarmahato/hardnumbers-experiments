# express-vs-fastapi

Dockerized benchmark: Express, Fastify, FastAPI (1 worker and 4 workers each) across 5 workloads.

```bash
python3 run.py --quick          # smoke test, ~10 min
python3 run.py                  # full matrix: 6 servers x 5 tasks x 4 concurrency x 5 repeats x 60s
python3 analyze.py > results/tables.md
```

- Only one server container runs at a time. Server: 4 CPUs / 2 GB. Postgres: 2 CPUs. Load generator ([oha](https://github.com/hatoo/oha)): 2 CPUs, on the same Docker network.
- Tasks: `json`, `validate` (zod / ajv / pydantic), `db` (random PK read, pool of 10 per process), `cpu` (20k chained sha256), `io` (50 ms sleep).
- Validation is each framework's idiomatic choice: Express+zod, Fastify+built-in JSON schema, FastAPI+pydantic v2.
- FastAPI `/cpu` is a plain `def` (threadpool), which is the idiomatic way to run sync work in FastAPI.
- Output: `results/results.json` (`{"results": [...]}`) for the seed script.
- Pinned: Node 22.11, Python 3.12.7, Express 5.1.0, Fastify 5.2.0, FastAPI 0.115.6, uvicorn 0.34.0, pydantic 2.10.4, Postgres 16.4. oha image digest is stored in results meta.
