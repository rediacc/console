/**
 * Shared Ceph RBD clone lifecycle scenario.
 *
 * Tests: clone create, list, delete.
 *
 * Runs in cloud mode (API-backed) or local mode (E2E, with SSH validation).
 * The parent image and a protected snapshot must already exist.
 *
 * @covers ceph_clone_create, ceph_clone_list, ceph_clone_delete
 */
import { expect, test } from '@playwright/test';
import { buildCommand, buildDeleteCommand } from '../utils/command-builder';
import type { TestContext } from '../utils/TestContext';

export interface CephCloneLifecycleOptions {
  /** Pool containing the parent image */
  poolName: string;
  /** Parent image name (must already exist) */
  imageName: string;
  /** Snapshot to clone from (must be protected) */
  snapshotName: string;
  /** Enable SSH-based validation */
  sshValidation?: boolean;
}

/**
 * Register shared ceph clone lifecycle tests.
 */
export function cephCloneLifecycleScenario(
  getCtx: () => TestContext,
  getOptions: () => CephCloneLifecycleOptions
) {
  const cloneName = `test-clone-lifecycle-${Date.now()}`;

  test('create clone from snapshot', async () => {
    const ctx = getCtx();
    const { poolName, imageName, snapshotName, sshValidation } = getOptions();
    test.setTimeout(ctx.defaultTimeout);

    const result = await ctx.runner.run(
      buildCommand(['ceph', 'clone', 'create'], ctx, {
        clone: cloneName,
        snapshot: snapshotName,
        image: imageName,
        pool: poolName,
      }),
      { timeout: ctx.defaultTimeout }
    );
    ctx.runner.expectSuccess(result);

    if (sshValidation && ctx.ssh) {
      const images = await ctx.ssh.rbdList(poolName);
      expect(images).toContain(cloneName);
    }
  });

  test('list clones should include created clone', async () => {
    const ctx = getCtx();
    const { poolName, imageName, snapshotName } = getOptions();
    test.setTimeout(ctx.defaultTimeout);

    const result = await ctx.runner.run(
      buildCommand(['ceph', 'clone', 'list'], ctx, {
        snapshot: snapshotName,
        image: imageName,
        pool: poolName,
      }),
      { timeout: ctx.defaultTimeout }
    );
    ctx.runner.expectSuccess(result);

    const output = result.stdout + result.stderr;
    expect(output).toContain(cloneName);
  });

  test('delete clone', async () => {
    const ctx = getCtx();
    const { poolName, imageName, snapshotName, sshValidation } = getOptions();
    test.setTimeout(ctx.defaultTimeout);

    const result = await ctx.runner.run(
      buildDeleteCommand(['ceph', 'clone', 'delete'], ctx, {
        clone: cloneName,
        snapshot: snapshotName,
        image: imageName,
        pool: poolName,
      }),
      { timeout: ctx.defaultTimeout }
    );
    ctx.runner.expectSuccess(result);

    if (sshValidation && ctx.ssh) {
      const images = await ctx.ssh.rbdList(poolName);
      expect(images).not.toContain(cloneName);
    }
  });
}
