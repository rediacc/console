/**
 * `backup run`, `backup cancel` and `backup status` reach every unit a strategy renders as: the base
 * unit, one per datastore (`.ds.`) and one per repository with its own cadence (`.repo.`).
 *
 * Before the wiring they only knew `rediacc-backup-<strategy>.service`, so a strategy split across
 * datastores could be neither triggered nor cancelled per unit, and an ad-hoc run built its commands
 * without the GUID resolution `backup schedule` applies.
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
  },
}));

const schedule = vi.hoisted(() => ({
  units: ['nightly', 'nightly.ds.fast', 'nightly.repo.gitlab'],
  buildStrategyCommandsForMachine: vi.fn(),
  reportBackupScheduleStatus: vi.fn(),
}));
vi.mock('../../services/backup/backup-schedule.js', () => ({
  expectedScheduleUnits: () =>
    Promise.resolve(
      schedule.units.map((unitName) => ({ unitName, strategyName: 'nightly', schedule: '' }))
    ),
  buildStrategyCommandsForMachine: schedule.buildStrategyCommandsForMachine,
  reportBackupScheduleStatus: schedule.reportBackupScheduleStatus,
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
/** The machine: `systemctl cat` prints for a deployed unit, `is-active` answers from `running`. */
function fakeExecStreaming(cmd: string, opts: { onStdout: (d: string) => void }): Promise<number> {
  machine.commands.push(cmd);
  const cat = /^systemctl cat rediacc-backup-(.+)\.service/.exec(cmd);
  if (cat && machine.deployed.has(cat[1])) opts.onStdout('[Unit]\n');
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
vi.mock('../../utils/errors.js', () => ({
  handleError: (error: unknown) => {
    throw error;
  },
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
  schedule.buildStrategyCommandsForMachine.mockReset();
  schedule.reportBackupScheduleStatus.mockReset();
});

describe('backup run', () => {
  it('starts every deployed unit of the strategy, the .ds. and .repo. ones included', async () => {
    for (const unit of schedule.units) machine.deployed.add(unit);

    await rdcBackup('run', '-m', 'm1');

    const starts = machine.commands.filter((c) => c.startsWith('sudo systemctl start'));
    expect(starts).toEqual([
      'sudo systemctl start rediacc-backup-nightly.service',
      'sudo systemctl start rediacc-backup-nightly.ds.fast.service',
      'sudo systemctl start rediacc-backup-nightly.repo.gitlab.service',
    ]);
    expect(schedule.buildStrategyCommandsForMachine).not.toHaveBeenCalled();
  });

  it('runs ad hoc with the GUID-resolved commands when no unit is deployed', async () => {
    schedule.buildStrategyCommandsForMachine.mockResolvedValue(['/r/renet backup snapshot x']);

    await rdcBackup('run', 'nightly', '-m', 'm1');

    expect(schedule.buildStrategyCommandsForMachine).toHaveBeenCalledWith(
      'm1',
      'nightly',
      STRATEGY,
      '/r/renet'
    );
    const adhoc = machine.commands.find((c) => c.startsWith('sudo systemd-run'));
    expect(adhoc).toContain('--unit=rediacc-backup-nightly-adhoc');
    expect(adhoc).toContain('/r/renet backup snapshot x');
  });
});

describe('backup cancel', () => {
  it('stops a running .repo. unit of the named strategy', async () => {
    machine.running.add('rediacc-backup-nightly.repo.gitlab.service');

    await rdcBackup('cancel', 'nightly', '-m', 'm1');

    const stops = machine.commands.filter((c) => c.startsWith('sudo systemctl stop'));
    expect(stops).toEqual(['sudo systemctl stop rediacc-backup-nightly.repo.gitlab.service']);
  });
});

describe('backup status', () => {
  it('reports through the per-unit schedule status', async () => {
    await rdcBackup('status', '-m', 'm1');

    expect(schedule.reportBackupScheduleStatus).toHaveBeenCalledWith('m1', undefined);
    expect(machine.commands).toEqual([]);
  });
});

describe('backup run ad hoc re-run', () => {
  it('clears an exited ad-hoc unit before systemd-run', async () => {
    schedule.buildStrategyCommandsForMachine.mockResolvedValue(['/r/renet backup snapshot x']);
    await rdcBackup('run', 'nightly', '-m', 'm1');
    const stopAt = machine.commands.findIndex((c) => c.includes('reset-failed'));
    const runAt = machine.commands.findIndex((c) => c.startsWith('sudo systemd-run'));
    expect(stopAt).toBeGreaterThan(-1);
    expect(stopAt).toBeLessThan(runAt);
  });

  it('refuses while the ad-hoc unit is still running', async () => {
    schedule.buildStrategyCommandsForMachine.mockResolvedValue(['/r/renet backup snapshot x']);
    machine.subState = 'running';
    await expect(rdcBackup('run', 'nightly', '-m', 'm1')).rejects.toThrow(/still running/);
    expect(machine.commands.some((c) => c.startsWith('sudo systemd-run'))).toBe(false);
  });

  it('exits non-zero when systemd-run fails', async () => {
    schedule.buildStrategyCommandsForMachine.mockResolvedValue(['/r/renet backup snapshot x']);
    machine.runExit = 1;
    await expect(rdcBackup('run', 'nightly', '-m', 'm1')).rejects.toThrow(/Failed to start/);
  });
});
