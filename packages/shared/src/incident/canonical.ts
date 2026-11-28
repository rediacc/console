/**
 * Canonical JSON for signed reports (D3 of PLAN-forensics-reports): sorted keys,
 * no insignificant whitespace, UTF-8, numbers only as integers (a fraction travels
 * as a decimal string). Two documents that differ only in key order or spacing
 * therefore hash to the same SHA-256.
 */

/** A value the canonical form can carry. */
export type CanonicalValue =
  | null
  | boolean
  | number
  | string
  | readonly CanonicalValue[]
  | { readonly [key: string]: CanonicalValue | undefined };

function compareKeys(a: string, b: string): number {
  if (a === b) return 0;
  return a < b ? -1 : 1;
}

function canonicalNumber(value: number): string {
  if (!Number.isSafeInteger(value)) {
    throw new TypeError(
      `canonical JSON carries integers only, got ${String(value)}; use a decimal string`
    );
  }
  return Object.is(value, -0) ? '0' : String(value);
}

function canonicalObject(record: { readonly [key: string]: CanonicalValue | undefined }): string {
  const parts: string[] = [];
  for (const key of Object.keys(record).sort(compareKeys)) {
    const member = record[key];
    if (member !== undefined) parts.push(`${JSON.stringify(key)}:${canonicalize(member)}`);
  }
  return `{${parts.join(',')}}`;
}

/** Serializes `value` canonically; throws on a non-integer number or an unsupported type. */
export function canonicalize(value: CanonicalValue): string {
  if (value === null) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number') return canonicalNumber(value);
  if (Array.isArray(value)) {
    return `[${(value as readonly CanonicalValue[]).map((v) => canonicalize(v)).join(',')}]`;
  }
  if (typeof value === 'object') return canonicalPlainObject(value);
  throw new TypeError(`canonical JSON cannot carry a ${typeof value}`);
}

/** A plain object's canonical form; a Date or class instance is refused rather than flattened. */
function canonicalPlainObject(value: object): string {
  const proto: unknown = Object.getPrototypeOf(value);
  if (proto !== Object.prototype && proto !== null) {
    throw new TypeError(
      'canonical JSON carries plain objects only; convert a Date or class instance first'
    );
  }
  return canonicalObject(value as { readonly [key: string]: CanonicalValue | undefined });
}

/** The UTF-8 bytes that are hashed and signed. */
export function canonicalBytes(value: CanonicalValue): Uint8Array {
  return new TextEncoder().encode(canonicalize(value));
}

/** Lowercase hex SHA-256 of the canonical form. */
export async function canonicalSha256(value: CanonicalValue): Promise<string> {
  const bytes = canonicalBytes(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes as Uint8Array<ArrayBuffer>);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}
