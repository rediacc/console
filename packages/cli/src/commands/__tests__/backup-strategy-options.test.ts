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
