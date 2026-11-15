const Fastify = require('fastify');
const adapters = require('./adapters');

(async () => {
  const db = await adapters[process.env.DB]();
  const rid = () => 1 + Math.floor(Math.random() * adapters.N);
  const app = Fastify({ logger: false });
  app.get('/read', async () => db.read(rid()));
  app.get('/write', async () => { await db.write(rid()); return { ok: true }; });
  app.get('/incr', async () => { await db.incr(rid()); return { ok: true }; });
  app.get('/query', async () => db.query(Math.floor(Math.random() * adapters.CATS)));
  app.get('/mixed', async () => { // 80% read / 20% write
    if (Math.random() < 0.8) return db.read(rid());
    await db.write(rid());
    return { ok: true };
  });
  await app.listen({ port: 3000, host: '0.0.0.0' });
})().catch((e) => { console.error(e); process.exit(1); });
