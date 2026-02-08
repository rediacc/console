/**
 * Ceph RBD Image CLI Tests
 *
 * Tests for Ceph RBD image CRUD operations.
 * Image commands are bridge functions that create queue tasks in cloud mode.
 */

import { test } from '@playwright/test';
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
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
      teamName = teams[0]?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;

      // Get region and bridge for machine creation
      const regionResult = await ctx.runner.run(['region', 'list']);
      const regions = ctx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
      const regionName = regions[0]?.regionName ?? SYSTEM_DEFAULTS.REGION_NAME;

      const bridgeResult = await ctx.runner.run(['bridge', 'list', '--region', regionName]);
      const bridges = ctx.runner.expectSuccessArray<{ bridgeName: string }>(bridgeResult);
      const bridgeName = bridges[0]?.bridgeName ?? SYSTEM_DEFAULTS.BRIDGE_NAME;

      // Set bridge in context so bridge-function commands can resolve it
      await ctx.runner.run(['context', 'set', 'bridge', bridgeName]);

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
      // Cleanup images (bridge function — no --force)
      for (const image of createdImages) {
        await ctx.runner
          .run([
            'ceph',
            'image',
            'delete',
            '--image',
            image,
            '--pool',
            poolName,
            '--team',
            teamName,
          ])
          .catch(() => {});
      }

      // Cleanup pool and cluster (native commands — support --force)
      await ctx.runner
        .run(['ceph', 'pool', 'delete', poolName, '--team', teamName, '--force'])
        .catch(() => {});
      await ctx.runner.run(['ceph', 'cluster', 'delete', clusterName, '--force']).catch(() => {});

      // Cleanup machine (native command)
      await ctx.runner
        .run(['machine', 'delete', machineName, '--team', teamName, '--force'])
        .catch(() => {});

      await ctx?.cleanup();
    });

    test('should list images (initially empty)', async () => {
      const result = await ctx.runner.run(['ceph', 'image', 'list']);

      expectEditionSuccess(result);
    });

    test('should create an image', async () => {
      const imageName = uniqueName('test-image');
      const result = await ctx.runner.run([
        'ceph',
        'image',
        'create',
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--size',
        '1G',
      ]);

      expectEditionSuccess(result);
      createdImages.push(imageName);
    });

    test('should create an image with size', async () => {
      const imageName = uniqueName('image-with-size');
      const result = await ctx.runner.run([
        'ceph',
        'image',
        'create',
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--size',
        '2G',
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
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--size',
        '1G',
      ]);
      createdImages.push(imageName);

      // Filter by pool — bridge function creates a queue task
      const result = await ctx.runner.run(['ceph', 'image', 'list', '--pool', poolName]);

      expectEditionSuccess(result);
    });

    test('should list images filtered by team', async () => {
      const result = await ctx.runner.run(['ceph', 'image', 'list', '--team', teamName]);

      expectEditionSuccess(result);
    });

    test('should delete an image', async () => {
      const imageName = uniqueName('delete-image');
      await ctx.runner.run([
        'ceph',
        'image',
        'create',
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--size',
        '1G',
      ]);

      const result = await ctx.runner.run([
        'ceph',
        'image',
        'delete',
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);

      expectEditionSuccess(result);
    });
  });
});
