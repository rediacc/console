import http from 'node:http';

const PORT = 3000;
// eBPF bind rewriting handles IP isolation transparently.
// Apps can bind to 0.0.0.0 and the kernel rewrites it to the
// correct loopback IP for this repository's network namespace.
const HOST = '0.0.0.0';

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({
    status: 'ok',
    host: HOST,
    pid: process.pid,
    uptime: Math.floor(process.uptime()),
  }) + '\n');
});

// CRIU: after checkpoint/restore, stale TCP sockets may trigger
// ECONNRESET before the new connection is established.
process.on('uncaughtException', (err) => {
  if (err.code === 'ECONNRESET') {
    console.warn('ECONNRESET (stale socket after CRIU restore), ignoring');
    return;
  }
  console.error('Uncaught exception:', err);
  process.exit(1);
});

server.listen(PORT, HOST, () => {
  console.log(`Server listening on ${HOST}:${PORT}`);
});
