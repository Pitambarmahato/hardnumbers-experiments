const crypto = require('node:crypto');
const { Pool } = require('pg');

const pool = new Pool({ connectionString: process.env.PG_URL, max: Number(process.env.PG_POOL || 10) });

// Identical across all stacks: 20k chained sha256 rounds.
function cpuWork() {
  let h = Buffer.from('hard-numbers');
  for (let i = 0; i < 20000; i++) h = crypto.createHash('sha256').update(h).digest();
  return h.toString('hex');
}

async function dbRead() {
  const id = 1 + Math.floor(Math.random() * 1000);
  const { rows } = await pool.query('SELECT id, name, value FROM items WHERE id = $1', [id]);
  return rows[0];
}

const sleep50 = () => new Promise((r) => setTimeout(r, 50));

module.exports = { cpuWork, dbRead, sleep50 };
