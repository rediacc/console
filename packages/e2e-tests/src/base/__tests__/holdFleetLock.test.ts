import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { holdFleetLock } from '../bridge-global-setup';

/** The lock file lives under XDG_RUNTIME_DIR, so a private directory keeps this test off the real fleet lock. */
describe('holdFleetLock', () => {
  const saved = {
    runtime: process.env.XDG_RUNTIME_DIR,
    wait: process.env.E2E_FLEET_WAIT_S,
  };
  let runtimeDir = '';

  beforeEach(() => {
    runtimeDir = fs.mkdtempSync(path.join(os.tmpdir(), 'fleet-lock-test-'));
    process.env.XDG_RUNTIME_DIR = runtimeDir;
    process.env.E2E_FLEET_WAIT_S = '1';
  });

  afterEach(() => {
    const restore = (key: string, value: string | undefined): void => {
      if (value === undefined) Reflect.deleteProperty(process.env, key);
      else process.env[key] = value;
    };
    restore('XDG_RUNTIME_DIR', saved.runtime);
    restore('E2E_FLEET_WAIT_S', saved.wait);
    fs.rmSync(runtimeDir, { recursive: true, force: true });
  });

  it('rejects when the wait runs out while another holder has the lock', async () => {
    const release = await holdFleetLock('holder');
    try {
      await expect(holdFleetLock('waiter')).rejects.toThrow(/fleet lock was not taken/);
    } finally {
      await release();
    }
  }, 30_000);

  it('frees the lock when the release runs, so the next holder takes it', async () => {
    const releaseFirst = await holdFleetLock('first');
    await releaseFirst();
    const releaseSecond = await holdFleetLock('second');
    await releaseSecond();
  }, 30_000);
});
