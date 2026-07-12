/**
 * Schema-driven config walker (structural half).
 *
 * Consumes SENSITIVITY_REGISTRY (populated by schema construction) to:
 *   - enumerate every sensitive leaf in a live config (walkSensitive)
 *   - read and write values by JSON Pointer (getByPointer / setByPointer)
 *   - list concrete pointers that need field-commitment hashes (pathsToCommit)
 *   - canonicalize a value for hashing (canonicalJson)
 *
 * Everything here is dependency-free and runs unchanged on Node, Cloudflare
 * Workers, and browsers, so the CLI, the executor, and the web console share
 * one implementation.
 *
 * The SHA-256 fingerprint helpers (shortFingerprint, digestForPointer,
 * redactClone) deliberately stay in packages/cli/src/schema/fingerprint.ts:
 * they need a SYNCHRONOUS hash and Web Crypto only offers an async one. Both
 * of their consumers, CLI redaction output and the MutationGate knowledge
 * check, run host-side. The browser never needs them because it holds the CEK
 * and edits real values.
 *
 * The server-side FCK-keyed HMAC commitments live in
 * `packages/shared/src/config-crypto/commitments.ts`; do not conflate.
 */

import type { PointerTemplate, SensitivityMeta } from './sensitivity.js';
import { SENSITIVITY_REGISTRY } from './sensitivity.js';

/** RFC 6901 escape for a single JSON Pointer segment. */
function escapePointerSegment(segment: string): string {
  return segment.replaceAll('~', '~0').replaceAll('/', '~1');
}

export function buildPointer(segments: string[]): string {
  if (segments.length === 0) return '';
  return `/${segments.map(escapePointerSegment).join('/')}`;
}

/**
 * Match a concrete pointer against a registry template. A template segment `*`
 * matches any single segment. All other segments must match exactly (after
 * RFC 6901 escape normalization).
 */
function matchTemplate(concrete: string, template: PointerTemplate): boolean {
  if (concrete === template) return true;
  const concreteSegments = concrete.split('/').slice(1);
  const templateSegments = template.split('/').slice(1);
  if (concreteSegments.length !== templateSegments.length) return false;
  return templateSegments.every((t, i) => t === '*' || t === concreteSegments[i]);
}

/**
 * Find the matching registry meta for a concrete pointer.
 * Returns undefined if the pointer is not registered (treat as public/unknown).
 */
export function metaForPointer(pointer: string): SensitivityMeta | undefined {
  const direct = SENSITIVITY_REGISTRY.get(pointer);
  if (direct) return direct;
  for (const [template, meta] of SENSITIVITY_REGISTRY) {
    if (template.includes('*') && matchTemplate(pointer, template)) {
      return meta;
    }
  }
  return undefined;
}

export interface WalkEntry {
  pointer: string;
  value: unknown;
  meta: SensitivityMeta;
}

/**
 * Walk the config value tree, yielding an entry for every leaf whose pointer
 * is registered in SENSITIVITY_REGISTRY. Non-registered leaves are skipped.
 *
 * "Leaf" = primitive, array of primitives, or explicitly registered object
 * (if a template matches a container path, the container is treated as a leaf).
 */
export function* walkSensitive(root: unknown): Generator<WalkEntry> {
  yield* walkInternal(root, []);
}

function* walkInternal(value: unknown, path: string[]): Generator<WalkEntry> {
  const pointer = buildPointer(path);
  const meta = pointer === '' ? undefined : metaForPointer(pointer);
  if (meta) {
    yield { pointer, value, meta };
    return;
  }
  if (value === null || value === undefined) return;
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) {
      yield* walkInternal(value[i], [...path, String(i)]);
    }
    return;
  }
  if (typeof value === 'object') {
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      yield* walkInternal(child, [...path, key]);
    }
  }
}

/**
 * Advance a cursor by one segment. Returns `undefined` to signal the path
 * does not exist (either the cursor is not traversable or the index is out of
 * range). Used by `getByPointer` to keep its loop body flat.
 */
function advanceCursorRead(cursor: unknown, segment: string): { next: unknown } | undefined {
  if (cursor === null || cursor === undefined) return undefined;
  if (Array.isArray(cursor)) {
    const idx = Number.parseInt(segment, 10);
    if (!Number.isFinite(idx)) return undefined;
    return { next: cursor[idx] };
  }
  if (typeof cursor === 'object') {
    return { next: (cursor as Record<string, unknown>)[segment] };
  }
  return undefined;
}

/**
 * Resolve a JSON Pointer against a value tree. Returns undefined for missing paths.
 * Handles RFC 6901 escapes (`~0` → `~`, `~1` → `/`).
 */
export function getByPointer(root: unknown, pointer: string): unknown {
  if (pointer === '') return root;
  const segments = pointer
    .split('/')
    .slice(1)
    .map((s) => s.replaceAll('~1', '/').replaceAll('~0', '~'));
  let cursor: unknown = root;
  for (const segment of segments) {
    const result = advanceCursorRead(cursor, segment);
    if (result === undefined) return undefined;
    cursor = result.next;
  }
  return cursor;
}

/**
 * Advance a mutable cursor (Record or Array) by one intermediate segment.
 * Returns the child container, or `undefined` if traversal should abort
 * (invalid array index or out-of-bounds).
 */
function advanceCursorWrite(
  cursor: Record<string, unknown> | unknown[],
  segment: string
): Record<string, unknown> | unknown[] | undefined {
  if (Array.isArray(cursor)) {
    const idx = Number.parseInt(segment, 10);
    if (!Number.isFinite(idx) || idx < 0 || idx >= cursor.length) return undefined;
    return cursor[idx] as Record<string, unknown> | unknown[];
  }
  return cursor[segment] as Record<string, unknown> | unknown[];
}

/**
 * Write `newValue` at `pointer` within a mutable cursor (Record or Array).
 */
function writeAtLeaf(
  cursor: Record<string, unknown> | unknown[],
  segment: string,
  newValue: unknown
): void {
  if (Array.isArray(cursor)) {
    const idx = Number.parseInt(segment, 10);
    if (Number.isFinite(idx)) cursor[idx] = newValue;
  } else {
    cursor[segment] = newValue;
  }
}

/**
 * Set a value at a JSON Pointer within a deep-cloned tree. Returns the cloned root.
 * Intermediate objects/arrays are created as needed; missing paths are a no-op on the clone.
 */
export function setByPointer(root: unknown, pointer: string, newValue: unknown): unknown {
  if (pointer === '') return newValue;
  const segments = pointer
    .split('/')
    .slice(1)
    .map((s) => s.replaceAll('~1', '/').replaceAll('~0', '~'));
  const clone = deepClone(root);
  let cursor: Record<string, unknown> | unknown[] = clone as Record<string, unknown>;
  for (let i = 0; i < segments.length - 1; i++) {
    const next = advanceCursorWrite(cursor, segments[i]);
    if (next === undefined) return clone;
    cursor = next;
  }
  writeAtLeaf(cursor, segments[segments.length - 1], newValue);
  return clone;
}

/**
 * List concrete pointers whose values should be included in the field-commitment
 * envelope (server-side precondition enforcement). Excludes `public` fields.
 */
export function pathsToCommit(config: unknown): string[] {
  const out: string[] = [];
  for (const { pointer, meta } of walkSensitive(config)) {
    if (meta.commit !== false && meta.kind !== 'public') out.push(pointer);
  }
  return out.sort();
}

/** Stable comparator for string keys used in canonical JSON sorting. */
function compareStrings(a: string, b: string): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

/**
 * Canonical JSON for hashing.
 *
 * Sort keys; no whitespace; use reserved string-literal type markers to
 * distinguish `null` / `undefined`-or-missing from empty-string and empty-array.
 * Kept simple (plain-text markers, no binary bytes) so call sites can
 * recompute the same hash with a trivial JS/shell one-liner.
 *
 * The server-side commitment canonicalization in
 * packages/shared/src/config-crypto/canonical.ts uses typed prefix bytes for
 * stronger collision resistance. The two canonical forms are NOT
 * interchangeable; this one is only used for in-process UX fingerprints.
 */
export function canonicalJson(value: unknown): string {
  if (value === null) return '@null';
  if (value === undefined) return '@undef';
  if (typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => compareStrings(a, b))
      .map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`);
    return `{${entries.join(',')}}`;
  }
  return String(value);
}

/**
 * Structural deep clone (plain JSON values only). Exported because the CLI's
 * fingerprint module builds redacted clones on top of it.
 */
export function deepClone<T>(v: T): T {
  if (v === null || typeof v !== 'object') return v;
  if (Array.isArray(v)) return v.map(deepClone) as unknown as T;
  const out: Record<string, unknown> = {};
  for (const [k, child] of Object.entries(v as Record<string, unknown>)) {
    out[k] = deepClone(child);
  }
  return out as T;
}
