import { randomBytes, randomUUID } from 'node:crypto';
import {
  generateConnectionName,
  removePersistedKeys,
  removeSSHConfigEntry,
} from '../remote/vscode/index.js';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { clusterMountRemotePath } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { localExecutorService } from '../services/executor/local-executor.js';
import { outputService } from '../services/core/output.js';
import { assertAgentRepoCreate } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { resolveRepoTarget } from '../utils/repo-target.js';
import { generateSSHKeyPair } from '../utils/ssh-keygen.js';
import { formatStepDuration } from '../utils/timeline.js';
import { assertMachineExists } from './_validate.js';

/** Clean up local VS Code SSH artifacts after a repo delete. Non-fatal. */
async function cleanupDeletedRepoSSH(machineName: string, repoName: string): Promise<void> {
  const teamName = (await configService.applyDefaults({})).team ?? '';
  const connectionName = generateConnectionName(teamName, machineName, repoName);
  removeSSHConfigEntry(connectionName);
  removePersistedKeys(teamName, machineName, repoName);
}

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

/** Render the create result: timeline/success on success, rollback + failure otherwise. */
async function renderCreateResult(
  name: string,
  result: import('../services/executor/local-executor.js').LocalExecuteResult
): Promise<void> {
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
}

/**
 * Handle `repo create --cluster <name>`: a Kubernetes repo is namespace
 * `<repo>` plus its storage in the cluster (design D14). Resolves the cluster's
 * control node and dispatches kube_namespace_create with KUBECONFIG injected
 * (kubeCluster routes through the wave-1 target funnel).
 */
async function handleRepoCreateCluster(
  name: string,
  options: { cluster: string; size: string; debug?: boolean }
): Promise<void> {
  try {
    assertAgentRepoCreate(name);
    const { machineName, kubeCluster } = await resolveRepoTarget({ cluster: options.cluster });
    const cluster = kubeCluster ?? options.cluster;
    outputService.info(
      t('commands.repo.create.clusterResolved', {
        repository: name,
        cluster,
        controlNode: machineName,
      })
    );
    const result = await localExecutorService.execute({
      functionName: 'kube_namespace_create',
      machineName,
      kubeCluster,
      params: { namespace: name, cluster, mount_path: clusterMountRemotePath(cluster) },
      debug: options.debug,
    });
    if (result.success) {
      outputService.success(
        t('commands.repo.clusterDone', { verb: 'Created', repository: name, cluster })
      );
    } else {
      renderLocalExecutionFailure(result, t('commands.repo.create.failed'));
    }
  } catch (error) {
    handleError(error);
  }
}

/** Handle the repo create action body. */
async function handleRepoCreate(
  name: string,
  options: {
    machine?: string;
    cluster?: string;
    size: string;
    noDocker?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
  }
): Promise<void> {
  if (options.cluster) {
    return handleRepoCreateCluster(name, {
      cluster: options.cluster,
      size: options.size,
      debug: options.debug,
    });
  }
  if (!options.machine) {
    handleError(new Error(t('errors.cluster.targetRequired')));
    return;
  }
  const machineTarget = options.machine;
  // Rollback must only ever remove the row THIS invocation registered —
  // a catch-all rollback would delete a pre-existing repo's config row
  // (credential included) when create fails with "already exists".
  let registered = false;
  try {
    assertAgentRepoCreate(name);

    await assertMachineExists(machineTarget);

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
    registered = true;

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
        machine: machineTarget,
      })
    );

    const result = await localExecutorService.execute({
      functionName: 'repository_create',
      machineName: machineTarget,
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

    await renderCreateResult(name, result);
  } catch (error) {
    if (registered) {
      await rollbackCreateRepo(name);
    }
    handleError(error);
  }
}

/** Handle post-delete success: cleanup, archiving, timeline, hints. */
async function handleDeleteSuccess(
  name: string,
  machineName: string,
  repoConfig: { repositoryGuid: string },
  archiveConfig: boolean,
  result: import('../services/executor/local-executor.js').LocalExecuteResult,
  originalRef?: string
): Promise<void> {
  await cleanupDeletedRepoSSH(machineName, name).catch(() => {});
  // When the user invoked `repo delete --name app` and the resolver returned
  // `app:latest`, VS Code SSH artifacts persisted under the original bare
  // alias survive the cleanup above. Sweep that name too.
  if (originalRef && originalRef !== name) {
    await cleanupDeletedRepoSSH(machineName, originalRef).catch(() => {});
  }

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
  outputService.info(t('commands.repo.delete.cloudBackupHint', { machine: machineName }));
}

/** Handle `repo delete --cluster <name>`: dispatch kube_namespace_delete on the cluster's control node (see handleRepoCreateCluster). */
async function handleRepoDeleteCluster(name: string, options: { cluster: string }): Promise<void> {
  try {
    const { machineName, kubeCluster } = await resolveRepoTarget({ cluster: options.cluster });
    const cluster = kubeCluster ?? options.cluster;
    outputService.info(
      t('commands.repo.create.clusterResolved', {
        repository: name,
        cluster,
        controlNode: machineName,
      })
    );
    const result = await localExecutorService.execute({
      functionName: 'kube_namespace_delete',
      machineName,
      kubeCluster,
      params: { namespace: name, cluster, mount_path: clusterMountRemotePath(cluster) },
    });
    if (result.success) {
      outputService.success(
        t('commands.repo.clusterDone', { verb: 'Deleted', repository: name, cluster })
      );
    } else {
      renderLocalExecutionFailure(result, t('commands.repo.delete.failed'));
    }
  } catch (error) {
    handleError(error);
  }
}

/** Handle the repo delete action body. */
async function handleRepoDelete(
  name: string,
  options: {
    machine?: string;
    cluster?: string;
    archiveConfig?: boolean;
    yes?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
    dryRun?: boolean;
  }
): Promise<void> {
  if (options.cluster) {
    return handleRepoDeleteCluster(name, { cluster: options.cluster });
  }
  if (!options.machine) {
    handleError(new Error(t('errors.cluster.targetRequired')));
    return;
  }
  const machineTarget = options.machine;
  try {
    const { key: target, config: repoConfig } = await configService.resolveDestructiveTarget(name);
    await assertCommandPolicy(CMD.REPO_DELETE, target);

    await configService.ensureRepositoryNetworkId(target);

    if (options.dryRun) {
      outputService.print(
        {
          dryRun: true,
          repository: target,
          machine: machineTarget,
          guid: repoConfig.repositoryGuid,
          archiveConfig: !!options.archiveConfig,
        },
        getOutputFormat()
      );
      return;
    }

    if (!options.yes) {
      const { askConfirm } = await import('../utils/prompt.js');
      const confirmed = await askConfirm(
        t('commands.repo.delete.confirm', { repository: target, machine: machineTarget })
      );
      if (!confirmed) {
        outputService.info(t('status.cancelled'));
        return;
      }
    }

    outputService.info(
      t('commands.repo.delete.starting', { repository: target, machine: machineTarget })
    );

    const result = await localExecutorService.execute({
      functionName: 'repository_delete',
      machineName: machineTarget,
      params: { repository: target },
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });

    if (result.success) {
      await handleDeleteSuccess(
        target,
        machineTarget,
        repoConfig,
        !!options.archiveConfig,
        result,
        name
      );
    } else {
      renderLocalExecutionFailure(result, t('commands.repo.delete.failed'));
    }
  } catch (error) {
    handleError(error);
  }
}

/** Register `repo create` and `repo delete` subcommands. */
export function registerRepoCreateDeleteCommands(repo: Command): void {
  // repo create --name <name>
  repo
    .command('create')
    .description(t('commands.repo.create.description'))
    .requiredOption('--name <name>', t('options.name'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--cluster <name>', t('commands.repo.clusterOption'))
    .requiredOption('--size <size>', t('commands.repo.create.sizeOption'))
    .option('--no-docker', t('commands.repo.create.noDockerOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options) => {
      const name = options.name;
      await handleRepoCreate(name, options);
    });

  // repo delete --name <name>
  const deleteCmd = repo
    .command('delete')
    .summary(t('commands.repo.delete.descriptionShort'))
    .description(t('commands.repo.delete.description'))
    .requiredOption('--name <name>', t('options.name'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--cluster <name>', t('commands.repo.clusterOption'))
    .option('--archive-config', t('commands.repo.delete.archiveOption'))
    .option('-y, --yes', t('options.yes'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(async (options) => {
      const name = options.name;
      await handleRepoDelete(name, options);
    });
  deleteCmd.addHelpText('after', t('commands.repo.delete.examples'));
}
