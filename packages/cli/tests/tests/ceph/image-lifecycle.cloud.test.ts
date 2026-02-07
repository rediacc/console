import { test } from '@playwright/test';
import { cephImageLifecycleScenario } from '../../src/scenarios/ceph-image-lifecycle';
import { createCloudTestContext, type TestContext } from '../../src/utils/TestContext';
import { uniqueName } from '../../src/utils/edition';

test.describe('Ceph Image Lifecycle (Cloud) @cli @ceph', () => {
  let ctx: TestContext;
  let poolName: string;
  let clusterName: string;

  test.beforeAll(async () => {
    ctx = await createCloudTestContext('ENTERPRISE');

    // Create cluster and pool for image tests
    clusterName = uniqueName('img-lc-cluster');
    await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

    poolName = uniqueName('img-lc-pool');
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
  });

  test.afterAll(async () => {
    if (ctx) {
      await ctx.runner
        .run(['ceph', 'pool', 'delete', poolName, '--team', ctx.teamName!, '--force'])
        .catch(() => {});
      await ctx.runner.run(['ceph', 'cluster', 'delete', clusterName, '--force']).catch(() => {});
      await ctx.cleanup();
    }
  });

  cephImageLifecycleScenario(() => ctx, {
    poolName,
    sshValidation: false,
  });
});
