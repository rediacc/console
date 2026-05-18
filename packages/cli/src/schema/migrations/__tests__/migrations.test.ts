import { describe, expect, it } from 'vitest';
import { RdcConfigSchema } from '../../schemas.js';
import { CURRENT_SCHEMA_VERSION, migrateV1ToV2, runMigrations } from '../index.js';

function makeV1Sample(): Record<string, unknown> {
  // A minimal valid v1 document — the v1 schema lacked the explicit
  // schemaVersion field. Everything else matches the current required
  // shape, which is what makes v1→v2 a metadata-only bump.
  return {
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 1,
    defaults: { language: 'en', datastoreSize: '95%' },
    encryption: { mode: 'plaintext' },
  };
}

describe('runMigrations', () => {
  it('treats missing schemaVersion as version 1 and upgrades to current', () => {
    const v1 = makeV1Sample();
    const result = runMigrations(v1);

    expect(result.migrated).toBe(true);
    expect(result.fromVersion).toBe(1);
    expect(result.toVersion).toBe(CURRENT_SCHEMA_VERSION);
    expect(result.config.schemaVersion).toBe(2);
  });

  it('is a no-op when input is already at current version', () => {
    const v2 = { ...makeV1Sample(), schemaVersion: 2 };
    const result = runMigrations(v2);

    expect(result.migrated).toBe(false);
    expect(result.fromVersion).toBe(CURRENT_SCHEMA_VERSION);
    expect(result.config).toBe(v2);
  });

  it('refuses to downgrade configs from a newer CLI', () => {
    const future = { ...makeV1Sample(), schemaVersion: 99 };
    expect(() => runMigrations(future)).toThrow(/newer than this CLI supports/);
  });

  it('rejects non-object roots', () => {
    expect(() => runMigrations(null)).toThrow(/must be an object/);
    expect(() => runMigrations([])).toThrow(/must be an object/);
    expect(() => runMigrations('foo')).toThrow(/must be an object/);
  });

  it('rejects invalid schemaVersion values', () => {
    expect(() => runMigrations({ schemaVersion: -1 })).toThrow(/Invalid schemaVersion/);
    expect(() => runMigrations({ schemaVersion: 1.5 })).toThrow(/Invalid schemaVersion/);
    expect(() => runMigrations({ schemaVersion: 'two' })).toThrow(/Invalid schemaVersion/);
  });

  it('produces output that passes the current RdcConfigSchema', () => {
    const v1 = makeV1Sample();
    const result = runMigrations(v1);
    const parsed = RdcConfigSchema.safeParse(result.config);
    expect(parsed.success).toBe(true);
  });
});

describe('migrateV1ToV2', () => {
  it('stamps schemaVersion: 2', () => {
    const input = { id: 'x', version: 1 };
    const out = migrateV1ToV2(input);
    expect(out.schemaVersion).toBe(2);
    expect(out.id).toBe('x');
  });

  it('is idempotent', () => {
    const input = { schemaVersion: 2, id: 'x', version: 1 };
    const once = migrateV1ToV2(input);
    const twice = migrateV1ToV2(once);
    expect(twice).toEqual(once);
  });
});
