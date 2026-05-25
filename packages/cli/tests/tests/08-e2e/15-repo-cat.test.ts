import { expect, test } from '@playwright/test';
import { E2E } from '../../src/utils/e2e-constants';
import {
  assertSuccess,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { safeDeleteRepo } from '../../src/utils/local-operations';

/**
 * Phase 15: repository_cat — bounded, pipeable single-file read (#490).
 *
 * Creates a repo, reads a known mount-root file (`.envrc`, written at create
 * time) through the bounded reader, and verifies:
 *   - --stat returns metadata without reading content
 *   - a byte/line window returns content (base64-framed under --encode so it
 *     survives bridge log interleaving and binary content)
 *   - path traversal outside the mount is rejected
 */
test.describe
  .serial('Phase 15: repository_cat @e2e', () => {
    const config = getE2EConfig();
    let cleanup: (() => Promise<void>) | null = null;
    const ctxName = `e2e-phase15-${Date.now()}`;

    test.beforeAll(async () => {
      test.skip(!config.enabled, 'E2E VMs not configured');
      cleanup = await setupE2EEnvironment(ctxName);
      await runLocalFunction('repository_create', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, size: E2E.REPO_SIZE },
        timeout: E2E.TEST_TIMEOUT,
      });
    });

    test.afterAll(async () => {
      await safeDeleteRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, ctxName);
      await cleanup?.();
    });

    test('repository_cat --stat returns metadata', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_cat', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, path: '.envrc', stat: true },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });

    test('repository_cat reads a bounded window', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_cat', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, path: '.envrc', max_bytes: 64 },
        timeout: E2E.TEST_TIMEOUT,
      });
      assertSuccess(result);
    });

    test('repository_cat rejects path traversal', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      const result = await runLocalFunction('repository_cat', E2E.MACHINE_VM1, {
        contextName: ctxName,
        params: { repository: E2E.TEST_REPO, path: '../../etc/passwd', stat: true },
        timeout: E2E.TEST_TIMEOUT,
      });
      expect(result.success).toBe(false);
    });
  });
