/**
 * The SSRF guard in front of the Client ID Metadata Document fetch (agent/plans/PLAN-rmcp-remote-worker.md Design 2).
 *
 * An OAuth client may name itself with an https URL; the authorization server then fetches that URL. The URL is attacker-chosen, so before the library fetches it the host is checked here: https only, no userinfo, the default port, a name that is not an internal one, and every address the host resolves to public (no private, loopback, link-local, metadata, shared or reserved range). A verdict is cached per host.
 *
 * What this check does not close on its own: the library's fetch connects after this check, so a DNS answer that changes between the two, and a redirect to an internal address, are closed at connect time by the Workers compatibility flag `global_fetch_strictly_public` (set in every wrangler file of this Worker), not here. The 5 KiB size cap and the 10 s timeout of the fetch are the library's own. On a host without that flag (the Node host) this check is the whole defense.
 */

/** Answer the public addresses (text form) a host name resolves to, or an empty list when it has none. */
export type HostResolver = (host: string) => Promise<readonly string[]>;

/** Why a client URL was refused; the text is safe to return to the client. */
export class ClientUrlRefused extends Error {
  constructor(reason: string) {
    super(reason);
    this.name = 'ClientUrlRefused';
  }
}

const POSITIVE_TTL_MS = 5 * 60_000;
const NEGATIVE_TTL_MS = 60_000;
const DOH_TIMEOUT_MS = 3000;

/** The four octets of dotted-quad text, or null when the text is not one. */
function ipv4Octets(text: string): number[] | null {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(text);
  const octets = match ? match.slice(1).map(Number) : null;
  return octets?.every((octet) => octet <= 255) ? octets : null;
}

/** IPv4 ranges outside the public unicast space, as `[base, prefix length]`. */
const PRIVATE_IPV4: readonly (readonly [string, number])[] = [
  ['0.0.0.0', 8],
  ['10.0.0.0', 8],
  ['100.64.0.0', 10],
  ['127.0.0.0', 8],
  ['169.254.0.0', 16],
  ['172.16.0.0', 12],
  ['192.0.0.0', 24],
  ['192.0.2.0', 24],
  ['192.168.0.0', 16],
  ['198.18.0.0', 15],
  ['198.51.100.0', 24],
  ['203.0.113.0', 24],
  ['224.0.0.0', 3],
];

function ipv4Number(octets: readonly number[]): number {
  return octets.reduce((total, octet) => total * 256 + octet, 0);
}

/** Each private range as its first address and its size. */
const PRIVATE_RANGES: readonly (readonly [number, number])[] = PRIVATE_IPV4.map(([base, bits]) => [
  ipv4Number(ipv4Octets(base) ?? []),
  2 ** (32 - bits),
]);

/** True for an IPv4 address outside the public unicast space. */
function privateIpv4(octets: readonly number[]): boolean {
  const ip = ipv4Number(octets);
  return PRIVATE_RANGES.some(([first, size]) => ip >= first && ip < first + size);
}

/** IPv6 text with a dotted-quad tail (`::ffff:10.0.0.1`) rewritten with the tail as two hex groups. */
function withHexTail(address: string): string | null {
  const tail = /(\d{1,3}(?:\.\d{1,3}){3})$/.exec(address);
  if (!tail) return address;
  const octets = ipv4Octets(tail[1]);
  if (!octets) return null;
  const high = ((octets[0] << 8) | octets[1]).toString(16);
  const low = ((octets[2] << 8) | octets[3]).toString(16);
  return `${address.slice(0, address.length - tail[1].length)}${high}:${low}`;
}

/** The eight 16-bit groups of an IPv6 address, or null when the text is not one. */
function ipv6Groups(text: string): number[] | null {
  const address = withHexTail(text);
  const halves = address?.split('::');
  if (!halves || halves.length > 2) return null;
  const head = halves[0] === '' ? [] : halves[0].split(':');
  const rest = halves[1] === undefined || halves[1] === '' ? [] : halves[1].split(':');
  const missing = 8 - head.length - rest.length;
  const compressed = halves.length === 2;
  if (compressed ? missing < 1 : missing !== 0) return null;
  const groups = [...head, ...Array<string>(compressed ? missing : 0).fill('0'), ...rest];
  const values = groups.map((group) =>
    /^[0-9a-f]{1,4}$/i.test(group) ? Number.parseInt(group, 16) : -1
  );
  return values.every((value) => value >= 0) ? values : null;
}

function privateIpv6(groups: readonly number[]): boolean {
  const [g0, g1] = groups as [number, number];
  const embedded = [groups[6]! >> 8, groups[6]! & 255, groups[7]! >> 8, groups[7]! & 255];
  const prefixIs = (...expected: number[]) => expected.every((value, i) => groups[i] === value);
  return (
    groups.slice(0, 7).every((group) => group === 0) || // :: and ::1
    (prefixIs(0, 0, 0, 0, 0) && privateIpv4(embedded)) || // IPv4-compatible
    (prefixIs(0, 0, 0, 0, 0, 0xffff) && privateIpv4(embedded)) || // IPv4-mapped
    (prefixIs(0x64, 0xff9b, 0, 0, 0, 0) && privateIpv4(embedded)) || // NAT64
    g0 === 0x2002 || // 6to4
    (g0 === 0x2001 && g1 === 0x0db8) || // documentation
    (g0 & 0xfe00) === 0xfc00 || // unique local
    (g0 & 0xffc0) === 0xfe80 || // link-local
    (g0 & 0xff00) === 0xff00 // multicast
  );
}

/** Whether `address` (IPv4 or IPv6 text, no brackets) is outside the public space; an unparsable one counts as private. */
export function isPrivateAddress(address: string): boolean {
  const v4 = ipv4Octets(address);
  if (v4) return privateIpv4(v4);
  const v6 = ipv6Groups(address);
  return v6 ? privateIpv6(v6) : true;
}

const INTERNAL_SUFFIXES = ['.localhost', '.local', '.internal', '.localdomain', '.home.arpa'];

function internalName(host: string): boolean {
  return (
    host === 'localhost' ||
    !host.includes('.') ||
    INTERNAL_SUFFIXES.some((suffix) => host.endsWith(suffix))
  );
}

/** The addresses of one record type that DNS-over-HTTPS answers for `host`. */
async function dohLookup(host: string, type: 'A' | 'AAAA'): Promise<string[]> {
  const url = `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(host)}&type=${type}`;
  const response = await fetch(url, {
    headers: { accept: 'application/dns-json' },
    signal: AbortSignal.timeout(DOH_TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`DNS lookup answered ${response.status}`);
  const body = (await response.json()) as { Answer?: { type: number; data: string }[] };
  const wanted = type === 'A' ? 1 : 28;
  return (body.Answer ?? [])
    .filter((answer) => answer.type === wanted)
    .map((answer) => answer.data);
}

/** Resolve a host through DNS-over-HTTPS, the resolver a Worker has: A and AAAA, each bounded by a timeout. */
export const dohResolver: HostResolver = async (host) => [
  ...(await dohLookup(host, 'A')),
  ...(await dohLookup(host, 'AAAA')),
];

export interface ClientUrlGuard {
  /** Throw {@link ClientUrlRefused} unless `clientId` may be fetched as a metadata document. */
  assertPublic(clientId: string): Promise<void>;
}

/** The refusal for an address literal, or null when it is public. */
function literalVerdict(literal: string): string | null {
  return isPrivateAddress(literal) ? 'the client URL names a non-public address' : null;
}

/** The refusal for a host name, resolving it; null when every address is public. */
async function nameVerdict(host: string, resolveHost: HostResolver): Promise<string | null> {
  if (internalName(host)) return 'the client URL names an internal host';
  let addresses: readonly string[];
  try {
    addresses = await resolveHost(host);
  } catch {
    return 'the client URL host could not be resolved';
  }
  if (addresses.length === 0) return 'the client URL host does not resolve';
  return addresses.some(isPrivateAddress)
    ? 'the client URL resolves to a non-public address'
    : null;
}

/** The refusal for a host, or null when it may be fetched. */
function hostVerdict(host: string, resolveHost: HostResolver): Promise<string | null> {
  const literal = host.startsWith('[') ? host.slice(1, -1) : host;
  const isLiteral = ipv4Octets(literal) !== null || literal.includes(':');
  return isLiteral ? Promise.resolve(literalVerdict(literal)) : nameVerdict(host, resolveHost);
}

/** The parsed client URL; throws {@link ClientUrlRefused} for a scheme, credentials or port a metadata document may not use. */
function shapeOf(clientId: string): URL {
  let url: URL;
  try {
    url = new URL(clientId);
  } catch {
    throw new ClientUrlRefused('the client URL is not a URL');
  }
  if (url.protocol !== 'https:') throw new ClientUrlRefused('the client URL must use https');
  if (url.username !== '' || url.password !== '') {
    throw new ClientUrlRefused('the client URL must not carry credentials');
  }
  if (url.port !== '') throw new ClientUrlRefused('the client URL must use the default port');
  return url;
}

export function createClientUrlGuard(
  resolveHost: HostResolver,
  now: () => number = Date.now
): ClientUrlGuard {
  const verdicts = new Map<string, { until: number; refusal: string | null }>();

  async function verdictFor(host: string): Promise<string | null> {
    const cached = verdicts.get(host);
    if (cached && cached.until > now()) return cached.refusal;
    const refusal = await hostVerdict(host, resolveHost);
    verdicts.set(host, {
      until: now() + (refusal === null ? POSITIVE_TTL_MS : NEGATIVE_TTL_MS),
      refusal,
    });
    return refusal;
  }

  return {
    async assertPublic(clientId) {
      const refusal = await verdictFor(shapeOf(clientId).hostname.toLowerCase());
      if (refusal !== null) throw new ClientUrlRefused(refusal);
    },
  };
}
