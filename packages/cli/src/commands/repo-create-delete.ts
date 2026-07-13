import { randomBytes, randomUUID } from 'node:crypto';
import type { Placement } from '@rediacc/shared/config-schema';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import {
  generateConnectionName,
  removePersistedKeys,
  removeSSHConfigEntry,
} from '../remote/vscode/index.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { assertAgentRepoCreate } from '../utils/agent-guard.js';
import { notFound, stateMismatch } from '../utils/cli-exit-error.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { resolveRepoRef } from '../utils/repo-target.js';
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
  result: import('../services/executor/local-executor.js').ExecuteResult
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

/** A resolved named-datastore placement: where the repo's data lives + how to reach it. */
interface DatastorePlacement {
  /** The machine that attaches the datastore (the SSH exec target). */
  machine: string;
  /** The datastore's cluster backref; set => a kubernetes-world datastore. */
  kubeCluster?: string;
  /** Remote mount path of the datastore on its machine. */
  mountPath: string;
}

/**
 * Resolve a named datastore to its attach machine and world (spec 03 §5.4 / #38).
 * A datastore with a cluster backref is the kubernetes DATA datastore a cluster
 * repo lands on (the one `repo replicate` can fork); without a backref it is a
 * docker-tiering datastore. Exit 5 if the datastore is unknown, exit 12 if it is
 * not attached to any machine.
 */
async function resolveDatastorePlacement(datastore: string): Promise<DatastorePlacement> {
  const config = await configService.getCurrent();
  const ds = config?.resources?.datastores?.[datastore];
  if (!ds) {
    throw notFound(t('commands.repo.create.datastoreNotFound', { datastore }));
  }
  // `ds` above proves the chain did not short-circuit, so `config` is non-null here.
  const attachedTo = config.state?.datastores?.[datastore]?.attachedTo;
  if (!attachedTo) {
    throw stateMismatch(t('commands.repo.create.datastoreNotAttached', { datastore }));
  }
  return {
    machine: attachedTo,
    ...(ds.cluster !== undefined && { kubeCluster: ds.cluster }),
    mountPath: namedDatastoreMount(datastore),
  };
}

/**
 * Register the birth record of a new repo, carrying its declared placement
 * (spec 03 §2.3: the R2-F1 tagged union derived-machine ops resolve through).
 * Throws if a repo of this name already exists.
 */
async function registerNewRepo(
  name: string,
  placement: Placement,
  extra: { sshPrivateKey?: string; sshPublicKey?: string }
): Promise<{ repositoryGuid: string; networkId: number }> {
  const existing = await configService.getRepository(name);
  if (existing) {
    throw new Error(t('commands.repo.create.alreadyExists', { name }));
  }
  const repositoryGuid = randomUUID();
  const networkId = await configService.allocateNetworkId();
  const { compositeKey } = await import('../utils/config-schema.js');
  await configService.addRepository(compositeKey(name, 'latest'), {
    repositoryGuid,
    tag: 'latest',
    credential: generateCredential(),
    networkId,
    placement,
    ...extra,
  });
  return { repositoryGuid, networkId };
}

/** `repo create <name> --machine <m>`: a docker repo on the machine's default datastore. */
async function handleRepoCreateOnMachine(
  name: string,
  options: {
    machine: string;
    size?: string;
    noDocker?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
  }
): Promise<void> {
  let registered = false;
  try {
    assertAgentRepoCreate(name);
    await assertMachineExists(options.machine);

    // R2-F12: a repo on a cluster machine needs a datastore, not --machine.
    const config = await configService.getCurrent();
    const membership = config?.resources?.machines?.[options.machine]?.cluster;
    if (membership) {
      throw new ValidationError(
        t('commands.repo.create.machineInCluster', {
          machine: options.machine,
          cluster: membership.cluster,
        })
      );
    }
    if (!options.size) {
      throw new ValidationError(t('commands.repo.create.sizeRequiredDocker'));
    }

    const { privateKey: sshPrivateKey, publicKey: sshPublicKey } = generateSSHKeyPair();
    const { repositoryGuid, networkId } = await registerNewRepo(
      name,
      { machine: options.machine },
      { sshPrivateKey, sshPublicKey }
    );
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
        machine: options.machine,
      })
    );

    const result = await getExecutor().execute({
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

    await renderCreateResult(name, result);
  } catch (error) {
    if (registered) await rollbackCreateRepo(name);
    handleError(error);
  }
}

/**
 * `repo create <name> --datastore <d>`: a repo on a NAMED datastore — docker
 * tiering (backref unset) or the kubernetes cluster form (backref set). The #38
 * fix: a cluster repo lands on its DATA datastore, the one `repo replicate` forks.
 */
async function handleRepoCreateOnDatastore(
  name: string,
  options: {
    datastore: string;
    size?: string;
    noDocker?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
  }
): Promise<void> {
  let registered = false;
  try {
    assertAgentRepoCreate(name);
    const placement = await resolveDatastorePlacement(options.datastore);
    const isK8s = placement.kubeCluster !== undefined;

    if (isK8s && options.size) {
      throw new ValidationError(t('commands.repo.create.sizeOnK8s'));
    }
    if (!isK8s && !options.size) {
      throw new ValidationError(t('commands.repo.create.sizeRequiredDocker'));
    }

    const { repositoryGuid, networkId } = await registerNewRepo(
      name,
      { datastore: options.datastore },
      {}
    );
    registered = true;

    outputService.info(
      t('commands.repo.create.registered', {
        repository: name,
        guid: repositoryGuid.slice(0, 8),
        networkId,
      })
    );
    outputService.info(
      t('commands.repo.create.startingDatastore', {
        repository: name,
        datastore: options.datastore,
        machine: placement.machine,
      })
    );

    const result = await getExecutor().execute({
      functionName: 'repository_create',
      machineName: placement.machine,
      ...(placement.kubeCluster !== undefined && { kubeCluster: placement.kubeCluster }),
      // #74: DISPATCH AGAINST THE DATASTORE WE JUST RECORDED. We resolved this
      // placement above and then said nothing about it, so renet fell back to the
      // machine's default docker datastore: the placement written to the config and
      // the placement sent to the machine were two different things, silently. This
      // is the executor's vault channel (ExecuteOptions.datastore), NOT a param —
      // `repository_create` reads its datastore from the machine vault.
      datastore: placement.mountPath,
      params: {
        repository: name,
        guid: repositoryGuid,
        network_id: networkId,
        mount_path: placement.mountPath,
        // #67: DECLARE the runtime for a cluster-placed repo, exactly as `repo up`
        // does (the #39 assertion channel: renet honors `runtime` as an assertion and
        // errors on a disagreement rather than silently falling to the docker arm).
        //
        // Without it, this dispatch was incoherent with the validation eight lines
        // above: the CLI knew the repo was kubernetes-placed, refused `--size` on
        // exactly that ground, and then sent the DOCKER create — which requires a
        // size. With --size the CLI refused; without it renet refused. No value of
        // the flag worked, and `repo create` was unusable on the cluster path.
        // The declaration is what lets renet size the volumes from the PVCs instead.
        ...(isK8s ? { runtime: 'kube', cluster: placement.kubeCluster, start_docker: false } : {}),
        ...(options.size ? { size: options.size } : {}),
        ...(options.noDocker && !isK8s ? { start_docker: false } : {}),
      },
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });

    await renderCreateResult(name, result);
  } catch (error) {
    if (registered) await rollbackCreateRepo(name);
    handleError(error);
  }
}

/**
 * Handle the repo create action body: the R2-F1 placement union (spec 03 §5.4).
 * Exactly one of `--machine` (docker, implicit default datastore) or
 * `--datastore` (named datastore — docker tiering, or the only kubernetes form).
 */
export async function handleRepoCreate(
  name: string,
  options: {
    machine?: string;
    datastore?: string;
    size?: string;
    noDocker?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
  }
): Promise<void> {
  const hasMachine = !!options.machine;
  const hasDatastore = !!options.datastore;
  if (hasMachine === hasDatastore) {
    // Both, or neither — the same teaching error either way (spec 02 §7).
    handleError(new ValidationError(t('commands.repo.create.placementRequired')));
    return;
  }
  if (options.machine) {
    return handleRepoCreateOnMachine(name, {
      machine: options.machine,
      size: options.size,
      noDocker: options.noDocker,
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });
  }
  return handleRepoCreateOnDatastore(name, {
    datastore: options.datastore as string,
    size: options.size,
    noDocker: options.noDocker,
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
  });
}

/** Handle post-delete success: cleanup, archiving, timeline, hints. */
async function handleDeleteSuccess(
  name: string,
  machineName: string,
  repoConfig: { repositoryGuid: string },
  archiveConfig: boolean,
  result: import('../services/executor/local-executor.js').ExecuteResult,
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

/**
 * Handle the repo delete action body (spec 03 §5.4): derive the machine (and the
 * kube arm) from the ref's placement, then resolve the STRICT destructive key so
 * a bare ambiguous ref fails closed (#495) rather than deleting the wrong repo.
 */
async function handleRepoDelete(
  ref: string,
  options: {
    archiveConfig?: boolean;
    yes?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
    dryRun?: boolean;
  }
): Promise<void> {
  try {
    const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
    const { key: target, config: repoConfig } =
      await configService.resolveDestructiveTarget(repoKey);
    await assertCommandPolicy(CMD.REPO_DELETE, target);

    await configService.ensureRepositoryNetworkId(target);

    if (options.dryRun) {
      outputService.print(
        {
          dryRun: true,
          repository: target,
          machine: machineName,
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
        t('commands.repo.delete.confirm', { repository: target, machine: machineName })
      );
      if (!confirmed) {
        outputService.info(t('status.cancelled'));
        return;
      }
    }

    outputService.info(
      t('commands.repo.delete.starting', { repository: target, machine: machineName })
    );

    const result = await getExecutor().execute({
      functionName: 'repository_delete',
      machineName,
      ...(kubeCluster !== undefined && { kubeCluster }),
      params: { repository: target },
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });

    if (result.success) {
      await handleDeleteSuccess(
        target,
        machineName,
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
  // repo create <name> --machine <m> | --datastore <d>  (placement union, spec §5.4)
  repo
    .command('create')
    .description(t('commands.repo.create.description'))
    .argument('<name>', t('options.name'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--datastore <name>', t('commands.repo.create.datastoreOption'))
    .option('--size <size>', t('commands.repo.create.sizeOption'))
    .option('--no-docker', t('commands.repo.create.noDockerOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (name: string, options) => {
      await handleRepoCreate(name, options);
    });

  // repo delete <ref>
  const deleteCmd = repo
    .command('delete')
    .summary(t('commands.repo.delete.descriptionShort'))
    .description(t('commands.repo.delete.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--archive-config', t('commands.repo.delete.archiveOption'))
    .option('-y, --yes', t('options.yes'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(async (ref: string, options) => {
      await handleRepoDelete(ref, options);
    });
  deleteCmd.addHelpText('after', t('commands.repo.delete.examples'));
}
