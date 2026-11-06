/**
 * `machine restart-services <m> --include-docker --repo <name>` maps the repo to its network id and scopes the
 * rolling restart to it. A renet that predates the scope answers with a refusal, and the command must exit 1
 * without ever running an unscoped restart.
 */
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installJobDeps } from '../../__tests__/job-deps.js';

const mocks = vi.hoisted(() => ({
  error: vi.fn(),
  info: vi.fn(),
  success: vi.fn(),
  print: vi.fn(),
  warn: vi.fn(),
  setExitCode: vi.fn(),
  repos: {} as Record<string, { networkId?: number }>,
  format: 'table',
}));

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));
vi.mock('../../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getOutputFormat: () => mocks.format,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../_validate.js', () => ({ assertMachineExists: async () => undefined }));
vi.mock('../../../services/core/output.js', () => ({
  outputService: {
    print: mocks.print,
    info: mocks.info,
    success: mocks.success,
    warn: mocks.warn,
    error: mocks.error,
  },
}));
vi.mock('../../../services/core/request-context.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  setExitCode: mocks.setExitCode,
  writeStdout: vi.fn(),
  writeStderr: vi.fn(),
}));
vi.mock('../../../services/config/config-resources.js', () => ({
  configService: { getRepository: async (ref: string) => mocks.repos[ref] },
}));
vi.mock('../../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));

const { registerRestartServicesCommand } = await import('../restart-services.js');

type Executed = {
  functionName: string;
  commandKind?: { name: string; args?: Record<string, unknown> };
};

const OK = { success: true, exitCode: 0, durationMs: 1, state: 'succeeded' as const };

let executed: Executed[];
let answer: Record<string, unknown>;
let restoreJobDeps: () => void;

beforeEach(() => {
  vi.clearAllMocks();
  mocks.format = 'table';
  executed = [];
  answer = { ...OK, stdout: JSON.stringify({ processes: [], repos: [] }) };
  mocks.repos = { mail: { networkId: 2880 }, bare: {} };
  restoreJobDeps = installJobDeps((options) => {
    executed.push(options as unknown as Executed);
    return Promise.resolve(answer as never);
  });
});

afterEach(() => {
  restoreJobDeps();
});

async function run(...argv: string[]) {
  const program = new Command();
  program.exitOverride();
  registerRestartServicesCommand(program.command('machine'));
  await program.parseAsync(['machine', 'restart-services', 'm1', ...argv], { from: 'user' });
}

describe('machine restart-services --repo', () => {
  it('maps the repo to its network id and passes it to the restart job', async () => {
    await run('--include-docker', '--repo', 'mail');

    expect(executed).toHaveLength(1);
    expect(executed[0].commandKind).toEqual({
      name: 'daemons-restart',
      args: { 'include-docker': true, 'network-ids': [2880] },
    });
  });

  it('refuses a repo with no network id and runs nothing', async () => {
    await run('--include-docker', '--repo', 'bare');

    expect(executed).toHaveLength(0);
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('refuses an unknown repo and runs nothing', async () => {
    await run('--include-docker', '--repo', 'ghost');

    expect(executed).toHaveLength(0);
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('refuses --repo without --include-docker and runs nothing', async () => {
    await run('--repo', 'mail');

    expect(executed).toHaveLength(0);
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  // CONTROL: an older renet refuses the scope argument; the command must exit 1 and never retry unscoped.
  it.each([
    ['an unknown flag', 'Error: unknown flag: --network-id'],
    ['an argument refusal', 'daemons-restart job: argument "network-ids" is not allowed'],
  ])('exits 1 on an older renet answering %s, with no unscoped restart', async (_name, text) => {
    answer = {
      success: false,
      exitCode: 1,
      durationMs: 1,
      state: 'failed',
      stdout: '',
      stderr: text,
    };

    await run('--include-docker', '--repo', 'mail');

    expect(executed).toHaveLength(1);
    expect(
      executed.every((e) => (e.commandKind?.args?.['network-ids'] as unknown[]).length === 1)
    ).toBe(true);
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
    expect(mocks.error.mock.calls.join(' ')).toContain('restartServices.repoRenetTooOld');
  });

  it('does not read a refusal into a failed run whose stdout is a restart report', async () => {
    answer = {
      success: false,
      exitCode: 1,
      durationMs: 1,
      state: 'failed',
      stdout: JSON.stringify({
        processes: [
          {
            unit: 'rediacc-docker-2880',
            state: 'failed',
            error: 'Error: unknown flag: --network-id',
          },
        ],
        repos: [],
      }),
      stderr: '',
    };
    await run('--include-docker', '--repo', 'mail');
    expect(mocks.error.mock.calls.join(' ')).not.toContain('repoRenetTooOld');
  });

  it('does not call another unknown flag a renet that predates --repo', async () => {
    answer = {
      success: false,
      exitCode: 1,
      durationMs: 1,
      state: 'failed',
      stdout: '',
      stderr: 'Error: unknown flag: --include-docker',
    };
    await run('--include-docker', '--repo', 'mail');
    expect(mocks.error.mock.calls.join(' ')).not.toContain('repoRenetTooOld');
  });

  it('answers a refusal under --json with the error envelope, not plain error text', async () => {
    mocks.format = 'json';
    await expect(run('--include-docker', '--repo', 'ghost', '--json')).rejects.toThrow(
      /repoNoNetworkId/
    );
    expect(mocks.error).not.toHaveBeenCalled();
    expect(executed).toHaveLength(0);

    answer = {
      success: false,
      exitCode: 1,
      durationMs: 1,
      state: 'failed',
      stdout: '',
      stderr: 'Error: unknown flag: --network-id',
    };
    await expect(run('--include-docker', '--repo', 'mail', '--json')).rejects.toThrow(
      /repoRenetTooOld/
    );
    expect(mocks.error).not.toHaveBeenCalled();
  });
});
