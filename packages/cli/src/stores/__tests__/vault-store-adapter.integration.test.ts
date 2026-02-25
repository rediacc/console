import { randomBytes } from 'node:crypto';
import { describe, it, expect, afterAll, beforeAll } from 'vitest';
import { VaultStoreAdapter } from '../vault-store-adapter.js';
import type { RdcConfig } from '../../types/index.js';

/**
 * Integration tests for VaultStoreAdapter.
 * Requires a running HashiCorp Vault instance:
 *
 *   docker run -d --name vault-test -p 8200:8200 \
 *     -e VAULT_DEV_ROOT_TOKEN_ID=myroot \
 *     -e VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200 \
 *     hashicorp/vault
 *
 * Environment variables:
 *   VAULT_ADDR  - Vault address (default: http://localhost:8200)
 *   VAULT_TOKEN - Vault token (default: myroot)
 */

const VAULT_ADDR = process.env.VAULT_ADDR ?? 'http://localhost:8200';
const VAULT_TOKEN = process.env.VAULT_TOKEN ?? 'myroot';

// Use a unique prefix per test run to avoid collisions
const TEST_PREFIX = `test-${Date.now()}-${randomBytes(4).toString('hex')}`;

function makeAdapter(overrides?: { vaultPrefix?: string }): VaultStoreAdapter {
  return new VaultStoreAdapter({
    name: 'test-vault',
    type: 'vault',
    vaultAddr: VAULT_ADDR,
    vaultToken: VAULT_TOKEN,
    vaultPrefix: overrides?.vaultPrefix ?? TEST_PREFIX,
  });
}

function makeConfig(id: string, version: number): RdcConfig {
  return {
    id,
    version,
    machines: { [`m-${version}`]: { ip: '10.0.0.1', user: 'root' } },
  };
}

/** Clean up all test secrets by deleting the metadata at the prefix */
async function cleanupPrefix(prefix: string): Promise<void> {
  // List all keys under the prefix
  const listUrl = `${VAULT_ADDR}/v1/secret/metadata/${prefix}?list=true`;
  const listRes = await fetch(listUrl, {
    headers: { 'X-Vault-Token': VAULT_TOKEN },
  });
  if (!listRes.ok) return;

  const body = (await listRes.json()) as { data?: { keys?: string[] } };
  const keys = body.data?.keys ?? [];

  // Delete each key's metadata (permanent delete)
  for (const key of keys) {
    if (key.endsWith('/')) continue; // skip subdirectories
    const url = `${VAULT_ADDR}/v1/secret/metadata/${prefix}/${key}`;
    await fetch(url, {
      method: 'DELETE',
      headers: { 'X-Vault-Token': VAULT_TOKEN },
    });
  }
}

describe('VaultStoreAdapter (integration)', () => {
  const adapter = makeAdapter();

  beforeAll(async () => {
    // Verify Vault is reachable
    const health = await fetch(`${VAULT_ADDR}/v1/sys/health`).catch(() => null);
    if (!health?.ok) {
      throw new Error(
        `Vault not reachable at ${VAULT_ADDR}. ` +
          'Start with: docker run -d -p 8200:8200 -e VAULT_DEV_ROOT_TOKEN_ID=myroot -e VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200 hashicorp/vault'
      );
    }
  });

  afterAll(async () => {
    await cleanupPrefix(TEST_PREFIX);
  });

  it('verify() returns true for healthy Vault', async () => {
    const ok = await adapter.verify();
    expect(ok).toBe(true);
  });

  it('full lifecycle: push → pull → list → delete', async () => {
    const config = makeConfig('lifecycle-id-1', 1);

    // Push
    const pushResult = await adapter.push(config, 'lifecycle-test');
    expect(pushResult.success).toBe(true);
    expect(pushResult.remoteVersion).toBe(1);

    // Pull
    const pullResult = await adapter.pull('lifecycle-test');
    expect(pullResult.success).toBe(true);
    expect(pullResult.config?.id).toBe('lifecycle-id-1');
    expect(pullResult.config?.version).toBe(1);
    expect(pullResult.config?.machines).toBeDefined();

    // List
    const names = await adapter.list();
    expect(names).toContain('lifecycle-test');

    // Delete
    const deleteResult = await adapter.delete('lifecycle-test');
    expect(deleteResult.success).toBe(true);

    // Verify gone
    const pullAfterDelete = await adapter.pull('lifecycle-test');
    expect(pullAfterDelete.success).toBe(false);
    expect(pullAfterDelete.error).toContain('not found');
  });

  it('conflict detection: version and GUID', async () => {
    const configV1 = makeConfig('conflict-id-1', 1);
    const configV2 = { ...configV1, version: 2 };
    const otherConfig = makeConfig('conflict-id-other', 1);

    // Push v1
    const first = await adapter.push(configV1, 'conflict-test');
    expect(first.success).toBe(true);

    // Push same version again (should succeed — version equal, not greater)
    const sameVersion = await adapter.push(configV1, 'conflict-test');
    expect(sameVersion.success).toBe(true);

    // Push v2 (should succeed — version is higher)
    const second = await adapter.push(configV2, 'conflict-test');
    expect(second.success).toBe(true);

    // Push with lower version (should fail — remote v2 > local v1)
    const conflict = await adapter.push(configV1, 'conflict-test');
    expect(conflict.success).toBe(false);
    expect(conflict.error).toContain('Version conflict');

    // Push with different GUID (should fail)
    const guidConflict = await adapter.push(otherConfig, 'conflict-test');
    expect(guidConflict.success).toBe(false);
    expect(guidConflict.error).toContain('GUID mismatch');

    // Cleanup
    await adapter.delete('conflict-test');
  });

  it('multiple configs: push and list', async () => {
    const prodConfig = makeConfig('multi-prod-id', 1);
    const stagingConfig = makeConfig('multi-staging-id', 1);

    await adapter.push(prodConfig, 'multi-production');
    await adapter.push(stagingConfig, 'multi-staging');

    const names = await adapter.list();
    expect(names).toContain('multi-production');
    expect(names).toContain('multi-staging');

    // Cleanup
    await adapter.delete('multi-production');
    await adapter.delete('multi-staging');
  });

  it('pull returns not-found for nonexistent config', async () => {
    const result = await adapter.pull('does-not-exist');
    expect(result.success).toBe(false);
    expect(result.error).toContain('not found');
  });

  it('list returns empty array when prefix has no secrets', async () => {
    const emptyAdapter = makeAdapter({ vaultPrefix: `empty-${Date.now()}` });
    const names = await emptyAdapter.list();
    expect(names).toEqual([]);
  });
});
