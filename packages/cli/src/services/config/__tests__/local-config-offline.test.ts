/**
 * A LOCAL config (no `remote` block) keeps every write working with the network gone (operator
 * ruling 2026-09-25: only a REMOTE config's writes fail closed offline). Every state and synced
 * write path runs here against a real config file with `fetch` refusing every connection, and
 * none of them may reach for the config server or the remote adapter.
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { configFileStorage } from '../../../adapters/config-file-storage.js';
import { RemoteConfigAdapter } from '../../../adapters/remote-config-adapter.js';
import type { RdcConfig } from '../../../types/index.js';
import { markRefreshAttempted } from '../../account/license-refresh-state.js';
import { recordBackupRun } from '../../backup/backup-runs-state.js';
import { outputService } from '../../core/output.js';
import { recordProvisionVerified } from '../../renet/provision-state.js';
import { configService } from '../config-resources.js';
import { updateConfigAtPointer, updateSyncedConfig } from '../synced-write.js';

const NAME = 'offline-local';

function configPath(): string {
  return join(getConfigDir(), `${NAME}.json`);
}

function onDisk(): RdcConfig {
  return JSON.parse(readFileSync(configPath(), 'utf8')) as RdcConfig;
}

const fetchSpy = vi.fn(() => Promise.reject(new TypeError('fetch failed')));

beforeEach(() => {
  mkdirSync(getConfigDir(), { recursive: true });
  writeFileSync(
    configPath(),
    JSON.stringify({
      schemaVersion: 3,
      id: '0b7e4f2a-1c3d-4e5f-8a9b-0c1d2e3f4a5b',
      version: 1,
      encryption: { mode: 'plaintext' },
      resources: { machines: { m1: { ip: '10.0.0.1', user: 'root' } } },
    })
  );
  configService.setRuntimeConfig(NAME);
  vi.stubGlobal('fetch', fetchSpy);
  vi.spyOn(RemoteConfigAdapter.prototype, 'pull');
  vi.spyOn(RemoteConfigAdapter.prototype, 'push');
});

afterEach(() => {
  configService.setRuntimeConfig(null);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  fetchSpy.mockClear();
});

describe('a local config writes offline without touching a server', () => {
  it('every state writer lands in the file', async () => {
    const warn = vi.spyOn(outputService, 'warn');

    await configFileStorage.updateState(NAME, (cfg) => ({
      ...cfg,
      state: { ...(cfg.state ?? {}), networkIds: { next: 2900 } },
    }));
    await recordBackupRun('mail', { kind: 'snapshot', status: 'stored' });
    await markRefreshAttempted('m1', 1_700_000_000_000);
    await recordProvisionVerified('10.0.0.1:22', { hash: 'h', arch: 'amd64', sourcePath: null });

    const state = onDisk().state;
    expect(state?.networkIds?.next).toBe(2900);
    expect(state?.backupRuns?.mail.status).toBe('stored');
    expect(state?.licenseRefresh?.m1).toBe(1_700_000_000_000);
    expect(state?.renetProvision?.['10.0.0.1:22']?.hash).toBe('h');
    expect(warn).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(RemoteConfigAdapter.prototype.pull).not.toHaveBeenCalled();
    expect(RemoteConfigAdapter.prototype.push).not.toHaveBeenCalled();
  });

  it('every synced and device-local writer lands in the file', async () => {
    await updateSyncedConfig(NAME, (cfg) => ({ ...cfg, infra: { certEmail: 'a@example.com' } }));
    await updateConfigAtPointer(NAME, '/account/accountServer', (cfg) => ({
      ...cfg,
      account: { ...(cfg.account ?? {}), accountServer: 'https://eu.example.test' },
    }));
    await updateConfigAtPointer(NAME, '/defaults/datastoreSize', (cfg) => ({
      ...cfg,
      defaults: { ...(cfg.defaults ?? {}), datastoreSize: '5G' },
    }));
    await configService.setDefault('pruneGraceDays', '9');

    const cfg = onDisk();
    expect(cfg.infra?.certEmail).toBe('a@example.com');
    expect(cfg.account?.accountServer).toBe('https://eu.example.test');
    expect(cfg.defaults).toEqual({ datastoreSize: '5G', pruneGraceDays: 9 });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(RemoteConfigAdapter.prototype.pull).not.toHaveBeenCalled();
    expect(RemoteConfigAdapter.prototype.push).not.toHaveBeenCalled();
  });
});
