/**
 * `rdc config remote disable` turns the cache back into a plain local config. The pull carries no host-local
 * sections, so the written file must take them from the local copy through `overlayHostLocal`
 * (PLAN-config-sync-hardening T3): networkIds, renetPath, the master-password verifier, the encryption mode and
 * unknown top-level keys all survive, and only the remote pointer goes.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RdcConfig } from '../../types/index.js';

const { mockPull, fileState, secureDelete, tokenDelete } = vi.hoisted(() => ({
  mockPull: vi.fn(),
  fileState: { current: undefined as unknown },
  secureDelete: vi.fn(() => Promise.resolve()),
  tokenDelete: vi.fn(() => Promise.resolve()),
}));

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    load: () => Promise.resolve(fileState.current),
    loadDecrypted: () => Promise.resolve(fileState.current),
    update: (_name: string, updater: (c: RdcConfig) => RdcConfig) => {
      fileState.current = updater(structuredClone(fileState.current) as RdcConfig);
      return Promise.resolve(fileState.current);
    },
    save: () => Promise.reject(new Error('disable must write through update(), under the lock')),
  },
}));

vi.mock('../../adapters/remote-config-adapter.js', () => ({
  RemoteConfigAdapter: class {
    pull = mockPull;
  },
  RemoteUnreachableError: class RemoteUnreachableError extends Error {},
}));

vi.mock('../../adapters/remote-token-storage.js', () => ({
  remoteTokenStorage: { delete: tokenDelete },
}));

vi.mock('../../utils/secure-storage.js', () => ({
  getSecureStorage: () => ({ delete: secureDelete }),
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getEffectiveConfigName: () => 'rediacc' },
}));

vi.mock('../../services/core/output.js', () => ({
  outputService: { success: vi.fn(), info: vi.fn(), warn: vi.fn() },
}));

const { registerRemoteCommands } = await import('../config-remote.js');

function localCache(): RdcConfig {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    version: 7,
    schemaVersion: 3,
    remote: {
      apiUrl: 'https://account.test',
      storeId: 'store-1',
      configId: 'cfg-1',
      storageKeyId: 'sk-1',
    },
    renetPath: '/opt/dev/renet',
    encryption: { mode: 'master-password' },
    credentials: { masterPasswordVerifier: 'mpv-hash' },
    defaults: { language: 'de' },
    state: { repos: { 'mail@m1': { networkId: 2816 } } },
    fromANewerCli: { keep: true },
  } as unknown as RdcConfig;
}

function pulled(): RdcConfig {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    version: 12,
    schemaVersion: 3,
    encryption: { mode: 'plaintext' },
    defaults: { language: 'en', universalUser: 'rediacc' },
    machines: { m1: { ip: '10.0.0.1', user: 'root' } },
  } as unknown as RdcConfig;
}

async function runDisable(): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRemoteCommands(program);
  await program.parseAsync(['node', 'rdc', 'remote', 'disable']);
}

describe('config remote disable', () => {
  beforeEach(() => {
    fileState.current = localCache();
    mockPull.mockResolvedValue({ config: pulled(), version: 12 });
  });

  it('keeps every host-local section and drops only the remote pointer', async () => {
    await runDisable();
    const written = fileState.current as Record<string, unknown> & RdcConfig;

    expect(written.remote).toBeUndefined();
    expect(written.machines).toEqual({ m1: { ip: '10.0.0.1', user: 'root' } });
    expect(
      (written.state as { repos: Record<string, { networkId: number }> }).repos['mail@m1'].networkId
    ).toBe(2816);
    expect(written.renetPath).toBe('/opt/dev/renet');
    expect(written.encryption).toEqual({ mode: 'master-password' });
    expect(written.credentials?.masterPasswordVerifier).toBe('mpv-hash');
    expect(written.fromANewerCli).toEqual({ keep: true });
    expect(written.defaults?.language).toBe('de');
    expect(tokenDelete).toHaveBeenCalledWith('rediacc');
    expect(secureDelete).toHaveBeenCalledWith('sk-1');
  });
});
