/**
 * DPAPI on a loaded Windows box: every call of the round trip spawns powershell.exe (about 1.7 s idle, far more under
 * load), so the spawn carries a generous time limit, and a spawn killed at that limit is reported as a timeout rather than
 * as a store that does not work (finding B3). powershell is a stand-in behind a mocked execFileSync, platform mocked.
 */
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const stand = vi.hoisted(() => ({
  mode: 'ok' as 'ok' | 'timeout' | 'broken',
  timeouts: [] as unknown[],
  stateDir: undefined as string | undefined,
}));

vi.mock('@rediacc/shared/paths', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@rediacc/shared/paths')>();
  return {
    ...actual,
    getRediaccDirs: () => ({ ...actual.getRediaccDirs(), state: stand.stateDir }),
  };
});

vi.mock('node:child_process', () => ({
  execFileSync: (_tool: string, _args: string[], options: { input?: string; timeout?: number }) => {
    stand.timeouts.push(options.timeout);
    if (stand.mode === 'timeout') {
      throw Object.assign(new Error('spawnSync powershell.exe ETIMEDOUT'), { code: 'ETIMEDOUT' });
    }
    if (stand.mode === 'broken') {
      throw Object.assign(new Error('exit 1'), { status: 1, stderr: 'Add-Type : access denied\n' });
    }
    // Protect and Unprotect both answer with the input, which is enough for a round trip.
    return `rdc-dpapi:${options.input}`;
  },
}));

/** A fresh module per test: a native backend that passed its proof is remembered for the process. */
function fresh(): Promise<typeof import('../secure-storage.js')> {
  vi.resetModules();
  return import('../secure-storage.js');
}

async function failure() {
  const { SecureStorageUnavailableError, getSecureStorage } = await fresh();
  try {
    getSecureStorage();
  } catch (error) {
    expect(error).toBeInstanceOf(SecureStorageUnavailableError);
    return error as InstanceType<typeof SecureStorageUnavailableError>;
  }
  throw new Error('getSecureStorage did not throw');
}

describe('DPAPI backend time limit (finding B3)', () => {
  const platform = Object.getOwnPropertyDescriptor(process, 'platform');
  beforeEach(() => {
    stand.mode = 'ok';
    stand.timeouts.length = 0;
    vi.stubEnv('REDIACC_SECRET_STORE', '');
    stand.stateDir = mkdtempSync(join(tmpdir(), 'rdc-b3-'));
    Object.defineProperty(process, 'platform', { value: 'win32' });
  });
  afterEach(() => {
    if (platform) Object.defineProperty(process, 'platform', platform);
    vi.unstubAllEnvs();
    stand.stateDir = undefined;
  });

  it('gives every powershell spawn a limit sized for a loaded machine', async () => {
    const { DPAPI_TIMEOUT_MS, getSecureStorage } = await fresh();
    expect(DPAPI_TIMEOUT_MS).toBeGreaterThanOrEqual(20_000);
    expect(getSecureStorage().type).toBe('dpapi');
    expect(stand.timeouts.length).toBeGreaterThan(0);
    expect(stand.timeouts.every((limit) => limit === DPAPI_TIMEOUT_MS)).toBe(true);
  });

  it('reports a spawn killed at the limit as a timeout that names the limit, not as an unusable store', async () => {
    stand.mode = 'timeout';
    const error = await failure();
    expect(error.timedOut).toBe(true);
    const { DPAPI_TIMEOUT_MS } = await fresh();
    expect(error.message).toContain(`${DPAPI_TIMEOUT_MS / 1000} seconds`);
    expect(error.message).not.toContain('could not be stored and read back');
  });

  it('still reports a powershell that ran and failed as an unusable store, with its own error line', async () => {
    stand.mode = 'broken';
    const error = await failure();
    expect(error.timedOut).toBe(false);
    expect(error.message).toContain('could not be stored and read back');
    expect(error.details?.[0]).toBe('Add-Type : access denied');
  });
});
