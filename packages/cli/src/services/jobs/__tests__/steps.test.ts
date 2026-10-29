import { describe, expect, it } from 'vitest';
import {
  dueSteps,
  listStepNames,
  pendingStepNames,
  planStep,
  stepIsDue,
  toSpoolSteps,
  toTicketSteps,
  triggerOf,
} from '../steps.js';

describe('step registry', () => {
  it('registers the existing client-side steps by name', () => {
    expect(listStepNames()).toEqual(
      expect.arrayContaining([
        'postRepoUpTasks',
        'reconcileBackupSchedules',
        'recordPushBase',
        'recordBackupRun',
        'recordBackupRunFailed',
        'migratePlacement',
        'rollbackCreate',
        'rollbackFork',
        'rollbackRestoreRegistration',
        'identityRefresh',
        'reportPushStats',
        'reportRestoreStats',
        'reportVerifyVerdict',
        'reportRestorePath',
      ])
    );
  });

  it('refuses an unknown step', () => {
    expect(() => planStep('noSuchStep')).toThrow(/Unknown step/);
  });

  it('keeps only declared scalar params and refuses a secret-looking key', () => {
    const step = planStep('postRepoUpTasks', {
      repo: 'web',
      machine: 'm1',
      extra: 'x',
      nested: {},
    });
    expect(step.params).toEqual({ repo: 'web', machine: 'm1' });
    expect(() => planStep('postRepoUpTasks', { repo: 'web', vault: '{"k":1}' })).toThrow(/secrets/);
    expect(() => planStep('postRepoUpTasks', { sshPrivateKey: 'x' })).toThrow(/secrets/);
  });

  it('writes the spool form renet parses, and the trigger is the registry one', () => {
    const steps = [
      planStep('migratePlacement', { repo: 'web', machine: 'm2' }),
      planStep('reportPushStats', { repo: 'web', target: 'm2', json: true }),
    ];
    expect(toSpoolSteps(steps)).toEqual([
      {
        name: 'migratePlacement',
        on: 'marker:cutover_complete',
        params: { repo: 'web', machine: 'm2' },
      },
      {
        name: 'reportPushStats',
        on: 'success',
        params: { repo: 'web', target: 'm2', json: true },
        needs_output: true,
      },
    ]);
    // The ticket mirror only knows success|failure; the registry restores the marker trigger.
    const mirrored = toTicketSteps(steps);
    expect(mirrored[0].on).toBe('success');
    expect(triggerOf(mirrored[0])).toBe('marker:cutover_complete');
  });
});

describe('stepIsDue', () => {
  it('a success step is due only on succeeded', () => {
    expect(stepIsDue('success', 'succeeded', undefined)).toBe(true);
    for (const state of ['failed', 'cancelled', 'running', 'unknown'] as const) {
      expect(stepIsDue('success', state, undefined)).toBe(false);
    }
  });

  it('a failure step is due only on failed or cancelled', () => {
    expect(stepIsDue('failure', 'failed', undefined)).toBe(true);
    expect(stepIsDue('failure', 'cancelled', undefined)).toBe(true);
    expect(stepIsDue('failure', 'succeeded', undefined)).toBe(false);
    expect(stepIsDue('failure', 'running', undefined)).toBe(false);
  });

  it('a marker step is due once its marker is seen, in any state', () => {
    expect(stepIsDue('marker:cutover_complete', 'running', ['cutover_complete'])).toBe(true);
    expect(stepIsDue('marker:cutover_complete', 'failed', ['cutover_complete'])).toBe(true);
    expect(stepIsDue('marker:cutover_complete', 'running', ['push'])).toBe(false);
    expect(stepIsDue('marker:cutover_complete', 'failed', ['push'])).toBe(false);
    // No stream seen: success implies the source job passed its last marker.
    expect(stepIsDue('marker:cutover_complete', 'succeeded', undefined)).toBe(true);
    expect(stepIsDue('marker:cutover_complete', 'failed', undefined)).toBe(false);
  });
});

describe('pending steps', () => {
  const steps = toTicketSteps([
    planStep('postRepoUpTasks', { repo: 'web', machine: 'm1' }),
    planStep('rollbackCreate', { repo: 'web' }),
  ]);

  it('a running ticket owes nothing yet', () => {
    expect(pendingStepNames({ steps, stepsDone: [], state: 'running' })).toEqual([]);
  });

  it('a finished ticket owes the steps of its outcome that are not done', () => {
    expect(pendingStepNames({ steps, stepsDone: [], state: 'succeeded' })).toEqual([
      'postRepoUpTasks',
    ]);
    expect(pendingStepNames({ steps, stepsDone: [], state: 'failed' })).toEqual(['rollbackCreate']);
    expect(pendingStepNames({ steps, stepsDone: ['postRepoUpTasks'], state: 'succeeded' })).toEqual(
      []
    );
  });

  it('dueSteps uses the markers it is given', () => {
    const migrate = toTicketSteps([planStep('migratePlacement', { repo: 'web', machine: 'm2' })]);
    expect(
      dueSteps({ steps: migrate, stepsDone: [] }, 'running', ['cutover_complete'])
    ).toHaveLength(1);
    expect(dueSteps({ steps: migrate, stepsDone: [] }, 'running', [])).toHaveLength(0);
  });
});
