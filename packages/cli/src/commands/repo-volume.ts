import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { assertCommandPolicy, CMD, type CommandPath } from '../utils/command-policy.js';
import { handleError } from '../utils/errors.js';
import { confirmBatch } from './repo-batch-utils.js';

type ExecOptions = {
  debug?: boolean;
  skipRouterRestart?: boolean;
  parallel?: boolean;
  concurrency?: string;
};
type Messages = { starting: string; completed: string; failed: string };

export function registerRepoVolumeCommands(
  repo: Command,
  executeRepoFunction: (
    fn: string,
    name: string,
    machine: string,
    params: Record<string, unknown>,
    options: ExecOptions,
    messages: Messages
  ) => Promise<void>,
  iterateAllRepos: (
    fn: string,
    machine: string,
    policy: CommandPath,
    params: Record<string, unknown>,
    options: ExecOptions,
    meta: { action: string }
  ) => Promise<void>
): void {
  // repo mount [name]
  repo
    .command('mount [name]')
    .description(t('commands.repo.mount.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--checkpoint', t('commands.repo.mount.checkpointOption'))
    .option('--parallel', t('commands.repo.upAll.parallelOption'))
    .option('--concurrency <n>', t('commands.repo.upAll.concurrencyOption'), '3')
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string | undefined,
        options: {
          machine: string;
          checkpoint?: boolean;
          parallel?: boolean;
          concurrency?: string;
          yes?: boolean;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          if (name) {
            await assertCommandPolicy(CMD.REPO_MOUNT, name);

            const params: Record<string, unknown> = {};
            if (options.checkpoint) params.checkpoint = true;

            await executeRepoFunction('repository_mount', name, options.machine, params, options, {
              starting: t('commands.repo.mount.starting', {
                repository: name,
                machine: options.machine,
              }),
              completed: t('commands.repo.mount.completed'),
              failed: t('commands.repo.mount.failed'),
            });
          } else {
            const repos = await configService.listRepositories();
            if (!options.yes && !(await confirmBatch('Mount', repos.length, options.machine))) {
              return;
            }
            const params: Record<string, unknown> = {};
            if (options.checkpoint) params.checkpoint = true;
            await iterateAllRepos(
              'repository_mount',
              options.machine,
              CMD.REPO_MOUNT,
              params,
              options,
              { action: 'Mount' }
            );
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo unmount [name]
  repo
    .command('unmount [name]')
    .description(t('commands.repo.unmount.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--checkpoint', t('commands.repo.unmount.checkpointOption'))
    .option('--parallel', t('commands.repo.upAll.parallelOption'))
    .option('--concurrency <n>', t('commands.repo.upAll.concurrencyOption'), '3')
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string | undefined,
        options: {
          machine: string;
          checkpoint?: boolean;
          parallel?: boolean;
          concurrency?: string;
          yes?: boolean;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          if (name) {
            await assertCommandPolicy(CMD.REPO_UNMOUNT, name);

            const params: Record<string, unknown> = {};
            if (options.checkpoint) params.checkpoint = true;

            await executeRepoFunction(
              'repository_unmount',
              name,
              options.machine,
              params,
              options,
              {
                starting: t('commands.repo.unmount.starting', {
                  repository: name,
                  machine: options.machine,
                }),
                completed: t('commands.repo.unmount.completed'),
                failed: t('commands.repo.unmount.failed'),
              }
            );
          } else {
            const repos = await configService.listRepositories();
            if (!options.yes && !(await confirmBatch('Unmount', repos.length, options.machine))) {
              return;
            }
            const params: Record<string, unknown> = {};
            if (options.checkpoint) params.checkpoint = true;
            await iterateAllRepos(
              'repository_unmount',
              options.machine,
              CMD.REPO_UNMOUNT,
              params,
              options,
              { action: 'Unmount' }
            );
          }
        } catch (error) {
          handleError(error);
        }
      }
    );
}
