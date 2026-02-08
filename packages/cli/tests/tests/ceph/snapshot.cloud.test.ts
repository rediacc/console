/**
 * Ceph RBD Snapshot CLI Tests
 *
 * Tests for Ceph RBD snapshot CRUD operations.
 */

import { test } from '@playwright/test';
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
import {
  createEditionContext,
  type EditionTestContext,
  expectEditionSuccess,
  uniqueName,
} from '../../src/utils/edition';

test.describe('Ceph Snapshot Commands @cli @ceph', () => {
  test.describe('ENTERPRISE edition - snapshot operations', () => {
    let ctx: EditionTestContext;
    let teamName: string;
    let clusterName: string;
    let poolName: string;
    let imageName: string;
    let machineName: string;
    const createdSnapshots: string[] = [];

    test.beforeAll(async () => {
      ctx = await createEditionContext('ENTERPRISE');

      // Get team
      const teamResult = await ctx.runner.teamList();
      const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
      teamName = teams[0]?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;

      // Get region and bridge
      const regionResult = await ctx.runner.run(['region', 'list']);
      const regions = ctx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
      const regionName = regions[0]?.regionName ?? SYSTEM_DEFAULTS.REGION_NAME;

      const bridgeResult = await ctx.runner.run(['bridge', 'list', '--region', regionName]);
      const bridges = ctx.runner.expectSuccessArray<{ bridgeName: string }>(bridgeResult);
      const bridgeName = bridges[0]?.bridgeName ?? SYSTEM_DEFAULTS.BRIDGE_NAME;

      // Set bridge in context so bridge-function commands can resolve it
      await ctx.runner.run(['context', 'set', 'bridge', bridgeName]);

      // Create machine
      machineName = uniqueName('snapshot-test-machine');
      await ctx.runner.run([
        'machine',
        'create',
        machineName,
        '--team',
        teamName,
        '--bridge',
        bridgeName,
      ]);

      // Create cluster, pool, and image
      clusterName = uniqueName('snapshot-test-cluster');
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

      poolName = uniqueName('snapshot-test-pool');
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

      imageName = uniqueName('snapshot-test-image');
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
        '--machine',
        machineName,
        '--size',
        '1G',
      ]);
    });

    test.afterAll(async () => {
      // Cleanup snapshots (bridge function — no --force)
      for (const snapshot of createdSnapshots) {
        await ctx.runner
          .run([
            'ceph',
            'snapshot',
            'delete',
            '--snapshot',
            snapshot,
            '--image',
            imageName,
            '--pool',
            poolName,
            '--team',
            teamName,
          ])
          .catch(() => {});
      }

      // Cleanup image (bridge function — no --force)
      await ctx.runner
        .run([
          'ceph',
          'image',
          'delete',
          '--image',
          imageName,
          '--pool',
          poolName,
          '--team',
          teamName,
        ])
        .catch(() => {});

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

    test('should list snapshots (initially empty)', async () => {
      const result = await ctx.runner.run(['ceph', 'snapshot', 'list']);

      expectEditionSuccess(result);
    });

    test('should create a snapshot', async () => {
      const snapshotName = uniqueName('test-snapshot');
      const result = await ctx.runner.run([
        'ceph',
        'snapshot',
        'create',
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);

      expectEditionSuccess(result);
      createdSnapshots.push(snapshotName);
    });

    test('should create another snapshot', async () => {
      const snapshotName = uniqueName('snapshot-two');
      const result = await ctx.runner.run([
        'ceph',
        'snapshot',
        'create',
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);

      expectEditionSuccess(result);
      createdSnapshots.push(snapshotName);
    });

    test('should list snapshots with filters', async () => {
      const snapshotName = uniqueName('filter-snapshot');
      await ctx.runner.run([
        'ceph',
        'snapshot',
        'create',
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);
      createdSnapshots.push(snapshotName);

      // Filter by image — bridge function creates a queue task
      const result = await ctx.runner.run(['ceph', 'snapshot', 'list', '--image', imageName]);

      expectEditionSuccess(result);
    });

    test('should list snapshots filtered by pool', async () => {
      const result = await ctx.runner.run(['ceph', 'snapshot', 'list', '--pool', poolName]);

      expectEditionSuccess(result);
    });

    test('should delete a snapshot', async () => {
      const snapshotName = uniqueName('delete-snapshot');
      await ctx.runner.run([
        'ceph',
        'snapshot',
        'create',
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);

      // Bridge function — no --force
      const result = await ctx.runner.run([
        'ceph',
        'snapshot',
        'delete',
        '--snapshot',
        snapshotName,
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
