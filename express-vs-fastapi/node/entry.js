const cluster = require('node:cluster');
const workers = Number(process.env.WORKERS || 1);
const start = require(`./${process.env.FRAMEWORK}.js`);

if (workers > 1 && cluster.isPrimary) {
  for (let i = 0; i < workers; i++) cluster.fork();
  cluster.on('exit', () => process.exit(1));
} else {
  start();
}
