/**
 * Ceph RBD Image CLI Tests
 *
 * Tests for Ceph RBD image CRUD operations.
 */

import { expect, test } from '@playwright/test';
import {
  createEditionContext,
  type EditionTestContext,
  expectEditionSuccess,
  uniqueName,
} from '../../src/utils/edition';

test.describe('Ceph Image Commands @cli @ceph', () => {
  test.describe('ENTERPRISE edition - image operations', () => {
    let ctx: EditionTestContext;
    let teamName: string;
    let clusterName: string;
    let poolName: string;
    let machineName: string;
    const createdImages: string[] = [];

    test.beforeAll(async () => {
      ctx = await createEditionContext('ENTERPRISE');

      // Get team
      const teamResult = await ctx.runner.teamList();
      const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
      teamName = teams[0]?.teamName ?? 'Private Team';

      // Get region and bridge for machine creation
      const regionResult = await ctx.runner.run(['region', 'list']);
      const regions = ctx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
      const regionName = regions[0]?.regionName ?? 'Default Region';

      const bridgeResult = await ctx.runner.run(['bridge', 'list', '--region', regionName]);
      const bridges = ctx.runner.expectSuccessArray<{ bridgeName: string }>(bridgeResult);
      const bridgeName = bridges[0]?.bridgeName ?? 'Global Bridges';

      // Create a machine
      machineName = uniqueName('image-test-machine');
      await ctx.runner.run([
        'machine',
        'create',
        machineName,
        '--team',
        teamName,
        '--bridge',
        bridgeName,
      ]);

      // Create cluster and pool
      clusterName = uniqueName('image-test-cluster');
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

      poolName = uniqueName('image-test-pool');
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
    });

    test.afterAll(async () => {
      // Cleanup images
      for (const image of createdImages) {
        await ctx.runner
          .run([
            'ceph',
            'image',
            'delete',
            image,
            '--pool',
            poolName,
            '--team',
            teamName,
            '--force',
          ])
          .catch(() => {});
      }

      // Cleanup pool and cluster
      await ctx.runner
        .run(['ceph', 'pool', 'delete', poolName, '--team', teamName, '--force'])
        .catch(() => {});
      await ctx.runner.run(['ceph', 'cluster', 'delete', clusterName, '--force']).catch(() => {});

      // Cleanup machine
      await ctx.runner
        .run(['machine', 'delete', machineName, '--team', teamName, '--force'])
        .catch(() => {});

      await ctx?.cleanup();
    });

    test('should list images (initially empty)', async () => {
      const result = await ctx.runner.run(['ceph', 'image', 'list']);

      expectEditionSuccess(result);
      expect(result.json).toBeInstanceOf(Array);
    });

    test('should create an image', async () => {
      const imageName = uniqueName('test-image');
      const result = await ctx.runner.run([
        'ceph',
        'image',
        'create',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--machine',
        machineName,
      ]);

      expectEditionSuccess(result);
      createdImages.push(imageName);
    });

    test('should create an image with vault', async () => {
      const imageName = uniqueName('image-with-vault');
      const vault = JSON.stringify({ size: '10G' });
      const result = await ctx.runner.run([
        'ceph',
        'image',
        'create',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--machine',
        machineName,
        '--vault',
        vault,
      ]);

      expectEditionSuccess(result);
      createdImages.push(imageName);
    });

    test('should list images with filters', async () => {
      const imageName = uniqueName('filter-image');
      await ctx.runner.run([
        'ceph',
        'image',
        'create',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--machine',
        machineName,
      ]);
      createdImages.push(imageName);

      // Filter by pool
      const result = await ctx.runner.run(['ceph', 'image', 'list', '--pool', poolName]);

      expectEditionSuccess(result);
      const images = ctx.runner.expectSuccessArray<{ imageName: string; poolName: string }>(result);
      const found = images.some((i) => i.imageName === imageName && i.poolName === poolName);
      expect(found, `Expected to find image "${imageName}" in filtered list`).toBe(true);
    });

    test('should list images filtered by team', async () => {
      const result = await ctx.runner.run(['ceph', 'image', 'list', '--team', teamName]);

      expectEditionSuccess(result);
      const images = ctx.runner.expectSuccessArray<{ teamName: string }>(result);
      if (images.length > 0) {
        expect(images.every((i) => i.teamName === teamName)).toBe(true);
      }
    });

    test('should delete an image', async () => {
      const imageName = uniqueName('delete-image');
      await ctx.runner.run([
        'ceph',
        'image',
        'create',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--machine',
        machineName,
      ]);

      const result = await ctx.runner.run([
        'ceph',
        'image',
        'delete',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--force',
      ]);

      expectEditionSuccess(result);
    });
  });
});
