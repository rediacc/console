import regions from '../../../regions.json';

/** The five generic probe kinds of D-runner. A target naming any other kind is kept and reported as an `unknown` probe. */
export const PROBE_KINDS = [
  'tls',
  'banner-465',
  'https',
  'health-endpoint',
  'dnsbl-over-DoH',
] as const;
export type ProbeKind = (typeof PROBE_KINDS)[number];

export interface ProbeTarget {
  id: string;
  kind: string;
  host: string;
  port?: number;
  path?: string;
  expect?: string;
  /** dnsbl-over-DoH only: the IPv4 address looked up in the zone named by `host`. */
  ip?: string;
}

export type TriState = 'green' | 'red' | 'unknown';

export interface TargetsLoad {
  probes: ProbeTarget[];
  /** The `targets` probe: green with a count when the secret parsed, unknown with the reason otherwise. */
  status: { state: TriState; detail: string };
  probeCount: number;
}

/** Probe ids the Worker itself owns; a target file may not reuse them. */
export const RESERVED_IDS = ['targets', 'mailer'] as const;

/** The id namespace of the build-time regions.json endpoints. */
const RESERVED_PREFIX = 'health:';

const ID_RE = /^[a-z0-9][a-z0-9._:-]{0,63}$/;
const HOST_RE = /^[A-Za-z0-9.-]{1,253}$/;
const IPV4_RE = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;

export class TargetsError extends Error {}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Throws TargetsError with `message` unless `ok`. */
function ensure(ok: boolean, message: string): void {
  if (!ok) throw new TargetsError(message);
}

function optionalField<T>(
  value: unknown,
  valid: (v: unknown) => v is T,
  message: string
): T | undefined {
  if (value === undefined) return undefined;
  ensure(valid(value), message);
  return value as T;
}

const isPort = (v: unknown): v is number =>
  typeof v === 'number' && Number.isInteger(v) && v >= 1 && v <= 65535;
const isPath = (v: unknown): v is string => typeof v === 'string' && v.startsWith('/');
const isNonEmpty = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const isHost = (v: unknown): v is string => typeof v === 'string' && HOST_RE.test(v);

function parseProbe(entry: unknown, index: number): ProbeTarget {
  const where = `probes[${index}]`;
  if (!isRecord(entry)) throw new TargetsError(`${where} is not an object`);
  const { id, kind, host } = entry;
  ensure(typeof id === 'string' && ID_RE.test(id), `${where}.id must match ${ID_RE.source}`);
  ensure(isNonEmpty(kind), `${where}.kind must be a non-empty string`);
  ensure(isHost(host), `${where}.host must be a host name`);
  const probe: ProbeTarget = { id: id as string, kind: kind as string, host: host as string };
  const port = optionalField(entry.port, isPort, `${where}.port must be an integer 1..65535`);
  const path = optionalField(entry.path, isPath, `${where}.path must start with /`);
  const expect = optionalField(
    entry.expect,
    isNonEmpty,
    `${where}.expect must be a non-empty string`
  );
  if (port !== undefined) probe.port = port;
  if (path !== undefined) probe.path = path;
  if (expect !== undefined) probe.expect = expect;
  return probe;
}

/** The `dnsbl` section: one dnsbl-over-DoH probe per zone, and the address a probes[] entry of that kind falls back to. */
function parseDnsbl(section: unknown): { ip?: string; probes: ProbeTarget[] } {
  if (section === undefined) return { probes: [] };
  if (!isRecord(section)) throw new TargetsError('dnsbl must be an object');
  const { ip, zones } = section;
  ensure(typeof ip === 'string' && IPV4_RE.test(ip), 'dnsbl.ip must be an IPv4 address');
  ensure(
    Array.isArray(zones) && zones.every((zone) => isHost(zone)),
    'dnsbl.zones must be an array of zone names'
  );
  const address = ip as string;
  return {
    ip: address,
    probes: (zones as string[]).map((zone) => ({
      id: `dnsbl:${zone.toLowerCase()}`,
      kind: 'dnsbl-over-DoH',
      host: zone,
      ip: address,
    })),
  };
}

/** Refuses a duplicate id, a Worker-owned id, and anything in the build-time `health:` namespace. */
function checkIds(probes: ProbeTarget[]): void {
  const seen = new Set<string>();
  for (const probe of probes) {
    ensure(!seen.has(probe.id), `duplicate probe id ${probe.id}`);
    const reserved =
      (RESERVED_IDS as readonly string[]).includes(probe.id) ||
      probe.id.startsWith(RESERVED_PREFIX);
    ensure(!reserved, `probe id ${probe.id} is reserved`);
    seen.add(probe.id);
  }
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    throw new TargetsError('not valid JSON');
  }
}

/**
 * The target file schema of D-record: `{version, probes: [{id, kind, host, port?, path?, expect?}], dnsbl: {ip, zones}}`. Throws TargetsError with the first problem; the deploy script (rediacc_ci.ops.deploy_ops_health) validates the same schema before it uploads anything.
 */
export function parseTargetFile(text: string): ProbeTarget[] {
  const doc = parseJson(text);
  if (!isRecord(doc)) throw new TargetsError('the document is not an object');
  ensure(doc.version === 1, 'version must be 1');
  if (!Array.isArray(doc.probes)) throw new TargetsError('probes must be an array');
  const probes = doc.probes.map((entry, index) => parseProbe(entry, index));
  const dnsbl = parseDnsbl(doc.dnsbl);
  for (const probe of probes) {
    if (probe.kind === 'dnsbl-over-DoH' && probe.ip === undefined) probe.ip = dnsbl.ip;
  }
  const all = [...probes, ...dnsbl.probes];
  checkIds(all);
  return all;
}

/** OPS_HEALTH_TARGETS as the Worker sees it: an absent or unparseable secret is the probe `targets` in state `unknown`, never green. */
export function loadTargets(secret: string | undefined): TargetsLoad {
  if (secret === undefined || secret.trim() === '') {
    return {
      probes: [],
      probeCount: 0,
      status: { state: 'unknown', detail: 'OPS_HEALTH_TARGETS is not set' },
    };
  }
  try {
    const probes = parseTargetFile(secret);
    return {
      probes,
      probeCount: probes.length,
      status: { state: 'green', detail: `${probes.length} target probe(s) loaded` },
    };
  } catch (error) {
    const reason = error instanceof TargetsError ? error.message : 'unreadable';
    return {
      probes: [],
      probeCount: 0,
      status: { state: 'unknown', detail: `OPS_HEALTH_TARGETS is invalid: ${reason}` },
    };
  }
}

interface RegionRow {
  id: string;
  domain: string;
}

/**
 * The only build-time targets: the account and proxy `/health` endpoints of every region in regions.json, which are public already.
 */
export function regionEndpoints(rows: RegionRow[] = regions.regions): ProbeTarget[] {
  const out: ProbeTarget[] = [];
  for (const row of rows) {
    out.push({
      id: `health:account-${row.id}`,
      kind: 'health-endpoint',
      host: row.domain,
      path: '/account/api/v1/health',
    });
    out.push({
      id: `health:proxy-${row.id}`,
      kind: 'health-endpoint',
      host: `proxy.${row.domain}`,
      path: '/v1/health',
    });
  }
  return out;
}
