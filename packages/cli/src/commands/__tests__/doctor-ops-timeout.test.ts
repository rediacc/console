/**
 * `renet ops host check` on a loaded Windows VM took longer than the 10 s every doctor probe got, and the row read
 * "check failed" with no hint at the cause (finding B3). spawnSync is a stand-in, so the limit is read, not waited out.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const stand = vi.hoisted(() => ({
  calls: [] as { args: string[]; timeout: unknown }[],
  timedOut: false,
}));

vi.mock('node:child_process', () => ({
  spawnSync: (_cmd: string, args: string[], options: { timeout?: number }) => {
    stand.calls.push({ args, timeout: options.timeout });
    if (stand.timedOut) {
      return {
        status: null,
        stdout: '',
        stderr: '',
        error: Object.assign(new Error('spawnSync renet ETIMEDOUT'), { code: 'ETIMEDOUT' }),
      };
    }
    return { status: 0, stdout: JSON.stringify({ checks: [] }), stderr: '' };
  },
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getLocalConfig: async () => ({ renetPath: process.execPath }),
  },
}));

import { checkVirtualization, OPS_CHECK_TIMEOUT_MS } from '../doctor.js';

describe('doctor OPS prerequisites time limit (finding B3)', () => {
  beforeEach(() => {
    stand.calls.length = 0;
    stand.timedOut = false;
  });

  it('runs the host check with the long limit, not the version-probe one', async () => {
    expect(OPS_CHECK_TIMEOUT_MS).toBeGreaterThanOrEqual(30_000);
    await checkVirtualization('linux');
    const call = stand.calls.find((c) => c.args.join(' ') === 'ops host check --json');
    expect(call?.timeout).toBe(OPS_CHECK_TIMEOUT_MS);
  });

  it('reports a killed check as a timed-out warning that names the limit, not "check failed"', async () => {
    stand.timedOut = true;
    const section = await checkVirtualization('linux');
    const row = section.checks[0];
    expect(row.status).toBe('warn');
    expect(row.value).toContain(`${OPS_CHECK_TIMEOUT_MS / 1000}s`);
    expect(row.value).toContain('timed out');
    expect(row.value).not.toBe('check failed');
  });
});
