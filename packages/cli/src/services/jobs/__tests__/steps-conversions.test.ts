/**
 * The client-side steps of the conversion boxes (PLAN-detached-jobs J16-J20, C2).
 *
 * Every step a JOB_PLANS entry names (column 4 of the J0b audit) must be registered and must resolve to a handler.
 * A step whose function is private to its module is a `boundStep`: it resolves only once that module calls
 * `bindStepHandler`. Those are listed in AWAITING_BIND and must still fail with StepHandlerUnboundError, so a bind that
 * lands forces its name out of the list rather than leaving the list stale.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { configService } from '../../config/config-resources.js';
import { outputService } from '../../core/output.js';
import { JOB_PLANS } from '../plans.js';
import {
  getStepDefinition,
  listStepNames,
  planStep,
  resolveStepHandler,
  type StepContext,
  StepHandlerUnboundError,
} from '../steps.js';

/** Steps whose module has not bound its handler yet, each with the module that must bind it. */
const AWAITING_BIND: Record<string, string> = {
  renderAutostartList: 'commands/repo-extended.ts',
  reportRepoFsck: 'commands/repo-maintenance.ts',
  reportRepoGc: 'commands/repo-maintenance.ts',
  recordCanary: 'services/cluster/repo-release.ts',
  forgetCanary: 'services/cluster/repo-release.ts',
  printRepoCat: 'commands/repo-cat.ts',
  renderRepoDiff: 'commands/repo-diff.ts',
  mirrorGpuGrants: 'commands/repo-gpu.ts',
  renderRepoList: 'commands/repo-batch-utils.ts',
  renderRepoLog: 'commands/repo-branching.ts',
  renderPolicyResult: 'commands/repo-policy.ts',
  renderRepoPrune: 'commands/repo-prune.ts',
  printRepoStatus: 'commands/repo.ts',
  renderRepoTrim: 'commands/repo-trim.ts',
  renderBackupBrowse: 'commands/backup-storage.ts',
  renderBackupList: 'commands/repo-backup-list.ts',
  seedStrategyRetention: 'commands/backup-ops.ts',
  renderBackupStatus: 'commands/backup-ops.ts',
  reconcileConfigState: 'commands/config.ts',
  settleConverge: 'commands/machine/converge.ts',
  settleConvergeFailed: 'commands/machine/converge.ts',
  renderGpuList: 'commands/machine/gpu.ts',
  renderMachineHealth: 'commands/machine/health.ts',
  ensureMachineDns: 'services/provision/infra-provision.ts',
  cleanupSshArtifacts: 'commands/machine/prune.ts',
  renderPruneOutcome: 'commands/machine/prune.ts',
  renderRestartServices: 'commands/machine/restart-services.ts',
  renderMachineStatus: 'commands/machine/status.ts',
  reportClusterSnapshot: 'services/cluster/cluster-snapshot.ts',
  renderSubscriptionRefresh: 'commands/subscription-actions.ts',
  renderSubscriptionStatus: 'commands/subscription-actions.ts',
};

const planned = [
  ...new Set(Object.values(JOB_PLANS).flatMap((plan) => [...(plan.steps ?? [])])),
].sort((a, b) => a.localeCompare(b));

/** `resolved`, `unbound` (StepHandlerUnboundError), or the failure text. */
async function resolution(name: string): Promise<string> {
  try {
    const handler = await resolveStepHandler(name);
    return typeof handler === 'function' ? 'resolved' : 'not a function';
  } catch (error) {
    if (error instanceof StepHandlerUnboundError) return 'unbound';
    return error instanceof Error ? error.message : String(error);
  }
}

function ctx(overrides: Partial<StepContext>): StepContext {
  return { jobId: 'job-1', machine: 'm1', params: {}, state: 'succeeded', ...overrides };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('conversion steps', () => {
  it('the plans name the audited steps', () => {
    expect(planned.length).toBeGreaterThan(40);
  });

  it('every step a plan names is registered', () => {
    expect(planned.filter((name) => !getStepDefinition(name))).toEqual([]);
  });

  it('every awaiting-bind step is registered and named by a plan', () => {
    for (const name of Object.keys(AWAITING_BIND)) {
      expect(getStepDefinition(name), name).toBeDefined();
      expect(planned, name).toContain(name);
    }
  });

  it('every registered step resolves, except the ones awaiting their bind', async () => {
    const failed: string[] = [];
    for (const name of listStepNames().filter((n) => !(n in AWAITING_BIND))) {
      const outcome = await resolution(name);
      if (outcome !== 'resolved') failed.push(`${name}: ${outcome}`);
    }
    expect(failed).toEqual([]);
  }, 60_000);

  it('an awaiting-bind step still fails as unbound, so a landed bind leaves the list', async () => {
    const stale: string[] = [];
    for (const name of Object.keys(AWAITING_BIND)) {
      const outcome = await resolution(name);
      if (outcome !== 'unbound') stale.push(`${name}: ${outcome}`);
    }
    expect(stale).toEqual([]);
  }, 60_000);

  it('no planned step declares a secret-looking param', () => {
    for (const name of planned) {
      const def = getStepDefinition(name);
      for (const key of def?.params ?? []) {
        expect(() => planStep(name, { [key]: 'x' }), `${name}.${key}`).not.toThrow();
      }
    }
  });
});

describe('conversion step handlers', () => {
  it('advanceHeadCommit moves the tip of the named repo', async () => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({ repositoryGuid: 'g' } as never);
    vi.spyOn(configService, 'getRepositoryKey').mockResolvedValue('app:latest');
    const add = vi.spyOn(configService, 'addRepository').mockResolvedValue(undefined as never);

    await (await resolveStepHandler('advanceHeadCommit'))(
      ctx({ params: { repo: 'app', commit: 'c-1' } })
    );

    expect(add).toHaveBeenCalledWith('app:latest', { repositoryGuid: 'g', headCommit: 'c-1' });
  });

  it('recordRepoCommit registers the commit object and advances the working tip', async () => {
    vi.spyOn(configService, 'getRepository').mockResolvedValue({
      repositoryGuid: 'g',
      networkId: 7,
      credential: 'cred-ref',
      headCommit: 'old',
    } as never);
    vi.spyOn(configService, 'getRepositoryKey').mockResolvedValue('app:latest');
    const add = vi.spyOn(configService, 'addRepository').mockResolvedValue(undefined as never);

    await (await resolveStepHandler('recordRepoCommit'))(
      ctx({ params: { repo: 'app', commit: 'c-2', message: 'm', parent: 'old' } })
    );

    expect(add).toHaveBeenNthCalledWith(
      1,
      'c-2',
      expect.objectContaining({
        repositoryGuid: 'c-2',
        grandGuid: 'g',
        parentGuid: 'g',
        immutable: true,
        commitMessage: 'm',
        commitParent: 'old',
      })
    );
    expect(add).toHaveBeenNthCalledWith(
      2,
      'app:latest',
      expect.objectContaining({ headCommit: 'c-2' })
    );
  });

  it('setDatastoreState stamps attachedAt from the job finish when the plan leaves it out', async () => {
    const setBucket = vi.spyOn(configService, 'setStateBucket').mockResolvedValue(undefined);
    vi.spyOn(configService, 'getCurrent').mockResolvedValue({ state: { datastores: {} } } as never);

    await (await resolveStepHandler('setDatastoreState'))(
      ctx({
        params: { datastore: 'ds1', state: JSON.stringify({ attachedTo: 'm2', mounted: true }) },
        finishedAt: '2026-10-29T12:00:00.000Z',
      })
    );

    expect(setBucket).toHaveBeenCalledWith('datastores', {
      ds1: { attachedTo: 'm2', mounted: true, attachedAt: '2026-10-29T12:00:00.000Z' },
    });
  });

  it('updateMachineCluster sets and clears the membership backref', async () => {
    const update = vi.spyOn(configService, 'updateMachine').mockResolvedValue(undefined);
    const handler = await resolveStepHandler('updateMachineCluster');

    await handler(ctx({ params: { machine: 'n1', cluster: 'c1', pool: 'agents' } }));
    await handler(ctx({ params: { machine: 'n1' } }));

    expect(update).toHaveBeenNthCalledWith(1, 'n1', { cluster: { cluster: 'c1', pool: 'agents' } });
    expect(update).toHaveBeenNthCalledWith(2, 'n1', { cluster: undefined });
  });

  it('removeClusterMembers removes the records above the target count and ignores a missing one', async () => {
    const remove = vi
      .spyOn(configService, 'removeMachine')
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('Machine not found'));

    await (await resolveStepHandler('removeClusterMembers'))(
      ctx({ params: { cluster: 'c1', pool: 'agents', targetCount: 1, currentCount: 3 } })
    );

    expect(remove.mock.calls.map((c) => c[0])).toEqual(['c1-agents-3', 'c1-agents-2']);
  });

  it('printCapturedJson prints the job output as data', async () => {
    const print = vi.spyOn(outputService, 'print').mockImplementation(() => undefined);

    await (await resolveStepHandler('printCapturedJson'))(ctx({ output: '{"snapshots":["s1"]}' }));

    expect(print).toHaveBeenCalledWith({ snapshots: ['s1'] }, expect.anything());
  });
});
