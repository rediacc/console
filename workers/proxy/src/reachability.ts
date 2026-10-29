/**
 * The outside-the-container check behind relocation (agent/plans/PLAN-org-executor-connect-timeout-relocate.md, operator ruling ASKED:2026-10-29T05:18Z): before an egress-unreachable report counts, the Worker itself tries the machine the executor could not reach.
 *
 * A Cloudflare container sees a TCP RST as a timeout (bench, 2026-10-28: iptables REJECT on hostinger port 1 still ended in EGRESS_UNREACHABLE), so a machine with a closed port looks the same as blocked egress. The probe tells them apart: a target that greets the Worker with an SSH banner is reachable, so the executor's own path is the broken one; anything else means the machine is the problem and moving the executor would not help.
 *
 * `probeTarget` decides which targets may be probed at all, since the container names the address: an integer port 1-65535 other than 25, and a public IPv4, IPv6 or DNS host. `probeSshBanner` only reads, at most 256 bytes, and never writes, so the container cannot use the Worker as a TCP client that sends anything.
 *
 * A DNS name is resolved by the Worker (DNS over HTTPS) before the probe, and EVERY address it answers is held to the same ranges as a literal: a name with any private, loopback, CGNAT or link-local answer is not probed, and the probe connects to a vetted address literal, never to the name, so a second resolution cannot hand it another address (review 5bce4385.1).
 *
 * What the probe can tell a tenant, weighed (review 5bce4385.1): the answer to a report is one verdict, whether an SSH banner greeted the Worker at host:port, at most PROBE_CAP times per window per instance. The executor container already runs with internet access (`enableInternet` in src/org-executor.ts), so it can connect to any public host itself and read far more than four bytes; the Worker adds only a second vantage point, which is the point of the check.
 */

import { connect } from 'cloudflare:sockets';

/** A machine address the executor reported, after `probeTarget` admitted it. */
export interface ProbeTarget {
  host: string;
  port: number;
}

/** Why a reported target is not probed: malformed, or a name or range the Worker never connects to. */
export type TargetRefusal = { refused: 'report-target-invalid' | 'report-target-refused' };

/** What a report's probe concluded. `skipped` means no probe ran (no target, or the probe cap was reached). */
export type ProbeVerdict = 'reachable' | 'target-unreachable' | 'skipped';

export type ProbeResult =
  | { verdict: 'reachable'; reason: 'banner' }
  | {
      verdict: 'target-unreachable';
      reason: 'no-banner' | 'timeout' | 'error' | 'unresolved' | 'refused-address';
    };

export interface ProbeDeps {
  connect: (address: SocketAddress, options?: SocketOptions) => Socket;
  /** Every address a DNS name answers (A and AAAA). Defaults to DNS over HTTPS. */
  resolve: (name: string) => Promise<string[]>;
  now: () => number;
  timeoutMs: number;
}

/** The DNS over HTTPS endpoint the default resolver asks (JSON API). */
const DOH_URL = 'https://cloudflare-dns.com/dns-query';
/** DNS record types: A and AAAA. */
const DNS_TYPES = { A: 1, AAAA: 28 } as const;

/** The A and AAAA answers for `name`, from DNS over HTTPS. */
export async function resolveDoh(name: string): Promise<string[]> {
  const out: string[] = [];
  for (const [type, code] of Object.entries(DNS_TYPES)) {
    const response = await fetch(`${DOH_URL}?name=${encodeURIComponent(name)}&type=${type}`, {
      headers: { accept: 'application/dns-json' },
    });
    if (!response.ok) throw new Error(`doh-http-${response.status}`);
    const body = (await response.json()) as { Answer?: { type?: number; data?: unknown }[] };
    for (const answer of body.Answer ?? []) {
      if (answer.type === code && typeof answer.data === 'string') out.push(answer.data);
    }
  }
  return out;
}

/** How long the probe waits for the banner. */
export const PROBE_TIMEOUT_MS = 4_000;
/** The most addresses of one name the probe tries, so a dead first answer does not mask a live one. */
const MAX_ADDRESSES = 4;
/** The most the probe reads before it decides. */
const MAX_READ_BYTES = 256;
/** Every SSH server opens with this (RFC 4253 section 4.2). */
const SSH_PREFIX = [0x53, 0x53, 0x48, 0x2d];
/** SMTP: never probed, so a report cannot point the Worker at a mail server. */
const SMTP_PORT = 25;

const INVALID: TargetRefusal = { refused: 'report-target-invalid' };
const REFUSED: TargetRefusal = { refused: 'report-target-refused' };

/** IPv4 ranges never probed, as [first octet, second octet low, second octet high]. */
const REFUSED_V4: readonly [number, number, number][] = [
  [0, 0, 255],
  [10, 0, 255],
  [100, 64, 127],
  [127, 0, 255],
  [169, 254, 254],
  [172, 16, 31],
  [192, 168, 168],
];

const V4_RE = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;
const LABEL = '[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?';
const HOSTNAME_RE = new RegExp(`^${LABEL}(?:\\.${LABEL})*\\.?$`);

/** The four octets of a strict dotted quad (no leading zeros), else undefined. */
function ipv4Octets(host: string): number[] | undefined {
  const match = V4_RE.exec(host);
  if (!match) return undefined;
  const parts = match.slice(1);
  if (parts.some((p) => p.length > 1 && p.startsWith('0'))) return undefined;
  const octets = parts.map(Number);
  return octets.every((o) => o <= 255) ? octets : undefined;
}

function v4Refused(octets: number[]): boolean {
  const [a, b] = octets;
  return REFUSED_V4.some(([first, low, high]) => a === first && b >= low && b <= high);
}

/** `host` with a dotted IPv4 tail rewritten as its two hextets, or undefined when that tail is malformed. */
function withHexTail(host: string): string | undefined {
  const lastColon = host.lastIndexOf(':');
  const tail = host.slice(lastColon + 1);
  if (!tail.includes('.')) return host;
  const octets = ipv4Octets(tail);
  if (!octets) return undefined;
  const hex = (hi: number, lo: number) => ((hi << 8) | lo).toString(16);
  return `${host.slice(0, lastColon + 1)}${hex(octets[0], octets[1])}:${hex(octets[2], octets[3])}`;
}

/** The hextets of a colon-separated run (empty for an empty run), or undefined. */
function hextetRun(part: string): number[] | undefined {
  if (part === '') return [];
  const groups = part.split(':');
  if (groups.some((g) => !/^[0-9a-f]{1,4}$/.test(g))) return undefined;
  return groups.map((g) => Number.parseInt(g, 16));
}

/** The eight hextets of an IPv6 literal (an embedded IPv4 tail included), else undefined. */
function ipv6Hextets(host: string): number[] | undefined {
  if (!/^[0-9a-f:.]+$/.test(host)) return undefined;
  const text = withHexTail(host);
  const halves = text?.split('::');
  if (!halves || halves.length > 2) return undefined;
  const head = hextetRun(halves[0]);
  if (!head) return undefined;
  if (halves.length === 1) return head.length === 8 ? head : undefined;
  const rest = hextetRun(halves[1]);
  if (!rest) return undefined;
  const fill = 8 - head.length - rest.length;
  if (fill < 1) return undefined;
  return [...head, ...new Array<number>(fill).fill(0), ...rest];
}

function v6Refused(h: number[]): boolean {
  const zeroHead = h.slice(0, 5).every((x) => x === 0);
  if (zeroHead && h[5] === 0 && h[6] === 0 && (h[7] === 0 || h[7] === 1)) return true;
  if ((h[0] & 0xfe00) === 0xfc00) return true;
  if ((h[0] & 0xffc0) === 0xfe80) return true;
  // An IPv4-mapped address (::ffff:a.b.c.d) is held to the IPv4 list.
  if (zeroHead && h[5] === 0xffff) {
    return v4Refused([h[6] >> 8, h[6] & 0xff, h[7] >> 8, h[7] & 0xff]);
  }
  return false;
}

/** A DNS name the Worker may resolve: well-formed, not localhost, and not a numeric or hex form a resolver could read as an address. */
function hostnameVerdict(host: string): 'ok' | TargetRefusal {
  if (host.length > 253 || !HOSTNAME_RE.test(host)) return INVALID;
  const labels = host.replace(/\.$/, '').split('.');
  const last = labels[labels.length - 1];
  if (/^\d+$/.test(last) || /^0x[0-9a-f]*$/.test(last)) return INVALID;
  if (last === 'localhost') return REFUSED;
  return 'ok';
}

/** Whether an address literal a name resolved to may be connected to. */
function addressAllowed(address: string): boolean {
  const host = address.trim().toLowerCase();
  const v4 = ipv4Octets(host);
  if (v4) return !v4Refused(v4);
  const v6 = host.includes(':') ? ipv6Hextets(host) : undefined;
  return v6 !== undefined && !v6Refused(v6);
}

/** Whether `host` is an address literal rather than a DNS name. */
function isAddressLiteral(host: string): boolean {
  return ipv4Octets(host) !== undefined || host.includes(':');
}

/** Whether `host` (lowercased, unbracketed) may be probed, or why not. */
function hostVerdict(host: string): 'ok' | TargetRefusal {
  if (host === '') return INVALID;
  const v4 = ipv4Octets(host);
  if (v4) return v4Refused(v4) ? REFUSED : 'ok';
  if (host.includes(':')) {
    const v6 = ipv6Hextets(host);
    if (!v6) return INVALID;
    return v6Refused(v6) ? REFUSED : 'ok';
  }
  if (/^[\d.]+$/.test(host)) return INVALID;
  return hostnameVerdict(host);
}

/** Admit a reported `{ host, port }`, or say why it is not probed. */
export function probeTarget(value: unknown): ProbeTarget | TargetRefusal {
  if (typeof value !== 'object' || value === null) return INVALID;
  const { host: rawHost, port } = value as Record<string, unknown>;
  if (typeof rawHost !== 'string' || typeof port !== 'number') return INVALID;
  if (!Number.isInteger(port) || port < 1 || port > 65535) return INVALID;
  if (port === SMTP_PORT) return REFUSED;
  const host = rawHost
    .trim()
    .toLowerCase()
    .replace(/^\[(.*)\]$/, '$1');
  const verdict = hostVerdict(host);
  return verdict === 'ok' ? { host, port } : verdict;
}

const TIMEOUT = Symbol('timeout');

/** `promise`, or TIMEOUT once `ms` pass. */
async function within<T>(promise: Promise<T>, ms: number): Promise<T | typeof TIMEOUT> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<typeof TIMEOUT>((resolve) => {
    timer = setTimeout(() => resolve(TIMEOUT), ms);
  });
  try {
    return await Promise.race([promise, deadline]);
  } finally {
    clearTimeout(timer);
  }
}

/** The next chunk's bytes, or the verdict that ends the read. */
async function nextChunk(
  reader: ReadableStreamDefaultReader<unknown>,
  remaining: number
): Promise<Uint8Array | ProbeResult> {
  if (remaining <= 0) return { verdict: 'target-unreachable', reason: 'timeout' };
  const step = await within(reader.read(), remaining);
  if (step === TIMEOUT) return { verdict: 'target-unreachable', reason: 'timeout' };
  if (step.done) return { verdict: 'target-unreachable', reason: 'no-banner' };
  if (!(step.value instanceof Uint8Array))
    return { verdict: 'target-unreachable', reason: 'error' };
  return step.value;
}

/** Read until the first four bytes are in, the stream ends, or the deadline passes. `opened` is never consulted: it can resolve for a connect the far side reset (workerd #1305). */
async function readBanner(
  reader: ReadableStreamDefaultReader<unknown>,
  deadline: number,
  now: () => number
): Promise<ProbeResult> {
  const bytes: number[] = [];
  while (bytes.length < SSH_PREFIX.length) {
    const chunk = await nextChunk(reader, deadline - now());
    if (!(chunk instanceof Uint8Array)) return chunk;
    bytes.push(...chunk.subarray(0, MAX_READ_BYTES - bytes.length));
  }
  return SSH_PREFIX.every((b, i) => bytes[i] === b)
    ? { verdict: 'reachable', reason: 'banner' }
    : { verdict: 'target-unreachable', reason: 'no-banner' };
}

/** Close without awaiting: `closed` may never settle for a reset connect, and a probe must not hang on it. */
function closeQuietly(socket: Socket): void {
  try {
    socket.closed.catch(() => undefined);
    socket.close().catch(() => undefined);
  } catch {
    // A socket that cannot even be closed is already gone.
  }
}

/** The addresses a DNS name resolved to, vetted: every answer must be allowed, and each is a candidate to connect to, in answer order (at most MAX_ADDRESSES). Otherwise the verdict that ends the probe. */
async function vettedAddresses(
  name: string,
  resolve: ProbeDeps['resolve'],
  remainingMs: number
): Promise<string[] | ProbeResult> {
  let answers: string[] | typeof TIMEOUT;
  try {
    answers = await within(resolve(name), remainingMs);
  } catch {
    return { verdict: 'target-unreachable', reason: 'unresolved' };
  }
  if (answers === TIMEOUT) return { verdict: 'target-unreachable', reason: 'timeout' };
  if (answers.length === 0) return { verdict: 'target-unreachable', reason: 'unresolved' };
  if (!answers.every(addressAllowed)) {
    return { verdict: 'target-unreachable', reason: 'refused-address' };
  }
  return answers.slice(0, MAX_ADDRESSES).map((answer) => answer.trim().toLowerCase());
}

/** The host in the form `connect` reads: an IPv6 literal goes in brackets. */
function addressHost(host: string): string {
  return host.includes(':') ? `[${host}]` : host;
}

/**
 * Connect to `target` from the Worker and wait up to `timeoutMs` for an SSH banner. Answers `reachable` only when the first bytes are `SSH-`; a refused or reset connect, a silent one, a non-SSH reply and a timeout are all `target-unreachable`. Never writes, never throws.
 */
export async function probeSshBanner(
  target: ProbeTarget,
  deps: Partial<ProbeDeps> = {}
): Promise<ProbeResult> {
  const doConnect = deps.connect ?? connect;
  const now = deps.now ?? Date.now;
  const deadline = now() + (deps.timeoutMs ?? PROBE_TIMEOUT_MS);
  const addresses = isAddressLiteral(target.host)
    ? [target.host]
    : await vettedAddresses(target.host, deps.resolve ?? resolveDoh, deadline - now());
  if (!Array.isArray(addresses)) return addresses;
  let result: ProbeResult = { verdict: 'target-unreachable', reason: 'error' };
  for (const [at, address] of addresses.entries()) {
    // Each address gets an even share of what is left, so a silent first one leaves time for the next.
    const left = addresses.length - at;
    const attemptDeadline = now() + Math.max(0, deadline - now()) / left;
    result = await probeAddress(address, target.port, doConnect, attemptDeadline, now);
    if (result.verdict === 'reachable') return result;
  }
  return result;
}

/** One connect and banner read against a single vetted address. */
async function probeAddress(
  address: string,
  port: number,
  doConnect: ProbeDeps['connect'],
  deadline: number,
  now: () => number
): Promise<ProbeResult> {
  let socket: Socket;
  try {
    socket = doConnect(
      { hostname: addressHost(address), port },
      { secureTransport: 'off', allowHalfOpen: false }
    );
  } catch {
    return { verdict: 'target-unreachable', reason: 'error' };
  }
  try {
    return await readBanner(socket.readable.getReader(), deadline, now);
  } catch {
    return { verdict: 'target-unreachable', reason: 'error' };
  } finally {
    closeQuietly(socket);
  }
}
