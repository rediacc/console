/**
 * `backup cancel` and `backup status` reach every unit a strategy renders as: the base
 * unit, one per datastore (`.ds.`) and one per repository with its own cadence (`.repo.`).
 * `backup run` is covered by job-plan-backup.test.ts.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const STRATEGY = vi.hoisted(() => ({
  schedule: '0 3 * * *',
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
    listRepositories: () => Promise.resolve([]),
  },
}));

const schedule = vi.hoisted(() => ({
  units: ['nightly', 'nightly.ds.fast', 'nightly.repo.gitlab'],
  expectedStatusUnits: vi.fn(),
}));
vi.mock('../../services/backup/backup-schedule.js', () => ({
  expectedScheduleUnits: () =>
    Promise.resolve(
      schedule.units.map((unitName) => ({ unitName, strategyName: 'nightly', schedule: '' }))
    ),
  buildStrategyCommandsForMachine: vi.fn(),
  expectedStatusUnits: schedule.expectedStatusUnits,
  renderBackupScheduleStatus: vi.fn(),
  sanitizeBackupOutput: (s: string) => s,
}));

vi.mock('../../services/renet/renet-execution.js', () => ({
  acquireRemoteRenet: () => Promise.resolve({ remotePath: '/r/renet' }),
  readSSHKey: () => Promise.resolve('KEY'),
}));

const machine = vi.hoisted(() => ({
  deployed: new Set<string>(),
  running: new Set<string>(),
  commands: [] as string[],
  subState: 'dead',
  runExit: 0,
}));
/** The machine: the systemd directory lists each deployed unit, `is-active` answers from `running`. */
function fakeExecStreaming(cmd: string, opts: { onStdout: (d: string) => void }): Promise<number> {
  machine.commands.push(cmd);
  if (cmd.startsWith('sudo -n ls -1')) {
    opts.onStdout([...machine.deployed].map((u) => `rediacc-backup-${u}.service\n`).join(''));
  }
  const active = /^systemctl is-active (\S+)/.exec(cmd);
  if (active) opts.onStdout(machine.running.has(active[1]) ? 'active\n' : 'inactive\n');
  if (cmd.startsWith('systemctl show -p SubState')) opts.onStdout(`${machine.subState}\n`);
  return Promise.resolve(cmd.startsWith('sudo systemd-run') ? machine.runExit : 0);
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

vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  handleError: (error: unknown) => {
    throw error;
  },
}));
const jobs = vi.hoisted(() => ({ runCommandJob: vi.fn() }));
vi.mock('../../services/jobs/command-job.js', () => ({
  runCommandJob: jobs.runCommandJob,
  pendingExitCode: vi.fn(),
}));

const { registerBackupOpsCommands } = await import('../backup-ops.js');

async function rdcBackup(...argv: string[]): Promise<void> {
  const backup = new Command('backup').exitOverride();
  registerBackupOpsCommands(backup);
  await backup.parseAsync(argv, { from: 'user' });
}

beforeEach(() => {
  machine.deployed.clear();
  machine.running.clear();
  machine.commands.length = 0;
  machine.subState = 'dead';
  machine.runExit = 0;
  schedule.expectedStatusUnits.mockReset();
  schedule.expectedStatusUnits.mockResolvedValue([
    { unitName: 'nightly', strategyName: 'nightly', schedule: '' },
  ]);
  jobs.runCommandJob.mockReset();
  jobs.runCommandJob.mockResolvedValue({ kind: 'finished', result: { success: true } });
});

describe('backup cancel', () => {
  it('stops a running .repo. unit of the named strategy', async () => {
    jobs.runCommandJob.mockResolvedValue({
      kind: 'finished',
      result: { success: true, stdout: 'cancelled rediacc-backup-nightly.repo.gitlab.service\n' },
    });

    await rdcBackup('cancel', 'nightly', '-m', 'm1');

    // One backup-cancel job names every unit of the strategy and its ad-hoc unit, and no client stop runs.
    expect(jobs.runCommandJob).toHaveBeenCalledTimes(1);
    expect(jobs.runCommandJob.mock.calls[0][1]).toMatchObject({
      functionName: 'backup-cancel',
      commandKind: {
        name: 'backup-cancel',
        args: {
          units: [
            'rediacc-backup-nightly',
            'rediacc-backup-nightly.ds.fast',
            'rediacc-backup-nightly.repo.gitlab',
            'rediacc-backup-nightly-adhoc',
          ],
        },
      },
    });
    expect(machine.commands).toEqual([]);
  });
});

describe('backup status', () => {
  it('reads the units through one backup-status job and touches the machine by no other route', async () => {
    await rdcBackup('status', '-m', 'm1');

    expect(schedule.expectedStatusUnits).toHaveBeenCalledWith('m1', undefined);
    expect(jobs.runCommandJob).toHaveBeenCalledTimes(1);
    expect(machine.commands).toEqual([]);
  });
});
