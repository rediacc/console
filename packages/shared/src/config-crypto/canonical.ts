/**
 * Canonical serialization for field-commitment hashes.
 *
 * Produces a stable byte sequence for any JSON-compatible value, such that two
 * equivalent values always serialize identically regardless of object key
 * insertion order, whitespace, or number formatting variations. This is the
 * input to HMAC when computing field commitments for the server-side envelope.
 *
 * Simpler than full RFC 8785 (no Unicode NFC normalization, no number-format
 * conformance to ES6 ToString) — sufficient for our use case because:
 *   - config values are under CLI control and go through Zod validation first
 *   - all runtimes on the wire are Node 20+ (CLI) and V8 workers (server), which
 *     agree on ES6 Number.toString behavior
 *
 * Typed prefix bytes ensure that `null` / `undefined-or-missing` / empty string /
 * empty array / empty object all produce distinct digests. This closes the
 * anti-downgrade attack where an agent could attempt to drop a sensitive field
 * (setting it to missing) to bypass the server's precondition check.
 *
 * Used by: packages/shared/src/config-crypto/commitments.ts.
 * Also mirrored (more loosely) in packages/cli/src/schema/walker.ts::canonicalJson
 * for UX fingerprints; that version is NOT interchangeable with this one.
 */

/** Typed prefix bytes — one per JSON primitive kind. Distinguishes null vs missing. */
const PREFIX_NULL = 0x00;
const PREFIX_BOOL = 0x01;
const PREFIX_NUMBER = 0x02;
const PREFIX_STRING = 0x03;
const PREFIX_ARRAY = 0x04;
const PREFIX_OBJECT = 0x05;
const PREFIX_BYTES = 0x06;
const PREFIX_MISSING = 0x07;

/**
 * Canonicalize any JSON-compatible value (plus Uint8Array) to a stable byte
 * sequence. Throws if the value contains non-serializable types (functions,
 * symbols, circular references) — callers must validate against the Zod schema
 * before canonicalizing.
 */
export function canonicalize(value: unknown): Uint8Array {
  const chunks: Uint8Array[] = [];
  writeValue(value, chunks);
  return concat(chunks);
}

function writeValue(value: unknown, out: Uint8Array[]): void {
  if (value === undefined) {
    out.push(new Uint8Array([PREFIX_MISSING]));
    return;
  }
  if (value === null) {
    out.push(new Uint8Array([PREFIX_NULL]));
    return;
  }
  if (typeof value === 'boolean') {
    out.push(new Uint8Array([PREFIX_BOOL, value ? 1 : 0]));
    return;
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new Error('Cannot canonicalize non-finite number');
    }
    out.push(new Uint8Array([PREFIX_NUMBER]));
    // ES6 Number.toString — stable on Node and V8 workers.
    out.push(new TextEncoder().encode(value.toString()));
    return;
  }
  if (typeof value === 'string') {
    out.push(new Uint8Array([PREFIX_STRING]));
    writeLengthPrefixed(new TextEncoder().encode(value), out);
    return;
  }
  if (value instanceof Uint8Array) {
    out.push(new Uint8Array([PREFIX_BYTES]));
    writeLengthPrefixed(value, out);
    return;
  }
  if (Array.isArray(value)) {
    out.push(new Uint8Array([PREFIX_ARRAY]));
    writeUint32(value.length, out);
    for (const item of value) writeValue(item, out);
    return;
  }
  if (typeof value === 'object') {
    out.push(new Uint8Array([PREFIX_OBJECT]));
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    writeUint32(entries.length, out);
    for (const [key, child] of entries) {
      writeLengthPrefixed(new TextEncoder().encode(key), out);
      writeValue(child, out);
    }
    return;
  }
  throw new Error(`Cannot canonicalize value of type ${typeof value}`);
}

function writeUint32(n: number, out: Uint8Array[]): void {
  const buf = new Uint8Array(4);
  const view = new DataView(buf.buffer);
  view.setUint32(0, n, false); // big-endian, platform-independent
  out.push(buf);
}

function writeLengthPrefixed(bytes: Uint8Array, out: Uint8Array[]): void {
  writeUint32(bytes.length, out);
  out.push(bytes);
}

function concat(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }
  return result;
}

/**
 * Typed value kind (for storing alongside the commitment HMAC).
 *
 * Having the kind in the envelope lets the server's anti-downgrade check
 * distinguish `null` (explicit absence) from `missing` (field not present) —
 * preventing agents from dropping a sensitive field to bypass preconditions.
 */
export type CommitmentValueKind =
  | 'null'
  | 'boolean'
  | 'number'
  | 'string'
  | 'array'
  | 'object'
  | 'bytes'
  | 'missing';

export function valueKind(value: unknown): CommitmentValueKind {
  if (value === undefined) return 'missing';
  if (value === null) return 'null';
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return 'number';
  if (typeof value === 'string') return 'string';
  if (value instanceof Uint8Array) return 'bytes';
  if (Array.isArray(value)) return 'array';
  return 'object';
}
