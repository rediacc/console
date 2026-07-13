// IMPORTANT: temp-config-env MUST be the first import so it redirects the
// config dir before config-file-storage captures getConfigDir(). Kept in its
// own import group (blank line below) so biome's organizeImports does not sort
// it back down into the block and reintroduce the ENOENT redirect race.
import { TEST_CONFIG_HOME } from './helpers/temp-config-env.js';

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { beforeEach, describe, expect, it } from 'vitest';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import type { RdcConfig } from '../../types/index.js';
import { configService } from '../config/config-resources.js';
import { RemoteResourceState } from '../config/resource-state.js';

const CONFIG_NAME = 'rediacc';
const GUID = 'a1111111-1111-4111-8111-111111111111';

function rawText(): string {
  return readFileSync(join(TEST_CONFIG_HOME, `${CONFIG_NAME}.json`), 'utf-8');
}
function rawFile(): RdcConfig {
  return JSON.parse(rawText()) as RdcConfig;
}

async function resetPlaintext(): Promise<void> {
  configFileStorage.clearCache();
  configService.setRuntimeConfig(null);
  await configFileStorage.update(CONFIG_NAME, (cfg) => ({
    ...cfg,
    account: undefined,
    resources: undefined,
    infra: undefined,
    state: undefined,
    encryption: { mode: 'plaintext' as const },
    credentials: undefined,
    renetPath: undefined,
  }));
  configFileStorage.clearCache();
  configService.setRuntimeConfig(null);
}

async function enableMasterPassword(): Promise<void> {
  await configFileStorage.update(CONFIG_NAME, (cfg) => ({
    ...cfg,
    credentials: { ...(cfg.credentials ?? {}), masterPasswordVerifier: 'verifier' },
    encryption: { mode: 'master-password' as const, encryptedFields: {} },
  }));
  configFileStorage.clearCache();
  configService.setRuntimeConfig(null);
}

/** Encrypted mode + every bucket + every encrypt-at-rest field kind. */
async function seedEncryptedFixture(): Promise<void> {
  await enableMasterPassword();
  await configService.addCluster('c1', {
    provider: 'hetzner',
    pools: [{ name: 'p1', role: 'k8s-server', count: 1 }],
  });
  await configService.addCloudProvider('hetzner', { apiToken: 'hz-api-token-secret' });
  await configService.setBackupStrategy('s1', { destinations: [], schedule: '0 2 * * *' });
  await configService.updateConfigFields({ cfDnsApiToken: 'cf-dns-token-secret' });

  const state = await configService.getResourceState();
  await state.setSSH({
    privateKey: '-----BEGIN OPENSSH PRIVATE KEY-----\nDEADBEEF\n-----END OPENSSH PRIVATE KEY-----',
  });
  const repos = state.getRepositories();
  repos['app:main'] = {
    repositoryGuid: GUID,
    tag: 'main',
    secrets: { STRIPE_KEY: { mode: 'env', value: 'sk_live_supersecret_value' } },
  };
  await state.setRepositories(repos);
  const machines = state.getMachines();
  machines.m1 = { ip: '10.0.0.1', user: 'deploy' };
  await state.setMachines(machines);
}

describe('persist unification (R2-F3 data-loss regression + per-field encryption)', () => {
  beforeEach(resetPlaintext);

  it('T1: cluster/provider/strategy survive an encrypted-mode repo+machine mutation', async () => {
    await seedEncryptedFixture();

    configFileStorage.clearCache();
    const resources = (rawFile().resources ?? {}) as Record<string, Record<string, unknown>>;
    expect(resources.clusters.c1).toBeDefined();
    expect(resources.cloudProviders.hetzner).toBeDefined();
    expect(resources.backupStrategies.s1).toBeDefined();
  });

  it('T2: sensitive values are encrypted at rest under concrete pointers', async () => {
    await seedEncryptedFixture();
    configFileStorage.clearCache();
    const text = rawText();

    // No plaintext secrets anywhere in the file.
    expect(text).not.toContain('hz-api-token-secret');
    expect(text).not.toContain('cf-dns-token-secret');
    expect(text).not.toContain('sk_live_supersecret_value');
    expect(text).not.toContain('BEGIN OPENSSH PRIVATE KEY');

    const enc = rawFile().encryption;
    expect(enc?.mode).toBe('master-password');
    const keys = Object.keys(enc?.encryptedFields ?? {});
    // Concrete leaf pointers, never the compound '/resources' blob.
    expect(keys).not.toContain('/resources');
    expect(keys).toContain('/resources/cloudProviders/hetzner/apiToken');
    expect(keys).toContain('/credentials/cfDnsApiToken');
    expect(keys).toContain('/credentials/ssh/privateKey');
    expect(keys).toContain('/resources/repositories/app/tags/main/secrets/STRIPE_KEY/value');
  });

  it('T3: decrypt-on-load round-trips every encrypted value', async () => {
    await seedEncryptedFixture();
    configFileStorage.clearCache();

    const decrypted = await configFileStorage.loadDecrypted(CONFIG_NAME);
    expect(decrypted.resources?.cloudProviders?.hetzner.apiToken).toBe('hz-api-token-secret');
    expect(decrypted.credentials?.cfDnsApiToken).toBe('cf-dns-token-secret');
    expect(decrypted.credentials?.ssh?.privateKey).toContain('DEADBEEF');
    expect(decrypted.resources?.repositories?.app.tags.main.secrets?.STRIPE_KEY.value).toBe(
      'sk_live_supersecret_value'
    );
  });

  it('T4: masterPasswordVerifier stays plaintext while mode is master-password', async () => {
    await enableMasterPassword();
    configFileStorage.clearCache();
    const raw = rawFile();
    expect(raw.encryption?.mode).toBe('master-password');
    expect(raw.credentials?.masterPasswordVerifier).toBe('verifier');
    expect(Object.keys(raw.encryption?.encryptedFields ?? {})).not.toContain(
      '/credentials/masterPasswordVerifier'
    );
  });

  it('T5: state writes do not bump the version counter; spec writes do', async () => {
    const v0 = (await configFileStorage.load(CONFIG_NAME)).version;

    await configFileStorage.updateState(CONFIG_NAME, (cfg) => ({
      ...cfg,
      state: { ...(cfg.state ?? {}), networkIds: { next: 3008 } },
    }));
    expect((await configFileStorage.load(CONFIG_NAME)).version).toBe(v0);

    await configFileStorage.update(CONFIG_NAME, (cfg) => ({ ...cfg, renetPath: '/opt/renet' }));
    expect((await configFileStorage.load(CONFIG_NAME)).version).toBe(v0 + 1);
  });

  it('T6: remote push includes spec buckets and excludes state', async () => {
    await configFileStorage.update(CONFIG_NAME, (cfg) => ({
      ...cfg,
      resources: {
        ...(cfg.resources ?? {}),
        clusters: {
          c1: { provider: 'hetzner', pools: [{ name: 'p1', role: 'k8s-server', count: 1 }] },
        },
      },
      state: { ...(cfg.state ?? {}), networkIds: { next: 3008 } },
    }));
    configFileStorage.clearCache();

    const config = await configFileStorage.load(CONFIG_NAME);
    let pushed: RdcConfig | undefined;
    const mockAdapter = {
      push: (doc: RdcConfig, version: number) => {
        pushed = doc;
        return Promise.resolve({ version: version + 1 });
      },
    };
    const remote = RemoteResourceState.load(
      config,
      CONFIG_NAME,
      mockAdapter as unknown as Parameters<typeof RemoteResourceState.load>[2],
      config.version,
      0
    );
    await remote.setMachines({ m1: { ip: '10.0.0.2', user: 'deploy' } });

    expect(pushed).toBeDefined();
    expect(pushed?.resources?.clusters?.c1).toBeDefined();
    expect(pushed?.resources?.machines?.m1).toBeDefined();
    expect(pushed?.state).toBeUndefined();
  });
});
