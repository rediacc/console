/**
 * Config sync has ONE exclusion list (T17, operator ruling 2026-09-25): every key of a config
 * document travels to the server except the pointers in DEVICE_LOCAL_POINTERS.
 *
 * The gate is measured, not declared. A document with every top-level key of RdcConfigSchema, and
 * every child of the hoisted roots (`resources`, `credentials`), is pushed through the real
 * projection and rebuilt by the real inverse. A key that does not come back is a key some list is
 * still dropping (how `renetPath`, `state.repos[*].networkId` (F3) and `policy` were lost); a new
 * schema key syncs by default, and this test fails if it does not. The other direction: an excluded
 * pointer that no longer names a schema node is a stale exclusion, and fails here too.
 */

import { describe, expect, it } from 'vitest';
import { fullConfigToRdcConfig } from '../../config-crypto/rotation.js';
import { toFullConfig } from '../payload.js';
import type { RdcConfig } from '../schemas.js';
import { RdcConfigSchema } from '../schemas.js';
import { DEVICE_LOCAL_POINTERS, SENSITIVITY_REGISTRY } from '../sensitivity.js';

const EXCLUDED: readonly string[] = DEVICE_LOCAL_POINTERS;
const HOISTED = ['resources', 'credentials'] as const;

function segments(pointer: string): string[] {
  return pointer.split('/').slice(1);
}

/** The object shape under a top-level key, unwrapping `.optional()`; undefined for non-objects. */
function childKeys(root: string): string[] | undefined {
  let schema = (RdcConfigSchema.shape as Record<string, unknown>)[root] as {
    unwrap?: () => unknown;
    shape?: Record<string, unknown>;
  };
  while (schema.unwrap && !schema.shape) schema = schema.unwrap() as typeof schema;
  return schema.shape ? Object.keys(schema.shape) : undefined;
}

/**
 * Every top-level key and every hoisted child present, each with a distinct marker value, so a
 * dropped or misplaced key is visible. The round trip is structural (no schema parse), which is
 * what lets one marker per key stand in for real content.
 */
function everyKeyPopulated(): Record<string, unknown> {
  const doc: Record<string, unknown> = {};
  for (const key of Object.keys(RdcConfigSchema.shape)) doc[key] = { marker: `/${key}` };
  doc.schemaVersion = 3;
  doc.id = '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f';
  doc.version = 5;
  for (const root of HOISTED) {
    doc[root] = Object.fromEntries(
      (childKeys(root) ?? []).map((child) => [child, { marker: `/${root}/${child}` }])
    );
  }
  doc['x-future-section'] = { marker: '/x-future-section' };
  return doc;
}

function roundTrip(doc: Record<string, unknown>): Record<string, unknown> {
  const full = toFullConfig(doc as unknown as RdcConfig, { version: 6, sdkEpoch: 1 });
  // The blob is JSON: whatever cannot survive serialization does not sync.
  return fullConfigToRdcConfig(JSON.parse(JSON.stringify(full))) as unknown as Record<
    string,
    unknown
  >;
}

/** Every pointer of the populated document, one level into the hoisted roots. */
function populatedPointers(doc: Record<string, unknown>): string[] {
  return Object.keys(doc).flatMap((key) =>
    (HOISTED as readonly string[]).includes(key)
      ? Object.keys(doc[key] as object).map((child) => `/${key}/${child}`)
      : [`/${key}`]
  );
}

function valueAt(doc: Record<string, unknown>, pointer: string): unknown {
  return segments(pointer).reduce<unknown>(
    (node, part) => (node as Record<string, unknown> | undefined)?.[part],
    doc
  );
}

describe('device-local registry: every config key syncs unless listed', () => {
  const doc = everyKeyPopulated();
  const rebuilt = roundTrip(doc);
  // The envelope carries these; the rebuilt document takes them from the envelope, not the blob.
  const envelope = new Set(['/id', '/version', '/schemaVersion']);

  it('the fixture populates every top-level key and every hoisted child (control)', () => {
    const pointers = populatedPointers(doc);
    const expected = Object.keys(RdcConfigSchema.shape).flatMap((key) =>
      (HOISTED as readonly string[]).includes(key)
        ? (childKeys(key) ?? []).map((child) => `/${key}/${child}`)
        : [`/${key}`]
    );
    for (const root of HOISTED) expect(childKeys(root)?.length, root).toBeGreaterThan(0);
    expect(pointers).toEqual(expect.arrayContaining([...expected, '/state']));
  });

  it('every key not in DEVICE_LOCAL_POINTERS comes back unchanged after push and pull', () => {
    const dropped = populatedPointers(doc)
      .filter((p) => !EXCLUDED.includes(p) && !envelope.has(p))
      .filter((p) => JSON.stringify(valueAt(rebuilt, p)) !== JSON.stringify(valueAt(doc, p)));
    expect(dropped, `synced keys lost or changed by the round trip: ${dropped.join(', ')}`).toEqual(
      []
    );
  });

  it('no excluded pointer travels', () => {
    const full = toFullConfig(doc as unknown as RdcConfig, { version: 6, sdkEpoch: 1 });
    const blob = JSON.stringify(full);
    const leaked = EXCLUDED.filter((p) => !envelope.has(p) && blob.includes(`"marker":"${p}"`));
    expect(leaked).toEqual([]);
    // The rebuilt document has no value of this device at an excluded pointer (encryption comes
    // back only as the plaintext placeholder the device overlay replaces).
    expect(rebuilt.remote).toBeUndefined();
    expect(rebuilt.renetPath).toBeUndefined();
    expect((rebuilt.credentials as Record<string, unknown>).masterPasswordVerifier).toBeUndefined();
    expect(rebuilt.encryption).toEqual({ mode: 'plaintext' });
  });

  it('names only real schema nodes (no stale exclusion)', () => {
    const topKeys = Object.keys(RdcConfigSchema.shape);
    const stale = EXCLUDED.filter((p) => {
      const [root, ...rest] = segments(p);
      if (!topKeys.includes(root)) return true;
      return rest.length > 0 && !(childKeys(root) ?? []).includes(rest[0]);
    });
    expect(stale).toEqual([]);
  });

  it('keeps every exclusion one or two segments deep', () => {
    expect(EXCLUDED.filter((p) => segments(p).length > 2)).toEqual([]);
  });

  it('the wire encoding cannot fold two document paths onto one blob key', () => {
    const hoistedChildren = HOISTED.flatMap((root) => childKeys(root) ?? []);
    const topLevel = Object.keys(RdcConfigSchema.shape).filter(
      (k) => !(HOISTED as readonly string[]).includes(k)
    );
    const all = [...hoistedChildren, ...topLevel];
    expect(all.filter((k, i) => all.indexOf(k) !== i)).toEqual([]);
  });

  it('commits nothing under an excluded pointer (committed means carried)', () => {
    const committed = [...SENSITIVITY_REGISTRY.entries()]
      .filter(([, meta]) => meta.commit)
      .map(([template]) => template)
      .filter((template) => EXCLUDED.some((p) => template === p || template.startsWith(`${p}/`)));
    expect(committed).toEqual([]);
  });
});
