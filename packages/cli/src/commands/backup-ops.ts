import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { replicateDestinations } from '../services/backup/backup-replication.js';
import { hasAccountToken, pushStrategyRetention } from '../services/backup/backup-retention.js';
import {
  HOME_STORE,
  readStoreStatuses,
  type StatusTargets,
} from '../services/backup/backup-store-pick.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode, writeStdout } from '../services/core/request-context.js';
import { pendingExitCode, runCommandJob } from '../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { str } from '../services/jobs/steps-support.js';
import { machineConnections } from '../services/machine/machine-connection.js';
import { acquireRemoteRenet, readSSHKey } from '../services/renet/renet-execution.js';
import { handleError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import {
  deployedStrategyUnits,
  resolveStrategyNames,
  stageAdhocUnit,
  strategyUnitNames,
  UNIT_PREFIX,
} from './backup-ops-unit-stage.js';

/**
 * Declare each strategy's retention on the lineages it covers, filling only lineages that have no
 * policy of their own (a per-repo `backup retention set` stays). Best-effort: the schedule or run it
 * rides on matters more than the policy push, and the server enforces its default meanwhile.
 */
async function seedStrategyRetention(names: string[], machineName: string): Promise<void> {
  if (!hasAccountToken()) return;
  const all = await configService.listBackupStrategies();
  for (const name of names) {
    const strategy = all[name] as (typeof all)[string] | undefined;
    if (!strategy?.retention) continue;
    try {
      const { pushed } = await pushStrategyRetention(strategy, { overwrite: false, machineName });
      if (pushed > 0) {
        outputService.info(
          t('commands.backup.retention.seeded', { strategy: name, count: pushed })
        );
      }
    } catch (error) {
      outputService.warn(
        t('commands.backup.retention.seedFailed', {
          strategy: name,
          reason: error instanceof Error ? error.message : String(error),
        })
      );
    }
  }
}

async function runBackupNow(
  machineName: string,
  strategyFilter?: string,
  debug?: boolean
): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    throw new Error(`Machine "${machineName}" not found`);
  }

  // Allow triggering strategies bound to the machine OR any strategy in config
  const allStrategies = await configService.listBackupStrategies();
  const boundNames = machine.backupStrategies ?? [];
  const toTrigger = resolveStrategyNames(strategyFilter, boundNames, Object.keys(allStrategies));

  if (toTrigger.length === 0) {
    throw new Error(
      'No backup strategies found. Create one with: rdc backup strategy set <name> --cron "..."'
    );
  }

  // Load strategy configs (cast to handle Record index access)
  const strategies: { name: string; config: (typeof allStrategies)[string] }[] = [];
  for (const stratName of toTrigger) {
    const config = allStrategies[stratName] as (typeof allStrategies)[string] | undefined;
    if (!config) {
      throw new Error(`Backup strategy "${stratName}" not found in config`);
    }
    strategies.push({ name: stratName, config });
  }

  await seedStrategyRetention(toTrigger, machineName);

  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  // Provision renet to get the remote path
  const { remotePath: remoteRenetPath } = await acquireRemoteRenet(
    'provision',
    { renetPath: localConfig.renetPath },
    machine,
    sshPrivateKey,
    { debug }
  );

  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
  const sftp = lease.sftp;
  const units: string[] = [];

  try {
    for (const { name, config } of strategies) {
      const deployed = await deployedStrategyUnits(
        sftp,
        name,
        await strategyUnitNames(machineName, name)
      );
      if (deployed.length > 0) {
        units.push(...deployed.map((unit) => `${UNIT_PREFIX}${unit}`));
        continue;
      }
      const adhoc = await stageAdhocUnit(sftp, machineName, name, config, remoteRenetPath, debug);
      if (adhoc) units.push(adhoc);
    }
  } finally {
    lease.release();
  }

  if (units.length > 0) await startBackupUnits(machineName, units, debug);
}

/**
 * Start every unit as ONE `backup-unit` job: renet runs `systemctl start` inside the job, so the backup outlives this
 * client, the spool holds its start and exit code, and a run past the attach window returns its ticket.
 */
async function startBackupUnits(
  machineName: string,
  units: string[],
  debug?: boolean
): Promise<void> {
  outputService.info(`Starting ${units.map((u) => `${u}.service`).join(', ')}...`);
  const outcome = await runCommandJob(
    'backup run',
    {
      functionName: 'backup-unit',
      machineName,
      commandKind: { name: 'backup-unit', args: { units } },
      debug,
    },
    []
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (outcome.result.success) {
    outputService.success(`Backup finished: ${units.join(', ')}`);
    return;
  }
  renderLocalExecutionFailure(outcome.result, `Backup failed on ${machineName}`);
}

/**
 * `backup cancel`: ONE `backup-cancel` job stops every scheduled unit of the strategies (base, `.ds.`, `.repo.`) and
 * their ad-hoc units. renet stops only the units systemd has loaded and prints `cancelled <unit>.service` for each one
 * that was running, which is where the per-strategy messages come from.
 */
async function cancelBackup(
  machineName: string,
  strategyFilter?: string,
  debug?: boolean
): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    throw new Error(`Machine "${machineName}" not found`);
  }

  const boundNames = machine.backupStrategies ?? [];
  const toCheck = strategyFilter ? [strategyFilter] : boundNames;

  if (toCheck.length === 0) {
    throw new Error(`No backup strategies bound to "${machineName}"`);
  }

  const unitsOf = new Map<string, string[]>();
  for (const name of toCheck) {
    const unitNames = new Set([name, ...(await strategyUnitNames(machineName, name))]);
    unitsOf.set(name, [
      ...[...unitNames].map((u) => `rediacc-backup-${u}`),
      `rediacc-backup-${name}-adhoc`,
    ]);
  }
  const units = [...new Set([...unitsOf.values()].flat())];

  const outcome = await runCommandJob(
    'backup cancel',
    {
      functionName: 'backup-cancel',
      machineName,
      commandKind: { name: 'backup-cancel', args: { units } },
      debug,
      captureOutput: true,
    },
    []
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) {
    renderLocalExecutionFailure(outcome.result, `Cancelling the backups failed on ${machineName}`);
    return;
  }
  const stopped = new Set(
    (outcome.result.stdout ?? '')
      .split('\n')
      .map((line) => /^cancelled (.+)\.service$/.exec(line.trim())?.[1])
      .filter((u): u is string => u !== undefined)
  );
  for (const [name, names] of unitsOf) {
    const cancelled = names.filter((u) => stopped.has(u));
    for (const unit of cancelled) {
      outputService.success(t('commands.backup.cancel.cancelled', { name: `${unit}.service` }));
    }
    if (cancelled.length === 0) {
      outputService.info(t('commands.backup.cancel.notRunning', { name }));
    }
  }
}

/**
 * The destination stores of each strategy and what each store reports for the machine's repositories: the data
 * behind the per-store rows. Read before the job so the step renders what was planned; a listing that cannot be read
 * leaves its columns `-`, never a failed status.
 */
async function readStatusTargets(
  machineName: string,
  strategies: string[]
): Promise<StatusTargets> {
  const byStrategy: Record<string, string[]> = {};
  const replicas: Record<string, Record<string, string>> = {};
  const bound = await configService.listBackupStrategies();
  for (const name of new Set(strategies)) {
    const destinations = bound[name]?.destinations ?? [];
    const enabled = destinations.filter((d) => d.enabled !== false);
    byStrategy[name] = [...new Set(enabled.map((d) => d.target ?? HOME_STORE))];
    // A replicate destination's row shows its copy lag against the store it copies from.
    const copies = replicateDestinations({ destinations: enabled }, true).filter((d) => d.from);
    if (copies.length > 0) {
      replicas[name] = Object.fromEntries(
        copies.map((d) => [d.target ?? HOME_STORE, d.from as string])
      );
    }
  }
  const repos = await configService.listRepositories();
  const lineages = new Set(
    repos
      .filter(({ config }) => config.placement && 'machine' in config.placement)
      .filter(({ config }) => (config.placement as { machine: string }).machine === machineName)
      .map(({ config }) => config.grandGuid ?? config.repositoryGuid)
  );
  return { byStrategy, replicas, stores: await readStoreStatuses([...lineages]) };
}

/**
 * `backup status`: one row per scheduled unit (base, `.ds.`, `.repo.`) with timer presence, last run
 * and result, next run and a missed-run verdict, then the recent journal of a named strategy's units.
 */
async function showBackupStatus(
  machineName: string,
  strategyFilter?: string,
  debug?: boolean
): Promise<void> {
  const { expectedStatusUnits, renderBackupScheduleStatus } = await import(
    '../services/backup/backup-schedule.js'
  );
  const expected = await expectedStatusUnits(machineName, strategyFilter);
  if (expected.length === 0) {
    // Nothing is bound: no unit to read, so no job.
    renderBackupScheduleStatus(machineName, expected, '');
    return;
  }

  // One read job (`systemctl show` of every unit's timer and service); the table is its step, so a ticket handed back early prints nothing half-done.
  const units = [...new Set(expected.map((u) => `rediacc-backup-${u.unitName}`))];
  const outcome = await runCommandJob(
    'backup status',
    {
      functionName: 'backup-status',
      machineName,
      commandKind: { name: 'backup-status', args: { units } },
      debug,
      captureOutput: true,
    },
    // The step renders the unit list the job read, not a recomputation from a config that may have changed since.
    [
      planStep('renderBackupStatus', {
        machine: machineName,
        expected: JSON.stringify(expected),
        targets: JSON.stringify(
          await readStatusTargets(
            machineName,
            expected.map((u) => u.strategyName)
          )
        ),
      }),
    ]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) {
    renderLocalExecutionFailure(
      outcome.result,
      `Reading the backup units failed on ${machineName}`
    );
    return;
  }
  if (!strategyFilter) return;

  // The recent journal of the strategy's units is a read job of its own (`backup-journal`), after the table's job.
  const journal = await runCommandJob(
    'backup status',
    {
      functionName: 'backup-journal',
      machineName,
      commandKind: { name: 'backup-journal', args: { strategy: strategyFilter } },
      debug,
      captureOutput: true,
    },
    []
  );
  if (journal.kind === 'pending') {
    const code = pendingExitCode(journal);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!journal.result.success) {
    renderLocalExecutionFailure(
      journal.result,
      `Reading the backup journal failed on ${machineName}`
    );
    return;
  }
  outputService.info(`\nRecent logs (${strategyFilter}):`);
  const lines = (journal.result.stdout ?? '').trim();
  writeStdout(`${lines || '(no logs)'}\n`);
}

bindStepHandler('seedStrategyRetention', async ({ machine, params }) => {
  const strategies = typeof params.strategies === 'string' ? params.strategies : '';
  await seedStrategyRetention(strategies ? strategies.split(',') : [], machine);
});

bindStepHandler('renderBackupStatus', async ({ machine, output, params }) => {
  const { renderBackupScheduleStatus } = await import('../services/backup/backup-schedule.js');
  // The job's own plan always sets `expected`; its absence is a corrupt step, not a schedule with no units.
  const expected: unknown = JSON.parse(str(params, 'expected'));
  if (!Array.isArray(expected)) throw new Error('step param "expected" is not a JSON array');
  const targets = typeof params.targets === 'string' ? params.targets : undefined;
  renderBackupScheduleStatus(
    machine,
    expected,
    output ?? '',
    targets === undefined ? undefined : (JSON.parse(targets) as StatusTargets)
  );
});

/** Register the machine-scoped backup ops: schedule, run, status, cancel. */
export function registerBackupOpsCommands(backup: Command): void {
  backup
    .command('schedule')
    .description(t('commands.backup.schedule.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--dry-run', t('commands.backup.schedule.optionDryRun'))
    .option('--force', t('commands.backup.schedule.optionForce'))
    .option('--reset-failed', t('commands.backup.schedule.optionResetFailed'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        const machineName = options.machine;
        const { pushBackupSchedule } = await import('../services/backup/backup-schedule.js');
        const bound = (await configService.getLocalConfig()).machines[machineName];
        const strategies = bound?.backupStrategies ?? [];
        // Retention seeding and the DR nudge (enabling backups without config-storage enrollment leaves the repo credentials host-local, spec/02 dec 14) follow the apply job as its steps.
        const steps = [
          planStep('seedStrategyRetention', {
            strategies: strategies.join(','),
            machine: machineName,
          }),
          planStep('warnIfConfigStorageUnenrolled', {}),
        ];
        const result = await pushBackupSchedule(machineName, {
          debug: options.debug,
          dryRun: options.dryRun,
          force: options.force,
          resetFailed: options.resetFailed,
          steps: options.dryRun ? [] : steps,
        });
        if (result === 'applied' || result === 'unchanged') {
          outputService.success(t('commands.backup.schedule.success', { machine: machineName }));
        }
        if (result === 'unchanged') {
          // No job ran, so the steps the job would have carried run here.
          await seedStrategyRetention(strategies, machineName);
          const { warnIfConfigStorageUnenrolled } = await import('../services/backup/dr-nudge.js');
          await warnIfConfigStorageUnenrolled();
        }
      } catch (error) {
        handleError(error);
      }
    });

  backup
    .command('run')
    .argument('[strategy]', t('options.strategyName'))
    .description(t('commands.backup.run.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (strategy: string | undefined, options) => {
      try {
        await runBackupNow(options.machine, strategy, options.debug);
      } catch (error) {
        handleError(error);
      }
    });

  backup
    .command('status')
    .argument('[strategy]', t('options.strategyName'))
    .description(t('commands.backup.status.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (strategy: string | undefined, options) => {
      try {
        await showBackupStatus(options.machine, strategy, options.debug);
      } catch (error) {
        handleError(error);
      }
    });

  backup
    .command('cancel')
    .argument('[strategy]', t('options.strategyName'))
    .description(t('commands.backup.cancel.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (strategy: string | undefined, options) => {
      try {
        await cancelBackup(options.machine, strategy, options.debug);
      } catch (error) {
        handleError(error);
      }
    });
}
