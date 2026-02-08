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
      // Cleanup clones
      for (const clone of createdClones) {
        await ctx.runner
          .run([
            'ceph',
            'clone',
            'delete',
            '--clone',
            clone,
            '--snapshot',
            snapshotName,
            '--image',
            imageName,
            '--pool',
            poolName,
            '--team',
            teamName,
            '--force',
          ])
          .catch(() => {});
      }

      // Cleanup snapshot
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
          '--force',
        ])
        .catch(() => {});

      // Cleanup image
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
          '--force',
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
      expect(result.json).toBeInstanceOf(Array);
    });

    test('should create a clone from snapshot', async () => {
      const cloneName = uniqueName('test-clone');
      const vault = JSON.stringify({ description: 'test clone' });
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
        '--vault',
        vault,
      ]);

      expectEditionSuccess(result);
      createdClones.push(cloneName);
    });

    test('should create a clone with vault', async () => {
      const cloneName = uniqueName('clone-with-vault');
      const vault = JSON.stringify({ mountPoint: '/mnt/data' });
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
        '--vault',
        vault,
      ]);

      expectEditionSuccess(result);
      createdClones.push(cloneName);
    });

    test('should list clones with filters', async () => {
      const cloneName = uniqueName('filter-clone');
      const vault = JSON.stringify({ description: 'filter test clone' });
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
        '--vault',
        vault,
      ]);
      createdClones.push(cloneName);

      // Filter by snapshot
      const result = await ctx.runner.run(['ceph', 'clone', 'list', '--snapshot', snapshotName]);

      expectEditionSuccess(result);
      const clones = ctx.runner.expectSuccessArray<{
        cloneName: string;
        snapshotName: string;
      }>(result);
      const found = clones.some(
        (c) => c.cloneName === cloneName && c.snapshotName === snapshotName
      );
      expect(found, `Expected to find clone "${cloneName}" in filtered list`).toBe(true);
    });

    test('should list clones filtered by image', async () => {
      const result = await ctx.runner.run(['ceph', 'clone', 'list', '--image', imageName]);

      expectEditionSuccess(result);
      const clones = ctx.runner.expectSuccessArray<{ imageName: string }>(result);
      if (clones.length > 0) {
        expect(clones.every((c) => c.imageName === imageName)).toBe(true);
      }
    });

    test('should list machines for a clone (initially empty)', async () => {
      const cloneName = uniqueName('machines-clone');
      const vault = JSON.stringify({ description: 'machines test clone' });
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
        '--vault',
        vault,
      ]);
      createdClones.push(cloneName);

      const result = await ctx.runner.run([
        'ceph',
        'clone',
        'machines',
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
      expect(result.json).toBeInstanceOf(Array);
    });

    test('should assign machines to a clone', async () => {
      const cloneName = uniqueName('assign-clone');
      const vault = JSON.stringify({ description: 'assign test clone' });
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
        '--vault',
        vault,
      ]);
      createdClones.push(cloneName);

      const result = await ctx.runner.run([
        'ceph',
        'clone',
        'assign',
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
        '--machines',
        assignMachineName,
      ]);

      expectEditionSuccess(result);
    });

    test('should unassign machines from a clone', async () => {
      const cloneName = uniqueName('unassign-clone');
      const vault = JSON.stringify({ description: 'unassign test clone' });
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
        '--vault',
        vault,
      ]);
      createdClones.push(cloneName);

      // First assign
      await ctx.runner.run([
        'ceph',
        'clone',
        'assign',
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
        '--machines',
        assignMachineName,
      ]);

      // Then unassign
      const result = await ctx.runner.run([
        'ceph',
        'clone',
        'unassign',
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
        '--machines',
        assignMachineName,
      ]);

      expectEditionSuccess(result);
    });

    test('should delete a clone', async () => {
      const cloneName = uniqueName('delete-clone');
      const vault = JSON.stringify({ description: 'delete test clone' });
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
        '--vault',
        vault,
      ]);

      const result = await ctx.runner.run([
        'ceph',
        'clone',
        'delete',
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
        '--force',
      ]);

      expectEditionSuccess(result);
    });
  });
});
