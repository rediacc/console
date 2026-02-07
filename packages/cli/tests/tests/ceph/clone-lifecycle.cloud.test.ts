import { test } from '@playwright/test';
import { cephCloneLifecycleScenario } from '../../src/scenarios/ceph-clone-lifecycle';
import { createCloudTestContext, type TestContext } from '../../src/utils/TestContext';
import { uniqueName } from '../../src/utils/edition';

test.describe('Ceph Clone Lifecycle (Cloud) @cli @ceph', () => {
  let ctx: TestContext;
  let poolName: string;
  let imageName: string;
  let snapshotName: string;
  let clusterName: string;

  test.beforeAll(async () => {
    ctx = await createCloudTestContext('ENTERPRISE');

    // Create full dependency chain: cluster → pool → image → snapshot
    clusterName = uniqueName('clone-lc-cluster');
    await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

    poolName = uniqueName('clone-lc-pool');
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

    imageName = uniqueName('clone-lc-image');
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

    snapshotName = uniqueName('clone-lc-snapshot');
    await ctx.runner.run([
      'ceph',
      'snapshot',
      'create',
      snapshotName,
      '--image',
      imageName,
      '--pool',
      poolName,
      '--team',
      ctx.teamName!,
    ]);
  });

  test.afterAll(async () => {
    if (ctx) {
      await ctx.runner
        .run([
          'ceph',
          'snapshot',
          'delete',
          snapshotName,
          '--image',
          imageName,
          '--pool',
          poolName,
          '--team',
          ctx.teamName!,
          '--force',
        ])
        .catch(() => {});
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
      await ctx.runner
        .run(['ceph', 'cluster', 'delete', clusterName, '--force'])
        .catch(() => {});
      await ctx.cleanup();
    }
  });

  cephCloneLifecycleScenario(() => ctx, () => ({
    poolName,
    imageName,
    snapshotName,
    sshValidation: false,
  }));
});
