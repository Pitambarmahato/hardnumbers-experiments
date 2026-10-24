const Fastify = require('fastify');
const { cpuWork, dbRead, sleep50 } = require('./common');

// Fastify's idiomatic validation is its built-in JSON schema (ajv), so that is what we use.
const validateSchema = {
  body: {
    type: 'object',
    required: ['name', 'age', 'tags'],
    properties: {
      name: { type: 'string', minLength: 1 },
      age: { type: 'integer', minimum: 0, maximum: 150 },
      tags: { type: 'array', items: { type: 'string' } },
    },
  },
};

module.exports = function start() {
  const app = Fastify({ logger: false });
  app.get('/json', async () => ({ message: 'ok', n: 42 }));
  app.post('/validate', { schema: validateSchema }, async (req) => ({
    ok: true, name: req.body.name, tags: req.body.tags.length,
  }));
  app.get('/db', async () => dbRead());
  app.get('/cpu', async () => ({ hash: cpuWork() }));
  app.get('/io', async () => { await sleep50(); return { ok: true }; });
  app.listen({ port: 3000, host: '0.0.0.0' });
};
