import { test } from '@playwright/test';
import { cephImageLifecycleScenario } from '../../src/scenarios/ceph-image-lifecycle';
import { getE2EConfig } from '../../src/utils/local';
import { createLocalTestContext, type TestContext } from '../../src/utils/TestContext';

test.describe
  .serial('Ceph Image Lifecycle (E2E) @cli @e2e', () => {
    let ctx: TestContext;
    const config = getE2EConfig();
    const cephConfigured = !!process.env.E2E_CEPH_NODES;

    test.beforeAll(async () => {
      test.skip(!config.enabled || !cephConfigured, 'E2E VMs or Ceph not configured');
      const localCtx = await createLocalTestContext('e2e-ceph-image');
      test.skip(!localCtx, 'E2E environment setup failed');
      ctx = localCtx!;
    });

    test.afterAll(async () => {
      await ctx?.cleanup();
    });

    cephImageLifecycleScenario(() => ctx, {
      poolName: 'rbd',
      imageSize: '1G',
      resizedSize: '2G',
      sshValidation: true,
    });
  });
