import { expect, test } from '@playwright/test';
import {
  assertSuccess,
  getE2EConfig,
  runLocalFunction,
  setupE2EEnvironment,
} from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';
import { E2E } from '../../src/utils/e2e-constants';
import { createRepo, safeDeleteRepo } from '../../src/utils/local-operations';

/**
 * Phase 6: Template Operations
 *
 * Tests repository_template_apply.
 *
 * Creates a repo, writes test files via SSH, then applies a template.
 * The template is a Base64-encoded JSON object that describes files/configs
 * to place in the repository.
 */
test.describe.serial('Phase 6: Template Operations @e2e', () => {
  const config = getE2EConfig();
  let ssh1: SSHValidator;
  let cleanup: (() => Promise<void>) | null = null;
  const ctxName = `e2e-phase6-${Date.now()}`;
  const repoMountPath = `${E2E.REPO_MOUNTS_BASE}/${E2E.TEST_REPO}`;

  test.beforeAll(async () => {
    test.skip(!config.enabled, 'E2E VMs not configured');
    ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
    cleanup = await setupE2EEnvironment(ctxName);

    // Create repository for template tests
    await createRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, E2E.REPO_SIZE, ctxName);
  });

  test.afterAll(async () => {
    await safeDeleteRepo(E2E.MACHINE_VM1, E2E.TEST_REPO, ctxName);
    await cleanup?.();
  });

  test('repository_template_apply - should apply template to repository', async () => {
    test.skip(!config.enabled, 'E2E not configured');
    test.setTimeout(E2E.TEST_TIMEOUT);

    // Create a minimal template — Base64-encoded JSON
    // Template structure provides a docker-compose definition for the repo
    const template = {
      version: '1',
      compose: E2E.DOCKER_COMPOSE_CONTENT,
    };
    const tmplBase64 = Buffer.from(JSON.stringify(template)).toString('base64');
    const grand = `e2e-grand-${Date.now()}`;

    const result = await runLocalFunction('repository_template_apply', E2E.MACHINE_VM1, {
      contextName: ctxName,
      params: {
        repository: E2E.TEST_REPO,
        tmpl: tmplBase64,
        grand,
      },
      timeout: E2E.TEST_TIMEOUT,
    });
    assertSuccess(result);

    // SSH validation: verify the template was applied
    // The template should have created config files in the repo directory
    const dirContents = await ssh1.listDir(repoMountPath);
    expect(dirContents.length).toBeGreaterThan(0);
  });
});
