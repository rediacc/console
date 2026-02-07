/**
 * Ceph Cluster CLI Tests
 *
 * Tests for Ceph cluster CRUD operations and vault management.
 */

import { expect, test } from '@playwright/test';
import {
  createEditionContext,
  type EditionTestContext,
  expectEditionSuccess,
  uniqueName,
} from '../../src/utils/edition';

test.describe('Ceph Cluster Commands @cli @ceph', () => {
  test.describe('BUSINESS edition - cluster operations', () => {
    let ctx: EditionTestContext;
    const createdClusters: string[] = [];

    test.beforeAll(async () => {
      ctx = await createEditionContext('BUSINESS');
    });

    test.afterAll(async () => {
      // Cleanup created clusters
      for (const cluster of createdClusters) {
        await ctx.runner.run(['ceph', 'cluster', 'delete', cluster, '--force']).catch(() => {});
      }
      await ctx?.cleanup();
    });

    test('should list clusters (initially empty)', async () => {
      const result = await ctx.runner.run(['ceph', 'cluster', 'list']);

      // Include debug info in assertion message for CI visibility
      const debugInfo = `
[DEBUG] success: ${result.success}
[DEBUG] exitCode: ${result.exitCode}
[DEBUG] json type: ${typeof result.json}
[DEBUG] json isArray: ${Array.isArray(result.json)}
[DEBUG] json value: ${JSON.stringify(result.json).slice(0, 500)}
[DEBUG] stdout: ${result.stdout.slice(0, 500)}
[DEBUG] stderr: ${result.stderr.slice(0, 500)}
[DEBUG] context: ${ctx.contextName}
[DEBUG] account: ${ctx.account.email}`;

      expect(result.success, `Command failed. ${debugInfo}`).toBe(true);
      expect(
        result.json,
        `Expected array but got ${typeof result.json}: ${JSON.stringify(result.json).slice(0, 500)}. ${debugInfo}`
      ).toBeInstanceOf(Array);
    });

    test('should create a cluster', async () => {
      const clusterName = uniqueName('test-cluster');
      const result = await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

      expectEditionSuccess(result);
      createdClusters.push(clusterName);
    });

    test('should create a cluster with vault', async () => {
      const clusterName = uniqueName('cluster-with-vault');
      const vault = JSON.stringify({ config: 'test' });
      const result = await ctx.runner.run([
        'ceph',
        'cluster',
        'create',
        clusterName,
        '--vault',
        vault,
      ]);

      expectEditionSuccess(result);
      createdClusters.push(clusterName);
    });

    test('should list clusters after creation', async () => {
      const clusterName = uniqueName('list-test-cluster');
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);
      createdClusters.push(clusterName);

      const result = await ctx.runner.run(['ceph', 'cluster', 'list']);

      expectEditionSuccess(result);
      const clusters = ctx.runner.expectSuccessArray<{ clusterName: string }>(result);
      const found = clusters.some((c) => c.clusterName === clusterName);
      expect(found, `Expected to find cluster "${clusterName}" in list`).toBe(true);
    });

    test('should get cluster vault', async () => {
      const clusterName = uniqueName('vault-get-cluster');
      const vaultContent = JSON.stringify({ key: 'value' });
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName, '--vault', vaultContent]);
      createdClusters.push(clusterName);

      const result = await ctx.runner.run(['ceph', 'cluster', 'vault', 'get', clusterName]);

      expectEditionSuccess(result);
      const vault = result.json as { clusterName: string; vaultVersion: number };
      expect(vault.clusterName).toBe(clusterName);
      expect(vault.vaultVersion).toBeGreaterThanOrEqual(0);
    });

    test('should update cluster vault', async () => {
      const clusterName = uniqueName('vault-update-cluster');
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);
      createdClusters.push(clusterName);

      // Get current vault version
      const getResult = await ctx.runner.run(['ceph', 'cluster', 'vault', 'get', clusterName]);
      const currentVault = getResult.json as { vaultVersion: number };

      // Update vault
      const newVault = JSON.stringify({ updated: true });
      const result = await ctx.runner.run([
        'ceph',
        'cluster',
        'vault',
        'update',
        clusterName,
        '--vault',
        newVault,
        '--version',
        String(currentVault.vaultVersion),
      ]);

      expectEditionSuccess(result);
    });

    test('should list machines in cluster (initially empty)', async () => {
      const clusterName = uniqueName('machines-cluster');
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);
      createdClusters.push(clusterName);

      const result = await ctx.runner.run(['ceph', 'cluster', 'machines', clusterName]);

      expectEditionSuccess(result);
      expect(result.json).toBeInstanceOf(Array);
    });

    test('should delete a cluster', async () => {
      const clusterName = uniqueName('delete-cluster');
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

      const result = await ctx.runner.run(['ceph', 'cluster', 'delete', clusterName, '--force']);

      expectEditionSuccess(result);
      // Remove from cleanup list since it's already deleted
    });

    test('should reject duplicate cluster names', async () => {
      const clusterName = uniqueName('duplicate-cluster');
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);
      createdClusters.push(clusterName);

      const result = await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

      expect(result.success).toBe(false);
    });
  });
});
