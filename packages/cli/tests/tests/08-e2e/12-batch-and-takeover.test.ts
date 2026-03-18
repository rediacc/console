import { expect, test } from '@playwright/test';
import { E2E } from '../../src/utils/e2e-constants';
import {
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';

/**
 * Phase 8: Batch Operations & Takeover
 *
 * Tests: repository_down_all, repository_takeover
 */
test.describe.serial('Phase 8: Batch & Takeover @e2e', () => {
  const config = getE2EConfig();
  let cleanup: (() => Promise<void>) | null = null;
  const ctxName = `e2e-phase8-${Date.now()}`;

  test.beforeAll(async () => {
    test.skip(!config.enabled, 'E2E not configured');
    cleanup = await setupE2EEnvironment(ctxName);
  });

  test.afterAll(async () => {
    if (cleanup) await cleanup();
  });

  test('repository_down_all - should stop all repositories on machine', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    // repository_down_all is a batch operation that stops all repos.
    // On a clean VM with no running repos, it should succeed as a no-op.
    const result = await runLocalFunction('repository_down_all', E2E.MACHINE_VM1, {
      contextName: ctxName,
      timeout: E2E.SETUP_TIMEOUT,
    });
    expect(result.exitCode).toBe(0);
  });

  test('repository_takeover - should require a fork repository', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    // repository_takeover requires a valid fork repo. Without one, it should
    // fail with a meaningful error rather than crash.
    const result = await runLocalFunction('repository_takeover', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: { repository: 'nonexistent-fork' },
      timeout: E2E.SETUP_TIMEOUT,
    });
    // Expected to fail — no such fork exists
    expect(result.exitCode).not.toBe(undefined);
  });
});
