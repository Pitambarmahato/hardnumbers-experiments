// One adapter per queue. Same contract for all four:
//   make(url, { fresh, persistent }) -> { enqueue(job), consume(W, handler), close() }
//   enqueue(job)   resolves when the BROKER has acknowledged the job (insert committed /
//                  Redis reply / publisher confirm / JetStream PubAck). Rejects otherwise.
//   consume(W, h)  keeps at most W jobs in flight; acks a job after h(job) resolves.
//                  returns { stop() }.
//   fresh: drop and recreate the queue before use (not used when counting after a crash).
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const POLL_MS = 5; // Postgres has no push; an idle worker polls every 5 ms

// ---------- Postgres: plain table, FOR UPDATE SKIP LOCKED ----------
async function postgres(url, { fresh }) {
  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: url, max: 40 });
  pool.on('error', () => {}); // idle clients die when the broker is killed
  if (fresh) {
    await pool.query('DROP TABLE IF EXISTS jobs');
    await pool.query('CREATE TABLE jobs (id bigserial PRIMARY KEY, body jsonb NOT NULL, locked boolean NOT NULL DEFAULT false)');
    await pool.query('CREATE INDEX jobs_ready ON jobs (id) WHERE NOT locked');
  }
  const CLAIM = `UPDATE jobs SET locked = true WHERE id = (
    SELECT id FROM jobs WHERE NOT locked ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id, body`;
  return {
    enqueue: (job) => pool.query('INSERT INTO jobs (body) VALUES ($1)', [job]),
    consume(W, handler) {
      let stopped = false;
      const loops = Array.from({ length: W }, async () => {
        while (!stopped) {
          const { rows } = await pool.query(CLAIM);
          if (!rows.length) { await sleep(POLL_MS); continue; }
          await handler(rows[0].body);
          await pool.query('DELETE FROM jobs WHERE id = $1', [rows[0].id]); // ack
        }
      });
      return { stop: async () => { stopped = true; await Promise.allSettled(loops); } };
    },
    close: () => pool.end().catch(() => {}),
  };
}

// ---------- Redis + BullMQ ----------
async function redis(url, { fresh }) {
  const { Queue, Worker } = require('bullmq');
  const IORedis = require('ioredis');
  if (fresh) { const c = new IORedis(url); await c.flushall(); await c.quit(); }
  // fail fast when the server is down instead of queueing commands until it comes back
  const queue = new Queue('jobs', {
    connection: new IORedis(url, { enableOfflineQueue: false, maxRetriesPerRequest: 1 }),
    defaultJobOptions: { removeOnComplete: true, removeOnFail: true },
  });
  queue.on('error', () => {});
  await queue.waitUntilReady();
  return {
    enqueue: (job) => queue.add('j', job),
    consume(W, handler) {
      const w = new Worker('jobs', (j) => handler(j.data), {
        connection: new IORedis(url, { maxRetriesPerRequest: null }), concurrency: W,
      });
      w.on('error', () => {});
      return { stop: () => w.close() };
    },
    close: () => queue.close().catch(() => {}),
  };
}

// ---------- RabbitMQ (amqplib) ----------
// persistent=false is the amqplib default: durable queue, but messages are transient.
async function rabbitmq(url, { fresh, persistent }) {
  const amqp = require('amqplib');
  const conn = await amqp.connect(url);
  conn.on('error', () => {});
  const pub = await conn.createConfirmChannel();
  pub.on('error', () => {});
  if (fresh) await pub.deleteQueue('jobs');
  await pub.assertQueue('jobs', { durable: true });
  return {
    enqueue: (job) => new Promise((res, rej) =>
      pub.sendToQueue('jobs', Buffer.from(JSON.stringify(job)), { persistent: !!persistent }, (e) => (e ? rej(e) : res()))),
    async consume(W, handler) {
      const ch = await conn.createChannel();
      ch.on('error', () => {});
      await ch.prefetch(W);
      await ch.consume('jobs', async (msg) => {
        try {
          await handler(JSON.parse(msg.content.toString()));
          ch.ack(msg);
        } catch { /* channel closed by stop() while this job was in flight */ }
      });
      return { stop: () => ch.close().catch(() => {}) };
    },
    close: () => conn.close().catch(() => {}),
  };
}

// ---------- NATS JetStream: file-backed work-queue stream, pull consumer ----------
async function nats(url, { fresh }) {
  const { connect } = require('@nats-io/transport-node');
  const { jetstream, jetstreamManager, AckPolicy, RetentionPolicy, StorageType } = require('@nats-io/jetstream');
  const nc = await connect({ servers: url, reconnect: false });
  nc.closed().catch(() => {});
  const jsm = await jetstreamManager(nc);
  const js = jetstream(nc);
  if (fresh) {
    await jsm.streams.delete('JOBS').catch(() => {});
    await jsm.streams.add({ name: 'JOBS', subjects: ['jobs'], retention: RetentionPolicy.Workqueue, storage: StorageType.File });
    await jsm.consumers.add('JOBS', { durable_name: 'w', ack_policy: AckPolicy.Explicit });
  }
  const dec = new TextDecoder();
  const enc = new TextEncoder();
  return {
    enqueue: (job) => js.publish('jobs', enc.encode(JSON.stringify(job))),
    async consume(W, handler) {
      const c = await js.consumers.get('JOBS', 'w');
      const msgs = await c.consume({ max_messages: W });
      (async () => {
        for await (const m of msgs) {
          Promise.resolve(handler(JSON.parse(dec.decode(m.data)))).then(() => m.ack()).catch(() => {});
        }
      })().catch(() => {});
      return { stop: async () => { await msgs.close().catch(() => {}); } };
    },
    close: () => nc.close().catch(() => {}),
  };
}

module.exports = { postgres, redis, rabbitmq, nats };
