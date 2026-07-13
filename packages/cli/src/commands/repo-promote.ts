import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { resolveRepoRef } from '../utils/repo-target.js';

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

async function handleRepoPromote(ref: string, options: PromoteOptions): Promise<void> {
  try {
    const { machineName, repoKey, kubeCluster } = await resolveRepoRef(ref);

    // Promote swaps two LUKS images inside one docker datastore; there is no
    // kubernetes equivalent in v1, so refuse a cluster-placed repo early rather
    // than failing downstream with a confusing renet error.
    if (kubeCluster) {
      throw new ValidationError(t('errors.cluster.dockerOnlyVerb', { verb: 'promote' }));
    }

    // Destructive verb: resolve the STRICT key so a bare ambiguous ref fails
    // closed (#495) instead of promoting (or refusing) the wrong record.
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

    const result = await getExecutor().execute({
      functionName: 'repository_promote',
      machineName,
      params: {
        parent: grandEntry.config.repositoryGuid,
        fork: forkConfig.repositoryGuid,
      },
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });

    if (!result.success) {
      renderLocalExecutionFailure(result, t('commands.repo.promote.failed'));
      return;
    }

    const { parseRepoRef } = await import('../utils/config-schema.js');
    const dateSuffix = new Date().toISOString().slice(0, 10).replaceAll('-', '');
    const backupName = `${parseRepoRef(forkRef).name}:pre-promote-${dateSuffix}`;
    await configService.addRepository(backupName, forkConfig);
    await configService.removeRepository(forkRef);
    outputService.success(t('commands.repo.promote.completed'));
    outputService.info(t('commands.repo.promote.backupInfo', { backup: backupName }));
    outputService.info(t('commands.repo.promote.revertHint', { backup: backupName }));
  } catch (error) {
    handleError(error);
  }
}

export function registerRepoPromoteCommand(repo: Command): void {
  const promoteCmd = repo
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
  promoteCmd.addHelpText('after', t('commands.repo.promote.examples'));
}
