#!/usr/bin/env node
/**
 * W0 spike of agent/plans/PLAN-health-checks-local.md: proves the five Worker facts D-runner rests on, against a throwaway Worker (`ops-health-spike`) written to a scratch directory, never under workers/.
 *
 *   node workers/ops-health/spike/w0.mjs --mx <host> --expired <host> --smtps <host> --ct <host> --dnsbl-name <name>
 *       runs `wrangler dev --test-scheduled` locally (no credentials) and prints the five facts.
 *   ... --deploy
 *       deploys the throwaway Worker to workers.dev with the caller's Cloudflare credentials, waits for one real cron run, prints the facts, and deletes the Worker.
 *
 * Fact 1 (outbound TCP to :25 refused) is a property of Cloudflare's production network: a local workerd connects, so only --deploy can confirm it. Exit 0 when every fact the mode can prove holds; 1 otherwise. Every host comes from the arguments, so this file names no target.
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const WRANGLER = join(HERE, '..', 'node_modules', '.bin', 'wrangler');
const PORT = 8790 + Math.floor(Math.random() * 100);

function args() {
  const out = { deploy: false };
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--deploy') out.deploy = true;
    else if (a.startsWith('--') && i + 1 < argv.length) out[a.slice(2)] = argv[++i];
    else throw new Error(`unexpected argument ${a}`);
  }
  for (const key of ['mx', 'expired', 'smtps', 'ct', 'dnsbl-name']) {
    if (!out[key]) throw new Error(`--${key} is required`);
  }
  return out;
}

const WORKER = `
import { DurableObject } from 'cloudflare:workers';
import { connect } from 'cloudflare:sockets';
export class SpikeState extends DurableObject {
  async bump(by) {
    const prev = (await this.ctx.storage.get('s')) ?? { writers: [] };
    const next = { writers: [...prev.writers, by] };
    await this.ctx.storage.put('s', next);
    return next;
  }
  async read() { return (await this.ctx.storage.get('s')) ?? { writers: [] }; }
}
const timeout = (p, ms) => Promise.race([p, new Promise((_, r) => setTimeout(() => r(new Error('timeout')), ms))]);
async function sock(host, port, tls, readLine) {
  try {
    const s = connect({ hostname: host, port }, { secureTransport: tls ? 'on' : 'off', allowHalfOpen: false });
    await timeout(s.opened, 10000);
    let line = '';
    if (readLine) {
      const r = s.readable.getReader();
      const { value } = await timeout(r.read(), 10000);
      line = new TextDecoder().decode(value ?? new Uint8Array()).split('\\r\\n')[0];
      r.releaseLock();
    }
    await s.close().catch(() => undefined);
    return { ok: true, line };
  } catch (e) { return { ok: false, error: String(e) }; }
}
async function facts(q) {
  const out = {};
  out.port25 = await sock(q.get('mx'), 25, false, true);
  out.expiredTls = await sock(q.get('expired'), 443, true, false);
  out.smtps465 = await sock(q.get('smtps'), 465, true, true);
  try {
    const u = 'https://api.certspotter.com/v1/issuances?match_wildcards=true&expand=dns_names&domain=' + encodeURIComponent(q.get('ct'));
    const rows = await (await fetch(u)).json();
    const dates = rows.map((r) => r.not_after).sort();
    out.certspotter = { count: rows.length, newest_not_after: dates[dates.length - 1] ?? null };
  } catch (e) { out.certspotter = { error: String(e) }; }
  try {
    const u = 'https://cloudflare-dns.com/dns-query?type=A&name=' + encodeURIComponent(q.get('dnsbl'));
    const body = await (await fetch(u, { headers: { accept: 'application/dns-json' } })).json();
    out.doh = { status: body.Status, answers: (body.Answer ?? []).map((a) => a.data) };
  } catch (e) { out.doh = { error: String(e) }; }
  return out;
}
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const stub = env.STATE.get(env.STATE.idFromName('state'));
    if (url.pathname === '/facts') return Response.json(await facts(url.searchParams));
    if (url.pathname === '/bump') return Response.json(await stub.bump('fetch'));
    if (url.pathname === '/state') return Response.json(await stub.read());
    return new Response('ops-health spike', { status: 404 });
  },
  async scheduled(_c, env) {
    await env.STATE.get(env.STATE.idFromName('state')).bump('cron');
  },
};
`;

function scratch(deploy) {
  const dir = mkdtempSync(join(tmpdir(), 'ops-health-spike-'));
  mkdirSync(join(dir, 'src'));
  writeFileSync(join(dir, 'src', 'index.js'), WORKER);
  writeFileSync(
    join(dir, 'wrangler.toml'),
    [
      'name = "ops-health-spike"',
      'main = "src/index.js"',
      'compatibility_date = "2026-01-20"',
      `workers_dev = ${deploy ? 'true' : 'false'}`,
      '[triggers]',
      `crons = ["${deploy ? '* * * * *' : '*/10 * * * *'}"]`,
      '[[durable_objects.bindings]]',
      'name = "STATE"',
      'class_name = "SpikeState"',
      '[[migrations]]',
      'tag = "v1"',
      'new_sqlite_classes = ["SpikeState"]',
      '',
    ].join('\n')
  );
  return dir;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getJson(url) {
  const res = await fetch(url);
  return res.json();
}

async function waitFor(fn, ms) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      const v = await fn();
      if (v) return v;
    } catch {
      // not up yet
    }
    await sleep(1000);
  }
  return null;
}

function verdict(f, state, deploy) {
  const checks = [
    ['1 port 25 refused', deploy ? !f.port25.ok : null, f.port25],
    ['2a expired TLS handshake fails', !f.expiredTls.ok, f.expiredTls],
    ['2b TLS on 465 yields a 220 line', f.smtps465.ok && /^220[ -]/.test(f.smtps465.line), f.smtps465],
    ['3 certspotter answers not_after', Boolean(f.certspotter.newest_not_after), f.certspotter],
    ['4 DoH answers 127.255.255.x', (f.doh.answers ?? []).some((a) => a.startsWith('127.255.255.')), f.doh],
    ['5 DO written by cron and fetch', state.writers.includes('cron') && state.writers.includes('fetch'), state],
  ];
  let ok = true;
  for (const [name, pass, evidence] of checks) {
    const mark = pass === null ? 'LOCAL-ONLY (needs --deploy)' : pass ? 'HOLDS' : 'DIFFERS';
    if (pass === false) ok = false;
    console.log(`${mark.padEnd(28)} ${name}: ${JSON.stringify(evidence)}`);
  }
  return ok;
}

// Cloudflare documents that a new Cron Trigger can take up to 15 minutes to reach its network, so a shorter wait reads a not-yet-scheduled cron as a Durable Object the cron cannot write (first run: 150 s, writers ["fetch"]).
const CRON_PROPAGATION_MS = 16 * 60 * 1000;

async function main() {
  const a = args();
  const dir = scratch(a.deploy);
  const q = new URLSearchParams({ mx: a.mx, expired: a.expired, smtps: a.smtps, ct: a.ct, dnsbl: a['dnsbl-name'] });
  let child;
  try {
    let base;
    if (a.deploy) {
      const out = spawnSync(WRANGLER, ['deploy'], { cwd: dir, encoding: 'utf8' });
      process.stderr.write(out.stderr);
      if (out.status !== 0) throw new Error(`wrangler deploy exited ${out.status}`);
      base = (out.stdout.match(/https:\/\/\S+\.workers\.dev/) ?? [])[0];
      if (!base) throw new Error('wrangler deploy printed no workers.dev URL');
      await waitFor(() => fetch(`${base}/state`).then((r) => r.ok), 60000);
    } else {
      child = spawn(WRANGLER, ['dev', '--test-scheduled', '--ip', '127.0.0.1', '--port', String(PORT)], {
        cwd: dir,
        stdio: ['ignore', 'ignore', 'inherit'],
      });
      base = `http://127.0.0.1:${PORT}`;
      if (!(await waitFor(() => fetch(`${base}/state`).then((r) => r.ok), 90000))) throw new Error('wrangler dev did not come up');
      await fetch(`${base}/__scheduled?cron=*/10+*+*+*+*`);
    }
    await getJson(`${base}/bump`);
    const state = a.deploy
      ? await waitFor(async () => {
          const s = await getJson(`${base}/state`);
          return s.writers.includes('cron') ? s : null;
        }, CRON_PROPAGATION_MS) ?? (await getJson(`${base}/state`))
      : await getJson(`${base}/state`);
    const f = await getJson(`${base}/facts?${q}`);
    return verdict(f, state, a.deploy) ? 0 : 1;
  } finally {
    if (child) child.kill('SIGTERM');
    if (a.deploy) spawnSync(WRANGLER, ['delete', '--name', 'ops-health-spike', '--force'], { cwd: dir, stdio: 'inherit' });
    rmSync(dir, { recursive: true, force: true });
  }
}

main().then(
  (code) => process.exit(code),
  (error) => {
    console.error(`w0 spike: ${error.message}`);
    process.exit(1);
  }
);
