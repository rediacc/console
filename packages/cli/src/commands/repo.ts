import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { listCanaries } from '../services/cluster/repo-release.js';
import { listReplicaSets } from '../services/cluster/repo-replicate.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { isAgentEnvironment } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { createRepoAdminCommand } from './repo-admin.js';
import { registerRepoBackupCommands } from './repo-backup.js';
import { handleDownAll, handleRepoList, handleUpAll, postRepoUpTasks } from './repo-batch-utils.js';
import { registerRepoBranchingCommands } from './repo-branching.js';
import { registerRepoCanaryCommands } from './repo-canary.js';
import { registerRepoCatCommand } from './repo-cat.js';
import { registerRepoContainerCommands } from './repo-container.js';
import { registerRepoCreateDeleteCommands } from './repo-create-delete.js';
import { registerRepoDiffCommand } from './repo-diff.js';
import { registerExtendedRepoCommands } from './repo-extended.js';
import { registerRepoForkCommand } from './repo-fork.js';
import { registerRepoMaintenanceCommands } from './repo-maintenance.js';
import { registerRepoMigrateCommand } from './repo-migrate.js';
import { registerRepoReplicateCommands } from './repo-replicate.js';
import { registerRepoSecretCommands } from './repo-secret.js';
import { registerRepoSyncCommands } from './repo-sync.js';
import { registerRepoTunnelCommand } from './repo-tunnel.js';

interface RepoUpSingleOptions {
  /** Commander sets this false when `--no-start` is passed (mount/prepare only). */
  start?: boolean;
  skipCheckpoint?: boolean;
  tls?: boolean;
  /** Commander sets this false when `--no-wait` is passed. */
  wait?: boolean;
  dryRun?: boolean;
  debug?: boolean;
  skipRouterRestart?: boolean;
}

async function handleSingleRepoUp(ref: string, options: RepoUpSingleOptions): Promise<void> {
  const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
  await assertCommandPolicy(CMD.REPO_UP, repoKey);

  // `--no-start` folds the retired `repo mount`: LUKS open / PV generation
  // without running the Rediaccfile up() steps.
  const noStart = options.start === false;

  const params: Record<string, unknown> = {};
  if (options.skipCheckpoint) params.skip_checkpoint = true;
  if (options.tls) params.tls = true;
  if (options.wait === false) params.detach = true;

  // #39: tell renet the runtime explicitly for a cluster-placed repo. renet
  // honors `runtime` as an assertion (values kube|docker): if the caller says
  // kube but the on-datastore descriptor resolves docker, it errors instead of
  // silently falling to the docker arm (the empty-manifests bug B1 caught). The
  // runtime is derived from placement, so a k8s repo can never guess wrong.
  if (kubeCluster) params.runtime = 'kube';

  // Pass grandGuid so renet can mark forks after mount
  {
    const repo = await configService.getRepository(repoKey);
    if (repo?.grandGuid && repo.grandGuid !== repo.repositoryGuid) {
      params.grand = repo.grandGuid;
    }
  }

  if (options.dryRun) {
    const repo = await configService.getRepository(repoKey);
    outputService.print(
      {
        dryRun: true,
        repository: name,
        machine: machineName,
        guid: repo?.repositoryGuid,
        action: noStart ? 'mount' : 'up',
        params,
      },
      getOutputFormat()
    );
    return;
  }

  const functionName = noStart ? 'repository_mount' : 'repository_up';
  const messages = noStart
    ? {
        starting: t('commands.repo.mount.starting', { repository: name, machine: machineName }),
        completed: t('commands.repo.mount.completed'),
        failed: t('commands.repo.mount.failed'),
      }
    : {
        starting: t('commands.repo.up.starting', { repository: name, machine: machineName }),
        completed: t('commands.repo.up.completed'),
        failed: t('commands.repo.up.failed'),
      };

  // deployRepoKeyIfNeeded + postRepoUpTasks (per-repo SSH key + DNS) are
  // docker up() concepts: skip them for a mount-only (--no-start) run and for
  // cluster repos (which route DNS via the cluster wildcard and inject
  // KUBECONFIG through the renet dual-runtime path).
  const dockerUp = !kubeCluster && !noStart;
  if (dockerUp) {
    await deployRepoKeyIfNeeded(repoKey, machineName);
  }
  await executeRepoFunction(
    functionName,
    repoKey,
    machineName,
    params,
    { ...options, kubeCluster },
    messages
  );
  if (dockerUp) {
    await postRepoUpTasks(repoKey, machineName);
  }
}

// executeRepoFunction imported from ../utils/repo-executor.js

export function registerRepoCommands(program: Command): void {
  const repo = program
    .command('repo')
    .summary(t('commands.repo.descriptionShort'))
    .description(t('commands.repo.description'));

  repo.addHelpText(
    'after',
    `\n${t('help.examples')}\n  $ rdc repo create my-app --machine server-1 --size 5G   ${t('help.repo.create')}\n  $ rdc repo up my-app                                      ${t('help.repo.up')}\n  $ rdc repo down my-app                                    ${t('help.repo.down')}\n  $ rdc repo fork my-app --tag test                        ${t('help.repo.fork')}\n`
  );

  if (isAgentEnvironment() || process.argv.includes('--help-all')) {
    repo.addHelpText('after', t('help.repo.keyConcepts'));
  }

  registerRepoCreateDeleteCommands(repo);

  // repo up [ref]  — positional ref (single), or --all --machine <m> (batch).
  repo
    .command('up')
    .summary(t('commands.repo.up.descriptionShort'))
    .description(t('commands.repo.up.description'))
    .argument('[ref]', t('options.repoRef'))
    .option('--no-start', t('commands.repo.up.noStartOption'))
    .option('--skip-checkpoint', t('commands.repo.up.skipCheckpointOption'))
    .option('--tls', t('commands.repo.up.tlsOption'))
    .option('--no-wait', t('commands.repo.up.noWaitOption'))
    .option('--all', t('commands.repo.up.allOption'))
    .option('-m, --machine <name>', t('commands.repo.batchMachineOption'))
    .option('--include-forks', t('commands.repo.upAll.includeForksOption'))
    .option('--parallel', t('commands.repo.upAll.parallelOption'))
    .option('--concurrency <n>', t('commands.repo.upAll.concurrencyOption'), '3')
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(
      async (
        ref: string | undefined,
        options: RepoUpSingleOptions & {
          all?: boolean;
          machine?: string;
          includeForks?: boolean;
          parallel?: boolean;
          concurrency?: string;
          yes?: boolean;
        }
      ) => {
        try {
          if (ref) {
            if (options.all || options.machine) {
              throw new ValidationError(t('commands.repo.batchRefConflict', { verb: 'up' }));
            }
            await handleSingleRepoUp(ref, options);
          } else {
            if (!options.all) {
              throw new ValidationError(t('commands.repo.batchNeedRefOrAll', { verb: 'up' }));
            }
            if (!options.machine) {
              throw new ValidationError(t('commands.repo.batchAllNeedsMachine', { verb: 'up' }));
            }
            await handleUpAll(options);
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo down [ref]  — positional ref (single), or --all --machine <m> (batch).
  repo
    .command('down')
    .summary(t('commands.repo.down.descriptionShort'))
    .description(t('commands.repo.down.description'))
    .argument('[ref]', t('options.repoRef'))
    .option('--unmount', t('commands.repo.down.unmountOption'))
    .option('--checkpoint', t('commands.repo.down.checkpointOption'))
    .option('--all', t('commands.repo.down.allOption'))
    .option('-m, --machine <name>', t('commands.repo.batchMachineOption'))
    .option('--parallel', t('commands.repo.upAll.parallelOption'))
    .option('--concurrency <n>', t('commands.repo.upAll.concurrencyOption'), '3')
    .option('-y, --yes', t('commands.repo.yesOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(
      async (
        ref: string | undefined,
        options: {
          unmount?: boolean;
          checkpoint?: boolean;
          all?: boolean;
          machine?: string;
          parallel?: boolean;
          concurrency?: string;
          yes?: boolean;
          debug?: boolean;
          skipRouterRestart?: boolean;
          dryRun?: boolean;
        }
      ) => {
        try {
          if (ref) {
            if (options.all || options.machine) {
              throw new ValidationError(t('commands.repo.batchRefConflict', { verb: 'down' }));
            }
            const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
            await assertCommandPolicy(CMD.REPO_DOWN, repoKey);

            const params: Record<string, unknown> = {};
            if (options.unmount) params.unmount = true;
            if (options.checkpoint) params.checkpoint = true;

            if (options.dryRun) {
              const repo = await configService.getRepository(repoKey);
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
              repoKey,
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
            if (!options.all) {
              throw new ValidationError(t('commands.repo.batchNeedRefOrAll', { verb: 'down' }));
            }
            if (!options.machine) {
              throw new ValidationError(t('commands.repo.batchAllNeedsMachine', { verb: 'down' }));
            }
            await handleDownAll(options);
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo status <ref>
  repo
    .command('status')
    .description(t('commands.repo.status.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        ref: string,
        options: {
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          // Read-only: derive the machine, skip step 5's remote round-trip.
          const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref, {
            readOnly: true,
          });
          await executeRepoFunction(
            'repository_status',
            repoKey,
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

  // repo list — the whole config's repos, narrowed by where they LIVE. A datastore
  // is the honest unit now (a repo lives in a datastore; the machine is wherever
  // that datastore happens to be attached today), so --datastore joins --machine.
  repo
    .command('list')
    .description(t('commands.repo.list.description'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--datastore <name>', t('commands.repo.list.datastoreOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(handleRepoList);
  registerRepoCatCommand(repo);
  registerRepoForkCommand(repo);
  registerRepoDiffCommand(repo);
  registerRepoBranchingCommands(repo);
  // The `repo admin` parent is created ONCE and handed to every registrar that
  // hangs a leaf off it (§5.4's plumbing subtree spans two files).
  const admin = createRepoAdminCommand(repo, program);
  registerRepoMaintenanceCommands(repo, admin);
  registerExtendedRepoCommands(repo, admin);
  registerRepoBackupCommands(repo);
  registerRepoMigrateCommand(repo);
  registerRepoReplicateCommands(repo);
  registerRepoCanaryCommands(repo);
  registerRepoSyncCommands(repo);
  registerRepoContainerCommands(repo);
  registerRepoTunnelCommand(repo);
  registerRepoSecretCommands(repo);
}
