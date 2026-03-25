import http from 'node:http';

const PORT = 3000;
let host = process.env.SERVICE_IP || '0.0.0.0';

let server = createServer();

// CRIU restore awareness: after checkpoint/restore the assigned SERVICE_IP
// may have changed (e.g. repo was pushed to another machine). Poll for
// changes and rebind the server to the new IP when detected.
setInterval(() => {
  const currentIP = process.env.SERVICE_IP;
  if (currentIP && currentIP !== host) {
    console.log(`SERVICE_IP changed: ${host} -> ${currentIP}, rebinding...`);
    server.close(() => {
      host = currentIP;
      server = createServer();
    });
  }
}, 5000);

function createServer() {
  const s = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      status: 'ok',
      host,
      pid: process.pid,
      uptime: Math.floor(process.uptime()),
    }) + '\n');
  });

  s.listen(PORT, host, () => {
    console.log(`Server listening on ${host}:${PORT}`);
  });

  return s;
}
