import { test } from '@playwright/test';
import { repositoryLifecycleScenario } from '../../src/scenarios/repository-lifecycle';
import { createCloudTestContext, type TestContext } from '../../src/utils/TestContext';

test.describe('Repository Lifecycle (Cloud) @cli @resources', () => {
  let ctx: TestContext;

  test.beforeAll(async () => {
    ctx = await createCloudTestContext();
  });

  test.afterAll(async () => {
    await ctx?.cleanup();
  });

  repositoryLifecycleScenario(() => ctx, { repoSize: '1G' });
});
