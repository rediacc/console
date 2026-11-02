import { randomBytes, randomUUID } from 'node:crypto';
import { handleRepoDelete, renderTimelineTotal } from './repo-create-delete-teardown.js';

export { handleDeleteSuccess } from './repo-create-delete-teardown.js';

import type { Placement } from '@rediacc/shared/config-schema';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import {
  allocateNetworkIdWithFloor,
  type NetworkIdTarget,
  targetFloor,
} from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { requestNetworkIdAuto } from '../services/executor/executor-factory.js';
import type { ExecuteOptions } from '../services/executor/types.js';
import {
  type CommandJobOutcome,
  JobDispatchedError,
  pendingExitCode,
  runCommandJob,
} from '../services/jobs/command-job.js';
import { outstandingSteps } from '../services/jobs/run-job.js';
import { bindStepHandler, type PlannedStep, planStep } from '../services/jobs/steps.js';
import { assertAgentRepoCreate } from '../utils/agent-guard.js';
import { notFound, stateMismatch } from '../utils/cli-exit-error.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { generateSSHKeyPair } from '../utils/ssh-keygen.js';
import { assertMachineExists } from './_validate.js';

function generateCredential(): string {
  return randomBytes(24).toString('base64');
}

/**
 * Rollback the registration this create made. The GUID is the identity: a same-named repo registered since the failure
 * (the step can run after a later command, from the finished notice) carries another GUID and is left alone.
 */
async function rollbackCreateRepo(name: string, guid: string): Promise<void> {
  const exists = await configService.getRepository(name);
  if (exists?.repositoryGuid === guid) {
    await configService.removeRepository(name);
    outputService.warn(t('commands.repo.create.rollback', { repository: name }));
  }
}

bindStepHandler('rollbackCreate', async ({ params }) => {
  for (const key of ['repo', 'guid'] as const) {
    if (typeof params[key] !== 'string' || params[key] === '') {
      throw new Error(`step param "${key}" is missing`);
    }
  }
  await rollbackCreateRepo(String(params.repo), String(params.guid));
});

/**
 * The steps a create job owes (PLAN-detached-jobs J16). A failed or cancelled job rolls the registration back; a
 * succeeded one refreshes the licence identity with the size it was created with and re-renders the backup units.
 * They ride the job's ticket, so a `--background` create or a lost tail still settles them from `rdc job wait`.
 */
function createSteps(
  name: string,
  guid: string,
  machine: string,
  size: string | undefined
): PlannedStep[] {
  return [
    planStep('rollbackCreate', { repo: name, guid }),
    planStep('identityRefresh', {
      function: 'repository_create',
      repository: name,
      ...(size ? { size } : {}),
    }),
    planStep('reconcileBackupSchedules', { machine }),
  ];
}

/**
 * Run the create as one machine job and render its outcome. The steps (rollback, identity refresh, schedule
 * re-render) already ran inside the job's attach window when this returns a finished outcome; a pending one owes them
 * to the ticket. `network_id: "auto"` replaces the client's allocation and its conflict retry (J0b finding 8), so
 * there is exactly one job and a refused start leaves the registration for the caller's catch to roll back.
 */
async function runCreateJob(
  name: string,
  guid: string,
  machine: string,
  size: string | undefined,
  options: ExecuteOptions
): Promise<void> {
  // A plain rejection here means the job did not start, so the caller rolls the registration back.
  let outcome: CommandJobOutcome;
  try {
    outcome = await runCommandJob(
      'repo create',
      { ...options, deferIdentityRefresh: true },
      createSteps(name, guid, machine, size)
    );
  } catch (error) {
    if (!(error instanceof JobDispatchedError)) throw error;
    // The job was dispatched and recording it failed: the repo exists on the machine, so the registration stays.
    // error.message already names the job and the ticket, so nothing is repeated here.
    outputService.warn(
      `repo create: ${name} was created, but its record could not be completed: ${error.message}. Run \`rdc repo status ${name}\` to check it and \`rdc job wait\` to settle any open steps.`
    );
    setExitCode(1);
    return;
  }
  // A failed job renders outside the finishing guard: its rendering is the failure report, not a post-create step.
  if (outcome.kind !== 'pending' && !outcome.result.success) {
    renderLocalExecutionFailure(outcome.result, t('commands.repo.create.failed'));
    return;
  }
  // From here the repo exists on the machine (or the job still runs): nothing below may reach the caller's rollback.
  try {
    settleCreateOutcome(name, outcome);
  } catch (error) {
    outputService.warn(
      `repo create: ${name} was created, but finishing it failed: ${error instanceof Error ? error.message : String(error)}`
    );
    setExitCode(1);
  }
}

/** Render the pending or succeeded create, and name the success-side steps that did not finish. */
function settleCreateOutcome(name: string, outcome: CommandJobOutcome): void {
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  const { result } = outcome;
  if (result.allSteps && result.allSteps.length > 0) {
    renderTimelineTotal(result.allSteps);
  } else {
    outputService.success(t('commands.repo.create.completed'));
  }
  const unfinished = outstandingSteps(outcome.steps);
  if (unfinished.length > 0) {
    outputService.warn(
      `repo create: ${name} was created, but the step(s) ${unfinished.join(', ')} did not finish; rdc job wait settles them.`
    );
  }
}

/** Ask the create job to have renet allocate the network ID, and record it in the config once it has. */
function requestCreateNetworkId(name: string, guid: string, machine: string): void {
  requestNetworkIdAuto({
    machine,
    aliases: [name, `${name}:latest`, guid],
    repoGuid: guid,
    repoName: name,
    recordAs: `${name}:latest`,
  });
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
  target: NetworkIdTarget,
  /** The create job asks renet for the ID (`network_id: "auto"`): no ID is allocated here and the record carries none. */
  networkIdAuto = false
): Promise<{ repositoryGuid: string; networkId?: number }> {
  // Validate before ANY write: allocateNetworkId persists, and a refused name must leave the config untouched.
  const { assertResourceName, compositeKey } = await import('../utils/config-schema.js');
  assertResourceName(name);
  const existing = await configService.getRepository(name);
  if (existing) {
    throw new Error(t('commands.repo.create.alreadyExists', { name }));
  }
  const repositoryGuid = randomUUID();
  // D3(a): the floor is the target machine's used set, so a lagging counter skips IDs other devices placed there.
  const networkId = networkIdAuto
    ? undefined
    : await allocateNetworkIdWithFloor(await targetFloor(target));
  await configService.addRepository(compositeKey(name, 'latest'), {
    repositoryGuid,
    tag: 'latest',
    credential: generateCredential(),
    ...(networkId === undefined || networkId <= 0 ? {} : { networkId }),
    placement,
    ...extra,
  });
  // In auto mode renet allocates the ID inside the job, so none is returned here.
  return networkId === undefined || networkId <= 0
    ? { repositoryGuid }
    : { repositoryGuid, networkId };
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
  let createdGuid: string | undefined;
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
    const { repositoryGuid } = await registerNewRepo(
      name,
      { machine: options.machine },
      { sshPrivateKey, sshPublicKey },
      target,
      true
    );
    createdGuid = repositoryGuid;

    outputService.info(
      t('commands.repo.create.registered', {
        repository: name,
        guid: repositoryGuid.slice(0, 8),
        networkId: 'auto',
      })
    );
    outputService.info(
      t('commands.repo.create.starting', {
        repository: name,
        size: options.size,
        machine: options.machine,
      })
    );

    // No network_id in the params below: requestCreateNetworkId queues a directive the executor seam spends on this dispatch (executor-factory requestNetworkIdAuto -> withDirective), which sends network_id "auto" to renet.
    requestCreateNetworkId(name, repositoryGuid, options.machine);
    await runCreateJob(name, repositoryGuid, options.machine, options.size, {
      functionName: 'repository_create',
      machineName: options.machine,
      params: {
        repository: name,
        size: options.size,
        guid: repositoryGuid,
        ...(options.noDocker ? { start_docker: false } : {}),
      },
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });
  } catch (error) {
    if (createdGuid !== undefined) await rollbackCreateRepo(name, createdGuid);
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
  let createdGuid: string | undefined;
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
    const { repositoryGuid } = await registerNewRepo(
      name,
      { datastore: options.datastore },
      {},
      target,
      true
    );
    createdGuid = repositoryGuid;

    outputService.info(
      t('commands.repo.create.registered', {
        repository: name,
        guid: repositoryGuid.slice(0, 8),
        networkId: 'auto',
      })
    );
    outputService.info(
      t('commands.repo.create.startingDatastore', {
        repository: name,
        datastore: options.datastore,
        machine: placement.machine,
      })
    );

    // No network_id in the params below: see the machine form, where the executor seam sends network_id "auto" from the directive.
    requestCreateNetworkId(name, repositoryGuid, placement.machine);
    await runCreateJob(name, repositoryGuid, placement.machine, options.size, {
      functionName: 'repository_create',
      machineName: placement.machine,
      ...(placement.kubeCluster !== undefined && { kubeCluster: placement.kubeCluster }),
      // #74: DISPATCH AGAINST THE DATASTORE WE JUST RECORDED. We resolved this placement above and then said nothing about it, so renet fell back to the machine's default docker datastore: the placement written to the config and the placement sent to the machine were two different things, silently. This is the executor's vault channel (ExecuteOptions.datastore), NOT a param ,
      // `repository_create` reads its datastore from the machine vault.
      datastore: placement.mountPath,
      params: {
        repository: name,
        guid: repositoryGuid,
        mount_path: placement.mountPath,
        // #67: DECLARE the runtime for a cluster-placed repo, exactly as `repo up` does (the #39 assertion channel: renet honors `runtime` as an assertion and errors on a disagreement rather than silently falling to the docker arm).
        //
        // Without it, this dispatch was incoherent with the validation eight lines above: the CLI knew the repo was kubernetes-placed, refused `--size` on exactly that ground, and then sent the DOCKER create, which requires a
        // size. With --size the CLI refused; without it renet refused. No value of
        // the flag worked, and `repo create` was unusable on the cluster path. The declaration is what lets renet size the volumes from the PVCs instead.
        ...(isK8s ? { runtime: 'kube', cluster: placement.kubeCluster, start_docker: false } : {}),
        ...(options.size ? { size: options.size } : {}),
        ...(options.noDocker && !isK8s ? { start_docker: false } : {}),
      },
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });
  } catch (error) {
    if (createdGuid !== undefined) await rollbackCreateRepo(name, createdGuid);
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

/**
 * Commander stores `--no-docker` as `docker: false` and never sets `noDocker`, so the flag was a no-op;
 * this maps the parsed options to the shape handleRepoCreate takes (callers other than the CLI pass
 * `noDocker` directly).
 */
export function repoCreateOptions(options: {
  machine?: string;
  datastore?: string;
  size?: string;
  docker?: boolean;
  debug?: boolean;
  skipRouterRestart?: boolean;
}): Parameters<typeof handleRepoCreate>[1] {
  const { docker, ...rest } = options;
  return { ...rest, noDocker: docker === false };
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
      await handleRepoCreate(name, repoCreateOptions(options));
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
