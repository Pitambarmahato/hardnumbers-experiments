// One adapter per store. Same document, same four operations, idiomatic driver use for each.
// Doc: { id, name, category (0-99), score, tags[3], bio (~800 chars) } -> ~1 KB JSON.
const N = 10000;
const CATS = 100;
const BIO = 'x'.repeat(800);
const makeDoc = (id) => ({ id, name: `user-${id}`, category: id % CATS, score: (id * 7) % 1000, tags: ['a', 'b', 'c'], bio: BIO });
const mongoDoc = (id) => ({ _id: id, name: `user-${id}`, category: id % CATS, score: (id * 7) % 1000, tags: ['a', 'b', 'c'], bio: BIO });

// ---- Postgres JSONB (baseline: "do you need NoSQL at all?") ----
async function postgres() {
  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: process.env.DB_URL, max: 10 });
  await pool.query('CREATE TABLE IF NOT EXISTS docs (id int PRIMARY KEY, doc jsonb NOT NULL)');
  await pool.query("CREATE INDEX IF NOT EXISTS docs_cat ON docs (((doc->>'category')::int), id)");
  const { rows } = await pool.query('SELECT count(*)::int AS n FROM docs');
  if (rows[0].n !== N) {
    await pool.query('TRUNCATE docs');
    for (let i = 1; i <= N; i += 500) {
      const vals = [], params = [];
      for (let id = i; id < i + 500 && id <= N; id++) {
        params.push(id, JSON.stringify(makeDoc(id)));
        vals.push(`($${params.length - 1}, $${params.length}::jsonb)`);
      }
      await pool.query(`INSERT INTO docs VALUES ${vals.join(',')}`, params);
    }
    await pool.query('ANALYZE docs');
  }
  return {
    read: async (id) => (await pool.query('SELECT doc FROM docs WHERE id = $1', [id])).rows[0].doc,
    write: (id) => pool.query('INSERT INTO docs VALUES ($1, $2::jsonb) ON CONFLICT (id) DO UPDATE SET doc = EXCLUDED.doc', [id, JSON.stringify(makeDoc(id))]),
    incr: (id) => pool.query("UPDATE docs SET doc = jsonb_set(doc, '{score}', to_jsonb((doc->>'score')::int + 1)) WHERE id = $1", [id]),
    query: async (cat) => (await pool.query("SELECT doc FROM docs WHERE (doc->>'category')::int = $1 ORDER BY id LIMIT 10", [cat])).rows.map((r) => r.doc),
  };
}

// ---- MongoDB ----
async function mongo() {
  const { MongoClient } = require('mongodb');
  const client = new MongoClient(process.env.DB_URL, { maxPoolSize: 10 });
  await client.connect();
  const c = client.db('bench').collection('docs');
  await c.createIndex({ category: 1, _id: 1 });
  if ((await c.countDocuments()) !== N) {
    await c.deleteMany({});
    const all = [];
    for (let id = 1; id <= N; id++) all.push(mongoDoc(id));
    await c.insertMany(all);
  }
  return {
    read: (id) => c.findOne({ _id: id }),
    write: (id) => c.replaceOne({ _id: id }, mongoDoc(id), { upsert: true }),
    incr: (id) => c.updateOne({ _id: id }, { $inc: { score: 1 } }),
    query: (cat) => c.find({ category: cat }).sort({ _id: 1 }).limit(10).toArray(),
  };
}

// ---- Redis / Valkey (same code: both speak RESP; docs are JSON strings, no module) ----
async function redisLike() {
  const Redis = require('ioredis');
  const r = new Redis(process.env.DB_URL); // one connection, auto-pipelined: the idiomatic ioredis setup
  const key = (id) => `doc:${id}`;
  if ((await r.dbsize()) < N) {
    await r.flushall();
    for (let i = 1; i <= N; i += 1000) {
      const p = r.pipeline();
      for (let id = i; id < i + 1000 && id <= N; id++) {
        const d = makeDoc(id);
        p.set(key(id), JSON.stringify(d));
        p.zadd(`cat:${d.category}`, id, id);
      }
      await p.exec();
    }
  }
  // Atomic read-modify-write for incr (no native JSON field increment without a module).
  r.defineCommand('incrScore', {
    numberOfKeys: 1,
    lua: "local d = cjson.decode(redis.call('GET', KEYS[1])); d.score = d.score + 1; return redis.call('SET', KEYS[1], cjson.encode(d))",
  });
  return {
    read: async (id) => JSON.parse(await r.get(key(id))),
    write: (id) => r.set(key(id), JSON.stringify(makeDoc(id))), // category unchanged, so cat:* index needs no update
    incr: (id) => r.incrScore(key(id)),
    // Application-maintained secondary index: sorted set per category, then MGET.
    query: async (cat) => {
      const ids = await r.zrange(`cat:${cat}`, 0, 9);
      return (await r.mget(ids.map(key))).map((s) => JSON.parse(s));
    },
  };
}

module.exports = { postgres, mongo, redis: redisLike, valkey: redisLike, N, CATS };
