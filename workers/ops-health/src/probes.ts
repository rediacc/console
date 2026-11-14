import { CONFIG, type OpsHealthConfig } from './config';
import type { ProbeTarget, TriState } from './targets';

const TLS_DEFAULT_PORT = 443;
const SMTPS_DEFAULT_PORT = 465;
const NO_CT_ANSWER = 'no CT answer';

/**
 * The five generic probe kinds of D-runner. Every probe answers green, red or unknown, and unknown is never folded into green. No probe writes to a socket or sends anything but a GET, so no code path here changes remote state.
 */

export interface ProbeResult {
  id: string;
  kind: string;
  state: TriState;
  detail: string;
}

/** One CT answer: the newest `not_after` that covers the host, or null when no source could say. */
export interface CtAnswer {
  notAfter: string | null;
  source: 'certspotter' | 'crt.sh' | 'cache' | 'none';
  detail?: string;
}

export type ConnectFn = (address: SocketAddress, options?: SocketOptions) => Socket;

export interface ProbeDeps {
  fetch: typeof fetch;
  connect: ConnectFn;
  now: () => number;
  /** Days-to-expiry source for the `tls` kind (host, optional issuer filter from the target's `expect`); index.ts wraps `lookupCt` with the state's cache. */
  ct: (host: string, issuer?: string) => Promise<CtAnswer>;
  spamhausKey?: string;
  config?: OpsHealthConfig;
}

const DAY_MS = 86_400_000;
const DOH_URL = 'https://cloudflare-dns.com/dns-query';
const CERTSPOTTER_URL = 'https://api.certspotter.com/v1/issuances';
const CRTSH_URL = 'https://crt.sh/';

class Timeout extends Error {}

function withTimeout<T>(promise: Promise<T>, ms: number, what: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const expiry = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Timeout(`${what} timed out after ${ms} ms`)), ms);
  });
  return Promise.race([promise, expiry]).finally(() => clearTimeout(timer));
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function result(target: ProbeTarget, state: TriState, detail: string): ProbeResult {
  return { id: target.id, kind: target.kind, state, detail };
}

async function closeQuietly(socket: Socket): Promise<void> {
  try {
    await socket.close();
  } catch {
    // A close that fails after a finished probe changes nothing about its answer.
  }
}

/** Opens an implicit-TLS connection; resolves the socket once the handshake has validated the served chain, or throws. */
async function tlsOpen(deps: ProbeDeps, host: string, port: number, ms: number): Promise<Socket> {
  const socket = deps.connect(
    { hostname: host, port },
    { secureTransport: 'on', allowHalfOpen: false }
  );
  try {
    await withTimeout(socket.opened, ms, `TLS handshake with ${host}:${port}`);
    return socket;
  } catch (error) {
    await closeQuietly(socket);
    throw error;
  }
}

/** Does a certificate name cover `host`: an exact match, or a wildcard one label up. */
export function covers(name: string, host: string): boolean {
  const n = name.toLowerCase();
  const h = host.toLowerCase();
  if (n === h) return true;
  if (!n.startsWith('*.')) return false;
  const dot = h.indexOf('.');
  return dot > 0 && h.slice(dot + 1) === n.slice(2);
}

function newest(dates: string[]): string | null {
  let best: number | null = null;
  for (const date of dates) {
    const ms = Date.parse(date);
    if (!Number.isNaN(ms) && (best === null || ms > best)) best = ms;
  }
  return best === null ? null : new Date(best).toISOString();
}

interface CertspotterIssuance {
  id: string;
  not_after: string;
  dns_names?: string[];
  issuer?: { friendly_name?: string; name?: string };
}

interface CtQuery {
  host: string;
  issuer?: string;
  fetch: typeof fetch;
  config: OpsHealthConfig;
}

/** Does an issuer match the target's filter (a case-insensitive substring of its friendly name or DN); no filter matches every issuer. */
function issuerMatches(filter: string | undefined, ...names: (string | undefined)[]): boolean {
  if (!filter) return true;
  const needle = filter.toLowerCase();
  return names.some((name) => (name ?? '').toLowerCase().includes(needle));
}

function certspotterUrl(host: string, after: string | undefined): string {
  const url = new URL(CERTSPOTTER_URL);
  url.searchParams.set('domain', host);
  url.searchParams.set('match_wildcards', 'true');
  url.searchParams.append('expand', 'dns_names');
  url.searchParams.append('expand', 'issuer');
  if (after) url.searchParams.set('after', after);
  return url.toString();
}

function coveringDates(rows: CertspotterIssuance[], q: CtQuery): string[] {
  return rows
    .filter((row) => (row.dns_names ?? []).some((name) => covers(name, q.host)))
    .filter((row) => issuerMatches(q.issuer, row.issuer?.friendly_name, row.issuer?.name))
    .map((row) => row.not_after);
}

/** certspotter's newest covering `not_after`, following its 100-row pages up to `ct_max_pages`; throws when it cannot say. */
async function certspotterNewest(q: CtQuery): Promise<string> {
  const ms = q.config.worker.probe_timeout_ms;
  const dates: string[] = [];
  let after: string | undefined;
  for (let page = 0; page < q.config.worker.ct_max_pages; page += 1) {
    const response = await q.fetch(certspotterUrl(q.host, after), {
      signal: AbortSignal.timeout(ms),
    });
    if (!response.ok) throw new Error(`certspotter answered ${response.status}`);
    const body = (await response.json()) as CertspotterIssuance[];
    if (!Array.isArray(body)) throw new Error('certspotter answered a non-list');
    dates.push(...coveringDates(body, q));
    if (body.length < 100) break;
    after = body[body.length - 1].id;
  }
  const found = newest(dates);
  if (!found) throw new Error('certspotter has no unexpired issuance covering the host');
  return found;
}

/** crt.sh's newest `not_after` for the host; throws when it cannot say. */
async function crtshNewest(q: CtQuery): Promise<string> {
  const url = new URL(CRTSH_URL);
  url.searchParams.set('q', q.host);
  url.searchParams.set('output', 'json');
  url.searchParams.set('exclude', 'expired');
  const response = await q.fetch(url.toString(), {
    signal: AbortSignal.timeout(q.config.worker.probe_timeout_ms),
  });
  if (!response.ok) throw new Error(`crt.sh answered ${response.status}`);
  const body = (await response.json()) as { not_after: string; issuer_name?: string }[];
  const found = newest(
    body
      .filter((row) => issuerMatches(q.issuer, row.issuer_name))
      .map((row) => (row.not_after.endsWith('Z') ? row.not_after : `${row.not_after}Z`))
  );
  if (!found) throw new Error('crt.sh has no unexpired issuance for the host');
  return found;
}

/**
 * The newest unexpired issuance covering `host` in Certificate Transparency: certspotter first (`match_wildcards=true`, because a host served by a wildcard certificate has no issuance under its own name, W0), crt.sh when certspotter cannot answer. An unreadable source is `notAfter: null`, which the `tls` probe reports as unknown.
 *
 * `issuer` narrows the issuances to the CA the origin really uses. W0 measured why it matters: a zone on Cloudflare also carries Cloudflare's own edge issuances for the same wildcard (Google Trust Services, expiring 2027-01-31) while the origin served a Let's Encrypt certificate expiring 2026-12-05, so the unfiltered newest issuance reads green through exactly the failed-renewal class (F17) this probe exists to see.
 */
export async function lookupCt(
  host: string,
  deps: Pick<ProbeDeps, 'fetch'> & { config?: OpsHealthConfig },
  issuer?: string
): Promise<CtAnswer> {
  const q: CtQuery = { host, issuer, fetch: deps.fetch, config: deps.config ?? CONFIG };
  let certspotterError: unknown;
  try {
    return { notAfter: await certspotterNewest(q), source: 'certspotter' };
  } catch (error) {
    certspotterError = error;
  }
  try {
    return { notAfter: await crtshNewest(q), source: 'crt.sh' };
  } catch (crtshError) {
    return {
      notAfter: null,
      source: 'none',
      detail: `${message(certspotterError)}; ${message(crtshError)}`,
    };
  }
}

async function handshakeError(
  target: ProbeTarget,
  deps: ProbeDeps,
  port: number
): Promise<ProbeResult | null> {
  const config = deps.config ?? CONFIG;
  try {
    const socket = await tlsOpen(deps, target.host, port, config.worker.probe_timeout_ms);
    await closeQuietly(socket);
    return null;
  } catch (error) {
    return result(
      target,
      'red',
      `TLS handshake with ${target.host}:${port} failed: ${message(error)}`
    );
  }
}

async function probeTls(target: ProbeTarget, deps: ProbeDeps): Promise<ProbeResult> {
  const config = deps.config ?? CONFIG;
  const failed = await handshakeError(target, deps, target.port ?? TLS_DEFAULT_PORT);
  if (failed) return failed;
  const ct = await deps.ct(target.host, target.expect);
  const scope = target.expect ? `issuer "${target.expect}"` : 'any issuer';
  if (ct.notAfter === null) {
    return result(
      target,
      'unknown',
      `handshake ok; days to expiry unknown for ${scope} (${ct.detail ?? NO_CT_ANSWER})`
    );
  }
  const days = Math.floor((Date.parse(ct.notAfter) - deps.now()) / DAY_MS);
  const base = `handshake ok; newest certificate (${scope}, ${ct.source}) expires ${ct.notAfter}, ${days} day(s)`;
  if (days < config.tls.red_days) {
    return result(target, 'red', `${base}: critical, under ${config.tls.red_days}`);
  }
  if (days < config.tls.warn_days) {
    return result(target, 'red', `${base}: warning, under ${config.tls.warn_days}`);
  }
  return result(target, 'green', base);
}

function compileExpect(expect: string | undefined, fallback: RegExp): RegExp | null {
  if (expect === undefined) return fallback;
  try {
    return new RegExp(expect);
  } catch {
    return null;
  }
}

/** Reads until the first line break (or 512 bytes, or the end); never writes. */
async function readFirstLine(socket: Socket, ms: number, what: string): Promise<string> {
  const reader = socket.readable.getReader();
  const decoder = new TextDecoder();
  let text = '';
  try {
    while (!text.includes('\n') && text.length < 512) {
      const { done, value } = await withTimeout(reader.read(), ms, what);
      if (done) break;
      text += decoder.decode(value, { stream: true });
    }
  } finally {
    reader.releaseLock();
  }
  return text.split(/\r?\n/)[0].slice(0, 200);
}

async function probeBanner(target: ProbeTarget, deps: ProbeDeps): Promise<ProbeResult> {
  const config = deps.config ?? CONFIG;
  const port = target.port ?? SMTPS_DEFAULT_PORT;
  const expect = compileExpect(target.expect, /^220[ -]/);
  if (expect === null) {
    return result(target, 'unknown', `expect is not a valid pattern: ${target.expect}`);
  }
  let socket: Socket;
  try {
    socket = await tlsOpen(deps, target.host, port, config.worker.probe_timeout_ms);
  } catch (error) {
    return result(
      target,
      'red',
      `TLS handshake with ${target.host}:${port} failed: ${message(error)}`
    );
  }
  let line: string;
  try {
    line = await readFirstLine(
      socket,
      config.worker.probe_timeout_ms,
      `banner from ${target.host}:${port}`
    );
  } catch (error) {
    return result(target, 'red', `no banner from ${target.host}:${port}: ${message(error)}`);
  } finally {
    await closeQuietly(socket);
  }
  if (line === '') return result(target, 'red', `${target.host}:${port} closed without a banner`);
  if (!expect.test(line)) {
    return result(target, 'red', `banner "${line}" does not match ${expect.source}`);
  }
  return result(target, 'green', `banner "${line}"`);
}

function targetUrl(target: ProbeTarget, defaultPath: string): string {
  const port = target.port ? `:${target.port}` : '';
  return `https://${target.host}${port}${target.path ?? defaultPath}`;
}

async function probeHttp(
  target: ProbeTarget,
  deps: ProbeDeps,
  defaultPath: string,
  accept: (status: number) => boolean
): Promise<ProbeResult> {
  const config = deps.config ?? CONFIG;
  const url = targetUrl(target, defaultPath);
  let response: Response;
  try {
    response = await deps.fetch(url, {
      method: 'GET',
      redirect: 'manual',
      signal: AbortSignal.timeout(config.worker.probe_timeout_ms),
      headers: { 'user-agent': 'rediacc-ops-health' },
    });
  } catch (error) {
    return result(target, 'red', `GET ${url} failed: ${message(error)}`);
  }
  if (!accept(response.status)) {
    return result(target, 'red', `GET ${url} answered ${response.status}`);
  }
  if (target.expect !== undefined) {
    const body = await response.text().catch(() => '');
    if (!body.includes(target.expect)) {
      return result(
        target,
        'red',
        `GET ${url} answered ${response.status} without "${target.expect}"`
      );
    }
  }
  return result(target, 'green', `GET ${url} answered ${response.status}`);
}

/** The DoH lookup name for an IPv4 address in a zone; Spamhaus zones go through the DQS key, since Spamhaus answers public resolvers with 127.255.255.x (W0). */
function dnsblName(ip: string, zone: string, key: string | undefined): string | null {
  const reversed = ip.split('.').reverse().join('.');
  if (/(^|\.)spamhaus\.org$/i.test(zone)) {
    if (!key) return null;
    return `${reversed}.${key}.${zone.replace(/\.spamhaus\.org$/i, '.dq.spamhaus.net')}`;
  }
  return `${reversed}.${zone}`;
}

interface DohAnswer {
  Status: number;
  Answer?: { type: number; data: string }[];
}

/** The state a DNSBL answer means: NXDOMAIN or no A record is not listed, 127.255.255.x is a refused resolver (unknown), any other 127.x is a listing. */
function classifyDoh(answer: DohAnswer, zone: string): { state: TriState; detail: string } {
  if (answer.Status === 3) return { state: 'green', detail: `not listed in ${zone}` };
  if (answer.Status !== 0) {
    return { state: 'unknown', detail: `DoH status ${answer.Status} for ${zone}` };
  }
  const addresses = (answer.Answer ?? []).filter((a) => a.type === 1).map((a) => a.data);
  const list = addresses.join(', ');
  if (addresses.length === 0) return { state: 'green', detail: `not listed in ${zone}` };
  if (addresses.some((a) => a.startsWith('127.255.255.'))) {
    return { state: 'unknown', detail: `${zone} refused the query (${list})` };
  }
  if (addresses.some((a) => a.startsWith('127.'))) {
    return { state: 'red', detail: `listed in ${zone} (${list})` };
  }
  return { state: 'unknown', detail: `${zone} answered an unexpected address (${list})` };
}

async function probeDnsbl(target: ProbeTarget, deps: ProbeDeps): Promise<ProbeResult> {
  const config = deps.config ?? CONFIG;
  const zone = target.host;
  if (!target.ip) {
    return result(target, 'unknown', `no IPv4 address to look up in ${zone} (dnsbl.ip)`);
  }
  const name = dnsblName(target.ip, zone, deps.spamhausKey);
  if (name === null) {
    return result(
      target,
      'unknown',
      `${zone} answers public resolvers with 127.255.255.x; SPAMHAUS_DQS_KEY is not set`
    );
  }
  const url = new URL(DOH_URL);
  url.searchParams.set('name', name);
  url.searchParams.set('type', 'A');
  try {
    const response = await deps.fetch(url.toString(), {
      headers: { accept: 'application/dns-json' },
      signal: AbortSignal.timeout(config.worker.probe_timeout_ms),
    });
    if (!response.ok) {
      return result(target, 'unknown', `DoH answered ${response.status} for ${zone}`);
    }
    const verdict = classifyDoh((await response.json()) as DohAnswer, zone);
    return result(target, verdict.state, verdict.detail);
  } catch (error) {
    return result(target, 'unknown', `DoH lookup in ${zone} failed: ${message(error)}`);
  }
}

type Prober = (target: ProbeTarget, deps: ProbeDeps) => Promise<ProbeResult>;

const PROBERS: Record<string, Prober> = {
  tls: probeTls,
  'banner-465': probeBanner,
  https: (target, deps) => probeHttp(target, deps, '/', (status) => status < 400),
  'health-endpoint': (target, deps) =>
    probeHttp(target, deps, '/health', (status) => status === 200),
  'dnsbl-over-DoH': probeDnsbl,
};

/** One probe; never throws. An unknown kind is an unknown probe. */
export async function runProbe(target: ProbeTarget, deps: ProbeDeps): Promise<ProbeResult> {
  const prober = Object.hasOwn(PROBERS, target.kind) ? PROBERS[target.kind] : undefined;
  if (!prober) return result(target, 'unknown', `unknown probe kind ${target.kind}`);
  try {
    return await prober(target, deps);
  } catch (error) {
    return result(target, 'unknown', `probe crashed: ${message(error)}`);
  }
}

export function runProbes(targets: ProbeTarget[], deps: ProbeDeps): Promise<ProbeResult[]> {
  return Promise.all(targets.map((target) => runProbe(target, deps)));
}
