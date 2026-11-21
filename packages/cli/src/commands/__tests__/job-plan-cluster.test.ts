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
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from 'vitest';

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
    updateCluster: provision.updateCluster,
    removeMachine: provision.removeMachine,
    allocateNetworkId: vi.fn().mockResolvedValue(7),
  },
}));
const clusterConfig = vi.hoisted(() => ({
  provider: 'kvm',
  pools: [
    { name: 'cp', role: 'k8s-server', count: 1 },
    { name: 'ag', role: 'k8s-agent', count: 1 },
  ] as { name: string; role: string; count: number }[],
}));
const provision = vi.hoisted(() => ({
  materialize: vi.fn().mockResolvedValue(undefined),
  updateCluster: vi.fn().mockResolvedValue(undefined),
  removeMachine: vi.fn().mockResolvedValue(undefined),
  bootstrap: vi.fn().mockResolvedValue(undefined),
  members: [] as { pool: string; index: number; ip: string }[],
}));
vi.mock('../../services/config/config-cluster-ops.js', () => ({
  getCluster: () => Promise.resolve(clusterConfig),
  materializeClusterMachines: provision.materialize,
  resolveControlNode: vi.fn().mockResolvedValue('c1-cp-1'),
}));
vi.mock('../../services/cluster/kvm-provisioner.js', () => ({
  provisionKvmCluster: () => Promise.resolve({ members: provision.members, kvm: {} }),
  teardownKvmCluster: vi.fn(),
}));
vi.mock('../../services/renet/machine-bootstrap.js', () => ({
  bootstrapMachine: provision.bootstrap,
  scanHostKeys: () => '',
  waitForSSH: () => Promise.resolve(),
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
const { registerClusterCommands } = await import('../cluster/index.js');
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

  it('datastore list prints the rows from the config and the state, filtered by place', async () => {
    m.listDatastores.mockResolvedValue({
      tier1: { backend: { kind: 'local' }, size: '1G', cluster: 'c1' },
      tier2: { backend: { kind: 'ceph' }, size: '2G' },
    });
    m.listDatastoreState.mockResolvedValue({ tier1: { attachedTo: 'm1', writes: 'local' } });
    // Per datastore: the row counts come from each one's own repositories, not from one constant answer.
    m.reposInDatastore.mockImplementation(async (name: string) =>
      name === 'tier1' ? ['r1', 'r2'] : ['r3']
    );
    onTestFinished(() => {
      m.listDatastores.mockResolvedValue({});
      m.reposInDatastore.mockResolvedValue([]);
    });

    await run('list');
    expect(m.print).toHaveBeenLastCalledWith(
      [
        {
          name: 'tier1',
          backend: 'local',
          size: '1G',
          cluster: 'c1',
          attachedTo: 'm1',
          writes: 'local',
          repos: 2,
        },
        {
          name: 'tier2',
          backend: 'ceph',
          size: '2G',
          cluster: undefined,
          attachedTo: undefined,
          writes: undefined,
          repos: 1,
        },
      ],
      'table'
    );

    await run('list', 'm1');
    expect(m.print.mock.lastCall?.[0]).toHaveLength(1);
    expect(m.print.mock.lastCall?.[0][0]).toMatchObject({ name: 'tier1' });
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

  it('snapshot create: renet refusing for no ceph datastore names the per-datastore fallback, with the exit code kept', async () => {
    const { createClusterSnapshot } = await import('../../services/cluster/cluster-snapshot.js');
    const { JobPreconditionRefusedError } = await import(
      '../../services/executor/detached-execution.js'
    );
    respond = (o) => {
      if (o.functionName === 'datastore_snapshot_create') {
        throw new JobPreconditionRefusedError(
          {
            refused: 'precondition',
            expect: 'ceph_datastores_exist',
            state: 'none',
            repository: '',
            repo_guid: '',
            message: 'Cluster c1 has no ceph-backed datastore.',
          },
          'c1-cp-1'
        );
      }
      return o.functionName === 'datastore_list' ? { ...FINISHED, stdout: '[]' } : undefined;
    };
    const failure = await createClusterSnapshot('c1', { snapshot: 's1' }).catch((e: unknown) => e);
    expect(failure).toMatchObject({
      message: expect.stringContaining('rdc datastore snapshot create <name>'),
      code: 'STATE_MISMATCH',
    });
    expect((failure as Error).message).toContain('Cluster c1 has no ceph-backed datastore.');
  });

  it('control: a refusal of another kind passes through without the snapshot hint', async () => {
    const { createClusterSnapshot } = await import('../../services/cluster/cluster-snapshot.js');
    const { JobPreconditionRefusedError } = await import(
      '../../services/executor/detached-execution.js'
    );
    respond = (o) => {
      if (o.functionName === 'datastore_snapshot_create') {
        throw new JobPreconditionRefusedError(
          {
            refused: 'precondition',
            expect: 'repo_unmounted',
            state: 'mounted',
            repository: 'r',
            repo_guid: 'g',
            message: 'still mounted',
          },
          'c1-cp-1'
        );
      }
      return o.functionName === 'datastore_list' ? { ...FINISHED, stdout: '[]' } : undefined;
    };
    const failure = await createClusterSnapshot('c1', { snapshot: 's1' }).catch((e: unknown) => e);
    expect((failure as Error).message).toBe('still mounted');
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

describe('cluster fork, migrate and rehearse (one job per phase, driven through the command)', () => {
  const machines: Record<string, Record<string, unknown>> = {
    'c1-cp-1': { ip: '10.0.0.1' },
    'c1-ag-1': { ip: '10.0.0.2' },
    'c2-cp-1': { ip: '10.0.1.1' },
    'c2-ag-1': { ip: '10.0.1.2' },
  };
  const DATASTORES = JSON.stringify([
    { name: 'ds-control-c1', backend: 'ceph', cluster: 'c1' },
    { name: 'data1', backend: 'ceph', cluster: 'c1' },
  ]);

  /** The machine's answers to the reads the chain consumes; `override` answers first and falls through. */
  const READS: Record<string, string> = {
    datastore_list: DATASTORES,
    datastore_fork: '{"name":"x"}',
    kube_join_token: 'token K10abc',
    ceph_client_config_export: '{"conf":"c","keyring":"k"}',
  };
  function scripted(override?: (o: Executed) => Record<string, unknown> | undefined) {
    return (o: Executed): Record<string, unknown> | undefined => {
      const first = override?.(o);
      if (first) return first;
      const stdout = READS[o.functionName] as string | undefined;
      return stdout === undefined ? undefined : { ...FINISHED, stdout };
    };
  }

  async function cluster(...argv: string[]): Promise<void> {
    const program = new Command();
    program.exitOverride();
    registerClusterCommands(program);
    await program.parseAsync(['node', 'rdc', 'cluster', ...argv]);
  }

  beforeEach(() => {
    cfg.getLocalMachine.mockImplementation((name: string) =>
      Promise.resolve(machines[name] ?? { ip: '10.0.9.9' })
    );
    respond = scripted();
    // The dest control node runs no k3s of its own: the fail-fast probe must fail for the fork to go on.
    m.direct.mockImplementation((options: unknown) => {
      direct.push(options as Executed);
      return Promise.resolve(
        (options as Executed).functionName === 'kube_health' ? FAILED : FINISHED
      );
    });
  });

  it('fork: every phase is its own job under the verb, with the chain in order and no job for the probe', async () => {
    await cluster('fork', 'c1', '--tag', 't1', '--to', 'c2');

    expect(executed.map((o) => [o.functionName, o.machineName])).toEqual([
      ['datastore_list', 'c1-cp-1'],
      ['datastore_snapshot_create', 'c1-cp-1'],
      ['datastore_fork', 'c1-cp-1'],
      ['datastore_adopt', 'c2-cp-1'],
      ['datastore_fork', 'c1-cp-1'],
      ['datastore_adopt', 'c2-cp-1'],
      ['datastore_attach', 'c2-cp-1'],
      ['datastore_attach', 'c2-cp-1'],
      ['kube_identity_rewrite', 'c2-cp-1'],
      ['kube_join_token', 'c2-cp-1'],
      ['kube_join', 'c2-ag-1'],
    ]);
    expect(direct.map((o) => o.functionName)).toEqual(['kube_health']);
    expect(cfg.audit).toHaveBeenCalledOnce();
    expect(m.success).toHaveBeenCalled();
  });

  it('fork: a phase still running stops the chain before the next phase starts', async () => {
    respond = scripted((o) =>
      o.functionName === 'datastore_snapshot_create' ? BACKGROUND : undefined
    );

    await expect(cluster('fork', 'c1', '--tag', 't1', '--to', 'c2')).rejects.toThrow(
      /still running/
    );
    expect(executed.map((o) => o.functionName).at(-1)).toBe('datastore_snapshot_create');
    expect(cfg.audit).not.toHaveBeenCalled();
  });

  it('fork: a failed phase throws with its function and machine, and the audit record is never written', async () => {
    respond = scripted((o) =>
      o.functionName === 'kube_identity_rewrite' ? { ...FAILED, error: 'rewrite broke' } : undefined
    );

    await expect(cluster('fork', 'c1', '--tag', 't1', '--to', 'c2')).rejects.toThrow(
      /kube_identity_rewrite.*c2-cp-1/
    );
    expect(executed.map((o) => o.functionName)).not.toContain('kube_join');
    expect(cfg.audit).not.toHaveBeenCalled();
  });
  describe('cluster scale', () => {
    const base = [...clusterConfig.pools];
    beforeEach(() => {
      clusterConfig.pools = [
        { name: 'cp', role: 'k8s-server', count: 1 },
        { name: 'ag', role: 'k8s-agent', count: 3 },
      ];
    });
    afterEach(() => {
      clusterConfig.pools = [...base];
    });

    it('shrink: each removed member is a prep job on it, then a removal job on the control plane, highest first', async () => {
      await cluster('scale', 'c1', '--pool', 'ag', '--count', '1');

      expect(executed.map((o) => [o.functionName, o.machineName])).toEqual([
        ['kube_prep_fork', 'c1-ag-3'],
        ['kube_node_remove', 'c1-cp-1'],
        ['kube_prep_fork', 'c1-ag-2'],
        ['kube_node_remove', 'c1-cp-1'],
      ]);
      expect(provision.updateCluster).toHaveBeenCalledOnce();
      expect(provision.removeMachine.mock.calls.map((call) => call[0])).toEqual([
        'c1-ag-3',
        'c1-ag-2',
      ]);
      expect(cfg.audit).toHaveBeenCalledOnce();
    });

    it('shrink: a phase still running stops the chain, records no pool count and drops no machine', async () => {
      respond = (o) => (o.functionName === 'kube_node_remove' ? BACKGROUND : undefined);

      await expect(cluster('scale', 'c1', '--pool', 'ag', '--count', '1')).rejects.toThrow(
        /still running/
      );

      expect(executed.map((o) => o.functionName)).toEqual(['kube_prep_fork', 'kube_node_remove']);
      expect(provision.updateCluster).not.toHaveBeenCalled();
      expect(provision.removeMachine).not.toHaveBeenCalled();
    });

    it('control: a count equal to the current one starts no job', async () => {
      await cluster('scale', 'c1', '--pool', 'ag', '--count', '3');

      expect(executed).toEqual([]);
    });
  });

  describe('cluster create over a ceph pool: one prerequisites job per member under one group', () => {
    const base = [...clusterConfig.pools];
    beforeEach(() => {
      clusterConfig.pools = [{ name: 'ceph', role: 'ceph', count: 3 }];
      provision.members = [1, 2, 3].map((index) => ({
        pool: 'ceph',
        index,
        ip: `10.0.2.${index}`,
      }));
      m.direct.mockImplementation((options: unknown) => {
        direct.push(options as Executed);
        // No mon answers yet, so the full install runs.
        return Promise.resolve(FAILED);
      });
    });
    afterEach(() => {
      clusterConfig.pools = [...base];
    });

    const groupOf = (call: Executed) =>
      call.jobSteps?.map((step) => ({ name: step.name, ...step.params }));

    it('starts three prerequisites jobs whose gates name one group and all three members, then the ceph chain', async () => {
      await cluster('create', 'c1');

      expect(executed.map((o) => [o.functionName, o.machineName])).toEqual([
        ['ceph_install_prerequisites', 'c1-ceph-1'],
        ['ceph_install_prerequisites', 'c1-ceph-2'],
        ['ceph_install_prerequisites', 'c1-ceph-3'],
        ['ceph_bootstrap_cluster', 'c1-ceph-1'],
        ['ceph_cluster_create', 'c1-ceph-1'],
        ['ceph_pool_create', 'c1-ceph-1'],
      ]);
      const gates = executed.slice(0, 3).map(groupOf);
      for (const gate of gates) {
        expect(gate?.map((step) => step.name)).toEqual([
          'groupMemberSucceeded',
          'groupMemberFailed',
        ]);
        expect(gate?.[0]).toMatchObject({ expected: 'c1-ceph-1,c1-ceph-2,c1-ceph-3' });
      }
      const groups = gates.map((gate) => (gate?.[0] as { group?: string } | undefined)?.group);
      expect(groups[0]).toEqual(expect.stringMatching(/\S/));
      expect(new Set(groups).size).toBe(1);
      expect(provision.bootstrap).toHaveBeenCalledTimes(3);
      expect(cfg.audit).toHaveBeenCalledOnce();
    });

    it('a failure on one member throws with the member named, and the bootstrap never starts', async () => {
      respond = (o) =>
        o.functionName === 'ceph_install_prerequisites' && o.machineName === 'c1-ceph-2'
          ? { ...FAILED, error: 'apt failed' }
          : undefined;

      await expect(cluster('create', 'c1')).rejects.toThrow(/c1-ceph-2: apt failed/);

      expect(executed.map((o) => o.functionName)).not.toContain('ceph_bootstrap_cluster');
      expect(cfg.audit).not.toHaveBeenCalled();
    });

    it('a member still running past its window stops the chain with the named pending error', async () => {
      respond = (o) =>
        o.functionName === 'ceph_install_prerequisites' && o.machineName === 'c1-ceph-3'
          ? BACKGROUND
          : undefined;

      const failure = await cluster('create', 'c1').catch((e: unknown) => e);

      expect((failure as Error).message).toMatch(/still running/);
      expect((failure as Error).message).toContain('"ceph_install_prerequisites" on c1-ceph-3 is');

      expect(executed.map((o) => o.functionName)).not.toContain('ceph_bootstrap_cluster');
    });

    it('control: a mon that already answers skips the prerequisites group', async () => {
      m.direct.mockImplementation((options: unknown) => {
        direct.push(options as Executed);
        return Promise.resolve(FINISHED);
      });

      await cluster('create', 'c1');

      expect(executed.map((o) => o.functionName)).toEqual(['ceph_pool_create']);
    });
  });

  describe('with a ceph pool', () => {
    const base = [...clusterConfig.pools];
    beforeEach(() => {
      clusterConfig.pools = [...base, { name: 'ceph', role: 'ceph', count: 1 }];
    });
    afterEach(() => {
      clusterConfig.pools = [...base];
    });

    it('migrate: the registry paperwork, the cutover and the forget are each their own job, in order', async () => {
      // The one direct kube_health is the post-cutover gate (it must pass to release the source); migrate runs no
      // destination probe, which is the fork's refuse-if-already-serving check and wants a failing health.
      m.direct.mockImplementation((options: unknown) => {
        direct.push(options as Executed);
        return Promise.resolve(FINISHED);
      });

      await cluster('migrate', 'c1', '--to', 'c2-cp-1');

      const phases = executed.map((o) => [o.functionName, o.machineName]);
      expect(phases).toContainEqual(['datastore_adopt', 'c2-cp-1']);
      expect(phases.slice(-5)).toEqual([
        ['kube_prep_fork', 'c1-cp-1'],
        ['datastore_detach', 'c1-cp-1'],
        ['datastore_attach', 'c2-cp-1'],
        ['kube_identity_rewrite', 'c2-cp-1'],
        ['datastore_forget', 'c1-cp-1'],
      ]);
      expect(direct.map((o) => o.functionName)).toEqual(['kube_health']);
      expect(cfg.audit).toHaveBeenCalledOnce();
    });

    it('migrate: a failed destination attach rolls the source back and records no audit', async () => {
      respond = scripted((o) =>
        o.functionName === 'datastore_attach' && o.machineName === 'c2-cp-1'
          ? { ...FAILED, error: 'fence refused' }
          : undefined
      );

      await expect(cluster('migrate', 'c1', '--to', 'c2-cp-1')).rejects.toThrow(/ROLLED BACK/);

      expect(executed.slice(-2).map((o) => [o.functionName, o.machineName])).toEqual([
        ['datastore_attach', 'c1-cp-1'],
        ['kube_identity_rewrite', 'c1-cp-1'],
      ]);
      expect(cfg.audit).not.toHaveBeenCalled();
    });

    it('migrate: a failed rollback is reported as not finished, never as ROLLED BACK', async () => {
      respond = scripted((o) => {
        if (o.functionName === 'datastore_attach') return { ...FAILED, error: 'fence refused' };
        return undefined;
      });

      const failure = await cluster('migrate', 'c1', '--to', 'c2-cp-1').catch((e: unknown) => e);

      expect((failure as Error).message).toMatch(/rollback to "c1-cp-1" did NOT finish/);
      expect((failure as Error).message).not.toMatch(/ROLLED BACK/);
      expect((failure as Error).message).toContain('fence refused');
    });

    it('rehearse: the fork phases run, then the discard runs as phases of its own', async () => {
      let probes = 0;
      m.direct.mockImplementation((options: unknown) => {
        direct.push(options as Executed);
        // The first kube_health is the dest probe, which must fail; the gate after the fork must pass.
        if ((options as Executed).functionName === 'kube_health') probes += 1;
        return Promise.resolve(
          probes === 1 && (options as Executed).functionName === 'kube_health' ? FAILED : FINISHED
        );
      });

      await cluster('rehearse', 'c1', '--on', 'c2', '--tag', 'r1');

      const names = executed.map((o) => o.functionName);
      expect(names).toContain('kube_identity_rewrite');
      expect(names.slice(-3)).toEqual(['kube_uninstall', 'datastore_detach', 'datastore_detach']);
      expect(executed.at(-1)?.params).toMatchObject({ name: 'data1:r1', discard: true });
      expect(executed.at(-1)?.machineName).toBe('c2-cp-1');
    });

    it('rehearse: a fork that fails still discards on the destination control machine, and the failure is the one thrown', async () => {
      respond = scripted((o) =>
        o.functionName === 'kube_identity_rewrite'
          ? { ...FAILED, error: 'rewrite broke' }
          : undefined
      );

      await expect(cluster('rehearse', 'c1', '--on', 'c2', '--tag', 'r1')).rejects.toThrow(
        /kube_identity_rewrite/
      );

      const discard = executed.filter((o) => o.functionName === 'kube_uninstall');
      expect(discard).toHaveLength(1);
      expect(discard[0].machineName).toBe('c2-cp-1');
    });
  });
});
