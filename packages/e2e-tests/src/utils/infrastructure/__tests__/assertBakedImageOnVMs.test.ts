import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { InfrastructureManager } from '../InfrastructureManager';

const KEY = 'v1-3f9a2c';

// vi.mock factories are hoisted above the imports, so everything they close over is hoisted too.
const { BRIDGE, WORKER, executeOnVM } = vi.hoisted(() => ({
  BRIDGE: '192.168.111.1',
  WORKER: '192.168.111.11',
  executeOnVM:
    vi.fn<
      (ip: string, command: string) => Promise<{ stdout: string; stderr: string; code: number }>
    >(),
}));

vi.mock('../../bridge/OpsManager', () => ({
  getOpsManager: () => ({
    getBridgeVMIp: () => BRIDGE,
    getWorkerVMIps: () => [WORKER],
    getAllVMIps: () => [BRIDGE, WORKER],
    executeOnVM,
  }),
}));
vi.mock('../../RenetResolver', () => ({ getRenetResolver: () => ({}) }));
vi.mock('../../ssh', () => ({ getSSHExecutor: () => ({}) }));

function markers(byIp: Record<string, { stdout: string; stderr?: string; code?: number }>) {
  executeOnVM.mockImplementation((ip: string) => {
    const entry = byIp[ip];
    return Promise.resolve({
      stdout: entry.stdout,
      stderr: entry.stderr ?? '',
      code: entry.code ?? 0,
    });
  });
}

describe('InfrastructureManager.assertBakedImageOnVMs', () => {
  beforeEach(() => {
    executeOnVM.mockReset();
    vi.stubEnv('BAKED_IMAGE_KEY', KEY);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('passes when every VM carries the key', async () => {
    markers({
      [BRIDGE]: { stdout: `${KEY}|ubuntu-24.04|v0.9.1\n` },
      [WORKER]: { stdout: `${KEY}|ubuntu-24.04|v0.9.1\n` },
    });
    await expect(new InfrastructureManager().assertBakedImageOnVMs()).resolves.toBeUndefined();
    expect(executeOnVM).toHaveBeenCalledWith(BRIDGE, 'sudo cat /var/lib/rediacc/baked-image');
    expect(executeOnVM).toHaveBeenCalledWith(WORKER, 'sudo cat /var/lib/rediacc/baked-image');
  });

  it('fails naming the VM whose marker holds a different key', async () => {
    markers({
      [BRIDGE]: { stdout: `${KEY}|debian-12|v0.9.1\n` },
      [WORKER]: { stdout: 'v1-000000|debian-12|v0.9.0\n' },
    });
    const run = new InfrastructureManager().assertBakedImageOnVMs();
    await expect(run).rejects.toThrow(
      `${WORKER}: /var/lib/rediacc/baked-image holds key 'v1-000000'`
    );
    await expect(run).rejects.not.toThrow(`${BRIDGE}:`);
  });

  it('fails naming the VM with no marker', async () => {
    markers({
      [BRIDGE]: {
        stdout: '',
        stderr: 'cat: /var/lib/rediacc/baked-image: No such file or directory',
        code: 1,
      },
      [WORKER]: { stdout: `${KEY}|fedora-42|v0.9.1\n` },
    });
    await expect(new InfrastructureManager().assertBakedImageOnVMs()).rejects.toThrow(
      `${BRIDGE}: no readable /var/lib/rediacc/baked-image (cat: /var/lib/rediacc/baked-image: No such file or directory)`
    );
  });

  it.each([
    ['unset', undefined],
    ['empty', ''],
  ])('reads nothing when BAKED_IMAGE_KEY is %s', async (_label, value) => {
    vi.stubEnv('BAKED_IMAGE_KEY', value);
    expect(process.env.BAKED_IMAGE_KEY).toBe(value);
    await expect(new InfrastructureManager().assertBakedImageOnVMs()).resolves.toBeUndefined();
    expect(executeOnVM).not.toHaveBeenCalled();
  });
});
