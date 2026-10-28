/**
 * CIDR parsing and matching, portable across Node, Cloudflare Workers and
 * browsers: no `node:net`, no Buffer. IPv6 arithmetic uses BigInt.
 *
 * Consumers: the config schema's `access.sourceRanges` validation (host bits,
 * duplicates after canonicalisation) and the CLI's authorized_keys lockout
 * guard (`cidrContains` against the address sshd reports in `$SSH_CONNECTION`).
 */

export interface ParsedCidr {
  family: 4 | 6;
  /** The address as written, as an unsigned integer (32 or 128 bits). */
  address: bigint;
  /** The address with every host bit cleared. */
  network: bigint;
  prefix: number;
}

const IPV4_OCTET = /^(0|[1-9]\d{0,2})$/;
const IPV6_GROUP = /^[0-9a-fA-F]{1,4}$/;
const PREFIX = /^(0|[1-9]\d{0,2})$/;

function parseIPv4(text: string): bigint | null {
  const parts = text.split('.');
  if (parts.length !== 4) return null;
  let value = 0n;
  for (const part of parts) {
    if (!IPV4_OCTET.test(part)) return null;
    const octet = Number(part);
    if (octet > 255) return null;
    value = (value << 8n) | BigInt(octet);
  }
  return value;
}

function parseIPv6Groups(text: string, quadAllowed: boolean): number[] | null {
  if (text === '') return [];
  const groups: number[] = [];
  const parts = text.split(':');
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    // An embedded dotted-quad is only allowed as the final 32 bits.
    if (quadAllowed && i === parts.length - 1 && part.includes('.')) {
      const v4 = parseIPv4(part);
      if (v4 === null) return null;
      groups.push(Number(v4 >> 16n), Number(v4 & 0xffffn));
      continue;
    }
    if (!IPV6_GROUP.test(part)) return null;
    groups.push(Number.parseInt(part, 16));
  }
  return groups;
}

/** The eight 16-bit groups of an IPv6 address, `::` expanded; null when malformed. */
function expandIPv6Groups(text: string): number[] | null {
  const halves = text.split('::');
  if (halves.length > 2) return null;
  // The dotted quad may only end the whole address, so the head of a '::' split never takes one.
  if (halves.length === 1) return parseIPv6Groups(text, true);
  const head = parseIPv6Groups(halves[0], false);
  const tail = parseIPv6Groups(halves[1], true);
  if (head === null || tail === null) return null;
  const missing = 8 - head.length - tail.length;
  if (missing < 1) return null;
  return [...head, ...new Array<number>(missing).fill(0), ...tail];
}

function parseIPv6(text: string): bigint | null {
  if (text.includes('%')) return null; // zone ids never appear in sshd's from= patterns
  const groups = expandIPv6Groups(text);
  if (groups === null || groups.length !== 8) return null;
  let value = 0n;
  for (const group of groups) value = (value << 16n) | BigInt(group);
  return value;
}

/** Parse a bare IPv4 or IPv6 address (no prefix). */
export function parseIpAddress(text: string): { family: 4 | 6; value: bigint } | null {
  if (text.includes(':')) {
    const value = parseIPv6(text);
    return value === null ? null : { family: 6, value };
  }
  const value = parseIPv4(text);
  return value === null ? null : { family: 4, value };
}

function bitsOf(family: 4 | 6): number {
  return family === 4 ? 32 : 128;
}

function maskOf(family: 4 | 6, prefix: number): bigint {
  const bits = BigInt(bitsOf(family));
  const all = (1n << bits) - 1n;
  return all ^ ((1n << (bits - BigInt(prefix))) - 1n);
}

/**
 * Parse `address/prefix`. Returns null for anything that is not a CIDR range
 * (a missing prefix included). A /0 parses: refusing it is policy, not syntax,
 * and the schema does that.
 */
export function parseCidr(text: string): ParsedCidr | null {
  const slash = text.indexOf('/');
  if (slash < 0 || slash !== text.lastIndexOf('/')) return null;
  const ip = parseIpAddress(text.slice(0, slash));
  const prefixText = text.slice(slash + 1);
  if (ip === null || !PREFIX.test(prefixText)) return null;
  const prefix = Number(prefixText);
  if (prefix > bitsOf(ip.family)) return null;
  return {
    family: ip.family,
    address: ip.value,
    network: ip.value & maskOf(ip.family, prefix),
    prefix,
  };
}

function formatIPv4(value: bigint): string {
  return [24n, 16n, 8n, 0n].map((shift) => String((value >> shift) & 0xffn)).join('.');
}

/** RFC 5952 text form: lowercase, no leading zeros, the longest run of 2+ zero groups as `::`. */
function formatIPv6(value: bigint): string {
  const groups: number[] = [];
  for (let shift = 112n; shift >= 0n; shift -= 16n) groups.push(Number((value >> shift) & 0xffffn));
  let bestStart = -1;
  let bestLength = 0;
  for (let i = 0; i < 8; ) {
    if (groups[i] !== 0) {
      i++;
      continue;
    }
    let j = i;
    while (j < 8 && groups[j] === 0) j++;
    if (j - i > bestLength) {
      bestStart = i;
      bestLength = j - i;
    }
    i = j;
  }
  const hex = groups.map((g) => g.toString(16));
  if (bestLength < 2) return hex.join(':');
  const head = hex.slice(0, bestStart).join(':');
  const tail = hex.slice(bestStart + bestLength).join(':');
  return `${head}::${tail}`;
}

function formatAddress(family: 4 | 6, value: bigint): string {
  return family === 4 ? formatIPv4(value) : formatIPv6(value);
}

/**
 * The canonical form of a range: the network address (host bits cleared) in
 * its canonical text form, then the prefix. `104.28.1.0/16` gives
 * `104.28.0.0/16`; `2A09:BAC0:0::/29` gives `2a09:bac0::/29`. Null when the
 * input is not a CIDR range.
 */
export function canonicalCidr(text: string): string | null {
  const parsed = parseCidr(text);
  if (parsed === null) return null;
  return `${formatAddress(parsed.family, parsed.network)}/${parsed.prefix}`;
}

/** Whether the range as written has no host bits set (sshd matches nothing otherwise). */
export function isNetworkAddress(parsed: ParsedCidr): boolean {
  return parsed.address === parsed.network;
}

/**
 * Whether `address` falls inside `cidr`. A family mismatch is false. An
 * IPv4-mapped IPv6 address (`::ffff:a.b.c.d`) is matched as its IPv4 address,
 * as OpenSSH does before evaluating `from=`. False for unparseable input.
 */
export function cidrContains(cidr: string, address: string): boolean {
  const range = parseCidr(cidr);
  const ip = parseIpAddress(address);
  if (range === null || ip === null) return false;
  let { family, value } = ip;
  if (family === 6 && value >> 32n === 0xffffn) {
    family = 4;
    value &= 0xffffffffn;
  }
  if (family !== range.family) return false;
  return (value & maskOf(family, range.prefix)) === range.network;
}
