import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockPullOrPurge, mockWriteRemoteCache } = vi.hoisted(() => ({
  mockPullOrPurge: vi.fn(),
  mockWriteRemoteCache: vi.fn(),
}));

vi.mock('../config/remote-cache.js', () => ({
  pullOrPurge: mockPullOrPurge,
  writeRemoteCache: mockWriteRemoteCache,
}));

import type { RemoteConfigAdapter } from '../../adapters/remote-config-adapter.js';
import type { RdcConfig } from '../../types/index.js';
import { ValidationError } from '../../utils/errors.js';
import { parseVersionArgument, restoreRemoteVersion } from '../config/remote-restore.js';

function doc(machines: string[], next?: number): RdcConfig {
  return {
    schemaVersion: 3,
    id: 'c',
    version: 1,
    resources: { machines: Object.fromEntries(machines.map((m) => [m, { ip: '10.0.0.1' }])) },
    ...(next === undefined ? {} : { state: { networkIds: { next } } }),
  } as unknown as RdcConfig;
}

function adapterWith(old: RdcConfig) {
  return {
    pullVersion: vi.fn((version: number) => Promise.resolve({ config: old, version, sdkEpoch: 1 })),
    push: vi.fn((_config: RdcConfig, _version: number, _options: unknown) =>
      Promise.resolve({ version: 4 })
    ),
  };
}

describe('config remote restore (T16)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('pushes the old content on top of the current version, with the current copy as base and the restored version named', async () => {
    const current = doc(['alpha', 'gamma'], 12);
    mockPullOrPurge.mockResolvedValueOnce({ config: current, version: 3, sdkEpoch: 1 });
    const adapter = adapterWith(doc(['alpha', 'beta'], 5));

    const result = await restoreRemoteVersion(adapter as unknown as RemoteConfigAdapter, 'cfg', 1);

    expect(result).toEqual({ restoredFrom: 1, replaced: 3, version: 4 });
    const [pushed, version, options] = adapter.push.mock.calls[0] as unknown as [
      RdcConfig,
      number,
      { base: RdcConfig; restoredFromVersion: number },
    ];
    expect(version).toBe(3);
    expect(options).toEqual({ base: current, restoredFromVersion: 1 });
    expect(Object.keys(pushed.resources?.machines ?? {})).toEqual(['alpha', 'beta']);
    // The network-ID allocator never moves back.
    expect(pushed.state?.networkIds?.next).toBe(12);
    expect(mockWriteRemoteCache).toHaveBeenCalledWith('cfg', pushed, 4);
  });

  it('keeps a higher allocator of the old copy', async () => {
    mockPullOrPurge.mockResolvedValueOnce({ config: doc([], 3), version: 3, sdkEpoch: 1 });
    const adapter = adapterWith(doc([], 9));
    await restoreRemoteVersion(adapter as unknown as RemoteConfigAdapter, 'cfg', 1);
    const pushed = adapter.push.mock.calls[0]?.[0];
    expect(pushed.state?.networkIds?.next).toBe(9);
  });

  it('writes nothing when the confirmation is declined', async () => {
    mockPullOrPurge.mockResolvedValueOnce({ config: doc(['alpha']), version: 3, sdkEpoch: 1 });
    const adapter = adapterWith(doc(['beta']));
    const confirm = vi.fn(() => Promise.resolve(false));

    await expect(
      restoreRemoteVersion(adapter as unknown as RemoteConfigAdapter, 'cfg', 2, confirm)
    ).resolves.toBeNull();
    expect(confirm).toHaveBeenCalledWith(3);
    expect(adapter.push).not.toHaveBeenCalled();
    expect(mockWriteRemoteCache).not.toHaveBeenCalled();
  });

  it('refuses to restore the current version', async () => {
    mockPullOrPurge.mockResolvedValueOnce({ config: doc(['alpha']), version: 3, sdkEpoch: 1 });
    const adapter = adapterWith(doc(['beta']));
    await expect(
      restoreRemoteVersion(adapter as unknown as RemoteConfigAdapter, 'cfg', 3)
    ).rejects.toBeInstanceOf(ValidationError);
    expect(adapter.pullVersion).not.toHaveBeenCalled();
  });

  it.each(['0', '-1', '1.5', 'v2', '', '99999999999'])('rejects the version argument %j', (raw) => {
    expect(() => parseVersionArgument(raw)).toThrow(ValidationError);
  });

  it('accepts a positive whole number', () => {
    expect(parseVersionArgument('17')).toBe(17);
  });
});
