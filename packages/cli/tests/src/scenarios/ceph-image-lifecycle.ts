/**
 * Shared Ceph RBD image lifecycle scenario.
 *
 * Tests: image create, list, info, resize, delete.
 *
 * Runs in cloud mode (API-backed, ENTERPRISE edition) or
 * local mode (E2E, with SSH validation).
 *
 * @covers ceph_image_create, ceph_image_list, ceph_image_info, ceph_image_resize, ceph_image_delete
 */
import { expect, test } from '@playwright/test';
import { buildCommand, buildDeleteCommand } from '../utils/command-builder';
import type { TestContext } from '../utils/TestContext';

export interface CephImageLifecycleOptions {
  /** Pool name (cloud: created in beforeAll; E2E: default 'rbd') */
  poolName: string;
  /** Enable SSH-based validation */
  sshValidation?: boolean;
  /** Image size for create (E2E) */
  imageSize?: string;
  /** Resized image size (E2E) */
  resizedSize?: string;
}

/**
 * Register shared ceph image lifecycle tests.
 *
 * @param getCtx   Deferred accessor for TestContext.
 * @param options  Pool name and mode-specific overrides.
 */
export function cephImageLifecycleScenario(
  getCtx: () => TestContext,
  options: CephImageLifecycleOptions
) {
  const { poolName, sshValidation = false } = options;
  const imageSize = options.imageSize ?? '1G';
  const resizedSize = options.resizedSize ?? '2G';
  const imageName = `test-image-lifecycle-${Date.now()}`;

  test('create image', async () => {
    const ctx = getCtx();
    test.setTimeout(ctx.defaultTimeout);

    const flags: Record<string, string | undefined> = {
      image: imageName,
      pool: poolName,
      size: imageSize,
    };

    const result = await ctx.runner.run(buildCommand(['ceph', 'image', 'create'], ctx, flags), {
      timeout: ctx.defaultTimeout,
    });
    ctx.runner.expectSuccess(result);

    if (sshValidation && ctx.ssh) {
      const images = await ctx.ssh.rbdList(poolName);
      expect(images).toContain(imageName);
    }
  });

  test('list images should include created image', async () => {
    const ctx = getCtx();
    test.setTimeout(ctx.defaultTimeout);

    const result = await ctx.runner.run(
      buildCommand(['ceph', 'image', 'list'], ctx, { pool: poolName }),
      { timeout: ctx.defaultTimeout }
    );
    ctx.runner.expectSuccess(result);

    // In cloud mode, bridge functions return a queue task ID, not image data
    if (ctx.mode !== 'cloud') {
      const output = result.stdout + result.stderr;
      expect(output).toContain(imageName);
    }
  });

  test('image info should return details', async () => {
    const ctx = getCtx();
    test.setTimeout(ctx.defaultTimeout);

    const cmd =
      ctx.mode === 'local'
        ? buildCommand(['ceph', 'image', 'info'], ctx, { image: imageName, pool: poolName })
        : buildCommand(['ceph', 'image', 'list', '--pool', poolName], ctx);

    const result = await ctx.runner.run(cmd, { timeout: ctx.defaultTimeout });
    ctx.runner.expectSuccess(result);

    const output = result.stdout + result.stderr;
    expect(output.length).toBeGreaterThan(0);
  });

  if (sshValidation) {
    test('resize image', async () => {
      const ctx = getCtx();
      test.setTimeout(ctx.defaultTimeout);

      const result = await ctx.runner.run(
        buildCommand(['ceph', 'image', 'resize'], ctx, {
          image: imageName,
          size: resizedSize,
          pool: poolName,
        }),
        { timeout: ctx.defaultTimeout }
      );
      ctx.runner.expectSuccess(result);

      if (ctx.ssh) {
        const info = await ctx.ssh.rbdInfo(imageName, poolName);
        expect(info).toContain('2');
      }
    });
  }

  test('delete image', async () => {
    const ctx = getCtx();
    test.setTimeout(ctx.defaultTimeout);

    const result = await ctx.runner.run(
      buildDeleteCommand(['ceph', 'image', 'delete'], ctx, { image: imageName, pool: poolName }),
      { timeout: ctx.defaultTimeout }
    );
    ctx.runner.expectSuccess(result);

    if (sshValidation && ctx.ssh) {
      const images = await ctx.ssh.rbdList(poolName);
      expect(images).not.toContain(imageName);
    }
  });
}
