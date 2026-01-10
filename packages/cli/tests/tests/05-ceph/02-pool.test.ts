/**
 * Ceph Pool CLI Tests
 *
 * Tests for Ceph pool CRUD operations and vault management.
 */

import { expect, test } from '@playwright/test';
import {
  createEditionContext,
  EditionErrorPatterns,
  type EditionTestContext,
  expectEditionError,
  expectEditionSuccess,
  uniqueName,
} from '../../src/utils/edition';

test.describe('Ceph Pool Commands @cli @ceph', () => {
  test.describe('ENTERPRISE edition - pool operations', () => {
    let ctx: EditionTestContext;
    let teamName: string;
    let clusterName: string;
    const createdPools: string[] = [];

    test.beforeAll(async () => {
      ctx = await createEditionContext('ENTERPRISE');

      // Get team
      const teamResult = await ctx.runner.teamList();
      const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
      teamName = teams[0]?.teamName ?? 'Private Team';

      // Create a cluster for pool tests
      clusterName = uniqueName('pool-test-cluster');
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);
    });

    test.afterAll(async () => {
      // Cleanup pools
      for (const pool of createdPools) {
        await ctx.runner
          .run(['ceph', 'pool', 'delete', pool, '--team', teamName, '--force'])
          .catch(() => {});
      }

      // Cleanup cluster
      await ctx.runner.run(['ceph', 'cluster', 'delete', clusterName, '--force']).catch(() => {});

      await ctx?.cleanup();
    });

    test('should list pools (initially empty)', async () => {
      const result = await ctx.runner.run(['ceph', 'pool', 'list']);

      expectEditionSuccess(result);
      expect(result.json).toBeInstanceOf(Array);
    });

    test('should create a pool', async () => {
      const poolName = uniqueName('test-pool');
      const result = await ctx.runner.run([
        'ceph',
        'pool',
        'create',
        poolName,
        '--cluster',
        clusterName,
        '--team',
        teamName,
      ]);

      expectEditionSuccess(result);
      createdPools.push(poolName);
    });

    test('should create a pool with vault', async () => {
      const poolName = uniqueName('pool-with-vault');
      const vault = JSON.stringify({ config: 'pool-test' });
      const result = await ctx.runner.run([
        'ceph',
        'pool',
        'create',
        poolName,
        '--cluster',
        clusterName,
        '--team',
        teamName,
        '--vault',
        vault,
      ]);

      expectEditionSuccess(result);
      createdPools.push(poolName);
    });

    test('should list pools with filters', async () => {
      const poolName = uniqueName('filter-pool');
      await ctx.runner.run([
        'ceph',
        'pool',
        'create',
        poolName,
        '--cluster',
        clusterName,
        '--team',
        teamName,
      ]);
      createdPools.push(poolName);

      // Filter by team
      const result = await ctx.runner.run(['ceph', 'pool', 'list', '--team', teamName]);

      expectEditionSuccess(result);
      const pools = ctx.runner.expectSuccessArray<{ poolName: string; teamName: string }>(result);
      const found = pools.some((p) => p.poolName === poolName && p.teamName === teamName);
      expect(found, `Expected to find pool "${poolName}" in filtered list`).toBe(true);
    });

    test('should list pools filtered by cluster', async () => {
      const result = await ctx.runner.run(['ceph', 'pool', 'list', '--cluster', clusterName]);

      expectEditionSuccess(result);
      const pools = ctx.runner.expectSuccessArray<{ clusterName: string }>(result);
      if (pools.length > 0) {
        expect(pools.every((p) => p.clusterName === clusterName)).toBe(true);
      }
    });

    test('should get pool vault', async () => {
      const poolName = uniqueName('vault-get-pool');
      const vaultContent = JSON.stringify({ key: 'pool-value' });
      await ctx.runner.run([
        'ceph',
        'pool',
        'create',
        poolName,
        '--cluster',
        clusterName,
        '--team',
        teamName,
        '--vault',
        vaultContent,
      ]);
      createdPools.push(poolName);

      const result = await ctx.runner.run([
        'ceph',
        'pool',
        'vault',
        'get',
        poolName,
        '--team',
        teamName,
      ]);

      expectEditionSuccess(result);
      const vault = result.json as { poolName: string; vaultVersion: number };
      expect(vault.poolName).toBe(poolName);
    });

    test('should update pool vault', async () => {
      const poolName = uniqueName('vault-update-pool');
      await ctx.runner.run([
        'ceph',
        'pool',
        'create',
        poolName,
        '--cluster',
        clusterName,
        '--team',
        teamName,
      ]);
      createdPools.push(poolName);

      // Get current vault version
      const getResult = await ctx.runner.run([
        'ceph',
        'pool',
        'vault',
        'get',
        poolName,
        '--team',
        teamName,
      ]);
      const currentVault = getResult.json as { vaultVersion: number };

      // Update vault
      const newVault = JSON.stringify({ updated: true });
      const result = await ctx.runner.run([
        'ceph',
        'pool',
        'vault',
        'update',
        poolName,
        '--team',
        teamName,
        '--vault',
        newVault,
        '--version',
        String(currentVault.vaultVersion),
      ]);

      expectEditionSuccess(result);
    });

    test('should delete a pool', async () => {
      const poolName = uniqueName('delete-pool');
      await ctx.runner.run([
        'ceph',
        'pool',
        'create',
        poolName,
        '--cluster',
        clusterName,
        '--team',
        teamName,
      ]);

      const result = await ctx.runner.run([
        'ceph',
        'pool',
        'delete',
        poolName,
        '--team',
        teamName,
        '--force',
      ]);

      expectEditionSuccess(result);
    });
  });

  test.describe('BUSINESS edition - pool limit enforcement', () => {
    let ctx: EditionTestContext;
    let teamName: string;
    let clusterName: string;
    const createdPools: string[] = [];

    test.beforeAll(async () => {
      ctx = await createEditionContext('BUSINESS');

      const teamResult = await ctx.runner.teamList();
      const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
      teamName = teams[0]?.teamName ?? 'Private Team';

      clusterName = uniqueName('business-pool-cluster');
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);
    });

    test.afterAll(async () => {
      for (const pool of createdPools) {
        await ctx.runner
          .run(['ceph', 'pool', 'delete', pool, '--team', teamName, '--force'])
          .catch(() => {});
      }
      await ctx.runner.run(['ceph', 'cluster', 'delete', clusterName, '--force']).catch(() => {});
      await ctx?.cleanup();
    });

    test('should allow creating first pool', async () => {
      const poolName = uniqueName('first-pool');
      const result = await ctx.runner.run([
        'ceph',
        'pool',
        'create',
        poolName,
        '--cluster',
        clusterName,
        '--team',
        teamName,
      ]);

      expectEditionSuccess(result);
      createdPools.push(poolName);
    });

    test('should reject second pool for same team (Business limit)', async () => {
      const poolName = uniqueName('second-pool');
      const result = await ctx.runner.run([
        'ceph',
        'pool',
        'create',
        poolName,
        '--cluster',
        clusterName,
        '--team',
        teamName,
      ]);

      expectEditionError(result, 402, EditionErrorPatterns.CEPH_POOL_LIMIT_BUSINESS);
    });
  });
});
