/**
 * Fork command implementation.
 * Extracted from repo-extended.ts to keep file size within limits.
 *
 * Orchestration for `repo fork --up`:
 * - DNS record creation (pure HTTP) is fired before any SSH work.
 * - The repo SSH key deploys over the shared pooled connection.
 * - The fork leg runs as ONE machine job, a compound `renet repository fork --up`
 *   (params { up, grand, repo_name }); --checkpoint keeps a separate up leg,
 *   which runs as a successor step.
 * - The license identity refresh, the DNS, certificate and URL steps and the
 *   backup-unit re-render ride the job's ticket (PLAN-detached-jobs J4), so a
 *   ticket handed back early records nothing before the fork exists.
 * - The backup-unit re-render is planned only when the fork moves a unit (a
 *   strategy names its family); a fork of a repository whose units name exact
 *   tags touches no schedule, and never provisions renet or refreshes the
 *   machine's licences for one.
 * - Every phase is timed into the timeline: the network-ID floor read, the
 *   machine connection, the key deploy, the job's own steps, and each ticket
 *   step with its claim, so "Total:" is accounted for line by line.
 * - "Total:" is printed once, at the true end, as wall time since entry.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { validateTag } from '../services/addressing/ref-parser.js';
import { repoChangeMovesSchedule } from '../services/backup/backup-schedule-repo-change.js';
import { reconcileBackupSchedules } from '../services/backup/repo-change-hook.js';
import { configService } from '../services/config/config-resources.js';
import { rerunAfterNetworkIdConflict } from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { type ExecuteResult, getExecutor } from '../services/executor/executor-factory.js';
import type { ExecuteOptions } from '../services/executor/types.js';
import {
  type CommandJobOutcome,
  JobDispatchedError,
  pendingExitCode,
  runCommandJob,
} from '../services/jobs/command-job.js';
import {
  bindStepHandler,
  type PlannedStep,
  planStep,
  resolveStepHandler,
} from '../services/jobs/steps.js';
import {
  type MachineConnectionLease,
  machineConnections,
} from '../services/machine/machine-connection.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { assertNoSlugCollision, repoDisplayKey } from '../services/repo/repo-slug-collision.js';
import { handleError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { ensureRecordedNetworkId, recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { recordTimelineStep, type TimelineStep } from '../utils/timeline.js';
import { assertMachineExists } from './_validate.js';
import { ensureDns, postRepoUpTasks } from './repo-batch-utils.js';
import { type ForkKeyState, registerFork, rollbackFork } from './repo-fork-registration.js';
import {
  createForkEventHandler,
  finishTimeline,
  recordTicketStepTimings,
  startIdentityRefresh,
} from './repo-fork-timeline.js';
import { rollbackRefusedStart } from './repo-rollback.js';

const DEFAULT_VERB = 'repo fork';

export interface ForkActionOptions {
  machine: string;
  /**
   * The datastore's cluster backref, set when the parent ref resolves to a
   * kubernetes-world repo. Threaded into the executor so it injects KUBECONFIG;
   * a docker parent leaves it unset and the fork runs against the machine's
   * Docker daemon exactly as before.
   */
  kubeCluster?: string;
  checkpoint?: boolean;
  immutable?: boolean;
  up?: boolean;
  detach?: boolean;
  debug?: boolean;
  skipRouterRestart?: boolean;
  /**
   * Base name for the new fork's config key. Defaults to the parent's base
   * name; `repo checkout` overrides it so a fork checked out from a
   * GUID-keyed commit still gets a human name (app:rollback, not <guid>:rollback).
   */
  forkBaseName?: string;
  /** The verb the fork job is recorded under: `repo checkout` forks through here too. */
  verb?: string;
  /** Success steps the caller adds to the fork job's ticket (`repo checkout` records the new fork's tip). */
  extraSteps?: PlannedStep[];
}

/** Validate mutually-exclusive fork option combinations. */
function assertForkOptions(options: { immutable?: boolean; up?: boolean }): void {
  if (options.immutable && options.up) {
    throw new Error(t('commands.repo.fork.immutableUpConflict'));
  }
}

export interface ForkPlan {
  parent: string;
  forkKey: string;
  grandGuid: string;
  repositoryGuid: string;
  networkId: number;
  startedAt: number;
  options: ForkActionOptions;
  lease: MachineConnectionLease;
  /** Filled when the repo key deploy starts; read by the rollback paths. */
  keyState: ForkKeyState;
  /** Phases timed before the orchestration started (the network-ID floor read, the machine connection). */
  timeline: TimelineStep[];
  /**
   * Mount path of the datastore the PARENT is recorded on (#74), undefined for a
   * repo on a machine's implicit default.
   *
   * The parent's datastore, not the fork's, because that is the question renet
   * is actually asking: `renet repository fork` resolves the parent image under
   * `--datastore`, and the reflink lands beside it. It reads that flag from the
   * MACHINE VAULT, never from the params bag, so a caller that stays silent gets
   * the machine's default docker datastore, and the fork of a repo living in a
   * named datastore then looks for its parent somewhere the parent has never
   * been.
   */
  datastoreMount?: string;
}

/** Build the repository_fork params. Compound legs add { up, grand, repo_name }. */
function buildForkParams(plan: ForkPlan, compound: boolean): Record<string, unknown> {
  return {
    repository: plan.parent,
    tag: plan.repositoryGuid,
    network_id: plan.networkId,
    ...(plan.options.checkpoint ? { checkpoint: true } : {}),
    ...(plan.options.immutable ? { immutable: true } : {}),
    ...(compound ? { up: true, grand: plan.grandGuid, repo_name: plan.forkKey } : {}),
    ...(compound && plan.options.detach ? { detach: true } : {}),
  };
}

/** Run the repository_fork job with its ticket steps, streaming renet steps into renetSteps. */
function executeForkLeg(
  plan: ForkPlan,
  params: Record<string, unknown>,
  renetSteps: TimelineStep[],
  steps: PlannedStep[]
): Promise<CommandJobOutcome> {
  return startForkJob(plan, params, renetSteps, steps);
}

/** `runCommandJob`, noting on the plan once the job exists so a later throw never undoes the registration the job owns. */
async function startForkJob(
  plan: ForkPlan,
  params: Record<string, unknown>,
  renetSteps: TimelineStep[],
  steps: PlannedStep[]
): Promise<CommandJobOutcome> {
  try {
    const outcome = await runCommandJob(
      plan.options.verb ?? DEFAULT_VERB,
      forkLegOptions(plan, params, renetSteps),
      steps
    );
    // From here the registration is the job's: a failed job's rollbackFork step removes it, a finished one keeps it, and the caller's catch touches neither.
    plan.keyState.jobStarted = true;
    return outcome;
  } catch (error) {
    if (error instanceof JobDispatchedError) plan.keyState.jobStarted = true;
    throw error;
  }
}

function forkLegOptions(
  plan: ForkPlan,
  params: Record<string, unknown>,
  renetSteps: TimelineStep[]
): ExecuteOptions {
  return {
    functionName: 'repository_fork',
    machineName: plan.options.machine,
    ...(plan.options.kubeCluster !== undefined && { kubeCluster: plan.options.kubeCluster }),
    ...(plan.datastoreMount !== undefined && { datastore: plan.datastoreMount }),
    params,
    debug: plan.options.debug,
    skipRouterRestart: plan.options.skipRouterRestart,
    eventsMode: true,
    quietSpinners: true,
    deferIdentityRefresh: true,
    onEvent: createForkEventHandler(renetSteps),
  };
}

/** Legacy second leg: mount + up after a plain fork. */
async function executeUpLeg(plan: ForkPlan, renetSteps: TimelineStep[]): Promise<ExecuteResult> {
  const upResult = await getExecutor().execute({
    functionName: 'repository_up',
    machineName: plan.options.machine,
    ...(plan.options.kubeCluster !== undefined && { kubeCluster: plan.options.kubeCluster }),
    // Same declaration as the fork leg: the fork lives in the parent's datastore, and `repository_up` resolves its image from the vault too. (The standalone `rdc repo up` gets this from executeRepoFunction; this leg bypasses that path, so it has to say so itself.)
    ...(plan.datastoreMount !== undefined && { datastore: plan.datastoreMount }),
    params: {
      repository: plan.forkKey,
      mount: true,
      grand: plan.grandGuid,
      ...(plan.options.detach ? { detach: true } : {}),
    },
    debug: plan.options.debug,
    skipRouterRestart: plan.options.skipRouterRestart,
    eventsMode: true,
    quietSpinners: true,
    onEvent: createForkEventHandler(renetSteps),
  });

  if (!upResult.success) {
    renderLocalExecutionFailure(upResult, t('commands.repo.up.failed'));
  }
  return upResult;
}

/**
 * Handle a failed fork leg. A compound --up failure can happen AFTER the
 * remote fork exists (mount, compose, readiness); rolling back the local
 * registration then would orphan a live remote repo. The cow_reflink /
 * cow_clone step completing is the signal that the fork image was created.
 */
async function handleForkLegFailure(
  plan: ForkPlan,
  result: ExecuteResult,
  orchestrated: TimelineStep[],
  renetSteps: TimelineStep[],
  dnsPromise: Promise<unknown> | undefined
): Promise<void> {
  const { forkKey, options } = plan;
  if (dnsPromise !== undefined) await Promise.allSettled([dnsPromise]);
  const forkCreated = renetSteps.some((s) => s.name === 'cow_reflink' || s.name === 'cow_clone');
  if (forkCreated) {
    outputService.warn(
      `Fork "${forkKey}" was created on the machine but its up phase failed; ` +
        `keeping the local registration. Retry with: rdc repo up ${forkKey} -m ${options.machine}`
    );
  }
  // Otherwise the job's rollbackFork step already dropped the registration and the deployed key.
  renderLocalExecutionFailure(result, t('commands.repo.fork.failed'));
  finishTimeline(plan, orchestrated, renetSteps, [result]);
}

/**
 * T3(e): renet refused the fork's network ID at its up phase, after the image was made. Move past the holder, record the new ID (the up leg reads it from the config), and bring the fork up once more. `undefined` when it is not a network-ID refusal or no fork image exists.
 */
function retryForkUpOnConflict(
  plan: ForkPlan,
  failed: ExecuteResult,
  renetSteps: TimelineStep[]
): Promise<ExecuteResult | undefined> {
  if (!renetSteps.some((s) => s.name === 'cow_reflink' || s.name === 'cow_clone')) {
    return Promise.resolve(undefined);
  }
  const { machine, kubeCluster } = plan.options;
  return rerunAfterNetworkIdConflict({
    failed,
    repoKey: plan.forkKey,
    target: { machine, datastore: plan.datastoreMount, kubeCluster },
    rerun: (networkId) => {
      plan.networkId = networkId;
      return executeUpLeg(plan, renetSteps);
    },
  });
}

/**
 * The fork job's ticket steps (PLAN-detached-jobs J4). On failure the registration is rolled back unless the stream
 * showed the image was made (the rollbackFork handler reads the markers). On success: the identity refresh, the legacy
 * up leg as a successor job for `--checkpoint --up`, the DNS, certificate and URL steps after an up, and, only when
 * `reconcileSchedule`, the backup-unit re-render (G4: a family-scoped strategy covers the new fork, so the machine's
 * units move with it; a fork no strategy names by family moves nothing and plans no re-render).
 */
function forkSteps(
  plan: ForkPlan,
  forkParams: Record<string, unknown>,
  legacyUp: boolean,
  reconcileSchedule: boolean
): PlannedStep[] {
  const { options, forkKey } = plan;
  return [
    planStep('rollbackFork', {
      repo: forkKey,
      machine: options.machine,
      guid: plan.repositoryGuid,
    }),
    planStep('identityRefresh', { function: 'repository_fork', ...forkParams }),
    ...(legacyUp
      ? [
          planStep('forkUp', {
            repo: forkKey,
            grand: plan.grandGuid,
            detach: options.detach === true,
            ...(plan.datastoreMount === undefined ? {} : { datastore: plan.datastoreMount }),
            ...(options.kubeCluster === undefined ? {} : { cluster: options.kubeCluster }),
            debug: options.debug === true,
          }),
        ]
      : []),
    ...(options.up
      ? [planStep('postRepoUpTasks', { repo: forkKey, machine: options.machine })]
      : []),
    ...(reconcileSchedule
      ? [planStep('reconcileBackupSchedules', { machine: options.machine })]
      : []),
    ...(options.extraSteps ?? []),
  ];
}

/** Orchestrate the fork job (+ optional up) over a shared machine connection lease. */
async function orchestrateFork(plan: ForkPlan): Promise<void> {
  const { options, forkKey } = plan;
  const orchestrated: TimelineStep[] = plan.timeline;
  const renetSteps: TimelineStep[] = [];

  // DNS records need only names, fire the HTTP call before any SSH work.
  const dnsPromise = options.up
    ? recordTimelineStep(orchestrated, 'dns', () => ensureDns(forkKey, options.machine), {
        parallel: true,
      })
    : undefined;

  plan.keyState.machine = options.machine;
  plan.keyState.guid = plan.repositoryGuid;
  await recordTimelineStep(orchestrated, 'key_deploy', () =>
    deployRepoKeyIfNeeded(forkKey, options.machine)
  );

  // One compound `renet repository fork --up`. `--checkpoint` keeps restore-on-first-up semantics through the separate up leg, a successor step. A renet without `job` is refused before any of this runs, and every renet with `job` has fork --up.
  const compound = Boolean(options.up && !options.checkpoint);
  const forkParams = buildForkParams(plan, compound);
  // A config read, no SSH: the re-render is planned only when the fork moves a unit.
  const reconcileSchedule = await repoChangeMovesSchedule(options.machine, plan.repositoryGuid);
  const outcome = await executeForkLeg(
    plan,
    forkParams,
    renetSteps,
    forkSteps(plan, forkParams, Boolean(options.up && !compound), reconcileSchedule)
  );
  recordTicketStepTimings(orchestrated, outcome.steps);
  if (outcome.kind === 'pending') {
    if (dnsPromise !== undefined) await Promise.allSettled([dnsPromise]);
    // The network-ID retry (retryForkUpOnConflict) is a client second leg: it reads the refusal from the job's stderr and writes a new ID to the config, neither of which a ticket step can do while the client is away. It does not run here, so say where a refusal leaves the fork.
    if (options.up) {
      outputService.info(
        `A network ID refusal at the up phase is not retried in the background: the fork "${forkKey}" stays registered once its image exists. ` +
          `Retry with: rdc repo up ${forkKey} -m ${options.machine}`
      );
    }
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  const { result } = outcome;
  if (result.success) {
    finishTimeline(plan, orchestrated, renetSteps, [result]);
    return;
  }

  // T3(e): a network-ID refusal at the up phase, after the image was made. The rollback step kept the registration (the stream showed the image), so bring the fork up once more and run the success steps the failed job did not.
  const retried = await retryForkUpOnConflict(plan, result, renetSteps);
  if (!retried?.success) {
    await handleForkLegFailure(plan, retried ?? result, orchestrated, renetSteps, dnsPromise);
    return;
  }
  await Promise.allSettled([
    startIdentityRefresh(orchestrated, options, forkParams),
    postRepoUpTasks(forkKey, options.machine, {
      dnsPromise,
      lease: plan.lease,
      steps: orchestrated,
    }),
  ]);
  if (reconcileSchedule) {
    await recordTimelineStep(orchestrated, 'backup_schedule', () =>
      reconcileBackupSchedules(options.machine)
    );
  }
  finishTimeline(plan, orchestrated, renetSteps, [result, retried]);
  for (const step of options.extraSteps ?? []) {
    const handler = await resolveStepHandler(step.name);
    await handler({ jobId: '', machine: options.machine, params: step.params, state: 'succeeded' });
  }
}

// `--checkpoint --up`: the up leg, as a successor job once the fork job succeeded.
bindStepHandler('forkUp', async ({ machine, params }) => {
  const text = (key: string) =>
    typeof params[key] === 'string' && params[key] !== '' ? String(params[key]) : undefined;
  const repo = text('repo');
  if (repo === undefined) throw new Error('step param "repo" is missing');
  const up = await getExecutor().execute({
    functionName: 'repository_up',
    machineName: machine,
    ...(text('cluster') === undefined ? {} : { kubeCluster: text('cluster') }),
    ...(text('datastore') === undefined ? {} : { datastore: text('datastore') }),
    params: {
      repository: repo,
      mount: true,
      ...(text('grand') === undefined ? {} : { grand: text('grand') }),
      ...(params.detach === true ? { detach: true } : {}),
    },
    debug: params.debug === true,
  });
  if (!up.success) renderLocalExecutionFailure(up, t('commands.repo.up.failed'));
});

/** Handle the fork action body. */
export async function handleForkAction(
  parent: string,
  tagName: string,
  options: ForkActionOptions
): Promise<void> {
  const startedAt = Date.now();
  const { parseRepoRef, compositeKey, assertNonLatestForkTag } = await import(
    '../utils/config-schema.js'
  );
  let forkKey = '';
  // Rollback must only ever remove the row THIS invocation registered, a catch-all rollback would delete a pre-existing fork's config row (credential included) when registerFork fails with "already exists".
  let forkGuid: string | undefined;
  const keyState: ForkKeyState = {};
  const timeline: TimelineStep[] = [];
  try {
    // Refuse the reserved birth tag `base` (exit 2) and enforce the fork-tag label grammar before any config mutation; `latest` stays reserved as the grand pointer that a fork must not clobber (#495).
    validateTag(tagName);
    assertNonLatestForkTag(tagName, t('commands.repo.fork.tagReservedLatest'));
    assertForkOptions(options);
    forkKey = compositeKey(options.forkBaseName ?? parseRepoRef(parent).name, tagName);
    const parentConfig = await configService.getRepository(parent);
    if (!parentConfig) {
      throw new Error(`Repository "${parent}" not found in context`);
    }

    await assertMachineExists(options.machine);
    // Before any config write: a fork whose slug equals another repo's would share its replica set and datastore fork tag.
    assertNoSlugCollision(
      repoDisplayKey(forkKey),
      (await configService.listRepositories()).map((repo) => repoDisplayKey(repo.name))
    );

    const { repositoryGuid, networkId, reattached } = await registerFork(
      parent,
      forkKey,
      tagName,
      options.machine,
      parentConfig,
      options.immutable === true,
      timeline
    );
    // A reattached row is the first attempt's, so this invocation's failure must not roll it back.
    if (!reattached) forkGuid = repositoryGuid;

    // Resolved BEFORE the lease: it is a config read, and anything between acquire() and the try/finally below escapes the release on a throw.
    const datastoreMount = await recordedDatastoreMount(parent);

    // Outer lease: every SSH consumer below (key deploy, fork/up legs, identity refresh, cert sync, service URLs) shares this pooled connection; the last release closes it.
    const lease = await recordTimelineStep(timeline, 'machine_connect', () =>
      machineConnections.acquire(options.machine)
    );
    try {
      await orchestrateFork({
        parent,
        forkKey,
        grandGuid: parentConfig.grandGuid ?? parentConfig.repositoryGuid,
        repositoryGuid,
        networkId,
        startedAt,
        options,
        lease,
        keyState,
        timeline,
        ...(datastoreMount !== undefined && { datastoreMount }),
      });
    } finally {
      lease.release();
    }
  } catch (error) {
    // Once the job exists on the machine, or its state is unknown after a timeout, the registration and the deployed key stay: a failed job's own rollbackFork step settles them, and a finished one keeps them.
    if (keyState.jobStarted !== true && forkGuid !== undefined) {
      await rollbackRefusedStart(error, rollbackFork, forkKey, keyState, forkGuid);
    }
    handleError(error);
  }
}

/**
 * Register `repo fork <ref>` (spec/03 §5.4). The parent repo is the positional
 * ref; its config placement derives the execution machine and, for a
 * kubernetes-world parent, the datastore's cluster backref (KUBECONFIG). There
 * is no `-m`/`--cluster`/`--parent`: cross-machine forking is `fork` then
 * `push`. Boolean flags are forwarded to the shared fork orchestration, which
 * also drives `repo checkout`.
 */
export function registerRepoForkCommand(repo: Command): void {
  repo
    .command('fork')
    .summary(t('commands.repo.fork.descriptionShort'))
    .description(t('commands.repo.fork.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--tag <name>', t('commands.repo.fork.tagOption'))
    .option('--checkpoint', t('commands.repo.fork.checkpointOption'))
    .option('--immutable', t('commands.repo.fork.immutableOption'))
    .option('--up', t('commands.repo.fork.upOption'))
    .option('--no-wait', t('commands.repo.fork.noWaitOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        ref: string,
        options: {
          tag: string;
          checkpoint?: boolean;
          immutable?: boolean;
          up?: boolean;
          // `--no-wait` sets `wait` to false (Commander negated-flag default true).
          wait?: boolean;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          // Mutating verb: derive the execution machine from the parent ref's
          // placement (spec/03 §2.3). No resolve options => step-5 mount
          // verification is skipped, matching the pre-reshape fork behavior.
          const { repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
          await ensureRecordedNetworkId(repoKey, machineName, kubeCluster);
          await handleForkAction(repoKey, options.tag, {
            machine: machineName,
            ...(kubeCluster !== undefined && { kubeCluster }),
            ...(options.checkpoint && { checkpoint: true }),
            ...(options.immutable && { immutable: true }),
            ...(options.up && { up: true }),
            // `--no-wait` maps to the unchanged `detach` wire param: return once containers start, do not block on the health check.
            ...(options.wait === false && { detach: true }),
            ...(options.debug && { debug: true }),
            ...(options.skipRouterRestart && { skipRouterRestart: true }),
          });
        } catch (error) {
          handleError(error);
        }
      }
    );
}
