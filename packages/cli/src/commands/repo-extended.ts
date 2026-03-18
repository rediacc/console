import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { generateSSHKeyPair } from '../utils/ssh-keygen.js';

/** Execute a machine-level function (no repository context needed). */
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
    renderLocalExecutionFailure(result, result.error ?? messages.failed);
  }
}

/** Execute a repository lifecycle function on a remote machine. */
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
    renderLocalExecutionFailure(result, result.error ?? messages.failed);
  }
}

/**
 * Register extended repo commands: fork, resize, expand, validate,
 * autostart, ownership, and template.
 */
export function registerExtendedRepoCommands(repo: Command): void {
  // repo fork <parent> <tag>
  repo
    .command('fork <parent> [tag]')
    .summary(t('commands.repo.fork.descriptionShort'))
    .description(t('commands.repo.fork.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--tag <name>', t('commands.repo.fork.tagOption'))
    .option('--checkpoint', t('commands.repo.fork.checkpointOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        parent: string,
        tagArg: string | undefined,
        options: {
          machine: string;
          tag?: string;
          checkpoint?: boolean;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        const { parseRepoRef, compositeKey } = await import('../utils/config-schema.js');
        const tagName = tagArg ?? options.tag;
        if (!tagName) {
          throw new Error(t('commands.repo.fork.tagRequired'));
        }

        const forkKey = compositeKey(parseRepoRef(parent).name, tagName);
        try {
          // Validate parent exists
          const parentConfig = await configService.getRepository(parent);
          if (!parentConfig) {
            throw new Error(`Repository "${parent}" not found in context`);
          }

          // Validate fork doesn't already exist
          const existing = await configService.getRepository(forkKey);
          if (existing) {
            throw new Error(t('commands.repo.fork.alreadyExists', { name: forkKey }));
          }

          // Generate new GUID, SSH key pair, and allocate networkId; reuse parent's credential
          const repositoryGuid = randomUUID();
          const networkId = await configService.allocateNetworkId();
          const { privateKey: sshPrivateKey, publicKey: sshPublicKey } = generateSSHKeyPair();

          await configService.addRepository(forkKey, {
            repositoryGuid,
            tag: tagName,
            credential: parentConfig.credential,
            networkId,
            grandGuid: parentConfig.grandGuid ?? parentConfig.repositoryGuid,
            parentGuid: parentConfig.repositoryGuid,
            sshPrivateKey,
            sshPublicKey,
          });

          outputService.info(
            t('commands.repo.fork.registered', {
              repository: forkKey,
              guid: repositoryGuid.slice(0, 8),
              networkId,
            })
          );
          outputService.info(
            t('commands.repo.fork.starting', {
              parent,
              repository: forkKey,
              machine: options.machine,
            })
          );

          // Deploy per-repo SSH key for the fork
          await deployRepoKeyIfNeeded(forkKey, options.machine);

          // Execute fork on remote (repository param = parent, tag = fork's GUID)
          const result = await localExecutorService.execute({
            functionName: 'repository_fork',
            machineName: options.machine,
            params: {
              repository: parent,
              tag: repositoryGuid,
              network_id: networkId,
              ...(options.checkpoint ? { checkpoint: true } : {}),
            },
            debug: options.debug,
            skipRouterRestart: options.skipRouterRestart,
          });

          if (result.success) {
            outputService.success(
              t('commands.repo.fork.completed', {
                repository: forkKey,
                machine: options.machine,
              })
            );
          } else {
            await configService.removeRepository(forkKey);
            outputService.warn(t('commands.repo.fork.rollback', { repository: forkKey }));
            renderLocalExecutionFailure(result, t('commands.repo.fork.failed'));
          }
        } catch (error) {
          const exists = await configService.getRepository(forkKey);
          if (exists) {
            await configService.removeRepository(forkKey);
            outputService.warn(t('commands.repo.fork.rollback', { repository: forkKey }));
          }
          handleError(error);
        }
      }
    );

  // repo takeover <fork>
  repo
    .command('takeover <fork>')
    .summary(t('commands.repo.takeover.descriptionShort'))
    .description(t('commands.repo.takeover.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--force', t('commands.repo.takeover.forceOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        forkRef: string,
        options: { machine: string; force?: boolean; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          // 1. Get fork config — validate it's a fork (has parentGuid)
          const forkConfig = await configService.getRepository(forkRef);
          if (!forkConfig) {
            throw new Error(`Repository "${forkRef}" not found in context`);
          }
          if (!forkConfig.parentGuid) {
            throw new Error(t('commands.repo.takeover.notAFork', { name: forkRef }));
          }

          const grandGuid = forkConfig.grandGuid ?? forkConfig.parentGuid;
          const repos = await configService.listRepositories();
          const grandEntry = repos.find((r) => r.config.repositoryGuid === grandGuid);
          if (!grandEntry) throw new Error(t('commands.repo.takeover.grandNotFound', { name: forkRef }));
          await assertCommandPolicy(CMD.REPO_TAKEOVER, grandEntry.name);
          outputService.info(t('commands.repo.takeover.starting', { grand: grandEntry.name, fork: forkRef, machine: options.machine }));

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
          const backupName = `${parseRepoRef(forkRef).name}:pre-takeover-${new Date().toISOString().slice(0, 10).replaceAll('-', '')}`;
          const forkCfg = await configService.getRepository(forkRef);
          if (forkCfg) {
            await configService.addRepository(backupName, forkCfg);
            await configService.removeRepository(forkRef);
          }
          outputService.success(t('commands.repo.takeover.completed'));
          outputService.info(t('commands.repo.takeover.backupInfo', { backup: backupName }));
          outputService.info(t('commands.repo.takeover.revertHint', { backup: backupName, machine: options.machine }));
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo resize <name>
  repo
    .command('resize <name>')
    .summary(t('commands.repo.resize.descriptionShort'))
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
          await assertCommandPolicy(CMD.REPO_RESIZE, name);
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
    .summary(t('commands.repo.expand.descriptionShort'))
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
          await assertCommandPolicy(CMD.REPO_EXPAND, name);
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
    .summary(t('commands.repo.validate.descriptionShort'))
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

  // repo autostart enable [name] — per-repo if name given, all repos if omitted
  autostart
    .command('enable [name]')
    .description(t('commands.repo.autostart.enable.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string | undefined,
        options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          if (name) {
            await assertCommandPolicy(CMD.REPO_AUTOSTART_ENABLE, name);
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
          } else {
            await executeMachineFunction('repository_autostart_enable_all', options, {
              starting: t('commands.repo.autostart.enable.startingAll', {
                machine: options.machine,
              }),
              completed: t('commands.repo.autostart.enable.completedAll'),
              failed: t('commands.repo.autostart.enable.failedAll'),
            });
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo autostart disable [name] — per-repo if name given, all repos if omitted
  autostart
    .command('disable [name]')
    .description(t('commands.repo.autostart.disable.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string | undefined,
        options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          if (name) {
            await assertCommandPolicy(CMD.REPO_AUTOSTART_DISABLE, name);
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
          } else {
            await executeMachineFunction('repository_autostart_disable_all', options, {
              starting: t('commands.repo.autostart.disable.startingAll', {
                machine: options.machine,
              }),
              completed: t('commands.repo.autostart.disable.completedAll'),
              failed: t('commands.repo.autostart.disable.failedAll'),
            });
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

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
    .summary(t('commands.repo.ownership.descriptionShort'))
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
          await assertCommandPolicy(CMD.REPO_OWNERSHIP, name);
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
    .summary(t('commands.repo.template.descriptionShort'))
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
          await assertCommandPolicy(CMD.REPO_TEMPLATE, name);
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
