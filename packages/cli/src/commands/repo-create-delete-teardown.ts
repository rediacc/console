/**
 * The delete side of `rdc repo`: the delete action body, its post-delete settlement and the local
 * VS Code SSH cleanup. The verbs are registered in repo-create-delete.ts.
 */

import { findUnreachable, RemoteWriteFailedClosedError } from '../adapters/remote-config-errors.js';
import { t } from '../i18n/index.js';
import {
  generateConnectionName,
  removePersistedKeys,
  removeSSHConfigEntry,
} from '../remote/vscode/index.js';
import { reconcileBackupSchedules } from '../services/backup/repo-change-hook.js';
import { configService } from '../services/config/config-resources.js';
import { ensureRepositoryNetworkId } from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import { writeStdout } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { ERROR_CODES } from '../types/errors.js';
import { CliExitError } from '../utils/cli-exit-error.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { formatStepDuration } from '../utils/timeline.js';
import {
  type DeletedRepoConfig,
  isFork,
  settleCloudBackups,
  settleConfigEntry,
  settleRepoLicense,
} from './repo-delete-settle.js';

/** Clean up local VS Code SSH artifacts after a repo delete. Non-fatal. */
async function cleanupDeletedRepoSSH(machineName: string, repoName: string): Promise<void> {
  const teamName = (await configService.applyDefaults({})).team ?? '';
  const connectionName = generateConnectionName(teamName, machineName, repoName);
  removeSSHConfigEntry(connectionName);
  removePersistedKeys(teamName, machineName, repoName);
}

/** Log total step duration and mark timeline as rendered. */
export function renderTimelineTotal(steps: { duration_ms: number }[]): void {
  const totalMs = steps.reduce((sum, s) => sum + s.duration_ms, 0);
  writeStdout(`\nTotal: ${formatStepDuration(totalMs)}\n`);
  outputService.setTimelineRendered();
}

/** Handle post-delete success: cleanup, timeline, config-entry settlement, hints. */
export async function handleDeleteSuccess(
  name: string,
  machineName: string,
  repoConfig: DeletedRepoConfig,
  archiveConfig: boolean,
  result: import('../services/executor/local-executor.js').ExecuteResult,
  originalRef?: string,
  purgeBackups = false
): Promise<void> {
  await cleanupDeletedRepoSSH(machineName, name).catch(() => {});
  // When the user invoked `repo delete --name app` and the resolver returned `app:latest`, VS Code SSH artifacts persisted under the original bare alias survive the cleanup above. Sweep that name too.
  if (originalRef && originalRef !== name) {
    await cleanupDeletedRepoSSH(machineName, originalRef).catch(() => {});
  }

  if (result.allSteps && result.allSteps.length > 0) {
    renderTimelineTotal(result.allSteps);
  } else {
    outputService.success(t('commands.repo.delete.completed'));
  }
  // ORDER: machine first, config second, and the pair is made safe by retry instead of by swapping. Config-first would risk the worse half-state: a config with no entry for an image that still exists on the machine (an orphaned encrypted volume nothing can name or reach). Machine-first leaves at worst an entry whose image is gone, and the retry converges: the presence probe in resolveRepoRef reports the image absent, the machine dispatch is skipped, and this settle step runs again.
  // The steps after this save (backup schedule reconcile, cloud backup settle, license settle) are deliberately DEFERRED to the retry rather than run before the throw: all three read the config entry this save settles (retention, archive and license state hang off it), so running them against an unsettled entry would act on stale state. The retry converges to this same function with the image absent, and runs them then.
  try {
    await settleConfigEntry(name, machineName, repoConfig, archiveConfig);
  } catch (error) {
    const retry = [
      'rdc repo delete',
      name,
      archiveConfig && '--archive-config',
      purgeBackups && '--purge-backups',
      '-y',
    ]
      .filter(Boolean)
      .join(' ');
    const networkDown = error instanceof RemoteWriteFailedClosedError || !!findUnreachable(error);
    throw new CliExitError(
      networkDown ? ERROR_CODES.NETWORK_ERROR : ERROR_CODES.GENERAL_ERROR,
      t('commands.repo.delete.configSaveFailed', {
        repository: name,
        machine: machineName,
        reason: error instanceof Error ? error.message : String(error),
        command: retry,
      }),
      { retryable: true }
    );
  }
  await reconcileBackupSchedules(machineName);
  await settleCloudBackups(name, repoConfig, purgeBackups);
  await settleRepoLicense(name, repoConfig);
  // --purge-backups just freed them: the hint that they outlive the repository would contradict that.
  if (!purgeBackups) {
    outputService.info(t('commands.repo.delete.cloudBackupHint', { machine: machineName }));
  }
}

/**
 * Handle the repo delete action body (spec 03 §5.4): derive the machine (and the
 * kube arm) from the ref's placement, then resolve the STRICT destructive key so
 * a bare ambiguous ref fails closed (#495) rather than deleting the wrong repo.
 */
export async function handleRepoDelete(
  ref: string,
  options: {
    archiveConfig?: boolean;
    purgeBackups?: boolean;
    yes?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
    dryRun?: boolean;
  }
): Promise<void> {
  try {
    // Converge-to-absent (#45/#95): delete RETAINS the config family by design ("may exist on other machines"), so a delete whose image is already gone is a legitimate sequence, resolve with absentOk and skip the machine dispatch on a definite absence instead of refusing with exit 12.
    const { name, repoKey, machineName, kubeCluster, imageAbsent } = await resolveRepoRef(ref, {
      absentOk: true,
    });
    const { key: target, config: repoConfig } =
      await configService.resolveDestructiveTarget(repoKey);
    await assertCommandPolicy(CMD.REPO_DELETE, target);
    // Refused before anything is deleted: a fork's lineage is its parent's, and a purge would take the parent's backups with it.
    if (options.purgeBackups && isFork(repoConfig)) {
      throw new ValidationError(t('commands.repo.delete.purgeForkRefused', { repository: target }));
    }

    // A definite absence skips the machine dispatch, so the ID is only needed when the image is there.
    if (!imageAbsent) {
      const datastore = await recordedDatastoreMount(target);
      await ensureRepositoryNetworkId(target, {
        machine: machineName,
        ...(datastore !== undefined && { datastore }),
        ...(kubeCluster !== undefined && { kubeCluster }),
      });
    }

    if (options.dryRun) {
      outputService.print(
        {
          dryRun: true,
          repository: target,
          machine: machineName,
          guid: repoConfig.repositoryGuid,
          archiveConfig: !!options.archiveConfig,
          purgeBackups: !!options.purgeBackups,
        },
        getOutputFormat()
      );
      return;
    }

    if (!options.yes) {
      const { askConfirm } = await import('../utils/prompt.js');
      const confirmed = await askConfirm(
        t('commands.repo.delete.confirm', { repository: target, machine: machineName })
      );
      if (!confirmed) {
        outputService.info(t('status.cancelled'));
        return;
      }
    }

    outputService.info(
      t('commands.repo.delete.starting', { repository: target, machine: machineName })
    );

    // Definite machine-arm absence: the image is already gone, converge straight to the config-side completion (retention/archive messaging).
    const result: import('../services/executor/local-executor.js').ExecuteResult = imageAbsent
      ? { success: true, stdout: '', stderr: '', exitCode: 0, durationMs: 0 }
      : await getExecutor().execute({
          functionName: 'repository_delete',
          machineName,
          ...(kubeCluster !== undefined && { kubeCluster }),
          // #74, the asymmetric half: `repository_create` above already declares the datastore it recorded, and delete said nothing, so a repo created on a named datastore could not be deleted from it, renet looking for the image on the machine's default.
          datastore: await recordedDatastoreMount(target),
          params: { repository: target },
          debug: options.debug,
          skipRouterRestart: options.skipRouterRestart,
        });

    if (result.success) {
      await handleDeleteSuccess(
        target,
        machineName,
        repoConfig,
        !!options.archiveConfig,
        result,
        name,
        !!options.purgeBackups
      );
    } else {
      renderLocalExecutionFailure(result, t('commands.repo.delete.failed'));
    }
  } catch (error) {
    handleError(error);
  }
}
