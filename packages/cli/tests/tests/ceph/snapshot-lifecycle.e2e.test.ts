import { test } from '@playwright/test';
import { cephSnapshotLifecycleScenario } from '../../src/scenarios/ceph-snapshot-lifecycle';
import { getE2EConfig } from '../../src/utils/local';
import { createLocalTestContext, type TestContext } from '../../src/utils/TestContext';

/**
 * E2E snapshot lifecycle.
 *
 * Requires a pre-existing RBD image. The beforeAll creates the image,
 * the scenario creates/lists/deletes a snapshot, and afterAll cleans up.
 */
test.describe
  .serial('Ceph Snapshot Lifecycle (E2E) @cli @e2e', () => {
    let ctx: TestContext;
    const config = getE2EConfig();
    const cephConfigured = !!process.env.E2E_CEPH_NODES;

    const poolName = 'rbd';
    const imageName = `snap-e2e-image-${Date.now()}`;

    test.beforeAll(async () => {
      test.skip(!config.enabled || !cephConfigured, 'E2E VMs or Ceph not configured');
      const localCtx = await createLocalTestContext('e2e-ceph-snap');
      test.skip(!localCtx, 'E2E environment setup failed');
      ctx = localCtx!;

      // Create parent image for snapshot tests
      const result = await ctx.runner.run(
        [
          'ceph',
          'image',
          'create',
          '--image',
          imageName,
          '--pool',
          poolName,
          '--size',
          '1G',
          '--machine',
          ctx.machineName,
        ],
        { timeout: ctx.defaultTimeout }
      );
      ctx.runner.expectSuccess(result);
    });

    test.afterAll(async () => {
      if (ctx) {
        await ctx.runner
          .run(
            [
              'ceph',
              'image',
              'delete',
              '--image',
              imageName,
              '--pool',
              poolName,
              '--machine',
              ctx.machineName,
            ],
            { timeout: 120_000 }
          )
          .catch(() => {});
        await ctx.cleanup();
      }
    });

    cephSnapshotLifecycleScenario(
      () => ctx,
      () => ({
        poolName,
        imageName,
        sshValidation: true,
      })
    );
  });
