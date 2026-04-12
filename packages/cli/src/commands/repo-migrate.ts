/**
 * Repository live migration command.
 *
 * Two-phase rsync with minimal downtime:
 *   Phase 1: Hot pre-copy (source stays running, bulk transfer)
 *   Phase 2: Cutover (stop source, delta rsync, unmount)
 *   Phase 3: Start on target + DNS switch
 *
 * Optional --checkpoint for CRIU live migration (process memory capture + restore).
 * Optional --provision to auto-create the target machine via cloud provider.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import { formatStepDuration } from '../utils/timeline.js';
import { autoProvisionTarget, buildPushParams, resolveExtraMachines } from './repo-backup.js';
import { postRepoUpTasks } from './repo-batch-utils.js';

export function registerRepoMigrateCommand(repoCommand: Command): void {
  repoCommand
    .command('migrate')
    .summary(t('commands.repo.migrate.descriptionShort'))
    .description(t('commands.repo.migrate.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('--from <machine>', t('commands.repo.migrate.optionFrom'))
    .requiredOption('--to <machine>', t('commands.repo.migrate.optionTo'))
    .option('--provision <provider>', t('commands.repo.migrate.optionProvision'))
    .option('--bwlimit <limit>', t('commands.repo.migrate.optionBwlimit'))
    .option('--checkpoint', t('commands.repo.migrate.optionCheckpoint'))
    .option('--skip-dns', t('commands.repo.migrate.optionSkipDns'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        await migrateRepo(options);
      } catch (error) {
        handleError(error);
      }
    });
}

interface MigrateOptions {
  name: string;
  from: string;
  to: string;
  provision?: string;
  bwlimit?: string;
  checkpoint?: boolean;
  skipDns?: boolean;
  debug?: boolean;
}

/** Execute backup_push with extraMachines resolution (needed for cross-machine rsync). */
async function executePush(
  repoName: string,
  machineName: string,
  params: Record<string, unknown>,
  debug?: boolean
): Promise<void> {
  await configService.ensureRepositoryNetworkId(repoName);
  const extraMachines = await resolveExtraMachines(params);
  const result = await localExecutorService.execute({
    functionName: 'backup_push',
    machineName,
    params: { repository: repoName, ...params },
    extraMachines,
    debug,
    quietSpinners: true,
  });
  if (!result.success) {
    throw new Error(`backup_push failed: ${result.error ?? 'unknown error'}`);
  }
}

/** Execute a repo bridge function quietly (spinner managed by caller). */
async function executeQuiet(
  functionName: string,
  repoName: string,
  machineName: string,
  params: Record<string, unknown>,
  debug?: boolean
): Promise<void> {
  await configService.ensureRepositoryNetworkId(repoName);
  const result = await localExecutorService.execute({
    functionName,
    machineName,
    params: { repository: repoName, ...params },
    debug,
    quietSpinners: true,
  });
  if (!result.success) {
    throw new Error(`${functionName} failed: ${result.error ?? 'unknown error'}`);
  }
}

async function migrateRepo(options: MigrateOptions): Promise<void> {
  const { name, from, to, provision, bwlimit, checkpoint, skipDns, debug } = options;
  const migrationStart = Date.now();

  await assertCommandPolicy(CMD.REPO_PUSH, name);

  // Validate repo exists in config
  const repoConfig = await configService.getRepository(name);
  if (!repoConfig) {
    throw new ValidationError(t('errors.repositoryNotFound', { name }));
  }

  // Phase 0: Provision target if needed
  if (provision) {
    await withSpinner(
      t('commands.repo.migrate.provisioning', { machine: to, provider: provision }),
      () => autoProvisionTarget(to, provision, from, !!debug),
      `Target ${to} provisioned`
    );
  }

  // Validate both machines exist
  const localConfig = await configService.getLocalConfig();
  const sourceMachine = localConfig.machines[from];
  const targetMachine = localConfig.machines[to];
  if (!sourceMachine) {
    throw new ValidationError(`Source machine "${from}" not found in config`);
  }
  if (!targetMachine) {
    throw new ValidationError(
      `Target machine "${to}" not found in config. Use --provision to auto-create it`
    );
  }

  // Safety: check if the repo is already mounted on the target machine.
  if (from !== to) {
    const targetCheck = await localExecutorService.execute({
      functionName: 'repository_list',
      machineName: to,
      params: {},
      captureOutput: true,
    });
    if (targetCheck.success && targetCheck.stdout) {
      try {
        const repos = JSON.parse(targetCheck.stdout);
        const mounted = (repos as { guid: string; mounted: boolean }[]).find(
          (r) => r.guid === repoConfig.repositoryGuid && r.mounted
        );
        if (mounted) {
          throw new ValidationError(
            `Repository "${name}" is already mounted on "${to}". ` +
              `Migrating over a live repo would corrupt it.\n` +
              `Run first: rdc repo down --name ${name} -m ${to} --unmount`
          );
        }
      } catch (e) {
        if (e instanceof ValidationError) throw e;
      }
    }
  }

  // ── Phase 1: Hot pre-copy ─────────────────────────────────────────
  outputService.info('\nPhase 1: Hot pre-copy (source stays running)');

  const pushParams = buildPushParams(name, repoConfig.repositoryGuid, 'machine', to, {
    force: true,
  });
  const seeds = [repoConfig.repositoryGuid, repoConfig.parentGuid, repoConfig.grandGuid].filter(
    (g): g is string => !!g
  );
  const uniqueSeeds = [...new Set(seeds)];
  if (uniqueSeeds.length > 0) pushParams.params.seed = uniqueSeeds.join(',');
  if (bwlimit) pushParams.params.bwlimit = bwlimit;

  await deployRepoKeyIfNeeded(name, to);
  await withSpinner(
    'Transferring bulk data...',
    () => executePush(name, from, pushParams.params, debug),
    'Bulk transfer complete'
  );

  // ── Phase 2: Cutover ──────────────────────────────────────────────
  outputService.info('\nPhase 2: Cutover');
  const cutoverStart = Date.now();

  if (checkpoint) {
    await withSpinner(
      'CRIU checkpoint + delta sync...',
      async () => {
        const deltaParams = buildPushParams(name, repoConfig.repositoryGuid, 'machine', to, {
          force: true,
          checkpoint: true,
        });
        if (bwlimit) deltaParams.params.bwlimit = bwlimit;
        await executePush(name, from, deltaParams.params, debug);
      },
      'Checkpoint + delta synced'
    );
  } else {
    await withSpinner(
      'Stopping source...',
      () => executeQuiet('repository_down', name, from, {}, debug),
      'Source stopped'
    );

    await withSpinner(
      'Syncing delta...',
      async () => {
        const deltaParams = buildPushParams(name, repoConfig.repositoryGuid, 'machine', to, {
          force: true,
        });
        if (bwlimit) deltaParams.params.bwlimit = bwlimit;
        await executePush(name, from, deltaParams.params, debug);
      },
      'Delta synced'
    );
  }

  await withSpinner(
    'Unmounting source...',
    () => executeQuiet('repository_down', name, from, { unmount: true }, debug),
    'Source unmounted'
  );

  const downtimeMs = Date.now() - cutoverStart;

  // ── Phase 3: Start on target ──────────────────────────────────────
  outputService.info('\nPhase 3: Starting on target');

  await withSpinner(
    'Starting services on target...',
    async () => {
      await deployRepoKeyIfNeeded(name, to);
      await executeQuiet('repository_up', name, to, {}, debug);
    },
    'Target running'
  );

  if (!skipDns) {
    await withSpinner('Switching DNS...', () => postRepoUpTasks(name, to), 'DNS updated');
  }

  // ── Summary ───────────────────────────────────────────────────────
  const totalMs = Date.now() - migrationStart;
  outputService.info('');
  outputService.success(t('commands.repo.migrate.complete', { name, from, to }));
  outputService.info(`  Total: ${formatStepDuration(totalMs)}`);
  outputService.info(`  Downtime: ${formatStepDuration(downtimeMs)} (Phase 2)`);
}
