import { test } from '@playwright/test';
import { cephCloneLifecycleScenario } from '../../src/scenarios/ceph-clone-lifecycle';
import { getE2EConfig } from '../../src/utils/local';
import { createLocalTestContext, type TestContext } from '../../src/utils/TestContext';

/**
 * E2E clone lifecycle.
 *
 * Requires: image + protected snapshot. The beforeAll creates them,
 * the scenario creates/lists/deletes a clone, afterAll cleans up.
 */
test.describe
  .serial('Ceph Clone Lifecycle (E2E) @cli @e2e', () => {
    let ctx: TestContext;
    const config = getE2EConfig();
    const cephConfigured = !!process.env.E2E_CEPH_NODES;

    const poolName = 'rbd';
    const imageName = `clone-e2e-image-${Date.now()}`;
    const snapshotName = `clone-e2e-snap-${Date.now()}`;

    test.beforeAll(async () => {
      test.skip(!config.enabled || !cephConfigured, 'E2E VMs or Ceph not configured');
      const localCtx = await createLocalTestContext('e2e-ceph-clone');
      test.skip(!localCtx, 'E2E environment setup failed');
      ctx = localCtx!;

      // Create image
      const imgResult = await ctx.runner.run(
        [
          'ceph',
          'image',
          'create',
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
      ctx.runner.expectSuccess(imgResult);

      // Create snapshot
      const snapResult = await ctx.runner.run(
        [
          'ceph',
          'snapshot',
          'create',
          snapshotName,
          '--image',
          imageName,
          '--pool',
          poolName,
          '--machine',
          ctx.machineName,
        ],
        { timeout: ctx.defaultTimeout }
      );
      ctx.runner.expectSuccess(snapResult);

      // Protect snapshot (required for cloning)
      const protectResult = await ctx.runner.run(
        [
          'ceph',
          'snapshot',
          'protect',
          snapshotName,
          '--image',
          imageName,
          '--pool',
          poolName,
          '--machine',
          ctx.machineName,
        ],
        { timeout: ctx.defaultTimeout }
      );
      ctx.runner.expectSuccess(protectResult);
    });

    test.afterAll(async () => {
      if (ctx) {
        // Unprotect + delete snapshot
        await ctx.runner
          .run(
            [
              'ceph',
              'snapshot',
              'unprotect',
              snapshotName,
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
        await ctx.runner
          .run(
            [
              'ceph',
              'snapshot',
              'delete',
              snapshotName,
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
        // Delete image
        await ctx.runner
          .run(
            [
              'ceph',
              'image',
              'delete',
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

    cephCloneLifecycleScenario(
      () => ctx,
      () => ({
        poolName,
        imageName,
        snapshotName,
        sshValidation: true,
      })
    );
  });
