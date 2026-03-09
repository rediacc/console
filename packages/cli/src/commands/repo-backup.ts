import { DEFAULTS } from '@rediacc/shared/config';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import {
  type CreateActionOptions,
  coerceCliParams,
  createAction,
  traceAction,
  validateFunctionParams,
} from './queue.js';

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
      t('commands.repo.push.destIgnoredForStorage', { dest, provided: options.dest })
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

/**
 * Auto-provision target machine if it doesn't exist and --provider is given.
 */
async function autoProvisionTarget(options: Record<string, unknown>): Promise<void> {
  if (!options.provider) return;
  const machines = await configService.listMachines();
  const exists = machines.some((m) => m.name === options.toMachine);
  if (exists) return;

  // Inherit infra config from source machine
  const sourceMachineName =
    (options.machine as string | undefined) ?? (await configService.getMachine());
  let sourceInfra: import('../types/index.js').InfraConfig | undefined;
  if (sourceMachineName) {
    try {
      const sourceMachine = await configService.getLocalMachine(sourceMachineName);
      sourceInfra = sourceMachine.infra;
    } catch {
      /* non-fatal */
    }
  }

  const { createCloudMachine } = await import('../services/tofu/index.js');
  await createCloudMachine(options.toMachine as string, options.provider as string, {
    inheritInfra: sourceInfra,
    debug: options.debug as boolean,
  });
}

/**
 * Register backup-related commands directly on the repo command:
 * - repo push <repo>
 * - repo pull <repo>
 * - repo list-backups
 */
export function registerRepoBackupCommands(repoCommand: Command): void {
  // repo push <repo>
  repoCommand
    .command('push <repo>')
    .description(t('commands.repo.push.description'))
    .option('--dest <filename>', t('commands.repo.push.optionDest'))
    .option('--to <storage>', t('commands.repo.push.optionToStorage'))
    .option('--to-machine <machine>', t('commands.repo.push.optionToMachine'))
    .option('--provider <name>', t('commands.repo.push.optionProvider'))
    .option('--checkpoint', t('commands.repo.push.optionCheckpoint'))
    .option('--force', t('commands.repo.push.optionForce'))
    .option('--tag <tag>', t('commands.repo.push.optionTag'))
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
          await autoProvisionTarget(options);
          ({ params, dest } = buildMachinePushParams(repo, repoConfig.repositoryGuid, options));
        } else {
          throw new ValidationError(t('commands.repo.push.destRequired'));
        }

        outputService.info(t('commands.repo.push.pushing', { repo, dest }));
        await executeFunction(`backup_push`, params, options, repoCommand);
      } catch (error) {
        handleError(error);
      }
    });

  // repo pull <repo>
  repoCommand
    .command('pull <repo>')
    .description(t('commands.repo.pull.description'))
    .option('--from <storage>', t('commands.repo.pull.optionFromStorage'))
    .option('--from-machine <machine>', t('commands.repo.pull.optionFromMachine'))
    .option('--force', t('commands.repo.pull.optionForce'))
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
          throw new ValidationError(t('commands.repo.pull.sourceRequired'));
        }

        if (options.force) params.force = true;

        outputService.info(t('commands.repo.pull.pulling', { repo }));
        await executeFunction(`backup_pull`, params, options, repoCommand);
      } catch (error) {
        handleError(error);
      }
    });

  // repo list-backups
  repoCommand
    .command('list-backups')
    .description(t('commands.repo.listBackups.description'))
    .option('--from <storage>', t('commands.repo.listBackups.optionFromStorage'))
    .option('--from-machine <machine>', t('commands.repo.listBackups.optionFromMachine'))
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
          throw new ValidationError(t('commands.repo.listBackups.sourceRequired'));
        }

        outputService.info(t('commands.repo.listBackups.listing'));
        await executeFunction(`backup_list`, params, options, repoCommand);
      } catch (error) {
        handleError(error);
      }
    });
}
