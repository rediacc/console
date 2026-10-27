import { describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '../../types/index.js';
import { changedPointers, explainVersions } from '../config/push-visibility.js';

function cfg(machines: Record<string, unknown>, extra: Record<string, unknown> = {}): RdcConfig {
  return { schemaVersion: 3, resources: { machines }, ...extra } as unknown as RdcConfig;
}

describe('config remote versions --explain', () => {
  it('diffs each kept version against the next older one, newest first', async () => {
    const docs: Record<number, RdcConfig> = {
      1: cfg({ a: { ip: '1' } }),
      2: cfg({ a: { ip: '1' }, b: { ip: '2' } }),
      3: cfg({ a: { ip: '9' }, b: { ip: '2' } }),
    };
    const pullVersion = vi.fn((v: number) => Promise.resolve({ config: docs[v], version: v }));
    const rows = await explainVersions({ pullVersion } as never, [
      { version: 3, archivedAt: 't3', sdkEpoch: 1 },
      { version: 2, archivedAt: 't2', sdkEpoch: 1 },
      { version: 1, archivedAt: 't1', sdkEpoch: 1 },
    ]);
    expect(rows.map((r) => r.version)).toEqual([3, 2, 1]);
    expect(rows[0].changes).toBe('/resources/machines/a/ip');
    expect(rows[1].changes).toBe('/resources/machines/b');
    expect(rows[2].changes).toBeNull();
  });

  it('degrades per version: an unreadable one gets a row with the reason, the rest still diff', async () => {
    const docs: Record<number, RdcConfig> = {
      1: cfg({ a: { ip: '1' } }),
      3: cfg({ a: { ip: '1' }, c: { ip: '3' } }),
    };
    const pullVersion = vi.fn((v: number) =>
      v === 2
        ? Promise.reject(new Error('key slot rotated'))
        : Promise.resolve({ config: docs[v], version: v })
    );
    const rows = await explainVersions({ pullVersion } as never, [
      { version: 3, archivedAt: 't3', sdkEpoch: 1 },
      { version: 2, archivedAt: 't2', sdkEpoch: 1 },
      { version: 1, archivedAt: 't1', sdkEpoch: 1 },
    ]);
    expect(rows.map((r) => r.version)).toEqual([3, 2, 1]);
    expect(rows[0].changes).toBe('/resources/machines/c');
    expect(rows[1]).toMatchObject({ changes: null, unreadable: 'key slot rotated' });
    expect(rows[2].changes).toBeNull();
  });

  it('escapes pointer segments', () => {
    expect(changedPointers({ 'a/b': 1 }, { 'a/b': 2 })).toEqual(['/a~1b']);
  });
});
