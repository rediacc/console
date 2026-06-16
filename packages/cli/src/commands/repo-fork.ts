/**
 * Fork command implementation.
 * Extracted from repo-extended.ts to keep file size within limits.
 *
 * Orchestration for `repo fork --up`:
 * - DNS record creation (pure HTTP) is fired before any SSH work.
 * - The repo SSH key deploys over the shared pooled connection.
 * - The fork leg runs as ONE compound `renet repository fork --up` execute
 *   (params { up, grand, repo_name }); a legacy fork-then-up two-leg path
 *   remains for --checkpoint and for remote renets that predate --up.
 * - License identity refresh, cert-cache sync, and service-URL resolution
 *   run concurrently after the up portion; failures are warn-only.
 * - "Total:" is printed once, at the true end, as wall time since entry.
 */
import { randomUUID } from 'node:crypto';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import {
  type LocalExecuteResult,
  localExecutorService,
  type RenetEvent,
} from '../services/local-executor.js';
import { type MachineConnectionLease, machineConnections } from '../services/machine-connection.js';
import { outputService } from '../services/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { handleError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { generateSSHKeyPair } from '../utils/ssh-keygen.js';
import {
  buildTimingSummary,
  formatStepDuration,
  getActiveLabel,
  getDoneLabel,
  recordTimelineStep,
  type TimelineStep,
} from '../utils/timeline.js';
import { assertMachineExists } from './_validate.js';
import { ensureDns, postRepoUpTasks } from './repo-batch-utils.js';

interface ForkActionOptions {
  machine: string;
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
}

/** Renet step names that only appear when the compound fork ran the up phase. */
const UP_PHASE_STEP_NAMES = new Set([
  'luks_mount',
  'docker_daemon',
  'compose_up',
  'service_ready',
  'thaw_resume',
]);

/** Print one completed-step line in the streamed timeline format. */
function printStepLine(step: TimelineStep): void {
  const detail = step.detail ? ` (${step.detail})` : '';
  process.stdout.write(
    `✔ ${getDoneLabel(step.name)}${detail} (${formatStepDuration(step.duration_ms)})\n`
  );
}

/** Print "Total: <wall>" once at the true end and mark the timeline rendered. */
function renderTimelineTotal(wallMs: number): void {
  process.stdout.write(`\nTotal: ${formatStepDuration(wallMs)}\n`);
  outputService.setTimelineRendered();
}

/** Handle a log event: only show errors/warnings. */
function handleLogEvent(event: RenetEvent): void {
  if (event.level === 'error' || event.level === 'fatal' || event.level === 'warning') {
    process.stderr.write(`  ${event.msg ?? ''}\n`);
  }
}

/** Handle a step_done event: render and record the step. */
function handleStepDoneEvent(
  event: RenetEvent,
  allSteps: TimelineStep[],
  startedAtMs?: number
): void {
  if (!event.name || event.duration_ms === undefined) return;
  const label = getDoneLabel(event.name);
  const detail = event.detail ? ` (${event.detail})` : '';
  process.stdout.write(`\r✔ ${label}${detail} (${formatStepDuration(event.duration_ms)})\n`);
  allSteps.push({
    name: event.name,
    duration_ms: event.duration_ms,
    detail: event.detail,
    ...(startedAtMs === undefined ? {} : { startedAtMs }),
  });
}

/** Create an event handler for streaming renet events during fork/up legs. */
function createForkEventHandler(allSteps: TimelineStep[]): (event: RenetEvent) => void {
  // step_start arrival times anchor the end-of-run waterfall chart.
  const stepStarts = new Map<string, number>();
  return (event: RenetEvent) => {
    switch (event.type) {
      case 'log':
        handleLogEvent(event);
        break;
      case 'step_start':
        if (event.name) stepStarts.set(event.name, Date.now());
        process.stdout.write(`⠋ ${getActiveLabel(event.name ?? '')}...`);
        break;
      case 'step_done': {
        const startedAtMs = event.name ? stepStarts.get(event.name) : undefined;
        if (event.name) stepStarts.delete(event.name);
        handleStepDoneEvent(event, allSteps, startedAtMs);
        break;
      }
      case 'output':
        if (
          event.msg &&
          (event.msg.includes('✔') || event.msg.includes('✗') || event.msg.includes('Error'))
        ) {
          process.stdout.write(`  ${event.msg}`);
        }
        break;
    }
  };
}

/** Rollback a fork registration if it exists. */
async function rollbackFork(forkKey: string): Promise<void> {
  const exists = await configService.getRepository(forkKey);
  if (exists) {
    await configService.removeRepository(forkKey);
    outputService.warn(t('commands.repo.fork.rollback', { repository: forkKey }));
  }
}

/** Validate and register a new fork in the config. Returns the new GUID and networkId. */
async function registerFork(
  parent: string,
  forkKey: string,
  tagName: string,
  machineName: string,
  parentConfig: NonNullable<Awaited<ReturnType<typeof configService.getRepository>>>,
  immutable = false
): Promise<{ repositoryGuid: string; networkId: number }> {
  const existing = await configService.getRepository(forkKey);
  if (existing) {
    throw new Error(t('commands.repo.fork.alreadyExists', { name: forkKey }));
  }

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
    ...(immutable ? { immutable: true } : {}),
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
    t('commands.repo.fork.starting', { parent, repository: forkKey, machine: machineName })
  );

  return { repositoryGuid, networkId };
}

/** Validate mutually-exclusive fork option combinations. */
function assertForkOptions(options: { immutable?: boolean; up?: boolean }): void {
  if (options.immutable && options.up) {
    throw new Error(t('commands.repo.fork.immutableUpConflict'));
  }
}

interface ForkPlan {
  parent: string;
  forkKey: string;
  grandGuid: string;
  repositoryGuid: string;
  networkId: number;
  startedAt: number;
  options: ForkActionOptions;
  lease: MachineConnectionLease;
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

/** Execute one repository_fork leg, streaming renet steps into renetSteps. */
function executeForkLeg(
  plan: ForkPlan,
  params: Record<string, unknown>,
  renetSteps: TimelineStep[]
): Promise<LocalExecuteResult> {
  return localExecutorService.execute({
    functionName: 'repository_fork',
    machineName: plan.options.machine,
    params,
    debug: plan.options.debug,
    skipRouterRestart: plan.options.skipRouterRestart,
    eventsMode: true,
    quietSpinners: true,
    deferIdentityRefresh: true,
    onEvent: createForkEventHandler(renetSteps),
  });
}

/** Whether a failed compound fork indicates the remote renet predates --up. */
function isUpFlagUnsupported(result: LocalExecuteResult): boolean {
  const text = `${result.error ?? ''}\n${result.stderr ?? ''}`;
  return /unknown (flag|shorthand flag|command)/i.test(text) && text.includes('--up');
}

/** Whether the compound fork actually ran the up phase remotely. */
function compoundUpRan(result: LocalExecuteResult, renetSteps: TimelineStep[]): boolean {
  const steps = result.steps && result.steps.length > 0 ? result.steps : renetSteps;
  return steps.some((s) => UP_PHASE_STEP_NAMES.has(s.name));
}

/**
 * Fire the deferred license-identity refresh. Runs concurrent with the up
 * portion (legacy leg) or the post-up tasks (compound leg). Warn-only: a
 * failed refresh never fails the fork.
 */
function startIdentityRefresh(
  steps: TimelineStep[],
  options: ForkActionOptions,
  forkParams: Record<string, unknown>
): Promise<void> {
  return recordTimelineStep(
    steps,
    'identity_refresh',
    () => localExecutorService.refreshIdentityFor('repository_fork', options.machine, forkParams),
    { parallel: true }
  ).catch((error: unknown) => {
    outputService.warn(
      `License identity refresh failed (non-fatal): ${error instanceof Error ? error.message : String(error)}`
    );
  });
}

/** Legacy second leg: mount + up after a plain fork. */
async function executeUpLeg(
  plan: ForkPlan,
  renetSteps: TimelineStep[]
): Promise<LocalExecuteResult> {
  const upResult = await localExecutorService.execute({
    functionName: 'repository_up',
    machineName: plan.options.machine,
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
 * Render the end-of-run timing charts (bars + waterfall + attribution).
 * TTY-gated; RDC_TIMING_CHART=1 forces rendering for piped output.
 */
function printTimingSummary(plan: ForkPlan, steps: TimelineStep[], wallMs: number): void {
  if (!process.stdout.isTTY && process.env.RDC_TIMING_CHART !== '1') return;
  const summary = buildTimingSummary(steps, wallMs, {
    epochMs: plan.startedAt,
    suggestDetach: Boolean(plan.options.up && !plan.options.detach),
  });
  if (summary) process.stdout.write(`\n${summary}\n`);
}

/**
 * Render the final timeline: CLI steps from each execute leg (recorded but
 * not streamed under quietSpinners), then orchestrated phases, then a single
 * wall-clock Total. Streamed renet steps were already printed live.
 */
function finishTimeline(
  plan: ForkPlan,
  orchestrated: TimelineStep[],
  renetSteps: TimelineStep[],
  results: (LocalExecuteResult | undefined)[]
): void {
  const cliSteps = results.flatMap((r) => r?.cliSteps ?? []);
  for (const step of cliSteps) {
    printStepLine(step);
  }
  for (const step of orchestrated) {
    printStepLine(step);
  }
  if (cliSteps.length + orchestrated.length + renetSteps.length > 0) {
    const wallMs = Date.now() - plan.startedAt;
    renderTimelineTotal(wallMs);
    if (plan.options.detach && plan.options.up) {
      outputService.info(t('commands.repo.fork.detachedHint', { machine: plan.options.machine }));
    }
    printTimingSummary(plan, [...cliSteps, ...orchestrated, ...renetSteps], wallMs);
  } else {
    outputService.success(
      t('commands.repo.fork.completed', {
        repository: plan.forkKey,
        machine: plan.options.machine,
      })
    );
  }
}

/** Run the fork leg, with compound --up when possible and graceful fallback. */
async function runForkLeg(
  plan: ForkPlan,
  renetSteps: TimelineStep[]
): Promise<{ result: LocalExecuteResult; forkParams: Record<string, unknown>; compound: boolean }> {
  // PRIMARY: one compound `renet repository fork --up`. The legacy two-leg
  // path remains for --checkpoint (restore-on-first-up semantics).
  let compound = Boolean(plan.options.up && !plan.options.checkpoint);
  let forkParams = buildForkParams(plan, compound);
  let result = await executeForkLeg(plan, forkParams, renetSteps);

  if (compound && !result.success && isUpFlagUnsupported(result)) {
    // Remote renet predates fork --up: retry as a plain fork; the caller
    // chains the legacy up leg.
    outputService.warn(
      `Remote renet does not support fork --up; falling back to fork + up (${plan.forkKey})`
    );
    compound = false;
    forkParams = buildForkParams(plan, compound);
    result = await executeForkLeg(plan, forkParams, renetSteps);
  }

  return { result, forkParams, compound };
}

/**
 * Handle a failed fork leg. A compound --up failure can happen AFTER the
 * remote fork exists (mount, compose, readiness); rolling back the local
 * registration then would orphan a live remote repo. The cow_reflink /
 * cow_clone step completing is the signal that the fork image was created.
 */
async function handleForkLegFailure(
  plan: ForkPlan,
  result: LocalExecuteResult,
  orchestrated: TimelineStep[],
  renetSteps: TimelineStep[],
  dnsPromise: Promise<unknown> | undefined
): Promise<void> {
  const { forkKey, options } = plan;
  if (dnsPromise) await Promise.allSettled([dnsPromise]);
  const forkCreated = renetSteps.some((s) => s.name === 'cow_reflink' || s.name === 'cow_clone');
  if (forkCreated) {
    outputService.warn(
      `Fork "${forkKey}" was created on the machine but its up phase failed; ` +
        `keeping the local registration. Retry with: rdc repo up --name ${forkKey} -m ${options.machine}`
    );
  } else {
    await configService.removeRepository(forkKey);
    outputService.warn(t('commands.repo.fork.rollback', { repository: forkKey }));
  }
  renderLocalExecutionFailure(result, t('commands.repo.fork.failed'));
  finishTimeline(plan, orchestrated, renetSteps, [result]);
}

/** Orchestrate fork (+ optional up) over a shared machine connection lease. */
async function orchestrateFork(plan: ForkPlan): Promise<void> {
  const { options, forkKey } = plan;
  const orchestrated: TimelineStep[] = [];
  const renetSteps: TimelineStep[] = [];

  // DNS records need only names — fire the HTTP call before any SSH work.
  const dnsPromise = options.up
    ? recordTimelineStep(orchestrated, 'dns', () => ensureDns(forkKey, options.machine), {
        parallel: true,
      })
    : undefined;

  await recordTimelineStep(orchestrated, 'key_deploy', () =>
    deployRepoKeyIfNeeded(forkKey, options.machine)
  );

  const { result, forkParams, compound } = await runForkLeg(plan, renetSteps);

  if (!result.success) {
    await handleForkLegFailure(plan, result, orchestrated, renetSteps, dnsPromise);
    return;
  }

  // The fork exists from here on — identity refresh can run concurrently
  // with the up portion and the post-up tasks.
  const identityPromise = startIdentityRefresh(orchestrated, options, forkParams);

  let upResult: LocalExecuteResult | undefined;
  if (options.up && !(compound && compoundUpRan(result, renetSteps))) {
    // Legacy/fallback up leg: --checkpoint flows, or a remote renet that
    // silently ignored the compound --up params.
    upResult = await executeUpLeg(plan, renetSteps);
  }

  if (options.up) {
    await Promise.allSettled([
      identityPromise,
      postRepoUpTasks(forkKey, options.machine, {
        dnsPromise,
        lease: plan.lease,
        steps: orchestrated,
      }),
    ]);
  } else {
    await identityPromise;
  }

  finishTimeline(plan, orchestrated, renetSteps, [result, upResult]);
}

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
  // Rollback must only ever remove the row THIS invocation registered — a
  // catch-all rollback would delete a pre-existing fork's config row
  // (credential included) when registerFork fails with "already exists".
  let registered = false;
  try {
    assertNonLatestForkTag(tagName, t('commands.repo.fork.tagReservedLatest'));
    assertForkOptions(options);
    forkKey = compositeKey(options.forkBaseName ?? parseRepoRef(parent).name, tagName);
    const parentConfig = await configService.getRepository(parent);
    if (!parentConfig) {
      throw new Error(`Repository "${parent}" not found in context`);
    }

    await assertMachineExists(options.machine);

    const { repositoryGuid, networkId } = await registerFork(
      parent,
      forkKey,
      tagName,
      options.machine,
      parentConfig,
      options.immutable
    );
    registered = true;

    // Outer lease: every SSH consumer below (key deploy, fork/up legs,
    // identity refresh, cert sync, service URLs) shares this pooled
    // connection; the last release closes it.
    const lease = await machineConnections.acquire(options.machine);
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
      });
    } finally {
      lease.release();
    }
  } catch (error) {
    if (registered) {
      await rollbackFork(forkKey);
    }
    handleError(error);
  }
}
