/**
 * PLAN-detached-jobs J17: `backup run` is ONE `backup-unit` command-kind job covering every unit it starts, and no
 * `systemctl start` runs on the client. The ad-hoc path (a strategy with no deployed unit) stages a oneshot service on
 * the machine and starts it through the same job, so it makes one job too. The executor is a recording fake behind the
 * runCommandJob seam; the machine is a fake SFTP that records every command it is asked to run.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const STRATEGY = vi.hoisted(() => ({
  schedule: '0 3 * * *',
  cpuLimit: 50,
  destinations: [{ kind: 'hosted-service', name: 'd' }],
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getLocalConfig: () =>
      Promise.resolve({
        machines: { m1: { ip: '10.0.0.1', user: 'root', backupStrategies: ['nightly'] } },
        sshPrivateKey: 'KEY',
        ssh: { privateKeyPath: '/k' },
      }),
    listBackupStrategies: () => Promise.resolve({ nightly: STRATEGY }),
  },
}));

const schedule = vi.hoisted(() => ({
  units: ['nightly', 'nightly.ds.fast', 'nightly.repo.gitlab'],
  buildStrategyCommandsForMachine: vi.fn(),
}));
vi.mock('../../services/backup/backup-schedule.js', () => ({
  expectedScheduleUnits: () =>
    Promise.resolve(
      schedule.units.map((unitName) => ({ unitName, strategyName: 'nightly', schedule: '' }))
    ),
  buildStrategyCommandsForMachine: schedule.buildStrategyCommandsForMachine,
  reportBackupScheduleStatus: vi.fn(),
  sanitizeBackupOutput: (s: string) => s,
}));
vi.mock('../../services/backup/backup-schedule-reconcile.js', () => ({
  resolveMachineCpuCount: () => Promise.resolve(8),
}));
vi.mock('../../services/backup/backup-retention.js', () => ({
  hasAccountToken: () => false,
  pushStrategyRetention: vi.fn(),
}));
vi.mock('../../services/renet/renet-execution.js', () => ({
  acquireRemoteRenet: () => Promise.resolve({ remotePath: '/r/renet' }),
  readSSHKey: () => Promise.resolve('KEY'),
}));

const machine = vi.hoisted(() => ({
  deployed: new Set<string>(),
  subState: 'dead',
  commands: [] as { command: string; stdin?: string }[],
  stageExit: 0,
}));
/** The machine: `systemctl cat` prints for a deployed unit, `show -p SubState` answers from `subState`. */
function fakeExecStreaming(
  cmd: string,
  opts: { stdin?: string; onStdout: (d: string) => void }
): Promise<number> {
  machine.commands.push({ command: cmd, stdin: opts.stdin });
  const cat = /^systemctl cat rediacc-backup-(.+)\.service/.exec(cmd);
  if (cat && machine.deployed.has(cat[1])) opts.onStdout('[Unit]\n');
  if (cmd.startsWith('systemctl show -p SubState')) opts.onStdout(`${machine.subState}\n`);
  return Promise.resolve(cmd.startsWith('sudo tee') ? machine.stageExit : 0);
}
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: {
    acquireFor: () =>
      Promise.resolve({
        release: () => undefined,
        sftp: { execStreaming: fakeExecStreaming },
      }),
  },
}));

const mockSetExitCode = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/request-context.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  setExitCode: mockSetExitCode,
  writeStderr: vi.fn(),
  writeStdout: vi.fn(),
}));
const mockRenderFailure = vi.hoisted(() => vi.fn());
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: mockRenderFailure,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  handleError: (error: unknown) => {
    throw error;
  },
}));

const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const { registerBackupOpsCommands } = await import('../backup-ops.js');

type Executed = {
  functionName: string;
  machineName: string;
  verb?: string;
  commandKind?: { name: string; args?: { units: string[] } };
  jobSteps?: unknown[];
};

const FINISHED = { success: true, exitCode: 0, durationMs: 5, state: 'succeeded' as const };
const RUNNING = { success: true, exitCode: 0, durationMs: 1, state: 'running' as const };

let dir: string;
let executed: Executed[];
let answer: Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  machine.deployed.clear();
  machine.commands.length = 0;
  machine.subState = 'dead';
  machine.stageExit = 0;
  schedule.buildStrategyCommandsForMachine.mockReset();
  executed = [];
  answer = FINISHED;
  dir = mkdtempSync(join(tmpdir(), 'job-plan-backup-'));
  const store = new TicketStore('test', dir);
  setCommandJobDeps({
    executor: () => ({
      execute: (options) => {
        executed.push(options as unknown as Executed);
        return Promise.resolve(answer as never);
      },
    }),
    store: () => store,
    stepDeps: () =>
      Promise.resolve({
        observer: { configName: 'test' },
        warn: () => undefined,
        claim: ({ steps }) =>
          Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const }))),
      }),
  });
});

afterEach(() => {
  setCommandJobDeps();
  rmSync(dir, { recursive: true, force: true });
});

async function rdcBackup(...argv: string[]): Promise<void> {
  const backup = new Command('backup').exitOverride();
  registerBackupOpsCommands(backup);
  await backup.parseAsync(argv, { from: 'user' });
}

const clientStarts = (): string[] =>
  machine.commands.map((c) => c.command).filter((c) => /systemctl start|systemd-run/.test(c));

describe('backup run on deployed units', () => {
  it('makes one backup-unit job for every unit of the strategy, and no systemctl start on the client', async () => {
    for (const unit of schedule.units) machine.deployed.add(unit);

    await rdcBackup('run', '-m', 'm1');

    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({
      functionName: 'backup-unit',
      machineName: 'm1',
      commandKind: {
        name: 'backup-unit',
        args: {
          units: [
            'rediacc-backup-nightly',
            'rediacc-backup-nightly.ds.fast',
            'rediacc-backup-nightly.repo.gitlab',
          ],
        },
      },
    });
    expect(clientStarts()).toEqual([]);
    expect(schedule.buildStrategyCommandsForMachine).not.toHaveBeenCalled();
  });

  it('returns the ticket past the attach window, without rendering a failure', async () => {
    machine.deployed.add('nightly');
    answer = RUNNING;

    await rdcBackup('run', '-m', 'm1');

    expect(executed).toHaveLength(1);
    expect(mockRenderFailure).not.toHaveBeenCalled();
    expect(mockSetExitCode).not.toHaveBeenCalled();
  });

  it('renders a failed job and sets no second job', async () => {
    machine.deployed.add('nightly');
    answer = { ...FINISHED, success: false, exitCode: 1, state: 'failed', error: 'job failed' };

    await rdcBackup('run', '-m', 'm1');

    expect(executed).toHaveLength(1);
    expect(mockRenderFailure).toHaveBeenCalledTimes(1);
  });
});

describe('backup run ad hoc', () => {
  beforeEach(() => {
    schedule.buildStrategyCommandsForMachine.mockResolvedValue(['/r/renet backup snapshot x']);
  });

  it('stages one oneshot unit with the GUID-resolved commands, then makes one job for it', async () => {
    await rdcBackup('run', 'nightly', '-m', 'm1');

    expect(schedule.buildStrategyCommandsForMachine).toHaveBeenCalledWith(
      'm1',
      'nightly',
      STRATEGY,
      '/r/renet'
    );
    const staged = machine.commands.find((c) => c.command.startsWith('sudo tee'));
    expect(staged?.command).toContain("'/etc/systemd/system/rediacc-backup-nightly-adhoc.service'");
    expect(staged?.stdin).toContain('Type=oneshot');
    expect(staged?.stdin).toContain('ExecStart=/r/renet backup snapshot x');
    expect(staged?.stdin).toContain('CPUQuota=400%');
    expect(executed).toHaveLength(1);
    expect(executed[0].commandKind?.args?.units).toEqual(['rediacc-backup-nightly-adhoc']);
    expect(clientStarts()).toEqual([]);
  });

  it('makes no job when the strategy covers no repository on the machine', async () => {
    schedule.buildStrategyCommandsForMachine.mockResolvedValue([]);

    await rdcBackup('run', 'nightly', '-m', 'm1');

    expect(executed).toHaveLength(0);
  });

  it('refuses while the ad-hoc unit is still running, before any file or job', async () => {
    machine.subState = 'running';

    await expect(rdcBackup('run', 'nightly', '-m', 'm1')).rejects.toThrow(/still running/);

    expect(machine.commands.some((c) => c.command.startsWith('sudo tee'))).toBe(false);
    expect(executed).toHaveLength(0);
  });

  it.each(['auto-restart', 'reload', 'stop-sigterm'])(
    'refuses while the ad-hoc unit is in the transitional state %s',
    async (subState) => {
      machine.subState = subState;

      await expect(rdcBackup('run', 'nightly', '-m', 'm1')).rejects.toThrow(/still running/);

      expect(machine.commands.some((c) => c.command.startsWith('sudo systemctl stop'))).toBe(false);
    }
  );

  it.each(['exited', 'failed'])('clears a finished ad-hoc unit in state %s', async (subState) => {
    machine.subState = subState;

    await rdcBackup('run', 'nightly', '-m', 'm1');

    expect(machine.commands.some((c) => c.command.includes('reset-failed'))).toBe(true);
    expect(executed).toHaveLength(1);
  });

  it('fails without a job when the unit cannot be staged', async () => {
    machine.stageExit = 1;

    await expect(rdcBackup('run', 'nightly', '-m', 'm1')).rejects.toThrow(/Failed to stage/);

    expect(executed).toHaveLength(0);
  });
});
