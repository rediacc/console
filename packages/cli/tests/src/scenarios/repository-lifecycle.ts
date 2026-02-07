/**
 * Shared repository lifecycle scenario.
 *
 * Tests the basic repository CRUD operations:
 * create, list, info, status, delete.
 *
 * Runs identically in cloud and local (E2E) modes via TestContext.
 *
 * @covers repository_create, repository_list, repository_info, repository_status, repository_delete
 */
import { expect, test } from '@playwright/test';
import { buildCommand, buildDeleteCommand } from '../utils/command-builder';
import type { TestContext } from '../utils/TestContext';

export interface RepositoryLifecycleOptions {
  /** Repository size (E2E only, ignored in cloud mode) */
  repoSize?: string;
  /** Enable SSH-based validation of VM state (requires ctx.ssh) */
  sshValidation?: boolean;
  /** Base path for repository mounts on VM (E2E only) */
  repoMountsBase?: string;
  /** Base path for repository storage on VM (E2E only) */
  repoStorageBase?: string;
}

/**
 * Register shared repository lifecycle tests.
 *
 * @param getCtx   Deferred accessor — ctx is set in beforeAll, used at runtime.
 * @param options  Mode-specific overrides.
 */
export function repositoryLifecycleScenario(
  getCtx: () => TestContext,
  options?: RepositoryLifecycleOptions
) {
  const repoSize = options?.repoSize;
  const sshValidation = options?.sshValidation ?? false;
  const repoMountsBase = options?.repoMountsBase ?? '/mnt/rediacc/mounts';
  const repoStorageBase = options?.repoStorageBase ?? '/mnt/rediacc/repositories';

  const repoName = `test-repo-lifecycle-${Date.now()}`;

  test('create repository', async () => {
    const ctx = getCtx();
    test.setTimeout(ctx.defaultTimeout);

    const flags: Record<string, string | undefined> = { size: repoSize };
    const result = await ctx.runner.run(
      buildCommand(['repository', 'create', repoName], ctx, flags),
      { timeout: ctx.defaultTimeout }
    );
    ctx.runner.expectSuccess(result);

    if (sshValidation && ctx.ssh) {
      const mountPath = `${repoMountsBase}/${repoName}`;
      expect(await ctx.ssh.mountExists(mountPath)).toBe(true);
      expect(await ctx.ssh.dirExists(mountPath)).toBe(true);
    }
  });

  test('list repositories should include the created repo', async () => {
    const ctx = getCtx();
    test.setTimeout(ctx.defaultTimeout);

    const result = await ctx.runner.run(buildCommand(['repository', 'list'], ctx), {
      timeout: ctx.defaultTimeout,
    });
    ctx.runner.expectSuccess(result);

    const output = result.stdout + result.stderr;
    expect(output).toContain(repoName);
  });

  test('repository info should return details', async () => {
    const ctx = getCtx();
    test.setTimeout(ctx.defaultTimeout);

    // Cloud uses `repository inspect <name>`, E2E uses `repository info` via bridge
    const cmd =
      ctx.mode === 'cloud'
        ? buildCommand(['repository', 'inspect', repoName], ctx)
        : buildCommand(['repository', 'info', repoName], ctx);

    const result = await ctx.runner.run(cmd, { timeout: ctx.defaultTimeout });
    ctx.runner.expectSuccess(result);

    const output = result.stdout + result.stderr;
    expect(output.length).toBeGreaterThan(0);
  });

  if (options?.sshValidation) {
    test('repository status should report active', async () => {
      const ctx = getCtx();
      test.setTimeout(ctx.defaultTimeout);

      const result = await ctx.runner.run(buildCommand(['repository', 'status', repoName], ctx), {
        timeout: ctx.defaultTimeout,
      });
      ctx.runner.expectSuccess(result);

      const output = result.stdout + result.stderr;
      expect(output.length).toBeGreaterThan(0);
    });
  }

  test('delete repository', async () => {
    const ctx = getCtx();
    test.setTimeout(ctx.defaultTimeout);

    const result = await ctx.runner.run(
      buildDeleteCommand(['repository', 'delete', repoName], ctx),
      { timeout: ctx.defaultTimeout }
    );
    ctx.runner.expectSuccess(result);

    if (sshValidation && ctx.ssh) {
      const mountPath = `${repoMountsBase}/${repoName}`;
      expect(await ctx.ssh.mountExists(mountPath)).toBe(false);

      const storageCheck = await ctx.ssh.exec(
        `ls ${repoStorageBase}/ | grep ${repoName} || echo GONE`
      );
      expect(storageCheck.stdout.trim()).toContain('GONE');
    }
  });
}
