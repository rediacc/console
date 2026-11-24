/**
 * Base URL guard for a customer AI provider profile (D5 of
 * PLAN-console-ai-providers).
 *
 * The executor sends the provider key to `baseURL`, so a profile must not be able
 * to aim it at the egress intercept (`account.internal`, `ai.internal`) or at the
 * executor's own host. Accepted: `https` only, a public host, no embedded
 * credentials. Refused: any `.internal` or `localhost` name, and loopback,
 * link-local, private (RFC 1918, IPv6 unique-local) and unspecified address
 * literals, including IPv4-mapped, NAT64 and 6to4 IPv6 forms.
 *
 * This is a static check on the URL text. A public-looking hostname whose DNS
 * answer is private is not caught here; the executor's egress layer is the
 * boundary for that.
 */

export type BaseUrlRefusal =
  | 'unparseable'
  | 'not-https'
  | 'credentials'
  | 'internal-host'
  | 'loopback'
  | 'link-local'
  | 'private-address'
  | 'unspecified';

export type BaseUrlCheck =
  | { ok: true; url: URL }
  | { ok: false; reason: BaseUrlRefusal; message: string };

const REFUSAL_TEXT: Record<BaseUrlRefusal, string> = {
  unparseable: 'baseURL is not a valid URL',
  'not-https': 'baseURL must use https',
  credentials: 'baseURL must not carry a user name or password',
  'internal-host': 'baseURL names an internal host',
  loopback: 'baseURL points at a loopback address',
  'link-local': 'baseURL points at a link-local address',
  'private-address': 'baseURL points at a private network address',
  unspecified: 'baseURL points at an unspecified address',
};

function refuse(reason: BaseUrlRefusal): BaseUrlCheck {
  return { ok: false, reason, message: REFUSAL_TEXT[reason] };
}

function classifyV4(octets: readonly number[]): BaseUrlRefusal | null {
  const [a, b] = octets;
  if (a === 127) return 'loopback';
  if (a === 0) return 'unspecified';
  if (a === 169 && b === 254) return 'link-local';
  if (a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)) {
    return 'private-address';
  }
  return null;
}

/** Replace a dotted IPv4 tail (`::ffff:1.2.3.4`) by two hex groups; null when an octet is out of range. */
function foldDottedTail(text: string): string | null {
  const dotted = /(\d+)\.(\d+)\.(\d+)\.(\d+)$/.exec(text);
  if (!dotted) return text;
  const parts = dotted.slice(1).map(Number);
  if (parts.some((n) => n > 255)) return null;
  const hi = ((parts[0] << 8) | parts[1]).toString(16);
  const lo = ((parts[2] << 8) | parts[3]).toString(16);
  return `${text.slice(0, dotted.index)}${hi}:${lo}`;
}

function hexGroups(part: string): string[] {
  return part === '' ? [] : part.split(':');
}

/** Eight 16-bit groups of an IPv6 literal (no brackets), or null when it does not parse. */
function expandV6(literal: string): number[] | null {
  const zone = literal.indexOf('%');
  const folded = foldDottedTail((zone === -1 ? literal : literal.slice(0, zone)).toLowerCase());
  if (folded === null) return null;
  const halves = folded.split('::');
  if (halves.length > 2) return null;
  const head = hexGroups(halves[0]);
  const tail = halves.length === 2 ? hexGroups(halves[1]) : [];
  const fill = 8 - head.length - tail.length;
  const compressed = halves.length === 2;
  if (compressed ? fill < 1 : fill !== 0) return null;
  const all = [...head, ...new Array<string>(compressed ? fill : 0).fill('0'), ...tail];
  const groups = all.map((g) => (/^[0-9a-f]{1,4}$/.test(g) ? Number.parseInt(g, 16) : Number.NaN));
  return groups.every((g) => !Number.isNaN(g)) ? groups : null;
}

const allZero = (groups: readonly number[]): boolean => groups.every((g) => g === 0);

function v4Of(hi: number, lo: number): BaseUrlRefusal | null {
  return classifyV4([hi >> 8, hi & 255, lo >> 8, lo & 255]);
}

/** The IPv4 range an IPv6 literal embeds, as `[refusal]`, or null when it embeds none. */
function embeddedV4(groups: readonly number[]): [BaseUrlRefusal | null] | null {
  // IPv4-mapped ::ffff:a.b.c.d and the deprecated IPv4-compatible ::a.b.c.d
  if (allZero(groups.slice(0, 5)) && (groups[5] === 0xffff || groups[5] === 0)) {
    return [v4Of(groups[6], groups[7])];
  }
  // NAT64 64:ff9b::a.b.c.d carries the target IPv4 in its last 32 bits.
  if (groups[0] === 0x64 && groups[1] === 0xff9b && allZero(groups.slice(2, 6))) {
    return [v4Of(groups[6], groups[7])];
  }
  // 6to4 2002:a.b:c.d::/48 carries the IPv4 in groups 1 and 2.
  if (groups[0] === 0x2002) return [v4Of(groups[1], groups[2])];
  return null;
}

function classifyV6(groups: readonly number[]): BaseUrlRefusal | null {
  if (allZero(groups)) return 'unspecified';
  if (allZero(groups.slice(0, 7)) && groups[7] === 1) return 'loopback';
  const embedded = embeddedV4(groups);
  if (embedded) return embedded[0];
  if ((groups[0] & 0xffc0) === 0xfe80) return 'link-local';
  if ((groups[0] & 0xfe00) === 0xfc00) return 'private-address';
  return null;
}

/** Why a host name or address literal is refused, or null when it is a public host. */
function refuseHost(host: string): BaseUrlRefusal | 'unparseable' | null {
  if (host.startsWith('[') && host.endsWith(']')) {
    const groups = expandV6(host.slice(1, -1));
    return groups ? classifyV6(groups) : 'unparseable';
  }
  const v4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (v4) return classifyV4(v4.slice(1).map(Number));
  const internal =
    host === 'localhost' ||
    host.endsWith('.localhost') ||
    host === 'internal' ||
    host.endsWith('.internal');
  return internal ? 'internal-host' : null;
}

/** Check a profile's base URL against D5. Returns the parsed URL when it is acceptable. */
export function validateBaseUrl(raw: string): BaseUrlCheck {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return refuse('unparseable');
  }
  if (url.protocol !== 'https:') return refuse('not-https');
  if (url.username !== '' || url.password !== '') return refuse('credentials');

  const host = url.hostname.toLowerCase().replace(/\.$/, '');
  const reason = host === '' ? 'unparseable' : refuseHost(host);
  return reason ? refuse(reason) : { ok: true, url };
}
