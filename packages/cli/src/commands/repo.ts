import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { isAgentEnvironment } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD, type CommandPath } from '../utils/command-policy.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoTarget } from '../utils/repo-target.js';
import { registerRepoBackupCommands } from './repo-backup.js';
import {
  handleDownAll,
  handleRepoList,
  handleUpAll,
  postRepoUpTasks,
  runBatchOperation,
} from './repo-batch-utils.js';
import { registerRepoBranchingCommands } from './repo-branching.js';
import { registerRepoMaintenanceCommands } from './repo-maintenance.js';
import { registerRepoCatCommand } from './repo-cat.js';
import { registerRepoCreateDeleteCommands } from './repo-create-delete.js';
import { registerRepoDiffCommand } from './repo-diff.js';
import { registerRepoSecretCommands } from './repo-secret.js';
import { registerExtendedRepoCommands } from './repo-extended.js';
import { registerRepoMigrateCommand } from './repo-migrate.js';
import { registerRepoReplicateCommands } from './repo-replicate.js';
import { registerRepoCanaryCommands } from './repo-canary.js';
import { listReplicaSets } from '../services/cluster/repo-replicate.js';
import { listCanaries } from '../services/cluster/repo-release.js';
import { registerRepoSyncCommands } from './repo-sync.js';
import { registerRepoTunnelCommand } from './repo-tunnel.js';
import { registerRepoVolumeCommands } from './repo-volume.js';

async function handleSingleRepoUp(
  name: string,
  options: {
    machine?: string;
    cluster?: string;
    skipCheckpoint?: boolean;
    tls?: boolean;
    detach?: boolean;
    dryRun?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
  }
): Promise<void> {
  await assertCommandPolicy(CMD.REPO_UP, name);
  const { machineName, kubeCluster } = await resolveRepoTarget(options);

  const params: Record<string, unknown> = {};
  if (options.skipCheckpoint) params.skip_checkpoint = true;
  if (options.tls) params.tls = true;
  if (options.detach) params.detach = true;

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
        machine: machineName,
        guid: repo?.repositoryGuid,
        params,
      },
      getOutputFormat()
    );
    return;
  }

  // deployRepoKeyIfNeeded + postRepoUpTasks (per-repo SSH key + DNS) are
  // docker-repo concepts; a cluster repo deploys through the renet dual-runtime
  // path (KUBECONFIG injected) and routes DNS via the cluster wildcard.
  if (!kubeCluster) {
    await deployRepoKeyIfNeeded(name, machineName);
  }
  await executeRepoFunction(
    'repository_up',
    name,
    machineName,
    params,
    { ...options, kubeCluster },
    {
      starting: t('commands.repo.up.starting', { repository: name, machine: machineName }),
      completed: t('commands.repo.up.completed'),
      failed: t('commands.repo.up.failed'),
    }
  );
  if (!kubeCluster) {
    await postRepoUpTasks(name, machineName);
  }
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
    `\n${t('help.examples')}\n  $ rdc repo create --name my-app -m server-1 --size 5G   ${t('help.repo.create')}\n  $ rdc repo up --name my-app -m server-1                   ${t('help.repo.up')}\n  $ rdc repo down --name my-app -m server-1                ${t('help.repo.down')}\n  $ rdc repo fork --parent my-app --tag test -m server-1   ${t('help.repo.fork')}\n`
  );

  if (isAgentEnvironment() || process.argv.includes('--help-all')) {
    repo.addHelpText('after', t('help.repo.keyConcepts'));
  }

  registerRepoCreateDeleteCommands(repo);

  registerRepoVolumeCommands(repo, executeRepoFunction, iterateAllRepos);

  // repo up [--name <name>]
  repo
    .command('up')
    .summary(t('commands.repo.up.descriptionShort'))
    .description(t('commands.repo.up.description'))
    .option('--name <name>', t('options.name'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--cluster <name>', t('commands.repo.clusterOption'))
    .option('--skip-checkpoint', t('commands.repo.up.skipCheckpointOption'))
    .option('--tls', t('commands.repo.up.tlsOption'))
    .option('--detach', t('commands.repo.up.detachOption'))
    .option('--include-forks', t('commands.repo.upAll.includeForksOption'))
    .option('--mount-only', t('commands.repo.upAll.mountOnlyOption'))
    .option('--parallel', t('commands.repo.upAll.parallelOption'))
    .option('--concurrency <n>', t('commands.repo.upAll.concurrencyOption'), '3')
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(
      async (options: {
        name?: string;
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
      }) => {
        try {
          const name = options.name;
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

  // repo down [--name <name>]
  repo
    .command('down')
    .summary(t('commands.repo.down.descriptionShort'))
    .description(t('commands.repo.down.description'))
    .option('--name <name>', t('options.name'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--cluster <name>', t('commands.repo.clusterOption'))
    .option('--unmount', t('commands.repo.down.unmountOption'))
    .option('--checkpoint', t('commands.repo.down.checkpointOption'))
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(
      async (options: {
        name?: string;
        machine?: string;
        cluster?: string;
        unmount?: boolean;
        checkpoint?: boolean;
        yes?: boolean;
        debug?: boolean;
        skipRouterRestart?: boolean;
        dryRun?: boolean;
      }) => {
        try {
          const name = options.name;
          if (name) {
            // Single-repo down
            await assertCommandPolicy(CMD.REPO_DOWN, name);
            const { machineName, kubeCluster } = await resolveRepoTarget(options);

            const params: Record<string, unknown> = {};
            if (options.unmount) params.unmount = true;
            if (options.checkpoint) params.checkpoint = true;

            if (options.dryRun) {
              const repo = await configService.getRepository(name);
              outputService.print(
                {
                  dryRun: true,
                  repository: name,
                  machine: machineName,
                  guid: repo?.repositoryGuid,
                  params,
                },
                getOutputFormat()
              );
              return;
            }

            await executeRepoFunction(
              'repository_down',
              name,
              machineName,
              params,
              { ...options, kubeCluster },
              {
                starting: t('commands.repo.down.starting', {
                  repository: name,
                  machine: machineName,
                }),
                completed: t('commands.repo.down.completed'),
                failed: t('commands.repo.down.failed'),
              }
            );
          } else {
            await handleDownAll(options);
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo status --name <name>
  repo
    .command('status')
    .description(t('commands.repo.status.description'))
    .requiredOption('--name <name>', t('options.name'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--cluster <name>', t('commands.repo.clusterOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        name: string;
        machine?: string;
        cluster?: string;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const name = options.name;
          const { machineName, kubeCluster } = await resolveRepoTarget(options);
          await executeRepoFunction(
            'repository_status',
            name,
            machineName,
            {},
            { ...options, kubeCluster },
            {
              starting: t('commands.repo.status.starting', {
                repository: name,
                machine: machineName,
              }),
              completed: t('commands.repo.status.completed'),
              failed: t('commands.repo.status.failed'),
            }
          );
          // Managed replica sets are CRUD-from-birth state (R2-F17): surface
          // any set built on this repo alongside its status.
          const replicaSets = Object.entries(await listReplicaSets()).filter(
            ([, set]) => set.repo === name
          );
          for (const [setName, set] of replicaSets) {
            const freshness = set.refreshedAt
              ? `refreshed ${set.refreshedAt}`
              : `created ${set.createdAt}`;
            outputService.info(
              `Replica set "${setName}": ${set.replicas.length} replica(s) on ` +
                `${set.replicas.map((r) => r.node).join(', ')} (${freshness})`
            );
          }
          const canaries = Object.entries(await listCanaries()).filter(
            ([, set]) => set.repo === name
          );
          for (const [setName, set] of canaries) {
            outputService.info(
              `Canary "${setName}": ${set.weight}% -> ${set.image} ` +
                `(stable service ${set.service}, undo snapshot ${set.undoSnapshot})`
            );
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo list (no positional arg — lists all repos on the machine)
  repo
    .command('list')
    .description(t('commands.repo.list.description'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--cluster <name>', t('commands.repo.clusterOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(handleRepoList);
  registerRepoCatCommand(repo);
  registerRepoDiffCommand(repo);
  registerRepoBranchingCommands(repo);
  registerRepoMaintenanceCommands(repo);
  registerExtendedRepoCommands(repo);
  registerRepoBackupCommands(repo);
  registerRepoMigrateCommand(repo);
  registerRepoReplicateCommands(repo);
  registerRepoCanaryCommands(repo);
  registerRepoSyncCommands(repo);
  registerRepoTunnelCommand(repo);
  registerRepoSecretCommands(repo);
}
