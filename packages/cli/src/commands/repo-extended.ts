import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import type { Command } from 'commander';

/**
 * Execute a machine-level function (no repository context needed).
 */
async function executeMachineFunction(
  functionName: string,
  options: { machine: string; debug?: boolean; skipRouterRestart?: boolean },
  messages: { starting: string; completed: string; failed: string }
): Promise<void> {
  outputService.info(messages.starting);

  const result = await localExecutorService.execute({
    functionName,
    machineName: options.machine,
    params: {},
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
  });

  if (result.success) {
    outputService.success(messages.completed);
  } else {
    outputService.error(result.error ?? messages.failed);
    process.exitCode = result.exitCode;
  }
}

/**
 * Execute a repository lifecycle function on a remote machine.
 * Validates the repository exists in context and runs the function via localExecutorService.
 */
async function executeRepoFunction(
  functionName: string,
  repoName: string,
  machineName: string,
  params: Record<string, unknown>,
  options: { debug?: boolean; skipRouterRestart?: boolean },
  messages: { starting: string; completed: string; failed: string }
): Promise<void> {
  // Validate repository exists in context
  const repo = await configService.getRepository(repoName);
  if (!repo) {
    throw new Error(`Repository "${repoName}" not found in context`);
  }
  if (!repo.credential) {
    outputService.warn(t('commands.repo.noCredential', { name: repoName }));
  }

  // Ensure network_id is assigned (auto-allocates for legacy repos without one)
  await configService.ensureRepositoryNetworkId(repoName);

  outputService.info(messages.starting);

  const result = await localExecutorService.execute({
    functionName,
    machineName,
    params: { repository: repoName, ...params },
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
  });

  if (result.success) {
    outputService.success(messages.completed);
  } else {
    outputService.error(result.error ?? messages.failed);
    process.exitCode = result.exitCode;
  }
}

/**
 * Register extended repo commands: fork, resize, expand, validate,
 * autostart, ownership, and template.
 */
export function registerExtendedRepoCommands(repo: Command): void {
  // repo fork <parent>
  repo
    .command('fork <parent>')
    .description(t('commands.repo.fork.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--tag <name>', t('commands.repo.fork.tagOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        parent: string,
        options: { machine: string; tag: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        const forkName = options.tag;
        try {
          // Validate parent exists
          const parentConfig = await configService.getRepository(parent);
          if (!parentConfig) {
            throw new Error(`Repository "${parent}" not found in context`);
          }

          // Validate fork doesn't already exist
          const existing = await configService.getRepository(forkName);
          if (existing) {
            throw new Error(t('commands.repo.fork.alreadyExists', { name: forkName }));
          }

          // Generate new GUID and allocate networkId; reuse parent's credential (same LUKS password)
          const repositoryGuid = randomUUID();
          const networkId = await configService.allocateNetworkId();

          await configService.addRepository(forkName, {
            repositoryGuid,
            tag: 'latest',
            credential: parentConfig.credential,
            networkId,
          });

          outputService.info(
            t('commands.repo.fork.registered', {
              repository: forkName,
              guid: repositoryGuid.slice(0, 8),
              networkId,
            })
          );
          outputService.info(
            t('commands.repo.fork.starting', {
              parent,
              repository: forkName,
              machine: options.machine,
            })
          );

          // Execute fork on remote (repository param = parent, tag = fork's GUID)
          const result = await localExecutorService.execute({
            functionName: 'repository_fork',
            machineName: options.machine,
            params: { repository: parent, tag: repositoryGuid },
            debug: options.debug,
            skipRouterRestart: options.skipRouterRestart,
          });

          if (result.success) {
            outputService.success(t('commands.repo.fork.completed'));
          } else {
            await configService.removeRepository(forkName);
            outputService.warn(t('commands.repo.fork.rollback', { repository: forkName }));
            outputService.error(result.error ?? t('commands.repo.fork.failed'));
            process.exitCode = result.exitCode;
          }
        } catch (error) {
          const exists = await configService.getRepository(forkName);
          if (exists) {
            await configService.removeRepository(forkName);
            outputService.warn(t('commands.repo.fork.rollback', { repository: forkName }));
          }
          handleError(error);
        }
      }
    );

  // repo resize <name>
  repo
    .command('resize <name>')
    .description(t('commands.repo.resize.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--size <size>', t('commands.repo.resize.sizeOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: { machine: string; size: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          await executeRepoFunction(
            'repository_resize',
            name,
            options.machine,
            { size: options.size },
            options,
            {
              starting: t('commands.repo.resize.starting', {
                repository: name,
                size: options.size,
                machine: options.machine,
              }),
              completed: t('commands.repo.resize.completed'),
              failed: t('commands.repo.resize.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo expand <name>
  repo
    .command('expand <name>')
    .description(t('commands.repo.expand.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--size <size>', t('commands.repo.expand.sizeOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: { machine: string; size: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          await executeRepoFunction(
            'repository_expand',
            name,
            options.machine,
            { size: options.size },
            options,
            {
              starting: t('commands.repo.expand.starting', {
                repository: name,
                size: options.size,
                machine: options.machine,
              }),
              completed: t('commands.repo.expand.completed'),
              failed: t('commands.repo.expand.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo validate <name>
  repo
    .command('validate <name>')
    .description(t('commands.repo.validate.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          await executeRepoFunction('repository_validate', name, options.machine, {}, options, {
            starting: t('commands.repo.validate.starting', {
              repository: name,
              machine: options.machine,
            }),
            completed: t('commands.repo.validate.completed'),
            failed: t('commands.repo.validate.failed'),
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo autostart (parent command with subcommands)
  const autostart = repo.command('autostart').description(t('commands.repo.autostart.description'));

  // repo autostart enable <name>
  autostart
    .command('enable <name>')
    .description(t('commands.repo.autostart.enable.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          await executeRepoFunction(
            'repository_autostart_enable',
            name,
            options.machine,
            {},
            options,
            {
              starting: t('commands.repo.autostart.enable.starting', {
                repository: name,
                machine: options.machine,
              }),
              completed: t('commands.repo.autostart.enable.completed'),
              failed: t('commands.repo.autostart.enable.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo autostart disable <name>
  autostart
    .command('disable <name>')
    .description(t('commands.repo.autostart.disable.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          await executeRepoFunction(
            'repository_autostart_disable',
            name,
            options.machine,
            {},
            options,
            {
              starting: t('commands.repo.autostart.disable.starting', {
                repository: name,
                machine: options.machine,
              }),
              completed: t('commands.repo.autostart.disable.completed'),
              failed: t('commands.repo.autostart.disable.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo autostart enable-all
  autostart
    .command('enable-all')
    .description(t('commands.repo.autostart.enableAll.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }) => {
      try {
        await executeMachineFunction('repository_autostart_enable_all', options, {
          starting: t('commands.repo.autostart.enableAll.starting', { machine: options.machine }),
          completed: t('commands.repo.autostart.enableAll.completed'),
          failed: t('commands.repo.autostart.enableAll.failed'),
        });
      } catch (error) {
        handleError(error);
      }
    });

  // repo autostart disable-all
  autostart
    .command('disable-all')
    .description(t('commands.repo.autostart.disableAll.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }) => {
      try {
        await executeMachineFunction('repository_autostart_disable_all', options, {
          starting: t('commands.repo.autostart.disableAll.starting', { machine: options.machine }),
          completed: t('commands.repo.autostart.disableAll.completed'),
          failed: t('commands.repo.autostart.disableAll.failed'),
        });
      } catch (error) {
        handleError(error);
      }
    });

  // repo autostart list
  autostart
    .command('list')
    .description(t('commands.repo.autostart.list.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }) => {
      try {
        await executeMachineFunction('repository_autostart_list', options, {
          starting: t('commands.repo.autostart.list.starting', { machine: options.machine }),
          completed: t('commands.repo.autostart.list.completed'),
          failed: t('commands.repo.autostart.list.failed'),
        });
      } catch (error) {
        handleError(error);
      }
    });

  // repo ownership <name>
  repo
    .command('ownership <name>')
    .description(t('commands.repo.ownership.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--uid <uid>', t('commands.repo.ownership.uidOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: { machine: string; uid?: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          const params: Record<string, unknown> = {};
          if (options.uid) params.owner_uid = options.uid;

          await executeRepoFunction(
            'repository_ownership',
            name,
            options.machine,
            params,
            options,
            {
              starting: t('commands.repo.ownership.starting', {
                repository: name,
                machine: options.machine,
              }),
              completed: t('commands.repo.ownership.completed'),
              failed: t('commands.repo.ownership.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo template <name>
  repo
    .command('template <name>')
    .description(t('commands.repo.template.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--file <path>', t('commands.repo.template.fileOption'))
    .option('--grand <name>', t('commands.repo.template.grandOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: {
          machine: string;
          file: string;
          grand?: string;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          // Read and base64-encode template file
          let fileContent: string;
          try {
            fileContent = readFileSync(options.file, 'utf-8');
          } catch {
            throw new Error(t('commands.repo.template.fileNotFound', { path: options.file }));
          }
          const tmpl = Buffer.from(fileContent).toString('base64');

          const params: Record<string, unknown> = { tmpl };

          // Resolve grand repo friendly name -> GUID
          if (options.grand) {
            const grandRepo = await configService.getRepository(options.grand);
            params.grand = grandRepo?.repositoryGuid ?? options.grand;
          }

          await executeRepoFunction(
            'repository_template_apply',
            name,
            options.machine,
            params,
            options,
            {
              starting: t('commands.repo.template.starting', {
                repository: name,
                machine: options.machine,
              }),
              completed: t('commands.repo.template.completed'),
              failed: t('commands.repo.template.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );
}
