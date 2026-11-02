import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockPrint = vi.hoisted(() => vi.fn());
const mockError = vi.hoisted(() => vi.fn());
const mockSetExitCode = vi.hoisted(() => vi.fn());
const mockRecord = vi.hoisted(() => vi.fn());

vi.mock('../../core/output.js', () => ({
  outputService: { print: mockPrint, error: mockError, warn: vi.fn(), info: vi.fn() },
}));
vi.mock('../../core/request-context.js', () => ({ setExitCode: mockSetExitCode }));
vi.mock('../../backup/backup-runs-state.js', () => ({ recordBackupRun: mockRecord }));
vi.mock('../../../utils/errors.js', () => ({ getOutputFormat: () => 'json' }));
vi.mock('../../../i18n/index.js', () => ({ t: (key: string) => key }));

import { resolveStepHandler, type StepContext } from '../steps.js';

function ctx(over: Partial<StepContext>): StepContext {
  return {
    jobId: 'j1',
    machine: 'm1',
    params: { repo: 'shop', level: 'spot' },
    state: 'succeeded',
    finishedAt: '2026-11-02T00:00:00Z',
    ...over,
  };
}

const recorded = () => mockRecord.mock.calls.map((c) => c[1].status);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('reportVerifyVerdict', () => {
  it('turns unreadable output into status unknown, reports failure and sets exit 1', async () => {
    const run = await resolveStepHandler('reportVerifyVerdict');
    await run(ctx({ output: 'garbage that is not a verdict' }));
    expect(mockPrint.mock.calls[0][0]).toMatchObject({ status: 'unknown', level: 'spot' });
    expect(mockError).toHaveBeenCalled();
    expect(mockSetExitCode).toHaveBeenCalledWith(1);
  });

  it('turns absent output into status unknown as well', async () => {
    const run = await resolveStepHandler('reportVerifyVerdict');
    await run(ctx({ output: undefined }));
    expect(mockPrint.mock.calls[0][0]).toMatchObject({ status: 'unknown' });
    expect(mockSetExitCode).toHaveBeenCalledWith(1);
  });

  it('prints a verified verdict with no failure', async () => {
    const run = await resolveStepHandler('reportVerifyVerdict');
    await run(ctx({ output: '{"status":"verified","level":"spot","checkedCells":8}' }));
    expect(mockPrint.mock.calls[0][0]).toMatchObject({ status: 'verified', checkedCells: 8 });
    expect(mockSetExitCode).not.toHaveBeenCalled();
    expect(mockError).not.toHaveBeenCalled();
  });
});

describe('recordVerifyVerdict (success outcome)', () => {
  it('records verified from a verified verdict', async () => {
    const run = await resolveStepHandler('recordVerifyVerdict');
    await run(ctx({ output: '{"status":"verified","level":"spot"}' }));
    expect(recorded()).toEqual(['verified']);
  });

  it('never records verified for a no-backup verdict, even on a job that exited 0', async () => {
    const run = await resolveStepHandler('recordVerifyVerdict');
    await run(ctx({ output: '{"status":"no-backup","level":"spot"}' }));
    expect(recorded()).toEqual(['no-backup']);
  });

  it('records unknown when the verdict cannot be read', async () => {
    const run = await resolveStepHandler('recordVerifyVerdict');
    await run(ctx({ output: 'nothing useful' }));
    expect(recorded()).toEqual(['unknown']);
  });
});

describe('recordVerifyVerdictFailed (failure outcome)', () => {
  it('records the verdict status, mismatch', async () => {
    const run = await resolveStepHandler('recordVerifyVerdictFailed');
    await run(
      ctx({ state: 'failed', exitCode: 1, output: '{"status":"mismatch","level":"full"}' })
    );
    expect(recorded()).toEqual(['mismatch']);
  });

  it('records no-backup, not a generic mismatch', async () => {
    const run = await resolveStepHandler('recordVerifyVerdictFailed');
    await run(ctx({ state: 'failed', exitCode: 1, output: '{"status":"no-backup"}' }));
    expect(recorded()).toEqual(['no-backup']);
  });

  it('records failed when the failed job left no verdict', async () => {
    const run = await resolveStepHandler('recordVerifyVerdictFailed');
    await run(ctx({ state: 'failed', exitCode: 1, output: '' }));
    expect(recorded()).toEqual(['failed']);
  });
});
