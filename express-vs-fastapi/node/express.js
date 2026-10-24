const express = require('express');
const { z } = require('zod');
const { cpuWork, dbRead, sleep50 } = require('./common');

const Body = z.object({
  name: z.string().min(1),
  age: z.number().int().min(0).max(150),
  tags: z.array(z.string()),
});

module.exports = function start() {
  const app = express();
  app.use(express.json());
  app.get('/json', (_req, res) => res.json({ message: 'ok', n: 42 }));
  app.post('/validate', (req, res) => {
    const r = Body.safeParse(req.body);
    if (!r.success) return res.status(422).json({ error: 'invalid' });
    res.json({ ok: true, name: r.data.name, tags: r.data.tags.length });
  });
  app.get('/db', async (_req, res) => res.json(await dbRead()));
  app.get('/cpu', (_req, res) => res.json({ hash: cpuWork() }));
  app.get('/io', async (_req, res) => { await sleep50(); res.json({ ok: true }); });
  app.listen(3000, '0.0.0.0');
};
