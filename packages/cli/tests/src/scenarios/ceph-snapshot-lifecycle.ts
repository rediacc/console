/**
 * Shared Ceph RBD snapshot lifecycle scenario.
 *
 * Tests: snapshot create, list, delete.
 *
 * Runs in cloud mode (API-backed) or local mode (E2E, with SSH validation).
 * The parent image must already exist before this scenario runs.
 *
 * @covers ceph_snapshot_create, ceph_snapshot_list, ceph_snapshot_delete
 */
import { expect, test } from '@playwright/test';
import { buildCommand, buildDeleteCommand } from '../utils/command-builder';
import type { TestContext } from '../utils/TestContext';

export interface CephSnapshotLifecycleOptions {
  /** Pool containing the parent image */
  poolName: string;
  /** Parent image name (must already exist) */
  imageName: string;
  /** Enable SSH-based validation */
  sshValidation?: boolean;
}

/**
 * Register shared ceph snapshot lifecycle tests.
 */
export function cephSnapshotLifecycleScenario(
  getCtx: () => TestContext,
  getOptions: () => CephSnapshotLifecycleOptions
) {
  const snapshotName = `test-snap-lifecycle-${Date.now()}`;

  test('create snapshot', async () => {
    const ctx = getCtx();
    const { poolName, imageName, sshValidation } = getOptions();
    test.setTimeout(ctx.defaultTimeout);

    const result = await ctx.runner.run(
      buildCommand(['ceph', 'snapshot', 'create'], ctx, {
        snapshot: snapshotName,
        image: imageName,
        pool: poolName,
      }),
      { timeout: ctx.defaultTimeout }
    );
    ctx.runner.expectSuccess(result);

    if (sshValidation && ctx.ssh) {
      const snaps = await ctx.ssh.rbdSnapList(imageName, poolName);
      const hasSnapshot = snaps.some((s: string) => s.includes(snapshotName));
      expect(hasSnapshot).toBe(true);
    }
  });

  test('list snapshots should include created snapshot', async () => {
    const ctx = getCtx();
    const { poolName, imageName } = getOptions();
    test.setTimeout(ctx.defaultTimeout);

    const result = await ctx.runner.run(
      buildCommand(['ceph', 'snapshot', 'list'], ctx, {
        image: imageName,
        pool: poolName,
      }),
      { timeout: ctx.defaultTimeout }
    );
    ctx.runner.expectSuccess(result);

    const output = result.stdout + result.stderr;
    expect(output).toContain(snapshotName);
  });

  test('delete snapshot', async () => {
    const ctx = getCtx();
    const { poolName, imageName, sshValidation } = getOptions();
    test.setTimeout(ctx.defaultTimeout);

    const result = await ctx.runner.run(
      buildDeleteCommand(['ceph', 'snapshot', 'delete'], ctx, {
        snapshot: snapshotName,
        image: imageName,
        pool: poolName,
      }),
      { timeout: ctx.defaultTimeout }
    );
    ctx.runner.expectSuccess(result);

    if (sshValidation && ctx.ssh) {
      const snaps = await ctx.ssh.rbdSnapList(imageName, poolName);
      const hasSnapshot = snaps.some((s: string) => s.includes(snapshotName));
      expect(hasSnapshot).toBe(false);
    }
  });
}
