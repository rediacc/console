import type { Command } from 'commander';
import { findUnreachable, RemoteWriteFailedClosedError } from '../adapters/remote-config-errors.js';
import { t } from '../i18n/index.js';
import { reconcileBackupSchedules } from '../services/backup/repo-change-hook.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { runCommandJob } from '../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { ERROR_CODES } from '../types/errors.js';
import { CliExitError } from '../utils/cli-exit-error.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { settleRepoJob } from './repo-job-outcome.js';

/**
 * `repo promote <fork-ref>` (spec/03 §5.4, renamed from `repo takeover`): make a
 * validated fork the production repository under its parent's name. The grand keeps
 * its identity (GUID, networkId, domains, autostart, backup chain) and receives the
 * fork's data; the old production data is preserved as a backup fork.
 *
 * Boundary (R2-F16): promote never fetches bytes. Use `repo push` / `backup restore`
 * to bring data in from another place first.
 */
interface PromoteOptions {
  yes?: boolean;
  debug?: boolean;
  skipRouterRestart?: boolean;
}

/**
 * Typed failure for a config save that fails after the machine promote.
 * ORDER: machine first, config second. The retry cannot converge here (unlike `repo delete`):
 * promote swaps two images that both still exist, so re-running would swap the data back.
 * The error names the manual config fix and forbids the re-run.
 */
function configSaveFailure(error: unknown, params: Record<string, string>): CliExitError {
  const networkDown = error instanceof RemoteWriteFailedClosedError || !!findUnreachable(error);
  return new CliExitError(
    networkDown ? ERROR_CODES.NETWORK_ERROR : ERROR_CODES.GENERAL_ERROR,
    t('commands.repo.promote.configSaveFailed', {
      ...params,
      reason: error instanceof Error ? error.message : String(error),
    }),
    { retryable: false }
  );
}

/**
 * The `settlePromote` step: the machine swapped the two images, so the config follows. The fork's record moves to the
 * pre-promote backup entry and the backup units re-render. A rerun after the move finds the fork gone and the backup
 * present, and only re-renders the units.
 */
bindStepHandler('settlePromote', async ({ params }) => {
  for (const key of ['fork', 'grand', 'machine', 'backup'] as const) {
    if (typeof params[key] !== 'string' || params[key] === '') {
      throw new Error(`step param "${key}" is missing`);
    }
  }
  const forkRef = String(params.fork);
  const machineName = String(params.machine);
  const backupName = String(params.backup);
  const forkConfig = await configService.getRepository(forkRef);
  if (forkConfig) {
    try {
      await configService.addRepository(backupName, forkConfig);
      await configService.removeRepository(forkRef);
    } catch (error) {
      throw configSaveFailure(error, {
        fork: forkRef,
        grand: String(params.grand),
        machine: machineName,
        backup: backupName,
      });
    }
  } else if (!(await configService.getRepository(backupName))) {
    throw new Error(`Repository "${forkRef}" is not in the config`);
  }
  outputService.success(t('commands.repo.promote.completed'));
  outputService.info(t('commands.repo.promote.backupInfo', { backup: backupName }));
  outputService.info(t('commands.repo.promote.revertHint', { backup: backupName }));
  // G4: the fork ref was renamed to the pre-promote backup, so the backup units re-render.
  await reconcileBackupSchedules(machineName);
});

async function handleRepoPromote(ref: string, options: PromoteOptions): Promise<void> {
  try {
    const { machineName, repoKey, kubeCluster } = await resolveRepoRef(ref);

    // Promote swaps two LUKS images inside one docker datastore; there is no
    // kubernetes equivalent in v1, so refuse a cluster-placed repo early rather than failing downstream with a confusing renet error.
    if (kubeCluster) {
      throw new ValidationError(t('errors.cluster.dockerOnlyVerb', { verb: 'promote' }));
    }

    // Destructive verb: resolve the STRICT key so a bare ambiguous ref fails closed (#495) instead of promoting (or refusing) the wrong record.
    const { key: forkRef, config: forkConfig } =
      await configService.resolveDestructiveTarget(repoKey);

    if (!forkConfig.parentGuid) {
      throw new ValidationError(t('commands.repo.promote.notAFork', { name: forkRef }));
    }

    const grandGuid = forkConfig.grandGuid ?? forkConfig.parentGuid;
    const repos = await configService.listRepositories();
    const grandEntry = repos.find((r) => r.config.repositoryGuid === grandGuid);
    if (!grandEntry) {
      throw new ValidationError(t('commands.repo.promote.grandNotFound', { name: forkRef }));
    }

    await assertCommandPolicy(CMD.REPO_PROMOTE, grandEntry.name);

    if (!options.yes) {
      const { askConfirm } = await import('../utils/prompt.js');
      const confirmed = await askConfirm(
        t('commands.repo.promote.confirm', { grand: grandEntry.name, fork: forkRef })
      );
      if (!confirmed) {
        outputService.info(t('status.cancelled'));
        return;
      }
    }

    outputService.info(
      t('commands.repo.promote.starting', {
        grand: grandEntry.name,
        fork: forkRef,
        machine: machineName,
      })
    );

    const { parseRepoRef } = await import('../utils/config-schema.js');
    const dateSuffix = new Date().toISOString().slice(0, 10).replaceAll('-', '');
    const backupName = `${parseRepoRef(forkRef).name}:pre-promote-${dateSuffix}`;
    // One job; renaming the fork to the backup entry and re-rendering the schedules is its success step, so a ticket handed back early records no swap that has not happened.
    const outcome = await runCommandJob(
      'repo promote',
      {
        functionName: 'repository_promote',
        machineName,
        // #74: both images are the same FAMILY, so one recorded placement answers
        // for the grand and the fork alike, a fork lives beside its parent.
        datastore: await recordedDatastoreMount(grandEntry.name),
        params: {
          parent: grandEntry.config.repositoryGuid,
          fork: forkConfig.repositoryGuid,
        },
        debug: options.debug,
        skipRouterRestart: options.skipRouterRestart,
      },
      [
        planStep('settlePromote', {
          fork: forkRef,
          grand: grandEntry.name,
          machine: machineName,
          backup: backupName,
        }),
      ]
    );
    settleRepoJob('repo promote', outcome, t('commands.repo.promote.failed'));
  } catch (error) {
    handleError(error);
  }
}

export function registerRepoPromoteCommand(repo: Command): void {
  repo
    .command('promote')
    .summary(t('commands.repo.promote.descriptionShort'))
    .description(t('commands.repo.promote.description'))
    .argument('<fork-ref>', t('options.repoRef'))
    .option('-y, --yes', t('options.yes'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (ref: string, options: PromoteOptions) => {
      await handleRepoPromote(ref, options);
    });
}
