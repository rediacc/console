/**
 * PLAN-detached-jobs J17: `backup run` is ONE `backup-unit` command-kind job covering every unit it starts, and no
 * `systemctl start` runs on the client. The ad-hoc path (a strategy with no deployed unit) stages a oneshot service on
 * the machine and starts it through the same job, so it makes one job too. The executor is a recording fake behind the
 * runCommandJob seam; the machine is a fake SFTP that records every command it is asked to run.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
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
  expectedStatusUnits: vi.fn(),
  renderBackupScheduleStatus: vi.fn(),
  pushBackupSchedule: vi.fn(),
}));
vi.mock('../../services/backup/backup-schedule.js', () => ({
  expectedScheduleUnits: () =>
    Promise.resolve(
      schedule.units.map((unitName) => ({ unitName, strategyName: 'nightly', schedule: '' }))
    ),
  buildStrategyCommandsForMachine: schedule.buildStrategyCommandsForMachine,
  expectedStatusUnits: schedule.expectedStatusUnits,
  renderBackupScheduleStatus: schedule.renderBackupScheduleStatus,
  pushBackupSchedule: schedule.pushBackupSchedule,
  sanitizeBackupOutput: (s: string) => s,
}));
vi.mock('../../services/backup/backup-schedule-reconcile.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
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
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), print: vi.fn(), error: vi.fn() },
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
  captureOutput?: boolean;
  jobSteps?: { name: string; on: string; params: Record<string, unknown> }[];
};

const FINISHED = { success: true, exitCode: 0, durationMs: 5, state: 'succeeded' as const };
const RUNNING = { success: true, exitCode: 0, durationMs: 1, state: 'running' as const };

let dir: string;
let store: InstanceType<typeof TicketStore>;
let executed: Executed[];
let answer: Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  machine.deployed.clear();
  machine.commands.length = 0;
  machine.subState = 'dead';
  machine.stageExit = 0;
  schedule.buildStrategyCommandsForMachine.mockReset();
  schedule.expectedStatusUnits.mockReset();
  schedule.renderBackupScheduleStatus.mockReset();
  schedule.pushBackupSchedule.mockReset();
  executed = [];
  answer = FINISHED;
  dir = mkdtempSync(join(tmpdir(), 'job-plan-backup-'));
  store = new TicketStore('test', dir);
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
    // The ticket is handed back: one pending ticket for the job, on the machine and the verb that started it.
    expect(store.tickets()).toHaveLength(1);
    expect(store.tickets()[0]).toMatchObject({
      machine: 'm1',
      verb: 'backup run',
      function: 'backup-unit',
    });
    expect(['starting', 'running']).toContain(store.tickets()[0].state);
  });

  it('control: a job that finished inside the window records a finished ticket, not a running one', async () => {
    machine.deployed.add('nightly');

    await rdcBackup('run', '-m', 'm1');

    expect(executed).toHaveLength(1);
    expect(store.tickets().map((ticket) => ticket.state)).toEqual(['succeeded']);
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

describe('backup status', () => {
  const EXPECTED = [
    { unitName: 'nightly', strategyName: 'nightly', schedule: '0 3 * * *' },
    { unitName: 'nightly.repo.gitlab', strategyName: 'nightly', schedule: '0 4 * * *' },
  ];
  const SHOW = 'Id=rediacc-backup-nightly.timer\nLoadState=loaded\n\n';

  beforeEach(() => {
    schedule.expectedStatusUnits.mockResolvedValue(EXPECTED);
  });

  it('reads every unit through one backup-status job and makes no client SSH command', async () => {
    answer = { ...FINISHED, stdout: SHOW };

    await rdcBackup('status', '-m', 'm1');

    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({
      functionName: 'backup-status',
      machineName: 'm1',
      verb: 'backup status',
      captureOutput: true,
      commandKind: {
        name: 'backup-status',
        args: { units: ['rediacc-backup-nightly', 'rediacc-backup-nightly.repo.gitlab'] },
      },
    });
    expect(machine.commands).toEqual([]);
    expect(executed[0].jobSteps).toEqual([
      expect.objectContaining({
        name: 'renderBackupStatus',
        params: { machine: 'm1', expected: JSON.stringify(EXPECTED) },
      }),
    ]);
  });

  it('renders the table in the job step from the job output, so the table content is the old one', async () => {
    answer = { ...FINISHED, stdout: SHOW };

    await rdcBackup('status', '-m', 'm1');

    expect(schedule.renderBackupScheduleStatus).toHaveBeenCalledWith('m1', EXPECTED, SHOW);
  });

  it('renders the units the job read, though the bindings changed after it started', async () => {
    answer = { ...FINISHED, stdout: SHOW };
    schedule.expectedStatusUnits.mockResolvedValueOnce(EXPECTED).mockResolvedValue([]);

    await rdcBackup('status', '-m', 'm1');

    expect(schedule.renderBackupScheduleStatus).toHaveBeenCalledWith('m1', EXPECTED, SHOW);
  });

  it('hands the ticket back past the attach window and renders nothing yet', async () => {
    answer = RUNNING;

    await rdcBackup('status', '-m', 'm1');

    expect(executed).toHaveLength(1);
    expect(schedule.renderBackupScheduleStatus).not.toHaveBeenCalled();
    expect(mockRenderFailure).not.toHaveBeenCalled();
  });

  it('renders a failed job as a failure and prints no table', async () => {
    answer = { ...FINISHED, success: false, exitCode: 1, state: 'failed', error: 'job failed' };

    await rdcBackup('status', '-m', 'm1');

    expect(mockRenderFailure).toHaveBeenCalledTimes(1);
    expect(schedule.renderBackupScheduleStatus).not.toHaveBeenCalled();
  });

  it('makes no job when no strategy is bound, and still reports through the renderer', async () => {
    schedule.expectedStatusUnits.mockResolvedValue([]);

    await rdcBackup('status', '-m', 'm1');

    expect(executed).toHaveLength(0);
    expect(schedule.renderBackupScheduleStatus).toHaveBeenCalledWith('m1', [], '');
  });

  it('fails on a failed journal job instead of printing an empty journal', async () => {
    const failed = { ...FINISHED, success: false, exitCode: 1, state: 'failed' as const };
    answer = { ...FINISHED, stdout: SHOW };
    // The table step runs inside the first job; the journal job after it answers with the failure.
    let tableSteps = 0;
    schedule.renderBackupScheduleStatus.mockImplementation(() => {
      tableSteps += 1;
      answer = failed;
    });

    await rdcBackup('status', 'nightly', '-m', 'm1');

    expect(tableSteps).toBe(1);
    expect(executed).toHaveLength(2);
    expect(mockRenderFailure).toHaveBeenCalledTimes(1);
  });

  it('control: a succeeding journal job renders no failure', async () => {
    answer = { ...FINISHED, stdout: SHOW };

    await rdcBackup('status', 'nightly', '-m', 'm1');

    expect(mockRenderFailure).not.toHaveBeenCalled();
  });

  it('the table step refuses a missing or malformed expected param, and renders with a valid one', async () => {
    const { resolveStepHandler } = await import('../../services/jobs/steps.js');
    const handler = await resolveStepHandler('renderBackupStatus');
    const ctx = { machine: 'm1', output: SHOW };
    await expect(handler({ ...ctx, params: {} } as never)).rejects.toThrow('"expected" is missing');
    await expect(handler({ ...ctx, params: { expected: '{}' } } as never)).rejects.toThrow(
      'not a JSON array'
    );
    expect(schedule.renderBackupScheduleStatus).not.toHaveBeenCalled();
    await handler({ ...ctx, params: { expected: '[]' } } as never);
    expect(schedule.renderBackupScheduleStatus).toHaveBeenCalledWith('m1', [], SHOW);
  });

  it('reads the strategy journal through a second backup-journal job, with no client SSH command', async () => {
    answer = { ...FINISHED, stdout: SHOW };

    await rdcBackup('status', 'nightly', '-m', 'm1');

    expect(executed).toHaveLength(2);
    expect(executed[1]).toMatchObject({
      functionName: 'backup-journal',
      machineName: 'm1',
      commandKind: { name: 'backup-journal', args: { strategy: 'nightly' } },
    });
    expect(machine.commands).toEqual([]);
  });
});

describe('backup status with the real renderer', () => {
  const EXPECTED = [
    { unitName: 'nightly', strategyName: 'nightly', schedule: '0 3 * * *' },
    { unitName: 'nightly.repo.gitlab', strategyName: 'nightly', schedule: '0 4 * * *' },
  ];
  // One loaded, active timer that never fired, and one unit with no timer on the machine.
  // The job folds each stdout line into an event and drops the empty ones, so no blank separator survives.
  const SHOW =
    'Id=rediacc-backup-nightly.timer\nLoadState=loaded\nActiveState=active\n' +
    'Id=rediacc-backup-nightly.service\nLoadState=loaded\nActiveState=inactive\n' +
    'Id=rediacc-backup-nightly.repo.gitlab.timer\nLoadState=not-found\nActiveState=inactive\n' +
    'Id=rediacc-backup-nightly.repo.gitlab.service\nLoadState=not-found\nActiveState=inactive\n';

  beforeEach(async () => {
    const actual = await vi.importActual<typeof import('../../services/backup/backup-schedule.js')>(
      '../../services/backup/backup-schedule.js'
    );
    schedule.expectedStatusUnits.mockResolvedValue(EXPECTED);
    schedule.renderBackupScheduleStatus.mockImplementation(actual.renderBackupScheduleStatus);
  });

  it('prints the table the old command printed, from the job output, and sets exit 1 for the unscheduled unit', async () => {
    answer = { ...FINISHED, stdout: SHOW };
    const { outputService } = await import('../../services/core/output.js');

    await rdcBackup('status', '-m', 'm1');

    expect(outputService.print).toHaveBeenCalledTimes(1);
    expect(outputService.print).toHaveBeenCalledWith(
      [
        {
          strategy: 'nightly',
          unit: 'nightly',
          status: 'scheduled',
          lastRun: '-',
          result: '-',
          nextRun: '-',
          missed: '-',
        },
        {
          strategy: 'nightly',
          unit: 'nightly.repo.gitlab',
          status: 'not scheduled',
          lastRun: '-',
          result: '-',
          nextRun: '-',
          missed: 'not scheduled: no timer on the machine (run: rdc backup schedule)',
        },
      ],
      'table'
    );
    expect(mockSetExitCode).toHaveBeenCalledWith(1);
  });

  it('empty job output prints could-not-read, not "no timer", and exits 2', async () => {
    answer = { ...FINISHED, stdout: '' };
    const { outputService } = await import('../../services/core/output.js');

    await rdcBackup('status', '-m', 'm1');

    const rows = vi.mocked(outputService.print).mock.calls[0][0] as {
      status: string;
      missed: string;
    }[];
    expect(rows.map((r) => r.status)).toEqual(['unreadable', 'unreadable']);
    expect(rows[0].missed).toMatch(/could not be read/);
    expect(JSON.stringify(rows)).not.toMatch(/no timer/);
    expect(mockSetExitCode).toHaveBeenCalledWith(2);
  });

  it('control: a table where every unit is scheduled sets no exit code', async () => {
    schedule.expectedStatusUnits.mockResolvedValue(EXPECTED.slice(0, 1));
    answer = { ...FINISHED, stdout: SHOW };

    await rdcBackup('status', '-m', 'm1');

    expect(mockSetExitCode).not.toHaveBeenCalled();
  });
});

describe('backup schedule unit content', () => {
  it('renders the service and timer units byte for byte', async () => {
    const generator = await import('../../services/backup/backup-schedule-unit-generator.js');
    const destinations = STRATEGY.destinations as never;

    const built = generator.generateServiceUnit(
      'nightly',
      STRATEGY as never,
      destinations,
      WK_DATASTORE_PATH,
      '/r/renet',
      { exclude: [] } as never,
      8
    );

    expect(built.serviceContent).toBe(
      [
        '[Unit]',
        'Description=Rediacc Scheduled Backup (nightly)',
        'After=network-online.target',
        'OnFailure=rediacc-backup-nightly.alert.service',
        '',
        '[Service]',
        'Type=oneshot',
        'Nice=10',
        'IOSchedulingClass=best-effort',
        'IOSchedulingPriority=7',
        'CPUQuota=400%',
        'TimeoutStartSec=infinity',
        'TimeoutStopSec=90',
        'ExecStartPre=-/r/renet license renew --jitter 45s',
        `ExecStart=/r/renet backup snapshot --datastore ${WK_DATASTORE_PATH} --parallelism 2 --expected-interval 86400s --cpu-limit 50 --cpu-quota 400%`,
        `ExecStart=/r/renet backup verify --datastore ${WK_DATASTORE_PATH} --level spot`,
        '',
        '[Install]',
        'WantedBy=multi-user.target',
        '',
      ].join('\n')
    );
    expect(built.envVars).toEqual({});
    expect(generator.generateTimerUnit('nightly', generator.cronToOnCalendar('0 3 * * *'))).toBe(
      '[Unit]\nDescription=Rediacc Backup Timer (nightly)\n\n[Timer]\nOnCalendar=*-*-* 03:00:00\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n'
    );
  });
});

describe('backup schedule', () => {
  it('hands the apply job its two follow-up steps and prints the success once it applied', async () => {
    schedule.pushBackupSchedule.mockResolvedValue('applied');

    await rdcBackup('schedule', '-m', 'm1');

    expect(schedule.pushBackupSchedule).toHaveBeenCalledTimes(1);
    const [machineName, options] = schedule.pushBackupSchedule.mock.calls[0] as [
      string,
      { steps: { name: string; params: Record<string, unknown> }[] },
    ];
    expect(machineName).toBe('m1');
    expect(options.steps.map((st) => st.name)).toEqual([
      'seedStrategyRetention',
      'warnIfConfigStorageUnenrolled',
    ]);
    expect(options.steps[0].params).toEqual({ strategies: 'nightly', machine: 'm1' });
    expect(executed).toHaveLength(0);
  });

  it('plans no step for a dry run', async () => {
    schedule.pushBackupSchedule.mockResolvedValue('dry-run');

    await rdcBackup('schedule', '-m', 'm1', '--dry-run');

    expect(schedule.pushBackupSchedule.mock.calls[0][1]).toMatchObject({ steps: [], dryRun: true });
  });

  it('prints no success while the job is pending: its steps run when it is observed finished', async () => {
    schedule.pushBackupSchedule.mockResolvedValue('pending');
    const { outputService } = await import('../../services/core/output.js');

    await rdcBackup('schedule', '-m', 'm1');

    expect(outputService.success).not.toHaveBeenCalled();
  });
});
