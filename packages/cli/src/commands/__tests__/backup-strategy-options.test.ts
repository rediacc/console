/**
 * `--target <storeId>` reaches the stored destination, and the removed `endpoint` / `vaultContent` fields are refused
 * with a message naming the replacement.
 */
import { describe, expect, it } from 'vitest';
import { BackupDestinationSchema } from '../../utils/config-schema.js';
import { buildDestination } from '../backup-strategy-options.js';

describe('buildDestination target', () => {
  it('carries --target into the destination', () => {
    expect(buildDestination({ destinationName: 'west', target: 'eu-west' })).toMatchObject({
      kind: 'hosted-service',
      name: 'west',
      target: 'eu-west',
    });
  });

  it('omits target when the flag is absent, so a merge keeps the stored one', () => {
    expect('target' in buildDestination({ destinationName: 'west', enabled: false })).toBe(false);
  });

  it('refuses a target that is not a store id', () => {
    expect(() => buildDestination({ destinationName: 'west', target: 'Bad Id' })).toThrow();
  });
});

describe('removed destination fields', () => {
  const base = { kind: 'hosted-service', name: 'd' };

  it.each(['endpoint', 'vaultContent'])(
    'refuses %s and names target as the replacement',
    (field) => {
      const result = BackupDestinationSchema.safeParse({
        ...base,
        [field]: field === 'endpoint' ? 'https://s3' : {},
      });
      expect(result.success).toBe(false);
      expect(JSON.stringify(result.error?.issues)).toMatch(/no longer carries/);
      expect(JSON.stringify(result.error?.issues)).toMatch(/target/);
    }
  );

  it('parses a plain destination', () => {
    expect(BackupDestinationSchema.safeParse({ ...base, target: 'home' }).success).toBe(true);
  });
});

describe('buildDestination --replicate-from', () => {
  it('stores a replicate destination with its source', () => {
    expect(
      buildDestination({ destinationName: 'copy', target: 'eu-west', replicateFrom: 'home' })
    ).toMatchObject({ mode: 'replicate', from: 'home', target: 'eu-west' });
  });

  it('omits mode and from when the flag is absent', () => {
    const built = buildDestination({ destinationName: 'copy', target: 'eu-west' });
    expect('mode' in built).toBe(false);
    expect('from' in built).toBe(false);
  });

  it('refuses a source that is not a store id', () => {
    expect(() => buildDestination({ destinationName: 'c', replicateFrom: 'Bad Id' })).toThrow();
  });
});

describe('destination mode and from in the schema', () => {
  const base = { kind: 'hosted-service', name: 'd', target: 'eu-west' };

  it('requires from for replicate', () => {
    const result = BackupDestinationSchema.safeParse({ ...base, mode: 'replicate' });
    expect(result.success).toBe(false);
    expect(JSON.stringify(result.error?.issues)).toMatch(/needs `from`/);
  });

  it('refuses from on an upload destination, explicit or implied', () => {
    expect(BackupDestinationSchema.safeParse({ ...base, from: 'home' }).success).toBe(false);
    expect(
      BackupDestinationSchema.safeParse({ ...base, mode: 'upload', from: 'home' }).success
    ).toBe(false);
  });

  it('admits replicate with from, and an explicit upload without it', () => {
    expect(
      BackupDestinationSchema.safeParse({ ...base, mode: 'replicate', from: 'home' }).success
    ).toBe(true);
    expect(BackupDestinationSchema.safeParse({ ...base, mode: 'upload' }).success).toBe(true);
  });
});
