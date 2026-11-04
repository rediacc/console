import { describe, expect, it } from 'vitest';
import { buildSchedulePayload } from '../backup-schedule-execute.js';
import type {
  DesiredUnit,
  ReconcilePlan,
  RemoteUnitState,
  StrategyDiff,
} from '../backup-schedule-reconcile.js';

function file(exists: boolean) {
  return { path: '/x', exists, sha256: exists ? 'x' : null };
}

function removed(name: string, timer: boolean): StrategyDiff {
  const remote: RemoteUnitState = {
    serviceFile: file(timer),
    timerFile: file(timer),
    envFile: file(true),
    isActiveService: false,
    isActiveAdhoc: false,
    isEnabledTimer: timer,
    isActiveTimer: timer,
    isFailed: false,
  };
  return { name, action: 'removed', desired: null, remote, changedFiles: [] };
}

function plan(parts: Partial<ReconcilePlan>): ReconcilePlan {
  return {
    toCreate: [],
    toUpdate: [],
    toRemove: [],
    unchanged: [],
    skippedInFlight: [],
    daemonReloadNeeded: false,
    ...parts,
  };
}

function desired(name: string, over: Partial<DesiredUnit> = {}): DesiredUnit {
  return {
    strategyName: name,
    serviceContent: `service ${name}`,
    timerContent: `timer ${name}`,
    envFileContent: `TOKEN=${name}`,
    ...over,
  } as DesiredUnit;
}

function created(name: string, changed: StrategyDiff['changedFiles'], over?: Partial<DesiredUnit>) {
  return {
    name,
    action: 'created',
    desired: desired(name, over),
    remote: null,
    changedFiles: changed,
  } as StrategyDiff;
}

describe('buildSchedulePayload removals', () => {
  it('removes a strategy whose units are gone but whose env file was left behind, without a timer to disable', () => {
    const { remove } = buildSchedulePayload(
      plan({ toRemove: [removed('weekly-cold', false)] }),
      {}
    );
    expect(remove).toEqual([
      { name: 'weekly-cold', timer: false, service: false, env: true, dangling: false },
    ]);
  });

  it('marks a timer systemd still runs after its unit file is gone as dangling', () => {
    const diff = removed('ghost', false);
    if (diff.remote) diff.remote.isActiveTimer = true;
    expect(buildSchedulePayload(plan({ toRemove: [diff] }), {}).remove[0].dangling).toBe(true);
  });

  it('marks a timer that is only enabled, without its file, as dangling too', () => {
    const diff = removed('linked', false);
    if (diff.remote) diff.remote.isEnabledTimer = true;
    expect(buildSchedulePayload(plan({ toRemove: [diff] }), {}).remove[0].dangling).toBe(true);
  });

  it('keeps a timer that exists as a disable, never dangling', () => {
    const [r] = buildSchedulePayload(plan({ toRemove: [removed('nightly', true)] }), {}).remove;
    expect(r).toMatchObject({ name: 'nightly', timer: true, service: true, dangling: false });
  });

  it('skips a removal with no remote state', () => {
    const diff = { ...removed('x', true), remote: null };
    expect(buildSchedulePayload(plan({ toRemove: [diff] }), {}).remove).toEqual([]);
  });
});

describe('buildSchedulePayload writes', () => {
  it('carries the changed files of a created strategy, its reload and its timer enable', () => {
    const p = buildSchedulePayload(
      plan({ toCreate: [created('a', ['service', 'timer', 'env'])], daemonReloadNeeded: true }),
      {}
    );
    expect(p.files).toEqual([
      { name: 'a', kind: 'env', content: 'TOKEN=a' },
      { name: 'a', kind: 'service', content: 'service a' },
      { name: 'a', kind: 'timer', content: 'timer a' },
    ]);
    expect(p.reload).toBe(true);
    expect(p.enable).toEqual(['a']);
  });

  it('writes only the files that changed', () => {
    const p = buildSchedulePayload(plan({ toUpdate: [created('a', ['timer'])] }), {});
    expect(p.files.map((f) => f.kind)).toEqual(['timer']);
  });

  it('removes an env file that is no longer needed instead of writing an empty one', () => {
    const p = buildSchedulePayload(
      plan({ toUpdate: [created('a', ['env'], { envFileContent: '' })] }),
      {}
    );
    expect(p.files).toEqual([]);
    expect(p.remove_env).toEqual(['a']);
  });

  it('enables no timer for a timerless unit', () => {
    const p = buildSchedulePayload(
      plan({ toCreate: [created('fail', ['service'], { timerContent: '' })] }),
      {}
    );
    expect(p.enable).toEqual([]);
  });

  it('resets a failed service only with --reset-failed', () => {
    const diff = created('a', ['service']);
    diff.remote = { ...removed('a', true).remote, isFailed: true } as RemoteUnitState;
    expect(buildSchedulePayload(plan({ toUpdate: [diff] }), {}).reset_failed).toEqual([]);
    expect(
      buildSchedulePayload(plan({ toUpdate: [diff] }), { resetFailed: true }).reset_failed
    ).toEqual(['a']);
  });
});
