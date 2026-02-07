import { expect, test } from '@playwright/test';
import { CliTestRunner } from '../../src/utils/CliTestRunner';
import { E2E } from '../../src/utils/e2e-constants';
import { getE2EConfig, setupE2EEnvironment } from '../../src/utils/local';
import { SSHValidator } from '../../src/utils/SSHValidator';

/**
 * Phase 6: Template Operations
 *
 * Tests repository_template_apply.
 *
 * Creates a repo, writes test files via SSH, then applies a template.
 * The template is a Base64-encoded JSON object that describes files/configs
 * to place in the repository.
 */
test.describe
  .serial('Phase 6: Template Operations @e2e', () => {
    const config = getE2EConfig();
    let ssh1: SSHValidator;
    let cleanup: (() => Promise<void>) | null = null;
    let runner: CliTestRunner;
    const ctxName = `e2e-phase6-${Date.now()}`;
    const repoMountPath = `${E2E.REPO_MOUNTS_BASE}/${E2E.REPO_TEMPLATE}`;

    test.beforeAll(async () => {
      test.skip(!config.enabled, 'E2E VMs not configured');
      ssh1 = new SSHValidator(config.vm1Ip, config.sshUser, config.sshKeyPath);
      cleanup = await setupE2EEnvironment(ctxName);
      runner = CliTestRunner.withContext(ctxName);

      // Force-delete stale repo from previous runs (ignore errors)
      try { await runner.run(['repository', 'down', E2E.REPO_TEMPLATE, '--machine', E2E.MACHINE_VM1, '--option', 'unmount'], { timeout: 60_000 }); } catch { /* ignore */ }
      try { await runner.run(['repository', 'delete', E2E.REPO_TEMPLATE, '--machine', E2E.MACHINE_VM1], { timeout: 60_000 }); } catch { /* ignore */ }

      // Create repository for template tests
      const createResult = await runner.run(
        ['repository', 'create', E2E.REPO_TEMPLATE, '--machine', E2E.MACHINE_VM1, '--size', E2E.REPO_SIZE],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(createResult);
    });

    test.afterAll(async () => {
      if (runner) {
        try {
          await runner.run(
            ['repository', 'down', E2E.REPO_TEMPLATE, '--machine', E2E.MACHINE_VM1, '--option', 'unmount'],
            { timeout: 120_000 }
          );
        } catch { /* ignore */ }
        try {
          await runner.run(
            ['repository', 'delete', E2E.REPO_TEMPLATE, '--machine', E2E.MACHINE_VM1],
            { timeout: 120_000 }
          );
        } catch { /* ignore */ }
      }
      await cleanup?.();
    });

    test('repository_template_apply - should apply template to repository', async () => {
      test.skip(!config.enabled, 'E2E not configured');
      test.setTimeout(E2E.TEST_TIMEOUT);

      // Create a minimal template — Base64-encoded JSON
      const template = {
        version: '1',
        compose: E2E.DOCKER_COMPOSE_CONTENT,
      };
      const tmplBase64 = Buffer.from(JSON.stringify(template)).toString('base64');
      const grand = `e2e-grand-${Date.now()}`;

      const result = await runner.run(
        [
          'repository', 'template', 'apply', E2E.REPO_TEMPLATE,
          '--machine', E2E.MACHINE_VM1,
          '--tmpl', tmplBase64,
          '--grand', grand,
        ],
        { timeout: E2E.TEST_TIMEOUT }
      );
      runner.expectSuccess(result);

      // SSH validation: verify the template was applied
      const dirContents = await ssh1.listDir(repoMountPath);
      expect(dirContents.length).toBeGreaterThan(0);
    });
  });
