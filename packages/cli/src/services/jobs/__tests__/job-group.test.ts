/**
 * One command's jobs on several machines under one ticket group (PLAN-detached-jobs J19, section 14).
 *
 * The executor is a recording fake behind the runCommandJob seam, the ticket store is real in a temp directory, and the
 * step claim grants every claim. The group's own steps are the registered audit step, told apart by the function it
 * records, so the test sees how often each ran.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installJobDeps } from '../../../commands/__tests__/job-deps.js';

const audit = vi.hoisted(() => ({ recorded: [] as { functionName: string }[] }));
vi.mock('../../core/audit.js', () => ({
  auditService: {
    recordOperation: (entry: { functionName: string }) => {
      audit.recorded.push(entry);
    },
  },
}));

const { RequestIdMinter, withInvocationMinter } = await import('../attach.js');
const { runJobGroup } = await import('../job-group.js');
const { planStep, resolveStepHandler } = await import('../steps.js');

const MEMBERS = ['m1', 'm2', 'm3'].map((machineName) => ({
  machineName,
  functionName: 'ceph_install_prerequisites',
  params: {},
}));
const groupSteps = {
  success: [planStep('recordClusterAudit', { function: 'group_ok', machine: 'cluster' })],
  failure: [planStep('recordClusterAudit', { function: 'group_failed', machine: 'cluster' })],
};
const OK = { success: true, exitCode: 0, durationMs: 1, state: 'succeeded' as const };

type Executed = {
  machineName: string;
  jobSteps?: { name: string; params: Record<string, unknown> }[];
};

let configDir: string;
let prevXdg: string | undefined;
let executed: Executed[];
let answer: (machine: string) => Record<string, unknown>;
let restore: () => void;

beforeEach(() => {
  audit.recorded.length = 0;
  executed = [];
  answer = () => OK;
  configDir = mkdtempSync(join(tmpdir(), 'job-group-'));
  prevXdg = process.env.XDG_CONFIG_HOME;
  process.env.XDG_CONFIG_HOME = configDir;
  restore = installJobDeps((options) => {
    executed.push(options as unknown as Executed);
    return Promise.resolve(answer(options.machineName) as never);
  });
});

afterEach(() => {
  restore();
  if (prevXdg === undefined) delete process.env.XDG_CONFIG_HOME;
  else process.env.XDG_CONFIG_HOME = prevXdg;
  rmSync(configDir, { recursive: true, force: true });
});

const recorded = () => audit.recorded.map((r) => r.functionName);

describe('runJobGroup', () => {
  it('makes one job per member under one group and runs the success step once, after all three succeeded', async () => {
    const result = await runJobGroup('cluster create', MEMBERS, groupSteps);

    expect(executed.map((e) => e.machineName).sort((a, b) => a.localeCompare(b))).toEqual([
      'm1',
      'm2',
      'm3',
    ]);
    const groups = new Set(executed.map((e) => String(e.jobSteps?.[0].params.group)));
    expect(groups.size).toBe(1);
    expect(groups.has(result.group)).toBe(true);
    expect(recorded()).toEqual(['group_ok']);
    expect(result.pending).toBe(false);
  });

  it('a failure on one member runs the failure step once and the success step never, and throws', async () => {
    answer = (machine) =>
      machine === 'm2' ? { ...OK, success: false, exitCode: 1, state: 'failed' } : OK;

    await expect(runJobGroup('cluster create', MEMBERS, groupSteps)).rejects.toThrow(/m2/);

    expect(recorded()).toEqual(['group_failed']);
  });

  it('a member that cannot start counts as a finished failure, so the group still settles once', async () => {
    restore();
    restore = installJobDeps((options) => {
      executed.push(options as unknown as Executed);
      if (options.machineName === 'm3') return Promise.reject(new Error('refused'));
      return Promise.resolve(OK as never);
    });

    await expect(runJobGroup('cluster create', MEMBERS, groupSteps)).rejects.toThrow(/m3: refused/);

    expect(recorded()).toEqual(['group_failed']);
  });

  it('holds the group steps while a member is still running, and the later observer runs them once', async () => {
    answer = (machine) => (machine === 'm3' ? { ...OK, state: 'running' } : OK);

    const result = await runJobGroup('cluster create', MEMBERS, groupSteps);

    expect(result.pending).toBe(true);
    expect(result.pendingMachines).toEqual(['m3']);
    expect(recorded()).toEqual([]);

    // The observer of m3's finish runs the ticket's gate: the one that completes the group settles it.
    const gate = executed.find((e) => e.machineName === 'm3')?.jobSteps?.[0];
    if (!gate) throw new Error('no gate on the pending member ticket');
    const handler = await resolveStepHandler('groupMemberSucceeded');
    const ctx = {
      jobId: 'j3',
      machine: 'm3',
      params: gate.params as never,
      state: 'succeeded' as const,
    };
    await handler(ctx);
    await handler(ctx);
    expect(recorded()).toEqual(['group_ok']);
  });

  it('a retried served invocation names the same group, so its members settle one group', async () => {
    const attempt = () =>
      withInvocationMinter(new RequestIdMinter('inv-1'), () =>
        runJobGroup('cluster create', MEMBERS, groupSteps)
      );
    const first = await attempt();
    const retried = await attempt();

    expect(first.group).toBe('inv-1.group.1');
    expect(retried.group).toBe(first.group);
    expect(recorded()).toEqual(['group_ok']);
  });

  it('control: two local groups in one run are two groups', async () => {
    const first = await runJobGroup('cluster create', MEMBERS);
    const second = await runJobGroup('cluster create', MEMBERS);

    expect(second.group).not.toBe(first.group);
  });

  it('control: members with no group steps settle without running anything', async () => {
    await runJobGroup('cluster create', MEMBERS);

    expect(recorded()).toEqual([]);
  });
});
