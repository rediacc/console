/**
 * `rdc machine converge` and the converge pass of `rdc machine setup`
 * (agent/plans/PLAN-renet-runtime-converge.md, D5).
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { calls, mockExecute, mockAcquireRemoteRenet, state } = vi.hoisted(() => ({
  calls: [] as string[],
  mockExecute: vi.fn(),
  mockAcquireRemoteRenet: vi.fn(),
  state: { stale: 1 },
}));

vi.mock('../../i18n/index.js', () => ({ t: (k: string) => k }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getLocalConfig: vi.fn().mockResolvedValue({ sshPrivateKey: 'key', ssh: {} }),
    getLocalMachine: vi.fn().mockResolvedValue({ ip: '10.0.0.1' }),
  },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), error: vi.fn(), success: vi.fn(), warn: vi.fn(), print: vi.fn() },
}));
vi.mock('../../services/core/request-context.js', () => ({
  setExitCode: vi.fn(),
  writeStdout: vi.fn(),
}));
vi.mock('../../services/machine/machine-remove-guard.js', () => ({ guardMachineRemoval: vi.fn() }));
vi.mock('../../services/provision/infra-provision.js', () => ({ pushInfraConfig: vi.fn() }));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({ deployAllRepoKeys: vi.fn() }));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn() }));
vi.mock('../../utils/errors.js', () => ({
  getOutputFormat: () => 'table',
  handleError: (e: unknown) => {
    throw e;
  },
}));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));
vi.mock('../../services/renet/renet-execution.js', () => ({
  acquireRemoteRenet: mockAcquireRemoteRenet,
  readSSHKey: vi.fn(),
}));
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: {
    acquireFor: vi.fn().mockResolvedValue({
      release: vi.fn(),
      sftp: {
        exec: vi.fn((cmd: string) => {
          if (cmd.includes('runtime status')) {
            calls.push('status');
            return Promise.resolve(JSON.stringify({ stale: state.stale, repos: [] }));
          }
          if (cmd.includes('rediacc-router')) {
            calls.push('router');
            return Promise.resolve('RESTARTED');
          }
          return Promise.resolve('');
        }),
        execStreaming: vi.fn(() => {
          calls.push('setup');
          return Promise.resolve(0);
        }),
      },
    }),
  },
  withSharedOrPooledSftp: vi.fn(),
}));

import { registerConvergeCommand } from '../machine/converge.js';
import { registerMachineRegistrationCommands } from '../machine/register.js';

function program(): Command {
  const p = new Command();
  const machine = p.command('machine');
  registerMachineRegistrationCommands(machine, p);
  registerConvergeCommand(machine);
  return p;
}

/** A report whose results match its summary, the way renet writes one: the CLI counts from results. */
function convergeStdout(summary: Record<string, number>): string {
  const statuses = ['converged', 'would_converge', 'skipped', 'failed', 'pending'];
  const results = statuses.flatMap((status) =>
    Array.from({ length: summary[status] ?? 0 }, (_, i) => ({
      network_id: 2816 + i,
      status,
    }))
  );
  return JSON.stringify({
    policy: 'epoch',
    runtime_epoch: 1,
    dry_run: false,
    aborted: false,
    plan: [],
    results,
    summary: {
      total: 1,
      converged: 0,
      would_converge: 0,
      skipped: 0,
      failed: 0,
      pending: 0,
      ...summary,
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  calls.length = 0;
  state.stale = 1;
  delete process.env.REDIACC_SKIP_RUNTIME_CONVERGE;
  delete process.env.REDIACC_SKIP_ROUTER_RESTART;
  mockAcquireRemoteRenet.mockResolvedValue({
    remotePath: '/usr/bin/renet',
    uploaded: true,
    drift: null,
    routerRefreshDue: true,
  });
  mockExecute.mockImplementation(() => {
    calls.push('converge');
    return Promise.resolve({
      success: true,
      exitCode: 0,
      durationMs: 1,
      stdout: convergeStdout({}),
    });
  });
});

describe('machine converge', () => {
  it('dispatches the converge function with every flag as a param', async () => {
    await program().parseAsync(
      [
        'machine',
        'converge',
        'm1',
        '--dry-run',
        '--policy',
        'always',
        '--include-unknown',
        '--continue-on-error',
      ],
      { from: 'user' }
    );

    expect(mockExecute).toHaveBeenCalledTimes(1);
    expect(mockExecute.mock.calls[0][0]).toMatchObject({
      functionName: 'machine_converge_runtime',
      machineName: 'm1',
      params: { dry_run: true, policy: 'always', include_unknown: true, continue_on_error: true },
      captureOutput: true,
    });
  });

  it('rejects an unknown policy', async () => {
    const p = program();
    p.exitOverride();
    p.commands[0].commands.forEach((c) => {
      c.exitOverride();
      c.configureOutput({ writeErr: () => undefined });
    });
    await expect(
      p.parseAsync(['machine', 'converge', 'm1', '--policy', 'sometimes'], { from: 'user' })
    ).rejects.toThrow();
    expect(mockExecute).not.toHaveBeenCalled();
  });
});

describe('machine setup converge pass', () => {
  it('defers the router refresh, converges a stale runtime after setup, then refreshes the router', async () => {
    await program().parseAsync(['machine', 'setup', 'm1'], { from: 'user' });

    expect(mockAcquireRemoteRenet.mock.calls[0][4]).toMatchObject({ deferRouterRefresh: true });
    expect(calls).toEqual(['setup', 'status', 'converge', 'router']);
  });

  it('leaves the router refresh to the executor when the pass moved a repo', async () => {
    mockExecute.mockImplementation(() => {
      calls.push('converge');
      return Promise.resolve({
        success: true,
        exitCode: 0,
        durationMs: 1,
        stdout: convergeStdout({ converged: 1 }),
      });
    });

    await program().parseAsync(['machine', 'setup', 'm1'], { from: 'user' });

    expect(calls).toEqual(['setup', 'status', 'converge']);
  });

  it('--no-converge reads no status and runs no pass, but still refreshes the router', async () => {
    await program().parseAsync(['machine', 'setup', 'm1', '--no-converge'], { from: 'user' });

    expect(calls).toEqual(['setup', 'router']);
    expect(mockExecute).not.toHaveBeenCalled();
  });

  it('REDIACC_SKIP_RUNTIME_CONVERGE=1 skips the pass the same way', async () => {
    process.env.REDIACC_SKIP_RUNTIME_CONVERGE = '1';

    await program().parseAsync(['machine', 'setup', 'm1'], { from: 'user' });

    expect(calls).toEqual(['setup', 'router']);
  });

  it('runs no pass when nothing is stale', async () => {
    state.stale = 0;

    await program().parseAsync(['machine', 'setup', 'm1'], { from: 'user' });

    expect(calls).toEqual(['setup', 'status', 'router']);
  });
});
