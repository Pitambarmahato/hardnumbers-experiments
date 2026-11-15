# queue-benchmark

Postgres vs RabbitMQ vs Redis (BullMQ) vs NATS JetStream used as a job queue, on one
machine, one broker at a time. Same 1 KB job, same producer and worker driver, same
CPU and memory limits. The question: how close is a Postgres queue to a real broker,
and what happens to confirmed jobs when the broker is `kill -9`ed.

Brief: `docs/kw-postgres-vs-rabbitmq-vs-redis-vs-nats-job-queue-benchmark.md`.

## Configs

| Config | Broker | How the queue is set up | Durability as configured |
| --- | --- | --- | --- |
| `postgres` | Postgres 16.4 | table + `FOR UPDATE SKIP LOCKED`, claim then `DELETE` on ack | fsync every commit |
| `postgres-nosync` | Postgres 16.4 | same, `synchronous_commit=off` | like Redis `everysec` |
| `redis` | Redis 8.0 | BullMQ, `removeOnComplete` | stock image: RDB snapshots only, no AOF |
| `redis-aof` | Redis 8.0 | BullMQ | `appendonly yes`, `appendfsync everysec` |
| `rabbitmq-default` | RabbitMQ 4.0 | amqplib, publisher confirms, durable queue | amqplib default: transient messages |
| `rabbitmq-persistent` | RabbitMQ 4.0 | same + `persistent: true` | messages written to disk |
| `nats` | NATS 2.10 | JetStream work-queue stream, file storage, pull consumer | server defaults |

Client versions are pinned in `app/package.json` and image digests are recorded in the
`meta` block of every results file.

## Contract every adapter follows (`app/adapters.js`)

- `enqueue(job)` resolves only when the broker has acknowledged the job (insert committed,
  Redis reply, publisher confirm, JetStream PubAck).
- `consume(W, handler)` keeps at most W jobs in flight and acks after the handler resolves.
  The handler is a no-op, so this measures queue overhead, not job work.

## Scenarios (`app/bench.js`)

- `enqueue`: 50,000 jobs, 10 in flight, as fast as the broker confirms.
- `drain`: 50,000 preloaded jobs (preload not timed), W = 1 / 4 / 16 workers.
- `latency`: open loop at 1,000 jobs/s for 30 s, 4 workers. Latency is measured from the
  intended send time, so a slow broker cannot hide its own delay. Jobs that cannot be
  scheduled because 2,000 are already in flight are counted as `skipped`.
- `crash`: producer at 2,000 jobs/s. 5 s in, `docker kill -s KILL <broker>`, restart it, drain
  what is left. A job counts as confirmed only if `enqueue()` resolved. Lost = confirmed but
  never processed.

## Fairness notes

- Broker: 2 CPUs / 2 GB. Driver: 2 CPUs / 1 GB. One broker up at a time. Docker VM: 8 CPUs, 7.6 GB.
- The driver is a single Node process, so it saturates near 100% CPU (not 200%). `analyze.py`
  prints peak driver CPU; a value near 90-100% means the driver, not the broker, set the
  ceiling for that cell. In the full run this applied to Redis and Redis+AOF (86-95%).
- Postgres has no push delivery here: an idle worker polls every 5 ms, which adds up to 5 ms
  to its latency. Redis, RabbitMQ and NATS push.
- Durability differs by default across these tools. That is the point of the `crash` test,
  and of running `postgres-nosync`, `redis-aof` and `rabbitmq-persistent` next to the defaults.
- `kill -9` kills the broker process. Data already written to the OS page cache survives it.
  It does not simulate power loss, which is where `fsync` policy decides what survives.

## How to run

Requires Docker.

```bash
python3 run.py --quick --only postgres     # smoke test, ~1 min per config
python3 run.py                             # full matrix, 3 repeats -> results/results.json
python3 analyze.py > results/tables.md
```
