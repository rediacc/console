/**
 * `rdc repo health <ref>` (G3): renet's `repository health --strict` report becomes exit 0 ok, 1 warning, 2 error.
 * A repo with no health() is "no check": exit 0, printed as such, never as healthy. A renet failure, an unreadable
 * answer and a renet that predates `--strict` are each exit 2.
 */

import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const out = vi.hoisted(() => ({
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
  print: vi.fn(),
}));
const exitCodes = vi.hoisted(() => [] as number[]);
const job = vi.hoisted(() => ({ runCommandJob: vi.fn() }));

vi.mock('../../services/core/output.js', () => ({ outputService: out }));
vi.mock('../../i18n/index.js', () => ({ t: (k: string) => k }));
vi.mock('../../services/core/request-context.js', () => ({
  setExitCode: (c: number) => exitCodes.push(c),
}));
vi.mock('../../services/jobs/steps.js', () => ({
  bindStepHandler: vi.fn(),
  planStep: (name: string, params: Record<string, unknown> = {}) => ({ name, params }),
}));
vi.mock('../../services/jobs/command-job.js', () => ({
  runCommandJob: job.runCommandJob,
  pendingExitCode: () => undefined,
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({
      name: 'shop',
      repoKey: 'shop:latest',
      machineName: 'm1',
      kubeCluster: undefined,
    }),
}));
vi.mock('../../services/config/network-id-discovery.js', () => ({
  ensureRepositoryNetworkId: () => Promise.resolve(),
}));
vi.mock('../../utils/repo-executor.js', () => ({
  recordedDatastoreMount: () => Promise.resolve(WK_DATASTORE_PATH),
}));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => 'table',
  handleError: (e: unknown) => {
    throw e;
  },
}));

const { handleRepoHealthOutput, handleRepoHealthJobFailure, registerRepoHealthCommand } =
  await import('../repo-health.js');

const report = (level: string | undefined, files: unknown[] = []) =>
  JSON.stringify({ state: 'healthy', ...(level ? { level } : {}), files });

const allPrinted = () =>
  [out.info, out.warn, out.error, out.success].flatMap((fn) => fn.mock.calls.map((c) => c[0]));

beforeEach(() => {
  for (const fn of Object.values(out)) fn.mockReset();
  exitCodes.length = 0;
  job.runCommandJob.mockReset();
});

describe('handleRepoHealthOutput', () => {
  it('a warning file exits 1', () => {
    const code = handleRepoHealthOutput(
      report('warning', [{ file: 'Rediaccfile', exit: 1, level: 'warning' }]),
      'shop',
      'm1',
      'table'
    );
    expect(code).toBe(1);
    expect(out.warn).toHaveBeenCalledWith('commands.repo.health.levelWarning');
  });

  it('an error file exits 2', () => {
    const code = handleRepoHealthOutput(
      report('error', [
        { file: 'app/Rediaccfile', exit: 2, level: 'error', detail: 'queue stuck' },
      ]),
      'shop',
      'm1',
      'table'
    );
    expect(code).toBe(2);
    expect(out.error).toHaveBeenCalledWith('commands.repo.health.levelError');
  });

  it('none exits 0 and prints "no check", never the healthy line', () => {
    const code = handleRepoHealthOutput(
      report('none', [{ file: 'Rediaccfile', exit: 42, level: 'none' }]),
      'shop',
      'm1',
      'table'
    );
    expect(code).toBe(0);
    expect(allPrinted()).toContain('commands.repo.health.levelNone');
    expect(allPrinted()).not.toContain('commands.repo.health.levelOk');
    expect(out.success).not.toHaveBeenCalled();
  });

  it('ok exits 0 with the healthy line (control)', () => {
    expect(handleRepoHealthOutput(report('ok'), 'shop', 'm1', 'table')).toBe(0);
    expect(out.success).toHaveBeenCalledWith('commands.repo.health.levelOk');
  });

  it('a report without a level (renet older than --strict) exits 2 naming the skew', () => {
    expect(handleRepoHealthOutput(report(undefined), 'shop', 'm1', 'table')).toBe(2);
    expect(out.error).toHaveBeenCalledWith('commands.repo.health.failed');
  });

  it('an unreadable answer exits 2', () => {
    expect(handleRepoHealthOutput('no json here', 'shop', 'm1', 'table')).toBe(2);
  });

  it('-o json carries level, files and the exit code', () => {
    const code = handleRepoHealthOutput(
      report('warning', [{ file: 'Rediaccfile', exit: 1, level: 'warning' }]),
      'shop',
      'm1',
      'json'
    );
    expect(code).toBe(1);
    expect(out.print).toHaveBeenCalledWith(
      expect.objectContaining({ repository: 'shop', level: 'warning', exitCode: 1 }),
      'json'
    );
  });

  it('-o json carries one coded finding with its fix for a warning, none for ok (X1)', () => {
    handleRepoHealthOutput(
      report('warning', [{ file: 'Rediaccfile', exit: 1, level: 'warning' }]),
      'shop',
      'm1',
      'json'
    );
    expect(out.print).toHaveBeenLastCalledWith(
      expect.objectContaining({
        findings: [
          expect.objectContaining({
            code: 'repo.health.warning',
            severity: 'warning',
            subject: 'shop',
            detail: 'Rediaccfile exit 1',
            fix: { action: 'repo-repair', class: 'auto-safe', window_only: false },
          }),
        ],
      }),
      'json'
    );
    handleRepoHealthOutput(
      report('ok', [{ file: 'Rediaccfile', exit: 0, level: 'ok' }]),
      'shop',
      'm1',
      'json'
    );
    expect(out.print).toHaveBeenLastCalledWith(expect.objectContaining({ findings: [] }), 'json');
  });
});

describe('handleRepoHealthJobFailure', () => {
  it('a renet transport failure exits 2', () => {
    expect(
      handleRepoHealthJobFailure({ error: 'ssh: connection refused' }, 'shop', 'm1', 'table')
    ).toBe(2);
  });

  it('an older renet that rejects --strict exits 2 with the skew message', () => {
    const code = handleRepoHealthJobFailure(
      { stderr: 'Error: unknown flag: --strict' },
      'shop',
      'm1',
      'json'
    );
    expect(code).toBe(2);
    expect(out.print).toHaveBeenCalledWith(
      expect.objectContaining({
        level: 'error',
        detail: 'commands.repo.health.unsupported',
        findings: [expect.objectContaining({ code: 'repo.health.failed', severity: 'error' })],
      }),
      'json'
    );
  });
});

describe('rdc repo health <ref>', () => {
  const run = async () => {
    const program = new Command().exitOverride();
    registerRepoHealthCommand(program);
    await program.parseAsync(['node', 'rdc', 'health', 'shop@m1']);
  };

  it('runs repository_health --strict for the repo and plans the render step', async () => {
    job.runCommandJob.mockResolvedValue({
      kind: 'finished',
      result: { success: true, exitCode: 0 },
    });
    await run();
    const [verb, options, steps] = job.runCommandJob.mock.calls[0];
    expect(verb).toBe('repo health');
    expect(options).toMatchObject({
      functionName: 'repository_health',
      machineName: 'm1',
      params: { repository: 'shop:latest', strict: true },
      captureOutput: true,
    });
    expect(steps).toEqual([{ name: 'printRepoHealth', params: { name: 'shop' } }]);
    expect(exitCodes).toEqual([]);
  });

  it('a failed job (renet transport failure) exits 2', async () => {
    job.runCommandJob.mockResolvedValue({
      kind: 'finished',
      result: { success: false, exitCode: 255, error: 'ssh: connect timed out' },
    });
    await run();
    expect(exitCodes).toEqual([2]);
  });
});
