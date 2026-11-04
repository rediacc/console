/**
 * One command's jobs on several machines under one ticket group (PLAN-detached-jobs section 14, J19).
 *
 * A cluster phase that touches every member (a prerequisite install, say) starts one job per member machine, each on
 * its own ticket. The group is the command's id, minted once: every member's ticket carries the same pair of gate
 * steps, and the gates settle the group through the scratch store the way `config reconcile` does. Each member's gate
 * records its outcome and marks the member finished. Whichever observer sees the LAST member finish claims the
 * group's settlement (a directory create, so exactly one does) and runs the group's success steps when every member
 * succeeded, or its failure steps when any did not. The group steps therefore run once, however many tickets carry
 * the gates and in whatever order the jobs end.
 */

import { getEffectiveConfigName } from '../config/config-name.js';
import type { ExecuteOptions } from '../executor/types.js';
import { invocationMinter } from './attach.js';
import { runCommandJob } from './command-job.js';
import { ScratchStore } from './scratch-store.js';
import {
  bindStepHandler,
  type PlannedStep,
  planStep,
  resolveStepHandler,
  type StepContext,
} from './steps.js';

/** One member's job: the renet call, on the member's machine. */
export interface JobGroupMember {
  machineName: string;
  functionName: string;
  params: Record<string, unknown>;
}

export interface JobGroupSteps {
  /** Run once, after every member's job succeeded. */
  success?: PlannedStep[];
  /** Run once, after every member's job ended and at least one did not succeed. */
  failure?: PlannedStep[];
}

/** The failure prefix when a caller names none. */
export const DEFAULT_STEP_LABEL = 'Cluster step';

export interface JobGroupOptions {
  debug?: boolean;
  /** Prefix of the failure message. */
  label?: string;
}

export interface JobGroupResult {
  /** The group id the tickets carry. */
  group: string;
  /** At least one member's job was still running when its attach window closed: the group settles later. */
  pending: boolean;
}

interface GroupStepWire {
  name: string;
  params: Record<string, string | number | boolean>;
}

function toWire(steps: PlannedStep[] | undefined): string {
  const wire: GroupStepWire[] = (steps ?? []).map((s) => ({ name: s.name, params: s.params }));
  return JSON.stringify(wire);
}

function fromWire(raw: unknown): GroupStepWire[] {
  if (typeof raw !== 'string' || raw === '') return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed)) throw new Error('group step list is not a JSON array');
  return parsed as GroupStepWire[];
}

async function runWire(steps: GroupStepWire[], ctx: StepContext): Promise<void> {
  for (const step of steps) {
    const handler = await resolveStepHandler(step.name);
    await handler({ ...ctx, params: step.params });
  }
}

/**
 * Record one member's outcome, and settle the group when it was the last to finish. A member that finishes after the
 * group settled leaves no record (the scratch store drops a late write).
 */
async function settleMember(
  scratch: ScratchStore,
  input: { group: string; machine: string; expected: string[]; ok: boolean; reason: string },
  ctx: StepContext,
  steps: { success: GroupStepWire[]; failure: GroupStepWire[] }
): Promise<void> {
  scratch.write(
    input.group,
    input.machine,
    input.ok ? { ok: true, value: '' } : { ok: false, error: input.reason }
  );
  scratch.finish(input.group, input.machine);
  if (!scratch.allFinished(input.group, input.expected)) return;
  if (!scratch.claim(input.group)) return;
  const records = scratch.read(input.group);
  scratch.drop(input.group);
  const allOk = input.expected.every((m) => records.get(m)?.ok === true);
  await runWire(allOk ? steps.success : steps.failure, ctx);
}

function memberInput(ctx: StepContext, ok: boolean): Parameters<typeof settleMember>[1] {
  const expected = String(ctx.params.expected);
  return {
    group: String(ctx.params.group),
    machine: ctx.machine,
    expected: expected === '' ? [] : expected.split(','),
    ok,
    reason: `exit code ${ctx.exitCode ?? 1}`,
  };
}

function groupSteps(ctx: StepContext): { success: GroupStepWire[]; failure: GroupStepWire[] } {
  return { success: fromWire(ctx.params.onSuccess), failure: fromWire(ctx.params.onFailure) };
}

bindStepHandler('groupMemberSucceeded', (ctx) =>
  settleMember(
    new ScratchStore(getEffectiveConfigName()),
    memberInput(ctx, true),
    ctx,
    groupSteps(ctx)
  )
);

bindStepHandler('groupMemberFailed', (ctx) =>
  settleMember(
    new ScratchStore(getEffectiveConfigName()),
    memberInput(ctx, false),
    ctx,
    groupSteps(ctx)
  )
);

/**
 * Start one job per member under one group and wait for each inside its attach window. The group steps run once the
 * last member finished, whether that is here or in a later observer (`rdc job wait`, the notice, a proxy poll). A
 * member whose job cannot start counts as a finished failure, so the group still settles.
 */
export async function runJobGroup(
  verb: string,
  members: JobGroupMember[],
  groupStepsOf: JobGroupSteps = {},
  options: JobGroupOptions = {}
): Promise<JobGroupResult> {
  // From the invocation, so a retried request settles the group its first attempt's members report to. The scratch store's names take no colon.
  const group = invocationMinter().next('group').replaceAll(':', '.');
  const expected = members.map((m) => m.machineName);
  const gates = [
    planStep('groupMemberSucceeded', {
      group,
      expected: expected.join(','),
      onSuccess: toWire(groupStepsOf.success),
      onFailure: toWire(groupStepsOf.failure),
    }),
    planStep('groupMemberFailed', {
      group,
      expected: expected.join(','),
      onSuccess: toWire(groupStepsOf.success),
      onFailure: toWire(groupStepsOf.failure),
    }),
  ];
  const scratch = new ScratchStore(getEffectiveConfigName());
  const settled = await Promise.all(
    members.map((member) =>
      startMember(verb, member, gates, options.debug, async (reason) => {
        // No job started, so no ticket carries the gates: this member settles the group for itself.
        await settleMember(
          scratch,
          { group, machine: member.machineName, expected, ok: false, reason },
          { jobId: '', machine: member.machineName, params: {}, state: 'failed' },
          { success: [], failure: fromWire(toWire(groupStepsOf.failure)) }
        );
      })
    )
  );

  const errors = settled.flatMap((m) => (m.error === undefined ? [] : [m.error]));
  if (errors.length > 0) {
    throw new Error(`${options.label ?? DEFAULT_STEP_LABEL} failed on ${errors.join('; ')}`);
  }
  return { group, pending: settled.some((m) => m.pending) };
}

/** One member's start: pending past the window, or the failure text of a finished or never-started job. */
async function startMember(
  verb: string,
  member: JobGroupMember,
  gates: PlannedStep[],
  debug: boolean | undefined,
  onNotStarted: (reason: string) => Promise<void>
): Promise<{ pending: boolean; error?: string }> {
  const call: ExecuteOptions = {
    functionName: member.functionName,
    machineName: member.machineName,
    params: member.params,
    debug,
  };
  try {
    const outcome = await runCommandJob(verb, call, gates);
    if (outcome.kind === 'pending') return { pending: true };
    if (outcome.result.success) return { pending: false };
    return {
      pending: false,
      error: `${member.machineName}: ${outcome.result.error ?? `exit code ${outcome.result.exitCode}`}`,
    };
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    await onNotStarted(reason);
    return { pending: false, error: `${member.machineName}: ${reason}` };
  }
}
