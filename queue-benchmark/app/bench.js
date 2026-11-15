// node bench.js <queue> <mode> [--url U] [--persistent] [--n N] [--p P] [--workers W] [--rate R] [--seconds S]
// Modes: enqueue | drain | latency | crash-produce | crash-count. Prints one line: RESULT {json}
const adapters = require('./adapters');

const argv = process.argv.slice(2);
const [queue, mode] = argv;
const opt = (k, d) => { const i = argv.indexOf(`--${k}`); return i < 0 ? d : (argv[i + 1] === undefined || argv[i + 1].startsWith('--') ? true : argv[i + 1]); };
const num = (k, d) => Number(opt(k, d));
const url = opt('url');
const persistent = argv.includes('--persistent');
const N = num('n', 50000), P = num('p', 10), W = num('workers', 4), RATE = num('rate', 1000), SECONDS = num('seconds', 30);

const PAD = 'x'.repeat(900); // job JSON is ~950 bytes
const mkJob = (id, t0) => ({ id, t0, pad: PAD });
const now = () => performance.now();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pct = (sorted, p) => (sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * p))] : null);
const out = (o) => console.log('RESULT ' + JSON.stringify(o));

async function closedLoop(n, p, fn) { // p jobs in flight, as fast as the broker confirms
  let next = 0;
  await Promise.all(Array.from({ length: p }, async () => {
    for (;;) { const i = next++; if (i >= n) return; await fn(i); }
  }));
}

// Open loop at `rate` jobs/s. t0 is the INTENDED send time, so a slow broker cannot hide its own delay.
async function openLoop(rate, seconds, send) {
  const start = now(); let sent = 0, skipped = 0, inflight = 0; const pending = [];
  await new Promise((resolve) => {
    const iv = setInterval(() => {
      const elapsed = now() - start;
      const due = Math.min(Math.floor(elapsed * rate / 1000), seconds * rate);
      while (sent < due) {
        const id = sent++, t0 = start + (id * 1000) / rate;
        if (inflight >= 2000) { skipped++; continue; } // broker is not keeping up; counted and reported
        inflight++;
        pending.push(send(id, t0).finally(() => inflight--));
      }
      if (elapsed >= seconds * 1000) { clearInterval(iv); resolve(); }
    }, 10);
  });
  await Promise.allSettled(pending);
  return { scheduled: sent, skipped };
}

(async () => {
  const fresh = mode !== 'crash-count';
  const q = await adapters[queue](url, { fresh, persistent });
  try {
    if (mode === 'enqueue') {
      const t = now();
      await closedLoop(N, P, (i) => q.enqueue(mkJob(i, 0)));
      const s = (now() - t) / 1000;
      out({ jobs: N, seconds: +s.toFixed(2), jobs_per_s: Math.round(N / s) });

    } else if (mode === 'drain') {
      await closedLoop(N, 20, (i) => q.enqueue(mkJob(i, 0))); // preload, not timed
      let done = 0, finish; const all = new Promise((r) => (finish = r));
      const t = now();
      const c = await q.consume(W, async () => { if (++done === N) finish(); });
      await all;
      const s = (now() - t) / 1000;
      await c.stop();
      out({ jobs: N, workers: W, seconds: +s.toFixed(2), jobs_per_s: Math.round(N / s) });

    } else if (mode === 'latency') {
      const lat = []; let done = 0;
      const c = await q.consume(W, async (j) => { lat.push(now() - j.t0); done++; });
      const { scheduled, skipped } = await openLoop(RATE, SECONDS, (id, t0) => q.enqueue(mkJob(id, t0)));
      const deadline = now() + 10000;
      while (done < scheduled - skipped && now() < deadline) await sleep(50);
      await c.stop();
      lat.sort((a, b) => a - b);
      out({ target_rate: RATE, workers: W, scheduled, skipped, processed: done,
        p50_ms: +pct(lat, 0.5).toFixed(2), p95_ms: +pct(lat, 0.95).toFixed(2), p99_ms: +pct(lat, 0.99).toFixed(2), max_ms: +lat[lat.length - 1].toFixed(2) });

    } else if (mode === 'crash-produce') {
      // The runner SIGKILLs the broker ~5 s after READY. A job counts as confirmed only if enqueue() resolved.
      const confirmed = []; let failed = 0;
      console.log('READY');
      await openLoop(RATE, SECONDS, async (id) => {
        try {
          await Promise.race([q.enqueue(mkJob(id, 0)), sleep(2000).then(() => { throw new Error('timeout'); })]);
          confirmed.push(id);
        } catch { failed++; }
      });
      out({ confirmed: confirmed.length, failed, confirmed_ids: confirmed });

    } else if (mode === 'crash-count') {
      // Broker restarted by the runner. Drain whatever survived, stop after 4 s with nothing arriving.
      const seen = new Map(); let last = now();
      const c = await q.consume(W, async (j) => { seen.set(j.id, (seen.get(j.id) || 0) + 1); last = now(); });
      while (now() - last < 4000) await sleep(200);
      await c.stop();
      out({ processed_unique: seen.size, duplicates: [...seen.values()].filter((v) => v > 1).length, processed_ids: [...seen.keys()] });

    } else {
      throw new Error('unknown mode ' + mode);
    }
  } finally {
    await Promise.race([q.close(), sleep(3000)]); // a client of a killed broker can hang on close
    process.exit(0);
  }
})().catch((e) => { console.error('BENCH ERROR', e); process.exit(1); });
