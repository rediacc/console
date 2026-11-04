/**
 * PLAN-detached-jobs J19: a datastore verb is one machine job whose config record rides the ticket as a step.
 *
 * `datastore resize` and `datastore create` are the converted rows here. The executor is a recording fake behind the
 * runCommandJob seam, the ticket store is real in a temp directory, and the step claim grants every claim, so the
 * test sees each command's own plan: one `job start` per verb, the record as a success step, and no config write
 * from the command body itself.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const m = vi.hoisted(() => ({
  getDatastore: vi.fn(),
  recordDatastore: vi.fn().mockResolvedValue(undefined),
  listDatastores: vi.fn().mockResolvedValue({}),
  requireDatastoreHost: vi.fn().mockResolvedValue('m1'),
  setDatastoreState: vi.fn().mockResolvedValue(undefined),
  forgetDatastore: vi.fn().mockResolvedValue(undefined),
  listDatastoreState: vi.fn().mockResolvedValue({}),
  reposInDatastore: vi.fn().mockResolvedValue([]),
  childDatastores: vi.fn().mockResolvedValue([]),
  print: vi.fn(),
  direct: vi.fn(),
  success: vi.fn(),
}));
vi.mock('../../services/config/config-datastores.js', () => ({
  assertCreatableName: vi.fn(),
  at: (state: Record<string, unknown>, ref: string) => state[ref],
  getDatastore: m.getDatastore,
  listDatastores: m.listDatastores,
  listDatastoreState: m.listDatastoreState,
  forgetDatastore: m.forgetDatastore,
  setDatastoreState: m.setDatastoreState,
  reposInDatastore: m.reposInDatastore,
  childDatastores: m.childDatastores,
  parseDatastoreRef: (ref: string) => ({ name: ref }),
  recordDatastore: m.recordDatastore,
  requireDatastoreHost: m.requireDatastoreHost,
}));
const cfg = vi.hoisted(() => ({
  getLocalMachine: vi.fn(),
  updateMachine: vi.fn().mockResolvedValue(undefined),
  audit: vi.fn(),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({}),
    listClusters: vi.fn(),
    getLocalMachine: cfg.getLocalMachine,
    updateMachine: cfg.updateMachine,
    allocateNetworkId: vi.fn().mockResolvedValue(7),
  },
}));
vi.mock('../../services/config/config-cluster-ops.js', () => ({
  getCluster: vi.fn().mockResolvedValue({
    pools: [
      { name: 'cp', role: 'k8s-server', count: 1 },
      { name: 'ag', role: 'k8s-agent', count: 1 },
    ],
  }),
}));
vi.mock('../../services/config/network-id-discovery.js', () => ({
  targetFloor: vi.fn().mockResolvedValue(0),
}));
vi.mock('../../services/account/license-preflight.js', () => ({
  assertMachineSlotsAvailable: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/core/audit.js', () => ({ auditService: { recordOperation: cfg.audit } }));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: m.direct }),
}));
vi.mock('../../services/executor/local-executor.js', () => ({ parseCapturedJson: JSON.parse }));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: {
    DATASTORE_RESIZE: 'datastore resize',
    DATASTORE_CREATE: 'datastore create',
    DATASTORE_ATTACH: 'datastore attach',
    DATASTORE_DETACH: 'datastore detach',
    DATASTORE_FORK: 'datastore fork',
    DATASTORE_DELETE: 'datastore delete',
    DATASTORE_SNAPSHOT_CREATE: 'datastore snapshot create',
  },
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: m.success, warn: vi.fn(), print: m.print },
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getOutputFormat: () => 'table',
  handleError: (e: unknown) => {
    throw e;
  },
}));

const { registerDatastoreCommands } = await import('../datastore.js');
const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const { resolveStepHandler } = await import('../../services/jobs/steps.js');

type Executed = {
  functionName: string;
  machineName: string;
  params: Record<string, unknown>;
  jobSteps?: { name: string; on: string; params: Record<string, unknown> }[];
  captureOutput?: boolean;
  expect?: unknown;
};

const BACKGROUND = {
  success: true,
  exitCode: 0,
  durationMs: 0,
  state: 'running' as const,
  jobId: 'job-1',
  attached: false,
};
const FINISHED = { ...BACKGROUND, durationMs: 5, state: 'succeeded' as const, attached: true };
const FAILED = { ...FINISHED, success: false, exitCode: 1, state: 'failed' as const };

let dir: string;
let store: InstanceType<typeof TicketStore>;
let executed: Executed[];
let direct: Executed[];
let answer: Record<string, unknown>;
let respond: ((options: Executed) => Record<string, unknown> | undefined) | undefined;

async function run(...argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerDatastoreCommands(program);
  await program.parseAsync(['node', 'rdc', 'datastore', ...argv]);
}

beforeEach(() => {
  vi.clearAllMocks();
  m.getDatastore.mockResolvedValue({
    backend: { kind: 'local', machine: 'm1', path: '/x' },
    size: '1G',
  });
  m.requireDatastoreHost.mockResolvedValue('m1');
  m.listDatastoreState.mockResolvedValue({});
  m.direct.mockImplementation((options: unknown) => {
    direct.push(options as Executed);
    return Promise.resolve(FINISHED);
  });
  direct = [];
  dir = mkdtempSync(join(tmpdir(), 'job-plan-cluster-'));
  store = new TicketStore('test', dir);
  executed = [];
  answer = FINISHED;
  respond = undefined;
  setCommandJobDeps({
    executor: () => ({
      execute: (options) => {
        executed.push(options as unknown as Executed);
        return Promise.resolve((respond?.(options as unknown as Executed) ?? answer) as never);
      },
    }),
    store: () => store,
    stepDeps: () =>
      Promise.resolve({
        observer: { configName: 'test' },
        warn: () => undefined,
        claim: ({ steps }) =>
          Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const }))),
      }),
  });
});

afterEach(() => {
  setCommandJobDeps();
  rmSync(dir, { recursive: true, force: true });
  process.exitCode = 0;
});

describe('datastore resize (one job; the record as a success step)', () => {
  it('makes one job start on the holder with the record planned, not written by the command', async () => {
    answer = BACKGROUND;
    await run('resize', 'tier1', '--size', '2G');

    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({
      functionName: 'datastore_resize',
      machineName: 'm1',
      params: { name: 'tier1', size: '2G' },
    });
    expect(executed[0].jobSteps?.map((s) => [s.name, s.on])).toEqual([
      ['setDatastoreSize', 'success'],
    ]);
    // A job still running owes the record to its ticket; nothing is written and no success is claimed.
    expect(m.recordDatastore).not.toHaveBeenCalled();
    expect(m.success).not.toHaveBeenCalled();
    expect(store.tickets()[0].steps.map((s) => s.name)).toEqual(['setDatastoreSize']);
  });

  it('control: followed, the record is written once with the new size', async () => {
    await run('resize', 'tier1', '--size', '2G');
    expect(m.recordDatastore).toHaveBeenCalledExactlyOnceWith('tier1', {
      backend: { kind: 'local', machine: 'm1', path: '/x' },
      size: '2G',
    });
    expect(m.success).toHaveBeenCalledOnce();
  });

  it('merges the size into the record as it is when the step runs, not as it was planned', async () => {
    m.getDatastore.mockResolvedValueOnce({
      backend: { kind: 'local', machine: 'm2', path: '/moved' },
    });
    await run('resize', 'tier1', '--size', '2G');
    expect(m.recordDatastore).toHaveBeenCalledExactlyOnceWith('tier1', {
      backend: { kind: 'local', machine: 'm2', path: '/moved' },
      size: '2G',
    });
  });

  it('a failed job throws and records nothing', async () => {
    answer = FAILED;
    await expect(run('resize', 'tier1', '--size', '2G')).rejects.toThrow(/datastore_resize/);
    expect(m.recordDatastore).not.toHaveBeenCalled();
  });
});

describe('datastore create (one job; the record as a success step)', () => {
  it('records the new datastore only through the ticket step', async () => {
    answer = BACKGROUND;
    await run('create', 'tier2', '-m', 'm1', '--size', '10G');

    expect(executed.map((o) => o.functionName)).toEqual(['datastore_create']);
    const ticket = store.tickets()[0];
    expect(ticket.steps.map((s) => s.name)).toEqual(['recordDatastore']);
    expect(m.recordDatastore).not.toHaveBeenCalled();

    // The observer that sees the job finish runs the step from the ticket's recorded params.
    const step = ticket.steps[0];
    const handler = await resolveStepHandler('recordDatastore');
    await handler({
      jobId: 'job-1',
      machine: 'm1',
      params: step.params ?? {},
      state: 'succeeded',
    });
    expect(m.recordDatastore).toHaveBeenCalledExactlyOnceWith('tier2', {
      backend: { kind: 'local', machine: 'm1', path: '/mnt/rediacc-ds/tier2' },
      size: '10G',
    });
  });
});

const record = { backend: { kind: 'rbd', pool: 'p', image: 'i' }, size: '1G' };

describe('datastore reads (one read job, rendered by its step)', () => {
  it('status on an attached datastore is one job with the render planned', async () => {
    m.listDatastoreState.mockResolvedValue({ tier1: { attachedTo: 'm1' } });
    answer = { ...BACKGROUND };
    await run('status', 'tier1');
    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({ functionName: 'datastore_status', captureOutput: true });
    expect(executed[0].jobSteps?.map((x) => x.name)).toEqual(['renderDatastoreStatus']);
    expect(m.print).not.toHaveBeenCalled();
  });

  it('control: followed, the render prints the record and the live payload once', async () => {
    m.listDatastoreState.mockResolvedValue({ tier1: { attachedTo: 'm1' } });
    answer = { ...FINISHED, stdout: '{"state":"ok"}' };
    await run('status', 'tier1');
    expect(m.print).toHaveBeenCalledOnce();
    expect(m.print.mock.calls[0][0]).toMatchObject({
      name: 'tier1',
      attachedTo: 'm1',
      live: { state: 'ok' },
    });
  });

  it('status on a detached datastore starts no job', async () => {
    await run('status', 'tier1');
    expect(executed).toHaveLength(0);
    expect(m.print.mock.calls[0][0]).toMatchObject({ attached: false });
  });

  it('snapshot list is one read job whose step prints the captured list', async () => {
    answer = { ...FINISHED, stdout: '[{"label":"a"}]' };
    await run('snapshot', 'list', 'tier1');
    expect(executed.map((o) => [o.functionName, o.captureOutput])).toEqual([
      ['datastore_snapshot_list', true],
    ]);
    expect(executed[0].jobSteps?.map((x) => x.name)).toEqual(['printCapturedJson']);
    expect(m.print).toHaveBeenCalledExactlyOnceWith([{ label: 'a' }], 'table');
  });

  it('control: datastore list is config only and starts no job', async () => {
    await run('list');
    expect(executed).toHaveLength(0);
  });
});

describe('datastore snapshot create (one job, no steps)', () => {
  it('starts one job and reports only once it finished', async () => {
    await run('snapshot', 'create', 'tier1', '--snapshot', 's1');
    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({
      functionName: 'datastore_snapshot_create',
      params: { name: 'tier1', snapshot: 's1' },
    });
    expect(m.success).toHaveBeenCalledOnce();
  });

  it('a ticket handed back early claims no success', async () => {
    answer = BACKGROUND;
    await run('snapshot', 'create', 'tier1', '--snapshot', 's1');
    expect(executed).toHaveLength(1);
    expect(m.success).not.toHaveBeenCalled();
  });
});

describe('datastore detach and attach (one job; the routing hint as a step)', () => {
  beforeEach(() => {
    m.getDatastore.mockResolvedValue(record);
    m.listDatastoreState.mockResolvedValue({ tier1: { attachedTo: 'm1' } });
  });

  it('detach plans the lastHolder hint and, with --discard, the forget', async () => {
    answer = BACKGROUND;
    await run('detach', 'tier1', '--discard', '-y');
    expect(executed[0].jobSteps?.map((x) => x.name)).toEqual([
      'setDatastoreState',
      'forgetDatastore',
    ]);
    expect(m.setDatastoreState).not.toHaveBeenCalled();
    expect(m.forgetDatastore).not.toHaveBeenCalled();
  });

  it('control: followed, detach records the last holder once and forgets only with --discard', async () => {
    await run('detach', 'tier1');
    expect(m.setDatastoreState).toHaveBeenCalledExactlyOnceWith('tier1', { lastHolder: 'm1' });
    expect(m.forgetDatastore).not.toHaveBeenCalled();
  });

  it('a failed detach job records nothing', async () => {
    answer = FAILED;
    await expect(run('detach', 'tier1')).rejects.toThrow(/datastore_detach/);
    expect(m.setDatastoreState).not.toHaveBeenCalled();
  });

  it('a plain attach is one job on the target with the state as its step', async () => {
    m.listDatastoreState.mockResolvedValue({});
    answer = BACKGROUND;
    await run('attach', 'tier1', '--to', 'm2');
    expect(executed.map((o) => [o.functionName, o.machineName])).toEqual([
      ['datastore_attach', 'm2'],
    ]);
    expect(executed[0].jobSteps?.map((x) => x.name)).toEqual(['setDatastoreState']);
    expect(m.setDatastoreState).not.toHaveBeenCalled();
  });

  it('control: followed, a plain attach records the holder with a stamped attachedAt', async () => {
    m.listDatastoreState.mockResolvedValue({});
    await run('attach', 'tier1', '--to', 'm2');
    expect(m.setDatastoreState).toHaveBeenCalledOnce();
    expect(m.setDatastoreState.mock.calls[0][1]).toMatchObject({
      attachedTo: 'm2',
      mounted: true,
      attachedAt: expect.any(String),
    });
  });

  it('a relocation starts with the holder read job and chains adopt, detach, attach from its step', async () => {
    answer = { ...FINISHED, stdout: JSON.stringify([{ name: 'tier1', backend: 'ceph' }]) };
    await run('attach', 'tier1', '--to', 'm2');
    expect(executed.map((o) => [o.functionName, o.machineName])).toEqual([
      ['datastore_list', 'm1'],
    ]);
    expect(executed[0].jobSteps?.map((x) => x.name)).toEqual(['relocateDatastore']);
    expect(direct.map((o) => [o.functionName, o.machineName])).toEqual([
      ['datastore_adopt', 'm2'],
      ['datastore_detach', 'm1'],
      ['datastore_attach', 'm2'],
    ]);
    expect(m.setDatastoreState.mock.calls[0][1]).toMatchObject({ attachedTo: 'm2' });
  });

  it('a relocation handed back early has made no adopt, detach or attach', async () => {
    answer = BACKGROUND;
    await run('attach', 'tier1', '--to', 'm2');
    expect(direct).toHaveLength(0);
    expect(m.setDatastoreState).not.toHaveBeenCalled();
  });

  it('a local-backed relocation stops before any destructive call', async () => {
    answer = { ...FINISHED, stdout: JSON.stringify([{ name: 'tier1', backend: 'local' }]) };
    await run('attach', 'tier1', '--to', 'm2');
    expect(direct).toHaveLength(0);
    expect(process.exitCode).toBe(1);
  });
});

describe('datastore fork and delete (a second phase as a step)', () => {
  beforeEach(() => {
    m.getDatastore.mockResolvedValue(record);
  });

  it('fork is one job on the holder, the record is its step, and --attach-to adds the attach step', async () => {
    answer = BACKGROUND;
    await run('fork', 'tier1', '--tag', 't', '--attach-to', 'm2', '--writes', 'ceph');
    expect(executed.map((o) => [o.functionName, o.machineName])).toEqual([
      ['datastore_fork', 'm1'],
    ]);
    expect(executed[0].jobSteps?.map((x) => x.name)).toEqual([
      'recordDatastore',
      'attachForkedDatastore',
    ]);
    expect(m.recordDatastore).not.toHaveBeenCalled();
    expect(direct).toHaveLength(0);
  });

  it('control: followed, fork records the fork then attaches it on the second machine', async () => {
    await run('fork', 'tier1', '--tag', 't', '--attach-to', 'm2', '--writes', 'ceph');
    expect(m.recordDatastore.mock.calls[0][0]).toBe('tier1:t');
    expect(direct.map((o) => [o.functionName, o.machineName])).toEqual([
      ['datastore_attach', 'm2'],
    ]);
    expect(m.setDatastoreState.mock.calls[0][0]).toBe('tier1:t');
  });

  it('delete of an attached datastore detaches as the job and unlinks from its step', async () => {
    m.listDatastoreState.mockResolvedValue({ tier1: { attachedTo: 'm1' } });
    answer = BACKGROUND;
    await run('delete', 'tier1', '-y');
    expect(executed.map((o) => o.functionName)).toEqual(['datastore_detach']);
    expect(executed[0].jobSteps?.map((x) => x.name)).toEqual([
      'setDatastoreState',
      'deleteDatastoreTail',
    ]);
    // Nothing is unlinked while the detach has not finished.
    expect(direct).toHaveLength(0);
    expect(m.forgetDatastore).not.toHaveBeenCalled();
  });

  it('control: followed, delete clears the hint, deletes the pool, then forgets the record', async () => {
    m.listDatastoreState.mockResolvedValue({ tier1: { attachedTo: 'm1' } });
    await run('delete', 'tier1', '-y');
    expect(m.setDatastoreState).toHaveBeenCalledWith('tier1', undefined);
    expect(direct.map((o) => [o.functionName, o.machineName])).toEqual([
      ['datastore_delete', 'm1'],
    ]);
    expect(m.forgetDatastore).toHaveBeenCalledExactlyOnceWith('tier1');
  });

  it('delete of a detached datastore starts no job', async () => {
    await run('delete', 'tier1', '-y');
    expect(executed).toHaveLength(0);
    expect(m.forgetDatastore).toHaveBeenCalledExactlyOnceWith('tier1');
  });

  it('a failed detach never unlinks', async () => {
    m.listDatastoreState.mockResolvedValue({ tier1: { attachedTo: 'm1' } });
    answer = FAILED;
    await expect(run('delete', 'tier1', '-y')).rejects.toThrow(/datastore_detach/);
    expect(direct).toHaveLength(0);
    expect(m.forgetDatastore).not.toHaveBeenCalled();
  });
});

describe('cluster verbs (one job per phase, one ticket per phase)', () => {
  const machines: Record<string, Record<string, unknown>> = {
    'c1-cp-1': { ip: '10.0.0.1' },
    'c1-ag-1': { ip: '10.0.0.2' },
  };
  beforeEach(() => {
    machines['c1-ag-1'] = { ip: '10.0.0.2' };
    cfg.getLocalMachine.mockImplementation((name: string) =>
      Promise.resolve(machines[name] ?? { ip: '10.0.0.9' })
    );
  });

  it('join: one cluster_join job on the member, carrying the control plane and the membership steps', async () => {
    const { joinCluster } = await import('../../services/cluster/cluster-membership.js');
    respond = () => FINISHED;
    await joinCluster('c1-ag-1', { cluster: 'c1' });
    expect(executed.map((o) => [o.functionName, o.machineName])).toEqual([
      ['cluster_join', 'c1-ag-1'],
    ]);
    expect(executed[0].params).toMatchObject({ to: 'c1-cp-1', role: 'agent', bind_ip: '10.0.0.2' });
    expect(JSON.stringify(executed[0])).not.toContain('K10');
    expect(executed[0].jobSteps?.map((x) => x.name)).toEqual([
      'updateMachineCluster',
      'recordClusterAudit',
    ]);
    expect(cfg.updateMachine).toHaveBeenCalledExactlyOnceWith('c1-ag-1', {
      cluster: { cluster: 'c1', pool: 'ag' },
    });
    expect(cfg.audit).toHaveBeenCalledOnce();
  });

  it('join handed back running records no membership until its steps run', async () => {
    const { joinCluster } = await import('../../services/cluster/cluster-membership.js');
    respond = () => BACKGROUND;
    await joinCluster('c1-ag-1', { cluster: 'c1' });
    expect(executed.map((o) => o.functionName)).toEqual(['cluster_join']);
    expect(cfg.updateMachine).not.toHaveBeenCalled();
    expect(cfg.audit).not.toHaveBeenCalled();
  });

  it('a failed join job records no membership', async () => {
    const { joinCluster } = await import('../../services/cluster/cluster-membership.js');
    respond = () => FAILED;
    await expect(joinCluster('c1-ag-1', { cluster: 'c1' })).rejects.toThrow(/cluster_join/);
    expect(cfg.updateMachine).not.toHaveBeenCalled();
  });

  it('evict: node removal on the control plane, then the uninstall carrying the deregistration', async () => {
    const { evictCluster } = await import('../../services/cluster/cluster-membership.js');
    machines['c1-ag-1'] = { ip: '10.0.0.2', cluster: { cluster: 'c1', pool: 'ag' } };
    await evictCluster('c1-ag-1', {});
    expect(executed.map((o) => [o.functionName, o.machineName])).toEqual([
      ['kube_node_remove', 'c1-cp-1'],
      ['kube_uninstall', 'c1-ag-1'],
    ]);
    expect(executed[1].jobSteps?.map((x) => x.name)).toEqual([
      'updateMachineCluster',
      'recordClusterAudit',
    ]);
    expect(cfg.updateMachine).toHaveBeenCalledExactlyOnceWith('c1-ag-1', { cluster: undefined });
  });

  it('evict deregisters inline when the node-side uninstall fails (a dead node)', async () => {
    const { evictCluster } = await import('../../services/cluster/cluster-membership.js');
    machines['c1-ag-1'] = { ip: '10.0.0.2', cluster: { cluster: 'c1', pool: 'ag' } };
    respond = (o) => (o.functionName === 'kube_uninstall' ? FAILED : undefined);
    await evictCluster('c1-ag-1', {});
    expect(cfg.updateMachine).toHaveBeenCalledExactlyOnceWith('c1-ag-1', { cluster: undefined });
    expect(cfg.audit).toHaveBeenCalledOnce();
  });

  it('evict handed back at the node removal never uninstalls or deregisters', async () => {
    const { evictCluster } = await import('../../services/cluster/cluster-membership.js');
    machines['c1-ag-1'] = { ip: '10.0.0.2', cluster: { cluster: 'c1', pool: 'ag' } };
    answer = BACKGROUND;
    await evictCluster('c1-ag-1', {});
    expect(executed.map((o) => o.functionName)).toEqual(['kube_node_remove']);
    expect(cfg.updateMachine).not.toHaveBeenCalled();
  });

  it('snapshot create: the listing, then the group snapshot job carrying the report step', async () => {
    const { createClusterSnapshot } = await import('../../services/cluster/cluster-snapshot.js');
    respond = (o) =>
      o.functionName === 'datastore_list'
        ? {
            ...FINISHED,
            stdout: JSON.stringify([
              { name: 'ds-control-c1', backend: 'ceph', cluster: 'c1' },
              { name: 'scratch', backend: 'local', cluster: 'c1' },
            ]),
          }
        : undefined;
    await createClusterSnapshot('c1', { snapshot: 's1' });
    expect(executed.map((o) => o.functionName)).toEqual([
      'datastore_list',
      'datastore_snapshot_create',
    ]);
    expect(executed[1].params).toMatchObject({ group: 'c1', snapshot: 's1' });
    // The no-ceph-datastore refusal is renet's precondition now, carried on the group job only.
    expect(executed[1].expect).toBe('ceph_datastores_exist');
    expect(executed[0].expect).toBeUndefined();
    expect(executed[1].jobSteps?.map((x) => x.name)).toEqual(['reportClusterSnapshot']);
    expect(m.success).toHaveBeenCalledOnce();
  });

  it('snapshot create handed back claims no snapshot', async () => {
    const { createClusterSnapshot } = await import('../../services/cluster/cluster-snapshot.js');
    respond = (o) =>
      o.functionName === 'datastore_list'
        ? {
            ...FINISHED,
            stdout: JSON.stringify([{ name: 'ds-control-c1', backend: 'ceph', cluster: 'c1' }]),
          }
        : BACKGROUND;
    await createClusterSnapshot('c1', { snapshot: 's1' });
    expect(m.success).not.toHaveBeenCalled();
  });

  it('snapshot list is one read job whose step prints', async () => {
    const { listClusterSnapshots } = await import('../../services/cluster/cluster-snapshot.js');
    answer = { ...FINISHED, stdout: '[{"snapshot":"s1"}]' };
    await listClusterSnapshots('c1');
    expect(executed.map((o) => o.functionName)).toEqual(['datastore_snapshot_list']);
    expect(m.print).toHaveBeenCalledExactlyOnceWith([{ snapshot: 's1' }], 'table');
  });

  it('a chain phase still running stops the chain with a named error instead of starting the next phase', async () => {
    const { dispatch } = await import('../../services/cluster/cluster-kube.js');
    answer = BACKGROUND;
    await expect(dispatch('kube_install', 'c1-cp-1', {})).rejects.toThrow(/still running/);
  });

  it('control: a finished chain phase returns its result', async () => {
    const { dispatch } = await import('../../services/cluster/cluster-kube.js');
    const result = await dispatch('kube_install', 'c1-cp-1', {});
    expect(result.success).toBe(true);
    expect(executed).toHaveLength(1);
  });
});
