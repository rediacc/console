import { randomBytes, randomUUID } from 'node:crypto';
import type { Placement } from '@rediacc/shared/config-schema';
import type { Command } from 'commander';
import { findUnreachable, RemoteWriteFailedClosedError } from '../adapters/remote-config-errors.js';
import { t } from '../i18n/index.js';
import {
  generateConnectionName,
  removePersistedKeys,
  removeSSHConfigEntry,
} from '../remote/vscode/index.js';
import { reconcileBackupSchedules } from '../services/backup/repo-change-hook.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import {
  allocateNetworkIdWithFloor,
  ensureRepositoryNetworkId,
  type NetworkIdTarget,
  runWithNetworkIdRetry,
  targetFloor,
} from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import { writeStdout } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { ERROR_CODES } from '../types/errors.js';
import { assertAgentRepoCreate } from '../utils/agent-guard.js';
import { CliExitError, notFound, stateMismatch } from '../utils/cli-exit-error.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { generateSSHKeyPair } from '../utils/ssh-keygen.js';
import { formatStepDuration } from '../utils/timeline.js';
import { assertMachineExists } from './_validate.js';
import {
  type DeletedRepoConfig,
  isFork,
  settleCloudBackups,
  settleConfigEntry,
  settleRepoLicense,
} from './repo-delete-settle.js';

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
  writeStdout(`\nTotal: ${formatStepDuration(totalMs)}\n`);
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
  machine: string,
  result: import('../services/executor/local-executor.js').ExecuteResult
): Promise<void> {
  if (result.success) {
    if (result.allSteps && result.allSteps.length > 0) {
      renderTimelineTotal(result.allSteps);
    } else {
      outputService.success(t('commands.repo.create.completed'));
    }
    await reconcileBackupSchedules(machine);
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
export async function registerNewRepo(
  name: string,
  placement: Placement,
  extra: { sshPrivateKey?: string; sshPublicKey?: string },
  target: NetworkIdTarget
): Promise<{ repositoryGuid: string; networkId: number }> {
  // Validate before ANY write: allocateNetworkId persists, and a refused name must leave the config untouched.
  const { assertResourceName, compositeKey } = await import('../utils/config-schema.js');
  assertResourceName(name);
  const existing = await configService.getRepository(name);
  if (existing) {
    throw new Error(t('commands.repo.create.alreadyExists', { name }));
  }
  const repositoryGuid = randomUUID();
  // D3(a): the floor is the target machine's used set, so a lagging counter skips IDs other devices placed there.
  const networkId = await allocateNetworkIdWithFloor(await targetFloor(target));
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
    await assertAgentRepoCreate(name, { machine: options.machine });
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
    const target: NetworkIdTarget = { machine: options.machine };
    const { repositoryGuid, networkId } = await registerNewRepo(
      name,
      { machine: options.machine },
      { sshPrivateKey, sshPublicKey },
      target
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

    const result = await runWithNetworkIdRetry({
      repoKey: name,
      target,
      networkId,
      run: (id) =>
        getExecutor().execute({
          functionName: 'repository_create',
          machineName: options.machine,
          params: {
            repository: name,
            size: options.size,
            guid: repositoryGuid,
            network_id: id,
            ...(options.noDocker ? { start_docker: false } : {}),
          },
          debug: options.debug,
          skipRouterRestart: options.skipRouterRestart,
        }),
    });

    await renderCreateResult(name, options.machine, result);
  } catch (error) {
    if (registered) await rollbackCreateRepo(name);
    handleError(error);
  }
}

/**
 * `repo create <name> --datastore <d>`: a repo on a NAMED datastore, docker
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
    await assertAgentRepoCreate(name, { datastore: options.datastore });
    const placement = await resolveDatastorePlacement(options.datastore);
    const isK8s = placement.kubeCluster !== undefined;

    if (isK8s && options.size) {
      throw new ValidationError(t('commands.repo.create.sizeOnK8s'));
    }
    if (!isK8s && !options.size) {
      throw new ValidationError(t('commands.repo.create.sizeRequiredDocker'));
    }

    const target: NetworkIdTarget = {
      machine: placement.machine,
      datastore: placement.mountPath,
      ...(placement.kubeCluster !== undefined && { kubeCluster: placement.kubeCluster }),
    };
    const { repositoryGuid, networkId } = await registerNewRepo(
      name,
      { datastore: options.datastore },
      {},
      target
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

    const result = await runWithNetworkIdRetry({
      repoKey: name,
      target,
      networkId,
      run: (id) =>
        getExecutor().execute({
          functionName: 'repository_create',
          machineName: placement.machine,
          ...(placement.kubeCluster !== undefined && { kubeCluster: placement.kubeCluster }),
          // #74: DISPATCH AGAINST THE DATASTORE WE JUST RECORDED. We resolved this placement above and then said nothing about it, so renet fell back to the machine's default docker datastore: the placement written to the config and the placement sent to the machine were two different things, silently. This is the executor's vault channel (ExecuteOptions.datastore), NOT a param ,
          // `repository_create` reads its datastore from the machine vault.
          datastore: placement.mountPath,
          params: {
            repository: name,
            guid: repositoryGuid,
            network_id: id,
            mount_path: placement.mountPath,
            // #67: DECLARE the runtime for a cluster-placed repo, exactly as `repo up` does (the #39 assertion channel: renet honors `runtime` as an assertion and errors on a disagreement rather than silently falling to the docker arm).
            //
            // Without it, this dispatch was incoherent with the validation eight lines above: the CLI knew the repo was kubernetes-placed, refused `--size` on exactly that ground, and then sent the DOCKER create, which requires a
            // size. With --size the CLI refused; without it renet refused. No value of
            // the flag worked, and `repo create` was unusable on the cluster path. The declaration is what lets renet size the volumes from the PVCs instead.
            ...(isK8s
              ? { runtime: 'kube', cluster: placement.kubeCluster, start_docker: false }
              : {}),
            ...(options.size ? { size: options.size } : {}),
            ...(options.noDocker && !isK8s ? { start_docker: false } : {}),
          },
          debug: options.debug,
          skipRouterRestart: options.skipRouterRestart,
        }),
    });

    await renderCreateResult(name, placement.machine, result);
  } catch (error) {
    if (registered) await rollbackCreateRepo(name);
    handleError(error);
  }
}

/**
 * Handle the repo create action body: the R2-F1 placement union (spec 03 §5.4).
 * Exactly one of `--machine` (docker, implicit default datastore) or
 * `--datastore` (named datastore, docker tiering, or the only kubernetes form).
 */
export function handleRepoCreate(
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
    // Both, or neither, the same teaching error either way (spec 02 §7).
    handleError(new ValidationError(t('commands.repo.create.placementRequired')));
    return Promise.resolve();
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
/** Handle post-delete success: cleanup, timeline, config-entry settlement, hints. */
export async function handleDeleteSuccess(
  name: string,
  machineName: string,
  repoConfig: DeletedRepoConfig,
  archiveConfig: boolean,
  result: import('../services/executor/local-executor.js').ExecuteResult,
  originalRef?: string,
  purgeBackups = false
): Promise<void> {
  await cleanupDeletedRepoSSH(machineName, name).catch(() => {});
  // When the user invoked `repo delete --name app` and the resolver returned `app:latest`, VS Code SSH artifacts persisted under the original bare alias survive the cleanup above. Sweep that name too.
  if (originalRef && originalRef !== name) {
    await cleanupDeletedRepoSSH(machineName, originalRef).catch(() => {});
  }

  if (result.allSteps && result.allSteps.length > 0) {
    renderTimelineTotal(result.allSteps);
  } else {
    outputService.success(t('commands.repo.delete.completed'));
  }
  // ORDER: machine first, config second, and the pair is made safe by retry instead of by swapping. Config-first would risk the worse half-state: a config with no entry for an image that still exists on the machine (an orphaned encrypted volume nothing can name or reach). Machine-first leaves at worst an entry whose image is gone, and the retry converges: the presence probe in resolveRepoRef reports the image absent, the machine dispatch is skipped, and this settle step runs again.
  // The steps after this save (backup schedule reconcile, cloud backup settle, license settle) are deliberately DEFERRED to the retry rather than run before the throw: all three read the config entry this save settles (retention, archive and license state hang off it), so running them against an unsettled entry would act on stale state. The retry converges to this same function with the image absent, and runs them then.
  try {
    await settleConfigEntry(name, machineName, repoConfig, archiveConfig);
  } catch (error) {
    const retry = [
      'rdc repo delete',
      name,
      archiveConfig && '--archive-config',
      purgeBackups && '--purge-backups',
      '-y',
    ]
      .filter(Boolean)
      .join(' ');
    const networkDown = error instanceof RemoteWriteFailedClosedError || !!findUnreachable(error);
    throw new CliExitError(
      networkDown ? ERROR_CODES.NETWORK_ERROR : ERROR_CODES.GENERAL_ERROR,
      t('commands.repo.delete.configSaveFailed', {
        repository: name,
        machine: machineName,
        reason: error instanceof Error ? error.message : String(error),
        command: retry,
      }),
      { retryable: true }
    );
  }
  await reconcileBackupSchedules(machineName);
  await settleCloudBackups(name, repoConfig, purgeBackups);
  await settleRepoLicense(name, repoConfig);
  // --purge-backups just freed them: the hint that they outlive the repository would contradict that.
  if (!purgeBackups) {
    outputService.info(t('commands.repo.delete.cloudBackupHint', { machine: machineName }));
  }
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
    purgeBackups?: boolean;
    yes?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
    dryRun?: boolean;
  }
): Promise<void> {
  try {
    // Converge-to-absent (#45/#95): delete RETAINS the config family by design ("may exist on other machines"), so a delete whose image is already gone is a legitimate sequence, resolve with absentOk and skip the machine dispatch on a definite absence instead of refusing with exit 12.
    const { name, repoKey, machineName, kubeCluster, imageAbsent } = await resolveRepoRef(ref, {
      absentOk: true,
    });
    const { key: target, config: repoConfig } =
      await configService.resolveDestructiveTarget(repoKey);
    await assertCommandPolicy(CMD.REPO_DELETE, target);
    // Refused before anything is deleted: a fork's lineage is its parent's, and a purge would take the parent's backups with it.
    if (options.purgeBackups && isFork(repoConfig)) {
      throw new ValidationError(t('commands.repo.delete.purgeForkRefused', { repository: target }));
    }

    // A definite absence skips the machine dispatch, so the ID is only needed when the image is there.
    if (!imageAbsent) {
      const datastore = await recordedDatastoreMount(target);
      await ensureRepositoryNetworkId(target, {
        machine: machineName,
        ...(datastore !== undefined && { datastore }),
        ...(kubeCluster !== undefined && { kubeCluster }),
      });
    }

    if (options.dryRun) {
      outputService.print(
        {
          dryRun: true,
          repository: target,
          machine: machineName,
          guid: repoConfig.repositoryGuid,
          archiveConfig: !!options.archiveConfig,
          purgeBackups: !!options.purgeBackups,
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

    // Definite machine-arm absence: the image is already gone, converge straight to the config-side completion (retention/archive messaging).
    const result: import('../services/executor/local-executor.js').ExecuteResult = imageAbsent
      ? { success: true, stdout: '', stderr: '', exitCode: 0, durationMs: 0 }
      : await getExecutor().execute({
          functionName: 'repository_delete',
          machineName,
          ...(kubeCluster !== undefined && { kubeCluster }),
          // #74, the asymmetric half: `repository_create` above already declares the datastore it recorded, and delete said nothing, so a repo created on a named datastore could not be deleted from it, renet looking for the image on the machine's default.
          datastore: await recordedDatastoreMount(target),
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
        name,
        !!options.purgeBackups
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
  // repo create <name> --machine <m> | --datastore <d> (placement union, spec §5.4)
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
  repo
    .command('delete')
    .summary(t('commands.repo.delete.descriptionShort'))
    .description(t('commands.repo.delete.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--archive-config', t('commands.repo.delete.archiveOption'))
    .option('--purge-backups', t('commands.repo.delete.purgeBackupsOption'))
    .option('-y, --yes', t('options.yes'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .option('--dry-run', t('options.dryRun'))
    .action(async (ref: string, options) => {
      await handleRepoDelete(ref, options);
    });
}
