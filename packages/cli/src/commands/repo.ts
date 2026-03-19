import { randomBytes, randomUUID } from 'node:crypto';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { telemetryService } from '../services/telemetry.js';
import {
  generateConnectionName,
  removePersistedKeys,
  removeSSHConfigEntry,
} from '@rediacc/shared-desktop/vscode';
import { assertAgentRepoCreate, isAgentEnvironment } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD, type CommandPath } from '../utils/command-policy.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap, resolveGuids } from '../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { formatStepDuration } from '../utils/timeline.js';
import { generateSSHKeyPair } from '../utils/ssh-keygen.js';
import { registerRepoBackupCommands } from './repo-backup.js';
import {
  handleDownAll,
  handleUpAll,
  postRepoUpTasks,
  runBatchOperation,
} from './repo-batch-utils.js';

/** Clean up local VS Code SSH artifacts after a repo delete. Non-fatal. */
async function cleanupDeletedRepoSSH(machineName: string, repoName: string): Promise<void> {
  const teamName = (await configService.applyDefaults({})).team ?? '';
  const connectionName = generateConnectionName(teamName, machineName, repoName);
  removeSSHConfigEntry(connectionName);
  removePersistedKeys(teamName, machineName, repoName);
}
import { registerExtendedRepoCommands } from './repo-extended.js';
import { parseRepositoryListOutput } from './repo-list-parser.js';
import { registerRepoSyncCommands } from './repo-sync.js';
import { registerRepoVolumeCommands } from './repo-volume.js';

function generateCredential(): string {
  return randomBytes(24).toString('base64');
}

/** Log total step duration and mark timeline as rendered. */
function renderTimelineTotal(steps: { duration_ms: number }[]): void {
  const totalMs = steps.reduce((sum, s) => sum + s.duration_ms, 0);
  process.stdout.write(`\nTotal: ${formatStepDuration(totalMs)}\n`);
  outputService.setTimelineRendered();
}

/** Rollback a created repo registration if it exists. */
async function rollbackCreateRepo(name: string): Promise<void> {
  const exists = await configService.getRepository(name);
  if (exists) {
    await configService.removeRepository(name);
    outputService.warn(t('commands.repo.create.rollback', { repository: name }));
  }
}

/** Handle the repo create action body. */
async function handleRepoCreate(
  name: string,
  options: {
    machine: string;
    size: string;
    noDocker?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
  }
): Promise<void> {
  try {
    assertAgentRepoCreate(name);

    const existing = await configService.getRepository(name);
    if (existing) {
      throw new Error(t('commands.repo.create.alreadyExists', { name }));
    }

    const repositoryGuid = randomUUID();
    const credential = generateCredential();
    const networkId = await configService.allocateNetworkId();
    const { privateKey: sshPrivateKey, publicKey: sshPublicKey } = generateSSHKeyPair();

    const { compositeKey } = await import('../utils/config-schema.js');
    const repoKey = compositeKey(name, 'latest');
    await configService.addRepository(repoKey, {
      repositoryGuid,
      tag: 'latest',
      credential,
      networkId,
      sshPrivateKey,
      sshPublicKey,
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

    const result = await localExecutorService.execute({
      functionName: 'repository_create',
      machineName: options.machine,
      params: {
        repository: name,
        size: options.size,
        guid: repositoryGuid,
        network_id: networkId,
        ...(options.noDocker ? { start_docker: false } : {}),
      },
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });

    if (result.success) {
      if (result.allSteps && result.allSteps.length > 0) {
        renderTimelineTotal(result.allSteps);
      } else {
        outputService.success(t('commands.repo.create.completed'));
      }
    } else {
      await rollbackCreateRepo(name);
      renderLocalExecutionFailure(result, t('commands.repo.create.failed'));
    }
  } catch (error) {
    await rollbackCreateRepo(name);
    handleError(error);
  }
}

/** Handle post-delete success: cleanup, archiving, timeline, hints. */
async function handleDeleteSuccess(
  name: string,
  machineName: string,
  repoConfig: { repositoryGuid: string },
  archiveConfig: boolean,
  result: import('../services/local-executor.js').LocalExecuteResult
): Promise<void> {
  await cleanupDeletedRepoSSH(machineName, name).catch(() => {});

  if (archiveConfig) {
    await configService.archiveRepository(name);
    outputService.info(t('commands.repo.delete.archived', { repository: name }));
    outputService.info(t('commands.repo.delete.restoreHint', { guid: repoConfig.repositoryGuid }));
  }
  if (result.allSteps && result.allSteps.length > 0) {
    renderTimelineTotal(result.allSteps);
  } else {
    outputService.success(t('commands.repo.delete.completed'));
  }
  outputService.info(t('commands.repo.delete.configRetained', { repository: name }));
  if (!archiveConfig) {
    outputService.info(t('commands.repo.delete.archiveHint', { repository: name }));
  }
}

/** Handle the repo delete action body. */
async function handleRepoDelete(
  name: string,
  options: {
    machine: string;
    archiveConfig?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
    dryRun?: boolean;
  }
): Promise<void> {
  try {
    await assertCommandPolicy(CMD.REPO_DELETE, name);

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
          archiveConfig: !!options.archiveConfig,
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
      await handleDeleteSuccess(name, options.machine, repoConfig, !!options.archiveConfig, result);
    } else {
      renderLocalExecutionFailure(result, t('commands.repo.delete.failed'));
    }
  } catch (error) {
    handleError(error);
  }
}

async function handleSingleRepoUp(
  name: string,
  options: {
    machine: string;
    mount?: boolean;
    skipCheckpoint?: boolean;
    tls?: boolean;
    dryRun?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
  }
): Promise<void> {
  await assertCommandPolicy(CMD.REPO_UP, name);

  const params: Record<string, unknown> = {};
  if (options.mount) params.mount = true;
  if (options.skipCheckpoint) params.skip_checkpoint = true;
  if (options.tls) params.tls = true;

  // Pass grandGuid so renet can mark forks after mount
  {
    const repo = await configService.getRepository(name);
    if (repo?.grandGuid && repo.grandGuid !== repo.repositoryGuid) {
      params.grand = repo.grandGuid;
    }
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

  await deployRepoKeyIfNeeded(name, options.machine);
  await executeRepoFunction('repository_up', name, options.machine, params, options, {
    starting: t('commands.repo.up.starting', { repository: name, machine: options.machine }),
    completed: t('commands.repo.up.completed'),
    failed: t('commands.repo.up.failed'),
  });
  await postRepoUpTasks(name, options.machine);
}

/**
 * Iterate a repo function across all repos in config.
 * Runs assertCommandPolicy per repo, logs progress, and collects results.
 */
async function iterateAllRepos(
  functionName: string,
  machineName: string,
  cmd: CommandPath,
  params: Record<string, unknown>,
  options: {
    debug?: boolean;
    skipRouterRestart?: boolean;
    parallel?: boolean;
    concurrency?: string;
  },
  messages: { action: string }
): Promise<void> {
  await runBatchOperation(
    messages.action,
    machineName,
    true,
    async (name) => {
      await assertCommandPolicy(cmd, name);
      await executeRepoFunction(functionName, name, machineName, params, options, {
        starting: '',
        completed: '',
        failed: '',
      });
    },
    options
  );
}

// executeRepoFunction imported from ../utils/repo-executor.js

export function registerRepoCommands(program: Command): void {
  const repo = program
    .command('repo')
    .summary(t('commands.repo.descriptionShort'))
    .description(t('commands.repo.description'));

  repo.addHelpText(
    'after',
    `\n${t('help.examples')}\n  $ rdc repo create my-app -m server-1 --size 5G   ${t('help.repo.create')}\n  $ rdc repo up my-app -m server-1 --mount          ${t('help.repo.up')}\n  $ rdc repo down my-app -m server-1                ${t('help.repo.down')}\n  $ rdc repo fork my-app my-app-test -m server-1    ${t('help.repo.fork')}\n`
  );

  if (isAgentEnvironment() || process.argv.includes('--help-all')) {
    repo.addHelpText('after', t('help.repo.keyConcepts'));
  }

  // repo create <name>
  repo
    .command('create <name>')
    .description(t('commands.repo.create.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--size <size>', t('commands.repo.create.sizeOption'))
    .option('--no-docker', t('commands.repo.create.noDockerOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (name: string, options) => {
      await handleRepoCreate(name, options);
    });

  // repo delete <name>
  repo
    .command('delete <name>')
    .summary(t('commands.repo.delete.descriptionShort'))
    .description(t('commands.repo.delete.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--archive-config', t('commands.repo.delete.archiveOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(async (name: string, options) => {
      await handleRepoDelete(name, options);
    });

  registerRepoVolumeCommands(repo, executeRepoFunction, iterateAllRepos);

  // repo up [name]
  repo
    .command('up [name]')
    .summary(t('commands.repo.up.descriptionShort'))
    .description(t('commands.repo.up.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--mount', t('commands.repo.up.mountOption'))
    .option('--skip-checkpoint', t('commands.repo.up.skipCheckpointOption'))
    .option('--tls', t('commands.repo.up.tlsOption'))
    .option('--include-forks', t('commands.repo.upAll.includeForksOption'))
    .option('--mount-only', t('commands.repo.upAll.mountOnlyOption'))
    .option('--parallel', t('commands.repo.upAll.parallelOption'))
    .option('--concurrency <n>', t('commands.repo.upAll.concurrencyOption'), '3')
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(
      async (
        name: string | undefined,
        options: {
          machine: string;
          mount?: boolean;
          skipCheckpoint?: boolean;
          tls?: boolean;
          includeForks?: boolean;
          mountOnly?: boolean;
          parallel?: boolean;
          concurrency?: string;
          yes?: boolean;
          debug?: boolean;
          skipRouterRestart?: boolean;
          dryRun?: boolean;
        }
      ) => {
        try {
          if (name) {
            await handleSingleRepoUp(name, options);
          } else {
            await handleUpAll(options);
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo down [name]
  repo
    .command('down [name]')
    .summary(t('commands.repo.down.descriptionShort'))
    .description(t('commands.repo.down.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--unmount', t('commands.repo.down.unmountOption'))
    .option('--checkpoint', t('commands.repo.down.checkpointOption'))
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(
      async (
        name: string | undefined,
        options: {
          machine: string;
          unmount?: boolean;
          checkpoint?: boolean;
          yes?: boolean;
          debug?: boolean;
          skipRouterRestart?: boolean;
          dryRun?: boolean;
        }
      ) => {
        try {
          if (name) {
            // Single-repo down
            await assertCommandPolicy(CMD.REPO_DOWN, name);

            const params: Record<string, unknown> = {};
            if (options.unmount) params.unmount = true;
            if (options.checkpoint) params.checkpoint = true;

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
          } else {
            await handleDownAll(options);
          }
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
          const resolve = createGuidResolver(await loadGuidMap());
          const resolved = resolveGuids(repositories, resolve, 'name');
          if (format === 'table') {
            const { parseRepoRef } = await import('../utils/config-schema.js');
            // Build GUID → config lookup from config to determine fork/grand + tag
            const repoConfigs = await configService.listRepositories().catch((err: unknown) => {
              telemetryService.trackError(err, { operation: 'repo.list_repositories' });
              return [];
            });
            const configLookup = new Map<string, { grandGuid?: string; tag?: string }>();
            for (const rc of repoConfigs) {
              configLookup.set(rc.config.repositoryGuid, {
                grandGuid: rc.config.grandGuid,
                tag: rc.config.tag,
              });
            }
            const compact = resolved.map((r) => {
              const guid = (r.guid ?? r.name) as string;
              const cfg = configLookup.get(guid);
              const resolvedName = r.name as string;
              const { name: baseName, tag: parsedTag } = parseRepoRef(resolvedName);
              return {
                name: baseName,
                tag: cfg?.tag ?? parsedTag,
                type: cfg?.grandGuid ? 'fork' : 'grand',
                size: r.size_human,
                mounted: r.mounted ? 'Yes' : 'No',
                docker: r.docker_running ? 'Yes' : 'No',
                containers: r.container_count,
                services: r.service_count,
                modified: r.modified_human,
              };
            });
            outputService.print(compact, format);
          } else {
            outputService.print(resolved, format);
          }
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
  registerExtendedRepoCommands(repo);
  registerRepoBackupCommands(repo);
  registerRepoSyncCommands(repo);
}
