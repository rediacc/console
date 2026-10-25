/**
 * An empty `resources.storages` (the family retired inside schema v3) is dropped before validation;
 * a non-empty one is still refused by name.
 */

import { describe, expect, it } from 'vitest';
import { runMigrations } from '../migrations/index.js';
import { normalizeV3Document } from '../normalize.js';
import { createEmptyRdcConfig, RdcConfigSchema } from '../schemas.js';

const ctx = {
  getMasterPassword: () => Promise.reject(new Error('unused')),
  decryptLegacyBlob: () => Promise.reject(new Error('unused')),
};

function withStorages(storages: unknown): Record<string, unknown> {
  return { ...createEmptyRdcConfig(), resources: { storages } };
}

describe('normalizeV3Document', () => {
  it('drops an empty storages object without mutating the input', () => {
    const input = withStorages({});
    const out = normalizeV3Document(input) as { resources: Record<string, unknown> };
    expect('storages' in out.resources).toBe(false);
    expect('storages' in (input.resources as Record<string, unknown>)).toBe(true);
  });

  it('keeps a non-empty storages object so the schema refuses it by name', () => {
    const input = withStorages({ s1: { provider: 's3' } });
    expect(normalizeV3Document(input)).toBe(input);
    const result = RdcConfigSchema.safeParse(normalizeV3Document(input));
    expect(result.success).toBe(false);
    expect(JSON.stringify(result.error?.issues)).toContain('resources.storages was removed');
  });

  it('loads a v3 document with empty storages through runMigrations and the strict schema', async () => {
    const { config, migrated } = await runMigrations(withStorages({}), ctx);
    expect(migrated).toBe(false);
    const parsed = RdcConfigSchema.parse(config);
    expect('storages' in (parsed.resources ?? {})).toBe(false);
  });
});
