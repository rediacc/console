/**
 * Schema-driven config walker.
 *
 * Consumes SENSITIVITY_REGISTRY (populated by schema construction) to:
 *   - enumerate every sensitive leaf in a live config (walkSensitive)
 *   - produce a redacted deep-clone for agent output (redactClone)
 *   - list concrete pointers that need field-commitment hashes (pathsToCommit)
 *   - compute a short SHA-256 fingerprint for a specific pointer (digestForPointer)
 *
 * Fingerprints produced here are UNKEYED SHA-256 — safe for UX stubs like
 * `<redacted:sha256:abc12345>` because SHA-256 preimage resistance holds.
 * The server-side FCK-keyed HMAC commitments live in
 * `packages/shared/src/config-crypto/commitments.ts`; do not conflate.
 */

import { createHash } from 'node:crypto';
import type { SensitivityMeta, PointerTemplate } from './sensitivity.js';
import { SENSITIVITY_REGISTRY } from './sensitivity.js';

/** RFC 6901 escape for a single JSON Pointer segment. */
export function escapePointerSegment(segment: string): string {
  return segment.replace(/~/g, '~0').replace(/\//g, '~1');
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
 * Short fingerprint used in redaction stubs (`<redacted:sha256:abc12345>`).
 *
 * Uses the first 8 hex chars of SHA-256 over the canonical JSON of the value.
 * `null` and missing values produce distinct fingerprints so redaction stubs
 * don't collide across those two states.
 */
export function shortFingerprint(value: unknown): string {
  const json = canonicalJson(value);
  const hash = createHash('sha256').update(json).digest('hex');
  return hash.slice(0, 8);
}

/**
 * Full SHA-256 digest of the value at a specific pointer. Returns undefined if
 * the pointer does not exist in the config.
 *
 * Used by MutationGate for the client-side knowledge check: the `--current`
 * value the agent supplied is canonicalized and hashed, then compared against
 * the digest of the currently-stored value at that pointer. Comparison is
 * constant-time irrelevant here since both sides originate on the same host.
 */
export function digestForPointer(root: unknown, pointer: string): string | undefined {
  const value = getByPointer(root, pointer);
  if (value === undefined) return undefined;
  return createHash('sha256').update(canonicalJson(value)).digest('hex');
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
    .map((s) => s.replace(/~1/g, '/').replace(/~0/g, '~'));
  let cursor: unknown = root;
  for (const segment of segments) {
    if (cursor === null || cursor === undefined) return undefined;
    if (Array.isArray(cursor)) {
      const idx = Number.parseInt(segment, 10);
      if (!Number.isFinite(idx)) return undefined;
      cursor = cursor[idx];
    } else if (typeof cursor === 'object') {
      cursor = (cursor as Record<string, unknown>)[segment];
    } else {
      return undefined;
    }
  }
  return cursor;
}

/**
 * Set a value at a JSON Pointer within a deep-cloned tree. Returns the cloned root.
 * Intermediate objects/arrays are created as needed; missing paths are a no-op on the clone.
 */
function setByPointer(root: unknown, pointer: string, newValue: unknown): unknown {
  if (pointer === '') return newValue;
  const segments = pointer
    .split('/')
    .slice(1)
    .map((s) => s.replace(/~1/g, '/').replace(/~0/g, '~'));
  const clone = deepClone(root);
  let cursor: Record<string, unknown> | unknown[] = clone as Record<string, unknown>;
  for (let i = 0; i < segments.length - 1; i++) {
    const segment = segments[i];
    if (cursor === null || cursor === undefined) return clone;
    if (Array.isArray(cursor)) {
      const idx = Number.parseInt(segment, 10);
      if (!Number.isFinite(idx) || idx < 0 || idx >= cursor.length) return clone;
      cursor = cursor[idx] as Record<string, unknown> | unknown[];
    } else {
      cursor = (cursor as Record<string, unknown>)[segment] as
        | Record<string, unknown>
        | unknown[];
    }
  }
  const last = segments[segments.length - 1];
  if (Array.isArray(cursor)) {
    const idx = Number.parseInt(last, 10);
    if (Number.isFinite(idx)) cursor[idx] = newValue;
  } else if (cursor && typeof cursor === 'object') {
    (cursor as Record<string, unknown>)[last] = newValue;
  }
  return clone;
}

/**
 * Produce a deep-cloned config with every sensitive leaf replaced by its
 * redaction stub. Public fields are passed through unchanged. Unregistered
 * leaves are passed through (fail-open for display); the CI gate
 * check:ci-schema-coverage catches missing annotations before they ship.
 */
export function redactClone<T>(config: T): T {
  let result: unknown = deepClone(config);
  for (const { pointer, value, meta } of walkSensitive(config)) {
    if (meta.kind === 'public') continue;
    const stub =
      value === null || value === undefined
        ? null
        : `${meta.redactAs ?? `<redacted:${meta.kind}>`}:${shortFingerprint(value)}`;
    result = setByPointer(result, pointer, stub);
  }
  return result as T;
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
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`);
    return `{${entries.join(',')}}`;
  }
  return String(value);
}

function deepClone<T>(v: T): T {
  if (v === null || typeof v !== 'object') return v;
  if (Array.isArray(v)) return v.map(deepClone) as unknown as T;
  const out: Record<string, unknown> = {};
  for (const [k, child] of Object.entries(v as Record<string, unknown>)) {
    out[k] = deepClone(child);
  }
  return out as T;
}
