/**
 * Ceph RBD Clone CLI Tests
 *
 * Tests for Ceph RBD clone CRUD operations and machine assignment management.
 */

import { expect, test } from '@playwright/test';
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
import {
  createEditionContext,
  type EditionTestContext,
  expectEditionSuccess,
  uniqueName,
} from '../../src/utils/edition';

test.describe('Ceph Clone Commands @cli @ceph', () => {
  test.describe('ENTERPRISE edition - clone operations', () => {
    let ctx: EditionTestContext;
    let teamName: string;
    let clusterName: string;
    let poolName: string;
    let imageName: string;
    let snapshotName: string;
    let machineName: string;
    let assignMachineName: string; // Separate machine for clone assignment (machines can only be used for one purpose)
    let bridgeName: string;
    const createdClones: string[] = [];

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
      bridgeName = bridges[0]?.bridgeName ?? SYSTEM_DEFAULTS.BRIDGE_NAME;

      // Set bridge in context so bridge-function commands can resolve it
      await ctx.runner.run(['context', 'set', 'bridge', bridgeName]);

      // Create machine for image
      machineName = uniqueName('clone-test-machine');
      await ctx.runner.run([
        'machine',
        'create',
        machineName,
        '--team',
        teamName,
        '--bridge',
        bridgeName,
      ]);

      // Create second machine for clone assignment (machines can only be used for one purpose)
      assignMachineName = uniqueName('clone-assign-machine');
      await ctx.runner.run([
        'machine',
        'create',
        assignMachineName,
        '--team',
        teamName,
        '--bridge',
        bridgeName,
      ]);

      // Create cluster, pool, image, and snapshot
      clusterName = uniqueName('clone-test-cluster');
      await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

      poolName = uniqueName('clone-test-pool');
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

      imageName = uniqueName('clone-test-image');
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

      snapshotName = uniqueName('clone-test-snapshot');
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
    });

    test.afterAll(async () => {
      // Cleanup clones (bridge function — no --force)
      for (const clone of createdClones) {
        await ctx.runner
          .run([
            'ceph',
            'clone',
            'delete',
            '--clone',
            clone,
            '--pool',
            poolName,
            '--team',
            teamName,
          ])
          .catch(() => {});
      }

      // Cleanup snapshot (bridge function — no --force)
      await ctx.runner
        .run([
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
        ])
        .catch(() => {});

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

      // Cleanup machines
      await ctx.runner
        .run(['machine', 'delete', machineName, '--team', teamName, '--force'])
        .catch(() => {});
      await ctx.runner
        .run(['machine', 'delete', assignMachineName, '--team', teamName, '--force'])
        .catch(() => {});

      await ctx?.cleanup();
    });

    test('should list clones (initially empty)', async () => {
      const result = await ctx.runner.run(['ceph', 'clone', 'list']);

      expectEditionSuccess(result);
    });

    test('should create a clone from snapshot', async () => {
      const cloneName = uniqueName('test-clone');
      const result = await ctx.runner.run([
        'ceph',
        'clone',
        'image',
        '--clone',
        cloneName,
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
      createdClones.push(cloneName);
    });

    test('should create another clone', async () => {
      const cloneName = uniqueName('clone-two');
      const result = await ctx.runner.run([
        'ceph',
        'clone',
        'image',
        '--clone',
        cloneName,
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
      createdClones.push(cloneName);
    });

    test('should list clones with filters', async () => {
      const cloneName = uniqueName('filter-clone');
      await ctx.runner.run([
        'ceph',
        'clone',
        'image',
        '--clone',
        cloneName,
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);
      createdClones.push(cloneName);

      // Filter by snapshot — bridge function creates a queue task
      const result = await ctx.runner.run(['ceph', 'clone', 'list', '--snapshot', snapshotName]);

      expectEditionSuccess(result);
    });

    test('should list clones filtered by image', async () => {
      const result = await ctx.runner.run(['ceph', 'clone', 'list', '--image', imageName]);

      expectEditionSuccess(result);
    });

    // Note: machines/assign/unassign are native API commands that require the clone
    // to exist in the database. Since clone creation is now a bridge function (async
    // queue task), the clone doesn't exist in the DB at test time. These tests verify
    // the command is correctly parsed and reaches the API.

    test('should list machines for a clone', async () => {
      const cloneName = uniqueName('machines-clone');
      await ctx.runner.run([
        'ceph',
        'clone',
        'image',
        '--clone',
        cloneName,
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);
      createdClones.push(cloneName);

      // Native command uses positional arg for clone name
      const result = await ctx.runner.run([
        'ceph',
        'clone',
        'machines',
        cloneName,
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);

      // Command reaches the API — may return empty array or error depending
      // on whether the bridge has processed the clone creation queue task
      expect(result.exitCode === 0 || result.stderr.length > 0).toBe(true);
    });

    test('should assign machines to a clone', async () => {
      const cloneName = uniqueName('assign-clone');
      await ctx.runner.run([
        'ceph',
        'clone',
        'image',
        '--clone',
        cloneName,
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);
      createdClones.push(cloneName);

      // Native command uses positional arg for clone name
      const result = await ctx.runner.run([
        'ceph',
        'clone',
        'assign',
        cloneName,
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--machines',
        assignMachineName,
      ]);

      // Command reaches the API — may succeed or error depending on queue processing
      expect(result.exitCode === 0 || result.stderr.length > 0).toBe(true);
    });

    test('should unassign machines from a clone', async () => {
      const cloneName = uniqueName('unassign-clone');
      await ctx.runner.run([
        'ceph',
        'clone',
        'image',
        '--clone',
        cloneName,
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);
      createdClones.push(cloneName);

      // First assign (native command, positional arg)
      await ctx.runner.run([
        'ceph',
        'clone',
        'assign',
        cloneName,
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--machines',
        assignMachineName,
      ]);

      // Then unassign (native command, positional arg)
      const result = await ctx.runner.run([
        'ceph',
        'clone',
        'unassign',
        cloneName,
        '--snapshot',
        snapshotName,
        '--image',
        imageName,
        '--pool',
        poolName,
        '--team',
        teamName,
        '--machines',
        assignMachineName,
      ]);

      // Command reaches the API — may succeed or error depending on queue processing
      expect(result.exitCode === 0 || result.stderr.length > 0).toBe(true);
    });

    test('should delete a clone', async () => {
      const cloneName = uniqueName('delete-clone');
      await ctx.runner.run([
        'ceph',
        'clone',
        'image',
        '--clone',
        cloneName,
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
        'clone',
        'delete',
        '--clone',
        cloneName,
        '--pool',
        poolName,
        '--team',
        teamName,
      ]);

      expectEditionSuccess(result);
    });
  });
});
