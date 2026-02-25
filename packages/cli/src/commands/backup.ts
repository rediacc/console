import { DEFAULTS } from '@rediacc/shared/config';
import {
  type CreateActionOptions,
  coerceCliParams,
  createAction,
  traceAction,
  validateFunctionParams,
} from './queue.js';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import type { Command } from 'commander';

/** Accumulate repeatable option values into an array. */
function collect(val: string, prev: string[]): string[] {
  return [...prev, val];
}

interface BackupRunOptions {
  machine?: string;
  debug?: boolean;
  watch?: boolean;
  skipRouterRestart?: boolean;
}

/** Resolve extra machines needed for multi-machine operations (e.g., backup push --to-machine). */
async function resolveExtraMachines(
  params: Record<string, unknown>
): Promise<Record<string, { ip: string; port?: number; user: string }> | undefined> {
  if (params.destinationType === 'machine' && typeof params.to === 'string') {
    const machine = await configService.getLocalMachine(params.to);
    return { [params.to]: { ip: machine.ip, port: machine.port, user: machine.user } };
  }
  if (params.sourceType === 'machine' && typeof params.from === 'string') {
    const machine = await configService.getLocalMachine(params.from);
    return { [params.from]: { ip: machine.ip, port: machine.port, user: machine.user } };
  }
  return undefined;
}

/** Execute a bridge function in the appropriate mode (local/s3/cloud). */
async function executeFunction(
  functionName: string,
  params: Record<string, unknown>,
  options: BackupRunOptions,
  program?: Command
): Promise<void> {
  const provider = await getStateProvider();
  const machineName = options.machine ?? (await configService.getMachine());

  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }

  const coerced = coerceCliParams(functionName, params as Record<string, string>);
  validateFunctionParams(functionName, coerced);

  if (provider.isCloud) {
    const createOptions: CreateActionOptions = {
      function: functionName,
      machine: machineName,
      priority: String(DEFAULTS.PRIORITY.QUEUE_PRIORITY),
      param: Object.entries(coerced).map(([k, v]) => `${k}=${v}`),
    };
    const result = await createAction(createOptions);
    if (options.watch && result.taskId && program) {
      outputService.info(t('commands.shortcuts.run.watching'));
      await traceAction(result.taskId, { watch: true, interval: '2000' }, program);
    }
  } else {
    outputService.info(
      t('commands.shortcuts.run.executingLocal', { function: functionName, machine: machineName })
    );
    const extraMachines = await resolveExtraMachines(coerced);
    const result = await localExecutorService.execute({
      functionName,
      machineName,
      params: coerced,
      extraMachines,
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });
    if (result.success) {
      outputService.success(
        t('commands.shortcuts.run.completedLocal', { duration: result.durationMs })
      );
    } else {
      outputService.error(t('commands.shortcuts.run.failedLocal', { error: result.error }));
      process.exitCode = result.exitCode;
    }
  }
}

/** Validate that exactly one sync direction (--to or --from) is specified. */
function validateSyncDirection(options: { to?: string; from?: string }): void {
  if (!options.to && !options.from) {
    throw new ValidationError(t('commands.backup.sync.directionRequired'));
  }
  if (options.to && options.from) {
    throw new ValidationError(t('commands.backup.sync.directionConflict'));
  }
}

/** Resolve an array of repo names to their corresponding GUIDs. */
async function resolveRepoGUIDs(repoNames: string[]): Promise<string[]> {
  const guids: string[] = [];
  for (const repoName of repoNames) {
    const repoConfig = await configService.getRepository(repoName);
    if (!repoConfig) {
      throw new ValidationError(t('errors.repositoryNotFound', { name: repoName }));
    }
    guids.push(repoConfig.repositoryGuid);
  }
  return guids;
}

/** Apply optional backup push flags (checkpoint, force, tag) to params. */
function applyPushFlags(
  params: Record<string, unknown>,
  options: { checkpoint?: boolean; force?: boolean; tag?: string }
): void {
  if (options.checkpoint) params.checkpoint = true;
  if (options.force) params.override = true;
  if (options.tag) params.tag = options.tag;
}

/** Build params for a storage-targeted backup push. */
function buildStoragePushParams(
  repo: string,
  repositoryGuid: string,
  options: { dest?: string; to: string; checkpoint?: boolean; force?: boolean; tag?: string }
): { params: Record<string, unknown>; dest: string } {
  const dest = repositoryGuid;
  if (options.dest && options.dest !== dest) {
    outputService.warn(
      t('commands.backup.push.destIgnoredForStorage', { dest, provided: options.dest })
    );
  }
  const params: Record<string, unknown> = {
    repository: repo,
    dest,
    destinationType: 'storage',
    to: options.to,
  };
  applyPushFlags(params, options);
  return { params, dest };
}

/** Build params for a machine-targeted backup push. */
function buildMachinePushParams(
  repo: string,
  repositoryGuid: string,
  options: { dest?: string; toMachine: string; checkpoint?: boolean; force?: boolean; tag?: string }
): { params: Record<string, unknown>; dest: string } {
  const dest = options.dest ?? repositoryGuid;
  const params: Record<string, unknown> = {
    repository: repo,
    dest,
    destinationType: 'machine',
    to: options.toMachine,
  };
  applyPushFlags(params, options);
  return { params, dest };
}

export function registerBackupCommands(program: Command): void {
  const backup = program.command('backup').description(t('commands.backup.description'));

  // backup push <repo>
  backup
    .command('push <repo>')
    .description(t('commands.backup.push.description'))
    .option('--dest <filename>', t('commands.backup.push.optionDest'))
    .option('--to <storage>', t('commands.backup.push.optionToStorage'))
    .option('--to-machine <machine>', t('commands.backup.push.optionToMachine'))
    .option('--checkpoint', t('commands.backup.push.optionCheckpoint'))
    .option('--force', t('commands.backup.push.optionForce'))
    .option('--tag <tag>', t('commands.backup.push.optionTag'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-w, --watch', t('options.watch'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (repo, options) => {
      try {
        const repoConfig = await configService.getRepository(repo);
        if (!repoConfig) {
          throw new ValidationError(t('errors.repositoryNotFound', { name: repo }));
        }

        let params: Record<string, unknown>;
        let dest: string;

        if (options.to) {
          ({ params, dest } = buildStoragePushParams(repo, repoConfig.repositoryGuid, options));
        } else if (options.toMachine) {
          ({ params, dest } = buildMachinePushParams(repo, repoConfig.repositoryGuid, options));
        } else {
          throw new ValidationError(t('commands.backup.push.destRequired'));
        }

        outputService.info(t('commands.backup.push.pushing', { repo, dest }));
        await executeFunction(`backup_push`, params, options, program);
      } catch (error) {
        handleError(error);
      }
    });

  // backup pull <repo>
  backup
    .command('pull <repo>')
    .description(t('commands.backup.pull.description'))
    .option('--from <storage>', t('commands.backup.pull.optionFromStorage'))
    .option('--from-machine <machine>', t('commands.backup.pull.optionFromMachine'))
    .option('--force', t('commands.backup.pull.optionForce'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-w, --watch', t('options.watch'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (repo, options) => {
      try {
        const params: Record<string, unknown> = { repository: repo };

        if (options.from) {
          params.sourceType = 'storage';
          params.from = options.from;
        } else if (options.fromMachine) {
          params.sourceType = 'machine';
          params.from = options.fromMachine;
        } else {
          throw new ValidationError(t('commands.backup.pull.sourceRequired'));
        }

        if (options.force) params.force = true;

        outputService.info(t('commands.backup.pull.pulling', { repo }));
        await executeFunction(`backup_pull`, params, options, program);
      } catch (error) {
        handleError(error);
      }
    });

  // backup list
  backup
    .command('list')
    .description(t('commands.backup.list.description'))
    .option('--from <storage>', t('commands.backup.list.optionFromStorage'))
    .option('--from-machine <machine>', t('commands.backup.list.optionFromMachine'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-w, --watch', t('options.watch'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options) => {
      try {
        const params: Record<string, unknown> = {};

        if (options.from) {
          params.sourceType = 'storage';
          params.from = options.from;
        } else if (options.fromMachine) {
          params.sourceType = 'machine';
          params.from = options.fromMachine;
        } else {
          throw new ValidationError(t('commands.backup.list.sourceRequired'));
        }

        outputService.info(t('commands.backup.list.listing'));
        await executeFunction(`backup_list`, params, options, program);
      } catch (error) {
        handleError(error);
      }
    });

  // =========================================================================
  // backup sync — bulk push/pull all repos
  // =========================================================================
  backup
    .command('sync')
    .description(t('commands.backup.sync.description'))
    .option('--to <storage>', t('commands.backup.sync.optionTo'))
    .option('--from <storage>', t('commands.backup.sync.optionFrom'))
    .option('--repo <name>', t('commands.backup.sync.optionRepo'), collect, [])
    .option('--override', t('commands.backup.sync.optionOverride'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        validateSyncDirection(options);

        const repoGUIDs = await resolveRepoGUIDs(options.repo as string[]);
        const repos = repoGUIDs.length > 0 ? repoGUIDs : undefined;

        const { runBackupSyncPush, runBackupSyncPull } = await import('../services/backup-sync.js');

        if (options.to) {
          await runBackupSyncPush({
            storageName: options.to,
            machine: options.machine,
            repos,
            debug: options.debug,
          });
          outputService.success(t('commands.backup.sync.pushSuccess'));
        } else {
          await runBackupSyncPull({
            storageName: options.from,
            machine: options.machine,
            repos,
            override: options.override,
            debug: options.debug,
          });
          outputService.success(t('commands.backup.sync.pullSuccess'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // =========================================================================
  // backup schedule — manage scheduled backup configuration
  // =========================================================================
  const schedule = backup
    .command('schedule')
    .description(t('commands.backup.schedule.description'));

  // backup schedule set
  schedule
    .command('set')
    .description(t('commands.backup.schedule.set.description'))
    .option('--destination <storage>', t('commands.backup.schedule.set.optionDestination'))
    .option('--cron <expression>', t('commands.backup.schedule.set.optionCron'))
    .option('--enable', t('commands.backup.schedule.set.optionEnable'))
    .option('--disable', t('commands.backup.schedule.set.optionDisable'))
    .action(async (options) => {
      try {
        if (!options.destination && !options.cron && !options.enable && !options.disable) {
          throw new ValidationError(t('commands.backup.schedule.set.noOptions'));
        }

        const updates: Record<string, unknown> = {};
        if (options.destination) updates.defaultDestination = options.destination;
        if (options.cron) updates.schedule = options.cron;
        if (options.enable) updates.enabled = true;
        if (options.disable) updates.enabled = false;

        await configService.setBackupConfig(updates);
        outputService.success(t('commands.backup.schedule.set.saved'));
      } catch (error) {
        handleError(error);
      }
    });

  // backup schedule show
  schedule
    .command('show')
    .description(t('commands.backup.schedule.show.description'))
    .action(async () => {
      try {
        const config = await configService.getBackupConfig();
        if (!config) {
          outputService.info(t('commands.backup.schedule.show.notConfigured'));
          return;
        }

        outputService.info(
          t('commands.backup.schedule.show.destination', { destination: config.defaultDestination })
        );
        if (config.schedule) {
          outputService.info(
            t('commands.backup.schedule.show.schedule', { schedule: config.schedule })
          );
        }
        outputService.info(
          t('commands.backup.schedule.show.enabled', { enabled: String(config.enabled !== false) })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // backup schedule push <machine>
  schedule
    .command('push <machine>')
    .description(t('commands.backup.schedule.push.description'))
    .option('--debug', t('options.debug'))
    .action(async (machine, options) => {
      try {
        const { pushBackupSchedule } = await import('../services/backup-schedule.js');
        await pushBackupSchedule(machine, { debug: options.debug });
        outputService.success(t('commands.backup.schedule.push.success', { machine }));
      } catch (error) {
        handleError(error);
      }
    });
}
