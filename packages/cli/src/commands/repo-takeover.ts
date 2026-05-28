import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';

export function registerRepoTakeoverCommand(repo: Command): void {
  const takeoverCmd = repo
    .command('takeover')
    .summary(t('commands.repo.takeover.descriptionShort'))
    .description(t('commands.repo.takeover.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--force', t('commands.repo.takeover.forceOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        name: string;
        machine: string;
        force?: boolean;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const { key: forkRef, config: forkConfig } = await configService.resolveDestructiveTarget(
            options.name
          );
          if (!forkConfig.parentGuid) {
            throw new Error(t('commands.repo.takeover.notAFork', { name: forkRef }));
          }

          const grandGuid = forkConfig.grandGuid ?? forkConfig.parentGuid;
          const repos = await configService.listRepositories();
          const grandEntry = repos.find((r) => r.config.repositoryGuid === grandGuid);
          if (!grandEntry) {
            throw new Error(t('commands.repo.takeover.grandNotFound', { name: forkRef }));
          }

          await assertCommandPolicy(CMD.REPO_TAKEOVER, grandEntry.name);
          outputService.info(
            t('commands.repo.takeover.starting', {
              grand: grandEntry.name,
              fork: forkRef,
              machine: options.machine,
            })
          );

          const result = await localExecutorService.execute({
            functionName: 'repository_takeover',
            machineName: options.machine,
            params: {
              parent: grandEntry.config.repositoryGuid,
              fork: forkConfig.repositoryGuid,
            },
            debug: options.debug,
            skipRouterRestart: options.skipRouterRestart,
          });

          if (!result.success) {
            renderLocalExecutionFailure(result, t('commands.repo.takeover.failed'));
            return;
          }

          const { parseRepoRef } = await import('../utils/config-schema.js');
          const dateSuffix = new Date().toISOString().slice(0, 10).replaceAll('-', '');
          const backupName = `${parseRepoRef(forkRef).name}:pre-takeover-${dateSuffix}`;
          await configService.addRepository(backupName, forkConfig);
          await configService.removeRepository(forkRef);
          outputService.success(t('commands.repo.takeover.completed'));
          outputService.info(t('commands.repo.takeover.backupInfo', { backup: backupName }));
          outputService.info(
            t('commands.repo.takeover.revertHint', { backup: backupName, machine: options.machine })
          );
        } catch (error) {
          handleError(error);
        }
      }
    );
  takeoverCmd.addHelpText('after', t('commands.repo.takeover.examples'));
}
