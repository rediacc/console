/**
 * `rdc backup churn <repo>`: drives the churn probe (function `backup_churn_probe`), prints the
 * projection and the cell recommendation, and always removes the probe's reflink base (W5, D-cells).
 *
 * The base pins extents on the machine until it is forgotten, so a run that fails halfway and
 * leaves it behind is a space leak the operator never sees. The other trap is a baseline: the
 * probe's first observation reports no changed bytes because nothing was compared, and a verb that
 * averaged it in would tell a busy repository it has no churn.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../utils/repo-executor.js', () => ({ executeRepoFunction: mockExecute }));
const mockResolveRef = vi.hoisted(() => vi.fn());
vi.mock('../../utils/repo-target.js', () => ({ resolveRepoRef: mockResolveRef }));

const mockInfo = vi.hoisted(() => vi.fn());
const mockWarn = vi.hoisted(() => vi.fn());
const mockSuccess = vi.hoisted(() => vi.fn());
const mockPrint = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mockInfo,
    success: mockSuccess,
    warn: mockWarn,
    error: vi.fn(),
    print: mockPrint,
    format: (rows: unknown) => JSON.stringify(rows),
  },
}));

const outputFormat = vi.hoisted(() => ({ value: 'table' }));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => outputFormat.value,
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

const { registerBackupChurn, measureChurn } = await import('../backup-churn.js');

const MIB = 1024 * 1024;
const GIB = 1024 ** 3;

const record = (over: Record<string, unknown> = {}) => ({
  guid: 'g1',
  status: 'measured',
  probedAt: '2026-11-02T10:00:00Z',
  intervalSeconds: 300,
  imageBytes: 8 * GIB,
  changedBytes: 40 * MIB,
  changedExtents: 40,
  projectedUploadBytes: {
    '1MiB': 40 * MIB,
    '2MiB': 80 * MIB,
    '4MiB': 160 * MIB,
    '8MiB': 320 * MIB,
  },
  projectedCells: { '1MiB': 40, '2MiB': 40, '4MiB': 40, '8MiB': 40 },
  ...over,
});
const baseline = () =>
  record({
    status: 'baseline',
    changedBytes: 0,
    changedExtents: 0,
    intervalSeconds: 0,
    projectedCells: undefined,
    projectedUploadBytes: undefined,
  });
const skipped = () =>
  record({
    status: 'skipped',
    reason: 'cold backup running for this repo',
    changedBytes: 0,
    projectedCells: undefined,
    projectedUploadBytes: undefined,
  });
const forgotten = () =>
  record({ status: 'forgotten', projectedCells: undefined, projectedUploadBytes: undefined });

/** The executor's answer for one probe call: the record on stdout. */
const answer = (rec: Record<string, unknown>) => ({
  success: true,
  exitCode: 0,
  stdout: `${JSON.stringify(rec)}\n`,
});

/** Serve the given records in order, then `forgotten` for the forget call. */
function serve(...records: Record<string, unknown>[]): void {
  const queue = [...records];
  mockExecute.mockImplementation(
    (_fn: string, _repo: string, _machine: string, params: { forget?: boolean }) =>
      Promise.resolve(params.forget ? answer(forgotten()) : answer(queue.shift() ?? skipped()))
  );
}

const probeParams = (): { forget?: boolean }[] =>
  mockExecute.mock.calls.map((c) => c[3] as { forget?: boolean });
const forgetCalls = (): number => probeParams().filter((p) => p.forget === true).length;
const text = (m: ReturnType<typeof vi.fn>) => m.mock.calls.map((c) => String(c[0])).join('\n');

async function run(argv: string[]): Promise<void> {
  const backup = new Command('backup');
  backup.exitOverride();
  registerBackupChurn(backup);
  await backup.parseAsync(['churn', ...argv], { from: 'user' });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockExecute.mockReset();
  outputFormat.value = 'table';
  process.exitCode = 0;
  mockResolveRef.mockResolvedValue({ repoKey: 'shop', machineName: 'm1' });
});

describe('measureChurn sampling', () => {
  it('takes a baseline, waits the interval, measures, then forgets the base', async () => {
    serve(baseline(), record());
    const sleep = vi.fn().mockResolvedValue(undefined);
    const result = await measureChurn({
      repoKey: 'shop',
      machineName: 'm1',
      samples: 1,
      intervalSeconds: 300,
      sleep,
    });

    expect(probeParams()).toEqual([{ forget: false }, { forget: false }, { forget: true }]);
    expect(sleep).toHaveBeenCalledTimes(1);
    expect(sleep).toHaveBeenCalledWith(300_000);
    expect(result.summary.samples).toBe(1);
    expect(result.forgotten).toBe(true);
  });

  it('stops as soon as it has the samples it was asked for, with no wait before the first', async () => {
    // A base left by an earlier run: the first probe is already a measurement.
    serve(record(), record());
    const sleep = vi.fn().mockResolvedValue(undefined);
    await measureChurn({
      repoKey: 'shop',
      machineName: 'm1',
      samples: 1,
      intervalSeconds: 300,
      sleep,
    });

    expect(probeParams()).toEqual([{ forget: false }, { forget: true }]);
    expect(sleep).not.toHaveBeenCalled();
  });

  it('asks for the repository by name and the forget flag only', async () => {
    serve(record());
    await measureChurn({
      repoKey: 'shop',
      machineName: 'm1',
      samples: 1,
      intervalSeconds: 60,
      sleep: vi.fn(),
    });

    const [fn, repo, machine, params, options] = mockExecute.mock.calls[0];
    expect(fn).toBe('backup_churn_probe');
    expect(repo).toBe('shop');
    expect(machine).toBe('m1');
    expect(params).toEqual({ forget: false });
    // The record on stdout is the answer, and a probe the verb reads must not be backgrounded.
    expect(options).toMatchObject({ captureOutput: true, probe: true });
  });
});

describe('measureChurn always removes the base', () => {
  it('forgets after a probe that failed, and reports the failure', async () => {
    mockExecute.mockImplementation(
      (_f: string, _r: string, _m: string, params: { forget?: boolean }) =>
        Promise.resolve(
          params.forget ? answer(forgotten()) : { success: false, exitCode: 1, stdout: '' }
        )
    );
    const result = await measureChurn({
      repoKey: 'shop',
      machineName: 'm1',
      samples: 2,
      intervalSeconds: 60,
      sleep: vi.fn(),
    });

    // THE DEFECT: a failure that skips the cleanup leaves a reflink base pinning extents on the machine.
    expect(forgetCalls()).toBe(1);
    expect(result.failed).toBe(true);
    expect(result.summary.samples).toBe(0);
  });

  it('forgets after the executor throws, and rethrows', async () => {
    mockExecute.mockImplementation(
      (_f: string, _r: string, _m: string, params: { forget?: boolean }) =>
        params.forget
          ? Promise.resolve(answer(forgotten()))
          : Promise.reject(new Error('ssh: connection lost'))
    );
    await expect(
      measureChurn({
        repoKey: 'shop',
        machineName: 'm1',
        samples: 1,
        intervalSeconds: 60,
        sleep: vi.fn(),
      })
    ).rejects.toThrow('ssh: connection lost');
    expect(forgetCalls()).toBe(1);
  });

  it('forgets once even when the wait between probes is interrupted', async () => {
    serve(baseline());
    const sleep = vi.fn().mockRejectedValue(new Error('interrupted'));
    await expect(
      measureChurn({ repoKey: 'shop', machineName: 'm1', samples: 1, intervalSeconds: 60, sleep })
    ).rejects.toThrow('interrupted');
    expect(forgetCalls()).toBe(1);
  });

  it('reports a base it could not remove', async () => {
    mockExecute.mockImplementation(
      (_f: string, _r: string, _m: string, params: { forget?: boolean }) =>
        Promise.resolve(
          params.forget
            ? answer({ ...forgotten(), status: 'failed', reason: 'permission denied' })
            : answer(record())
        )
    );
    const result = await measureChurn({
      repoKey: 'shop',
      machineName: 'm1',
      samples: 1,
      intervalSeconds: 60,
      sleep: vi.fn(),
    });

    expect(result.forgotten).toBe(false);
  });
});

describe('measureChurn: a baseline is not zero churn', () => {
  it('a skipped probe after the baseline leaves no measurement, not "no churn"', async () => {
    serve(baseline(), skipped());
    const result = await measureChurn({
      repoKey: 'shop',
      machineName: 'm1',
      samples: 1,
      intervalSeconds: 60,
      sleep: vi.fn(),
    });

    expect(result.summary.samples).toBe(0);
    expect(result.summary.changedCellsPerRun).toBeUndefined();
    expect(result.summary.recommendation).toBeUndefined();
  });
});

describe('backup churn command', () => {
  it('prints the projection per cell size and the recommendation, then says the base is gone', async () => {
    serve(record());
    await run(['shop', '--samples', '1', '--interval', '1m']);

    const rows = text(mockPrint);
    expect(rows).toContain('1MiB');
    expect(rows).toContain('4MiB');
    // 40 changed cells at 1 MiB against 160 MiB at 4 MiB saves 75%: the recommendation is 1 MiB.
    const info = text(mockInfo) + text(mockSuccess);
    expect(info).toContain('commands.backup.churn.recommend.scattered-small');
    expect(info).toContain('"savedPercent":75');
    expect(info).toContain('commands.backup.churn.forgotten');
    expect(process.exitCode).toBe(0);
  });

  it('with only a baseline, says no measurement was made and exits 1', async () => {
    serve(baseline(), skipped());
    // One real second between the two probes.
    await run(['shop', '--samples', '1', '--interval', '1s']);

    expect(text(mockWarn)).toContain('commands.backup.churn.noMeasurement');
    expect(text(mockInfo)).not.toContain('commands.backup.churn.recommend');
    expect(mockPrint).not.toHaveBeenCalled();
    expect(process.exitCode).toBe(1);
    expect(forgetCalls()).toBe(1);
  });

  it('carries the records and the summary in -o json', async () => {
    outputFormat.value = 'json';
    serve(record());
    await run(['shop', '--samples', '1', '--interval', '1m']);

    const [payload, format] = mockPrint.mock.calls[0] as [Record<string, unknown>, string];
    expect(format).toBe('json');
    expect(payload).toMatchObject({
      forgotten: true,
      summary: { samples: 1, recommendation: { cellBytes: MIB, rule: 'scattered-small' } },
    });
    expect((payload.records as unknown[]).length).toBe(1);
  });

  it('a failed probe exits through the executor and still forgets the base', async () => {
    mockExecute.mockImplementation(
      (_f: string, _r: string, _m: string, params: { forget?: boolean }) => {
        if (params.forget) return Promise.resolve(answer(forgotten()));
        process.exitCode = 3;
        return Promise.resolve({ success: false, exitCode: 3, stdout: '' });
      }
    );
    await run(['shop', '--samples', '1', '--interval', '1m']);

    expect(forgetCalls()).toBe(1);
    expect(process.exitCode).toBe(3);
    expect(mockPrint).not.toHaveBeenCalled();
  });

  it('warns with the repository when the base could not be removed, and exits 1', async () => {
    mockExecute.mockImplementation(
      (_f: string, _r: string, _m: string, params: { forget?: boolean }) =>
        Promise.resolve(
          params.forget ? { success: false, exitCode: 1, stdout: '' } : answer(record())
        )
    );
    await run(['shop', '--samples', '1', '--interval', '1m']);

    expect(text(mockWarn)).toContain('commands.backup.churn.forgetFailed');
    expect(text(mockWarn)).toContain('shop');
    expect(process.exitCode).toBe(1);
  });

  it.each([
    ['--samples', '0'],
    ['--samples', 'many'],
    ['--samples', '1.5'],
    ['--samples', '500'],
    ['--interval', '90'],
    ['--interval', '0m'],
    ['--interval', '2d'],
  ])('refuses %s %s before touching the machine', async (flag, value) => {
    await expect(run(['shop', flag, value])).rejects.toThrow(
      /commands.backup.churn.(samples|interval)Invalid/
    );
    expect(mockExecute).not.toHaveBeenCalled();
  });
});
