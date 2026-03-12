import { randomBytes, randomUUID } from 'node:crypto';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap, resolveGuids } from '../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { parseRepositoryListOutput } from './repo-list-parser.js';
import { registerRepoBackupCommands } from './repo-backup.js';
import { registerExtendedRepoCommands } from './repo-extended.js';
import { registerRepoSnapshotCommands } from './repo-snapshot.js';
import { registerRepoSyncCommands } from './repo-sync.js';

function generateCredential(): string {
  return randomBytes(24).toString('base64');
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
    renderLocalExecutionFailure(result, result.error ?? messages.failed);
  }
}

export function registerRepoCommands(program: Command): void {
  const repo = program.command('repo').description(t('commands.repo.description'));

  repo.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc repo create my-app -m server-1 --size 5G   ${t('help.repo.create')}
  $ rdc repo up my-app -m server-1 --mount          ${t('help.repo.up')}
  $ rdc repo down my-app -m server-1                ${t('help.repo.down')}
  $ rdc repo fork my-app my-app-test -m server-1    ${t('help.repo.fork')}
`
  );

  // repo create <name>
  repo
    .command('create <name>')
    .description(t('commands.repo.create.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--size <size>', t('commands.repo.create.sizeOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: { machine: string; size: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          // Validate doesn't already exist
          const existing = await configService.getRepository(name);
          if (existing) {
            throw new Error(t('commands.repo.create.alreadyExists', { name }));
          }

          // Generate UUID, credential, and allocate networkId
          const repositoryGuid = randomUUID();
          const credential = generateCredential();
          const networkId = await configService.allocateNetworkId();

          // Register in config.json first (so the executor can find it)
          await configService.addRepository(name, {
            repositoryGuid,
            tag: 'latest',
            credential,
            networkId,
          });

          outputService.info(
            t('commands.repo.create.registered', {
              repository: name,
              guid: repositoryGuid.slice(0, 8),
              networkId,
            })
          );
          outputService.info(
            t('commands.repo.create.starting', {
              repository: name,
              size: options.size,
              machine: options.machine,
            })
          );

          // Execute on remote
          const result = await localExecutorService.execute({
            functionName: 'repository_create',
            machineName: options.machine,
            params: { repository: name, size: options.size },
            debug: options.debug,
            skipRouterRestart: options.skipRouterRestart,
          });

          if (result.success) {
            outputService.success(t('commands.repo.create.completed'));
          } else {
            // Rollback: remove from config.json
            await configService.removeRepository(name);
            outputService.warn(t('commands.repo.create.rollback', { repository: name }));
            renderLocalExecutionFailure(result, t('commands.repo.create.failed'));
          }
        } catch (error) {
          // Rollback on unexpected error
          const exists = await configService.getRepository(name);
          if (exists) {
            await configService.removeRepository(name);
            outputService.warn(t('commands.repo.create.rollback', { repository: name }));
          }
          handleError(error);
        }
      }
    );

  // repo delete <name>
  repo
    .command('delete <name>')
    .description(t('commands.repo.delete.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(
      async (
        name: string,
        options: { machine: string; debug?: boolean; skipRouterRestart?: boolean; dryRun?: boolean }
      ) => {
        try {
          await assertCommandPolicy(CMD.REPO_DELETE, name);

          // Validate exists
          const repoConfig = await configService.getRepository(name);
          if (!repoConfig) {
            throw new Error(`Repository "${name}" not found in context`);
          }

          await configService.ensureRepositoryNetworkId(name);

          if (options.dryRun) {
            outputService.print(
              {
                dryRun: true,
                repository: name,
                machine: options.machine,
                guid: repoConfig.repositoryGuid,
              },
              getOutputFormat()
            );
            return;
          }

          outputService.info(
            t('commands.repo.delete.starting', { repository: name, machine: options.machine })
          );

          const result = await localExecutorService.execute({
            functionName: 'repository_delete',
            machineName: options.machine,
            params: { repository: name },
            debug: options.debug,
            skipRouterRestart: options.skipRouterRestart,
          });

          if (result.success) {
            await configService.archiveRepository(name);
            outputService.info(t('commands.repo.delete.archived', { repository: name }));
            outputService.info(
              t('commands.repo.delete.restoreHint', { guid: repoConfig.repositoryGuid })
            );
            outputService.success(t('commands.repo.delete.completed'));
          } else {
            renderLocalExecutionFailure(result, t('commands.repo.delete.failed'));
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo mount <name>
  repo
    .command('mount <name>')
    .description(t('commands.repo.mount.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--checkpoint', t('commands.repo.mount.checkpointOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: {
          machine: string;
          checkpoint?: boolean;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
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
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo unmount <name>
  repo
    .command('unmount <name>')
    .description(t('commands.repo.unmount.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--checkpoint', t('commands.repo.unmount.checkpointOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: {
          machine: string;
          checkpoint?: boolean;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          await assertCommandPolicy(CMD.REPO_UNMOUNT, name);

          const params: Record<string, unknown> = {};
          if (options.checkpoint) params.checkpoint = true;

          await executeRepoFunction('repository_unmount', name, options.machine, params, options, {
            starting: t('commands.repo.unmount.starting', {
              repository: name,
              machine: options.machine,
            }),
            completed: t('commands.repo.unmount.completed'),
            failed: t('commands.repo.unmount.failed'),
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo up <name>
  repo
    .command('up <name>')
    .description(t('commands.repo.up.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--mount', t('commands.repo.up.mountOption'))
    .option('--checkpoint', t('commands.repo.up.checkpointOption'))
    .option('--grand <name>', t('commands.repo.up.grandOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(
      async (
        name: string,
        options: {
          machine: string;
          mount?: boolean;
          checkpoint?: boolean;
          grand?: string;
          debug?: boolean;
          skipRouterRestart?: boolean;
          dryRun?: boolean;
        }
      ) => {
        try {
          await assertCommandPolicy(CMD.REPO_UP, name);

          const params: Record<string, unknown> = {};
          if (options.mount) params.mount = true;
          if (options.checkpoint) params.checkpoint = true;

          // Resolve grand repo friendly name → GUID
          if (options.grand) {
            const grandRepo = await configService.getRepository(options.grand);
            params.grand = grandRepo?.repositoryGuid ?? options.grand;
          }

          if (options.dryRun) {
            const repo = await configService.getRepository(name);
            outputService.print(
              {
                dryRun: true,
                repository: name,
                machine: options.machine,
                guid: repo?.repositoryGuid,
                params,
              },
              getOutputFormat()
            );
            return;
          }

          await executeRepoFunction('repository_up', name, options.machine, params, options, {
            starting: t('commands.repo.up.starting', {
              repository: name,
              machine: options.machine,
            }),
            completed: t('commands.repo.up.completed'),
            failed: t('commands.repo.up.failed'),
          });

          // Ensure per-repo wildcard DNS records (non-blocking)
          try {
            const machineConfig = await configService.getLocalMachine(options.machine);
            if (machineConfig.infra?.baseDomain) {
              const localConfig = await configService.getLocalConfig();
              const { ensureRepoDnsRecords } = await import('../services/infra-provision.js');
              await ensureRepoDnsRecords(options.machine, name, machineConfig.infra, localConfig);
            }
          } catch {
            // Non-fatal: DNS record creation failure should not block repo up
          }

          // Update cert cache after deployment (new wildcard cert may have been issued)
          try {
            const { downloadCertCache } = await import('../services/cert-cache.js');
            await downloadCertCache(options.machine, { silent: true });
          } catch {
            // Non-fatal: cert cache failure should not block repo up
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo up-all
  repo
    .command('up-all')
    .description(t('commands.repo.upAll.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--include-forks', t('commands.repo.upAll.includeForksOption'))
    .option('--mount-only', t('commands.repo.upAll.mountOnlyOption'))
    .option('--dry-run', t('commands.repo.upAll.dryRunOption'))
    .option('--parallel', t('commands.repo.upAll.parallelOption'))
    .option('--concurrency <n>', t('commands.repo.upAll.concurrencyOption'), '3')
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        machine: string;
        includeForks?: boolean;
        mountOnly?: boolean;
        dryRun?: boolean;
        parallel?: boolean;
        concurrency?: string;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const params: Record<string, unknown> = {};
          if (options.includeForks) params.include_forks = true;
          if (options.mountOnly) params.mount_only = true;
          if (options.dryRun) params.dry_run = true;
          if (options.parallel) params.parallel = true;
          if (options.parallel && options.concurrency) {
            params.concurrency = Number.parseInt(options.concurrency, 10);
          }

          outputService.info(t('commands.repo.upAll.starting', { machine: options.machine }));

          const result = await localExecutorService.execute({
            functionName: 'repository_up_all',
            machineName: options.machine,
            params,
            debug: options.debug,
            skipRouterRestart: options.skipRouterRestart,
          });

          if (result.success) {
            outputService.success(t('commands.repo.upAll.completed'));
          } else {
            renderLocalExecutionFailure(result, t('commands.repo.upAll.failed'));
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo down <name>
  repo
    .command('down <name>')
    .description(t('commands.repo.down.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--unmount', t('commands.repo.down.unmountOption'))
    .option('--grand <name>', t('commands.repo.down.grandOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(
      async (
        name: string,
        options: {
          machine: string;
          unmount?: boolean;
          grand?: string;
          debug?: boolean;
          skipRouterRestart?: boolean;
          dryRun?: boolean;
        }
      ) => {
        try {
          await assertCommandPolicy(CMD.REPO_DOWN, name);

          const params: Record<string, unknown> = {};
          if (options.unmount) params.unmount = true;

          // Resolve grand repo friendly name → GUID
          if (options.grand) {
            const grandRepo = await configService.getRepository(options.grand);
            params.grand = grandRepo?.repositoryGuid ?? options.grand;
          }

          if (options.dryRun) {
            const repo = await configService.getRepository(name);
            outputService.print(
              {
                dryRun: true,
                repository: name,
                machine: options.machine,
                guid: repo?.repositoryGuid,
                params,
              },
              getOutputFormat()
            );
            return;
          }

          await executeRepoFunction('repository_down', name, options.machine, params, options, {
            starting: t('commands.repo.down.starting', {
              repository: name,
              machine: options.machine,
            }),
            completed: t('commands.repo.down.completed'),
            failed: t('commands.repo.down.failed'),
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo status <name>
  repo
    .command('status <name>')
    .description(t('commands.repo.status.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        name: string,
        options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }
      ) => {
        try {
          await executeRepoFunction('repository_status', name, options.machine, {}, options, {
            starting: t('commands.repo.status.starting', {
              repository: name,
              machine: options.machine,
            }),
            completed: t('commands.repo.status.completed'),
            failed: t('commands.repo.status.failed'),
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo list (no positional arg — lists all repos on the machine)
  repo
    .command('list')
    .description(t('commands.repo.list.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }) => {
      try {
        outputService.info(t('commands.repo.list.starting', { machine: options.machine }));
        const format = getOutputFormat();

        const result = await localExecutorService.execute({
          functionName: 'repository_list',
          machineName: options.machine,
          params: {},
          debug: options.debug,
          captureOutput: true,
          skipRouterRestart: options.skipRouterRestart,
        });

        if (result.success) {
          const repositories = parseRepositoryListOutput(result.stdout ?? '[]');
          const guidMap = await loadGuidMap();
          const resolve = createGuidResolver(guidMap);
          const resolved = resolveGuids(repositories, resolve, 'name');
          outputService.print(resolved, format);
          outputService.success(t('commands.repo.list.completed'));
        } else {
          renderLocalExecutionFailure(
            result,
            t('commands.repo.list.failed', { error: result.error })
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  // Extended commands: fork, resize, expand, validate, autostart, ownership, template
  registerExtendedRepoCommands(repo);

  // Backup commands: push, pull, list-backups
  registerRepoBackupCommands(repo);

  // Sync commands: push-all, pull-all, upload, download, status
  registerRepoSyncCommands(repo);

  // Snapshot commands: create, list, delete
  registerRepoSnapshotCommands(repo);
}
