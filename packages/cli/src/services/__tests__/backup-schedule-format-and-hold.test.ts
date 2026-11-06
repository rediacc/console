/**
 * Two live-run defects (2026-11-06, production machine): `backup status -o json` printed the human
 * table because the render passed a literal 'table', and `backup schedule` announced "Provisioning
 * renet" while REDIACC_NO_PROVISION=1 held provisioning.
 *
 * Real: the status render and the schedule pre-deploy step. Fake: output, the renet acquire, license refresh.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  print: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
  acquire: vi.fn(() => Promise.resolve({ remotePath: '/r/renet' })),
}));

vi.mock('../core/output.js', () => ({
  outputService: {
    print: mocks.print,
    info: mocks.info,
    warn: mocks.warn,
    error: mocks.error,
    debug: vi.fn(),
    success: vi.fn(),
  },
}));
vi.mock('../renet/renet-execution.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../renet/renet-execution.js')>()),
  acquireRemoteRenet: mocks.acquire,
}));
// A release build: a development build holds the machine's renet (renet-provision-hold.test.ts).
vi.mock('../../utils/platform.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/platform.js')>()),
  isDevBuild: () => false,
}));
vi.mock('../account/license.js', () => ({
  refreshRepoLicensesBatch: () =>
    Promise.resolve({ scanned: 0, valid: 0, issued: 0, refreshed: 0, unchanged: 0, failed: 0 }),
}));

const { renderBackupScheduleStatus, _testing } = await import('../backup/backup-schedule.js');
const { setOutputFormat } = await import('../../utils/errors.js');

const EXPECTED = [{ unitName: 'nightly', strategyName: 'nightly', schedule: '0 3 * * *' }];

describe('backup status honours the output format', () => {
  beforeEach(() => {
    mocks.print.mockClear();
  });
  afterEach(() => {
    setOutputFormat('table');
  });

  it('passes json through to the printer', () => {
    setOutputFormat('json');
    renderBackupScheduleStatus('m1', EXPECTED, '');
    expect(mocks.print).toHaveBeenCalledTimes(1);
    expect(mocks.print.mock.calls[0]?.[1]).toBe('json');
  });

  it('CONTROL: the default stays table', () => {
    renderBackupScheduleStatus('m1', EXPECTED, '');
    expect(mocks.print.mock.calls[0]?.[1]).toBe('table');
  });
});

describe('the provisioning announcement follows the hold', () => {
  beforeEach(() => {
    mocks.info.mockClear();
  });
  afterEach(() => {
    delete process.env.REDIACC_NO_PROVISION;
  });
  const infos = () => mocks.info.mock.calls.map((c) => String(c[0]));
  const run = () =>
    _testing.preDeployProvisioning('m1', {} as never, { ip: '10.0.0.9', user: 'root' }, 'KEY', {});

  it('CONTROL: announces provisioning when not held', async () => {
    await run();
    expect(infos().some((m) => m.includes('Provisioning renet to 10.0.0.9'))).toBe(true);
  });

  it('does not announce provisioning when held, and names the hold', async () => {
    process.env.REDIACC_NO_PROVISION = '1';
    await run();
    expect(infos().some((m) => m.includes('Provisioning renet'))).toBe(false);
    expect(infos().some((m) => m.includes('REDIACC_NO_PROVISION=1'))).toBe(true);
  });
});
