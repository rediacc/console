import { test } from '@playwright/test';
import { repositoryLifecycleScenario } from '../../src/scenarios/repository-lifecycle';
import { E2E } from '../../src/utils/e2e-constants';
import { getE2EConfig } from '../../src/utils/local';
import { createLocalTestContext, type TestContext } from '../../src/utils/TestContext';

test.describe.serial('Repository Lifecycle (E2E) @cli @e2e', () => {
  let ctx: TestContext;
  const config = getE2EConfig();

  test.beforeAll(async () => {
    test.skip(!config.enabled, 'E2E VMs not configured');
    const localCtx = await createLocalTestContext('e2e-repo-lifecycle');
    test.skip(!localCtx, 'E2E environment setup failed');
    ctx = localCtx!;
  });

  test.afterAll(async () => {
    await ctx?.cleanup();
  });

  repositoryLifecycleScenario(() => ctx, {
    repoSize: E2E.REPO_SIZE,
    sshValidation: true,
    repoMountsBase: E2E.REPO_MOUNTS_BASE,
    repoStorageBase: E2E.REPO_STORAGE_BASE,
  });
});
