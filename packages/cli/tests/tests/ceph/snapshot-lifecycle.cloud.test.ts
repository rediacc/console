import { test } from '@playwright/test';
import { cephSnapshotLifecycleScenario } from '../../src/scenarios/ceph-snapshot-lifecycle';
import { uniqueName } from '../../src/utils/edition';
import { createCloudTestContext, type TestContext } from '../../src/utils/TestContext';

test.describe('Ceph Snapshot Lifecycle (Cloud) @cli @ceph', () => {
  let ctx: TestContext;
  let poolName: string;
  let imageName: string;
  let clusterName: string;

  test.beforeAll(async () => {
    ctx = await createCloudTestContext('ENTERPRISE');

    // Create cluster, pool, and image for snapshot tests
    clusterName = uniqueName('snap-lc-cluster');
    await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

    poolName = uniqueName('snap-lc-pool');
    await ctx.runner.run([
      'ceph',
      'pool',
      'create',
      poolName,
      '--cluster',
      clusterName,
      '--team',
      ctx.teamName!,
    ]);

    imageName = uniqueName('snap-lc-image');
    await ctx.runner.run([
      'ceph',
      'image',
      'create',
      imageName,
      '--pool',
      poolName,
      '--team',
      ctx.teamName!,
      '--machine',
      ctx.machineName,
    ]);
  });

  test.afterAll(async () => {
    if (ctx) {
      await ctx.runner
        .run([
          'ceph',
          'image',
          'delete',
          imageName,
          '--pool',
          poolName,
          '--team',
          ctx.teamName!,
          '--force',
        ])
        .catch(() => {});
      await ctx.runner
        .run(['ceph', 'pool', 'delete', poolName, '--team', ctx.teamName!, '--force'])
        .catch(() => {});
      await ctx.runner.run(['ceph', 'cluster', 'delete', clusterName, '--force']).catch(() => {});
      await ctx.cleanup();
    }
  });

  cephSnapshotLifecycleScenario(
    () => ctx,
    () => ({
      poolName,
      imageName,
      sshValidation: false,
    })
  );
});
