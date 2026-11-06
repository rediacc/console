/**
 * One cluster phase as one machine job (PLAN-detached-jobs J19, sections 14 and 18).
 *
 * A cluster verb sequences renet calls across several machines, and a later call consumes an earlier one (the token
 * read feeds the join, the identity rewrite follows the attach) or a client decision sits between them. renet has no
 * compound function for those chains, so each phase is its own job on its own ticket (a phase over every member is one
 * job per member under one group, services/jobs/job-group.ts), started through `runCommandJob` under the verb's name,
 * and the client drives the order. The audit record and the config writes of a verb that has a single closing call ride that call's ticket as steps; a chain never ends
 * early, because a phase still running past the attach window stops the chain with a named error instead of letting
 * the next phase start before the previous one finished.
 */

import { AsyncLocalStorage } from 'node:async_hooks';
import { DEFAULTS } from '@rediacc/shared/config';
import type { ExecuteResult, RepoExpectation } from '../executor/types.js';
import { runCommandJob } from '../jobs/command-job.js';
import { DEFAULT_STEP_LABEL } from '../jobs/job-group.js';
import { outstandingSteps } from '../jobs/run-job.js';
import type { PlannedStep } from '../jobs/steps.js';

const DEFAULT_VERB = 'cluster';
const verbs = new AsyncLocalStorage<string>();

/** Run `fn` with `verb` as the label of every cluster phase it starts. */
export function withClusterVerb<T>(verb: string, fn: () => Promise<T>): Promise<T> {
  return verbs.run(verb, fn);
}

/** The verb label of the enclosing {@link withClusterVerb}, for a phase that starts its own group of jobs. */
export function clusterVerb(): string {
  return verbs.getStore() ?? DEFAULT_VERB;
}

/** A phase of a chain was still running when its attach window closed, so the next phase cannot start. */
export class ClusterPhasePendingError extends Error {
  constructor(
    readonly functionName: string,
    readonly machineName: string,
    readonly jobId: string | undefined
  ) {
    super(
      `Cluster phase "${functionName}" on ${machineName} is still running` +
        `${jobId ? ` (job ${jobId})` : ''}, and the next phase needs its result. ` +
        `This verb runs as one job per phase, so each phase has to finish before the next one starts: ` +
        `run it without --background, or wait with "rdc job wait".`
    );
    this.name = 'ClusterPhasePendingError';
  }
}

export interface ClusterPhaseOptions {
  debug?: boolean;
  capture?: boolean;
  /** Client-side steps this phase's ticket carries; they run once the job succeeded, wherever it is observed. */
  steps?: PlannedStep[];
  /** A start precondition renet checks before any unit exists (private/renet/pkg/jobs/precondition.go). */
  expect?: RepoExpectation;
  /** The verb label; defaults to the enclosing {@link withClusterVerb}. */
  verb?: string;
  /** Prefix of the failure message, e.g. `Cluster step`. */
  label?: string;
}

export interface ClusterPhaseResult {
  result: ExecuteResult;
  /** The phase is still running: only a phase that carries `steps` may return this. */
  pending: boolean;
  /** Steps of a finished phase that did not run to completion; `rdc job wait` settles them. */
  unfinished: string[];
}

/**
 * Run one renet function as a job with its own ticket. A finished failure throws with renet's message, as the old
 * per-module dispatch did. A pending phase throws {@link ClusterPhasePendingError} unless it carries steps, in which
 * case the ticket owes them and the caller must not report success.
 */
export async function runClusterPhase(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  options: ClusterPhaseOptions = {}
): Promise<ClusterPhaseResult> {
  const verb = options.verb ?? verbs.getStore() ?? DEFAULT_VERB;
  const outcome = await runCommandJob(
    verb,
    {
      functionName,
      machineName,
      params,
      debug: options.debug,
      captureOutput: options.capture,
      ...(options.expect ? { expect: options.expect } : {}),
    },
    options.steps ?? []
  );
  if (outcome.kind === 'pending') {
    if ((options.steps ?? []).length === 0) {
      throw new ClusterPhasePendingError(functionName, machineName, outcome.result.jobId);
    }
    return { result: outcome.result, pending: true, unfinished: [] };
  }
  if (!outcome.result.success) {
    throw new Error(
      `${options.label ?? DEFAULT_STEP_LABEL} "${functionName}" failed on ${machineName}: ${
        outcome.result.error ?? DEFAULTS.CLOUD.UNKNOWN_ERROR
      }`
    );
  }
  return { result: outcome.result, pending: false, unfinished: outstandingSteps(outcome.steps) };
}
