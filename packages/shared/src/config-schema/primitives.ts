/**
 * Primitive validators the config schema composes: IP and cron checks, the
 * UTF-8 byte length the secret caps use, and the name, path, domain, port and
 * UUID field schemas. Portable across Node, Workers and browsers.
 */

import { z } from 'zod';

// =============================================================================
// Primitive validators
// =============================================================================

/**
 * Portable replacement for node:net's `isIP`, so this module runs unchanged on
 * Node, Cloudflare Workers, and browsers. Same contract: 4, 6, or 0 for
 * "not an IP address". Backed by zod's own IP validators rather than a
 * hand-rolled regex.
 */
const ipv4Check = z.ipv4();
const ipv6Check = z.ipv6();

export function ipVersion(value: string): 0 | 4 | 6 {
  if (ipv4Check.safeParse(value).success) return 4;
  if (ipv6Check.safeParse(value).success) return 6;
  return 0;
}

/**
 * Byte length of a UTF-8 string without Node's Buffer, so the secret size caps
 * below evaluate identically in the browser and in Workers.
 */
const utf8Encoder = new TextEncoder();

export function utf8ByteLength(value: string): number {
  return utf8Encoder.encode(value).length;
}

const CRON_RANGES: [number, number][] = [
  [0, 59],
  [0, 23],
  [1, 31],
  [1, 12],
  [0, 7],
];

function isValidCronField(field: string, min: number, max: number): boolean {
  if (field === '*') return true;
  if (field.startsWith('*/')) {
    const step = Number.parseInt(field.slice(2), 10);
    return Number.isInteger(step) && step >= 1 && step <= max;
  }
  return field.split(',').every((part) => {
    const rangeMatch = /^(\d+)-(\d+)$/.exec(part);
    if (rangeMatch) {
      const lo = Number.parseInt(rangeMatch[1], 10);
      const hi = Number.parseInt(rangeMatch[2], 10);
      return lo >= min && hi <= max && lo <= hi;
    }
    const num = Number.parseInt(part, 10);
    return Number.isInteger(num) && num >= min && num <= max;
  });
}

export function isValidCron(expr: string): boolean {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return false;
  return parts.every((field, i) => isValidCronField(field, CRON_RANGES[i][0], CRON_RANGES[i][1]));
}

/** A resource name (machine, repository, key, cluster): lowercase alphanumeric with hyphens. */
export const resourceName = z
  .string()
  .min(1, 'Name cannot be empty')
  .max(63, 'Name must be 63 characters or fewer')
  .regex(
    /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/,
    'Must be lowercase alphanumeric with hyphens, starting and ending with alphanumeric'
  );

/**
 * A datastore registry key: `name` for a datastore, `name:tag` for a fork.
 * Unlike repositories (families, 06 §6.4), datastore forks are FLAT entries
 * with a `parent` backref, mirroring the machine-side registry which keys a
 * fork as `<parent>:<tag>` (renet pkg/datastore/registry.go).
 */
export const datastoreRef = z
  .string()
  .min(1, 'Name cannot be empty')
  .max(127, 'Ref must be 127 characters or fewer')
  .regex(
    /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(:[a-z0-9]([a-z0-9-]*[a-z0-9])?)?$/,
    'Must be lowercase alphanumeric with hyphens (name or name:tag)'
  );

/**
 * Structural repository tag. ':' and '@' are structurally impossible in a key
 * that matches this regex, which is the create-time validation for the tag
 * position (06 §6.4) — composite `name:tag` keys can no longer exist.
 */
export const TagName = z
  .string()
  .min(1)
  .max(63)
  .regex(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/, 'Tag must be lowercase alphanumeric with hyphens');

export const ipOrHostname = z
  .string()
  .min(1, 'IP address or hostname cannot be empty')
  .refine(
    (v) => ipVersion(v) !== 0 || /^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$/.test(v),
    'Must be a valid IP address or hostname'
  );

export const absolutePath = z.string().refine((v) => v.startsWith('/'), 'Must be an absolute path');

export const domain = z
  .string()
  .min(1)
  .regex(/^[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$/, 'Must be a valid domain (e.g. example.com)');

export const port = z
  .number()
  .int('Port must be an integer')
  .min(1, 'Port minimum is 1')
  .max(65535, 'Port maximum is 65535');

export const uuid = z.uuid('Must be a valid UUID');
