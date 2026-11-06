/**
 * `repo replicate`, `refresh` and `remove` as machine jobs (PLAN-detached-jobs).
 *
 * The executor is a small model of the machines behind the runCommandJob seam: per machine a datastore registry, one
 * shared pool of rbd images and snapshots, and the licences installed per fork id. It answers the renet compounds the
 * way private/renet/pkg/datastore/replica.go does, reuse included, so the kill-at-each-hop cases measure what a rerun
 * really converges to. The ticket store is real in a temp directory, and the step claim grants every claim.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { ReplicaSet } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { configService } from '../../config/config-resources.js';
import { outputService } from '../../core/output.js';
import { setCommandJobDeps } from '../../jobs/command-job.js';
import { runTicketSteps, type StepRunnerDeps } from '../../jobs/run-job.js';
import { resolveStepHandler } from '../../jobs/steps.js';
import { TicketStore } from '../../jobs/ticket-store.js';
import { removeReplicaSet, replicateRepo } from '../repo-replicate-ops.js';
import { __setReplicateClock } from '../repo-replicate-phase.js';
import { refreshReplicaSet } from '../repo-replicate-refresh.js';

vi.mock('../cluster-target.js', () => ({
  resolveExecutionTarget: vi.fn(() => Promise.resolve({ machineName: 'cp1', cluster: 'prod' })),
}));
vi.mock('../../config/config-cluster-ops.js', () => ({
  getCluster: vi.fn(() =>
    Promise.resolve({
      provider: 'kvm',
      pools: [{ name: 'w', role: 'hyperconverged', count: 2 }],
    })
  ),
}));

const lic = vi.hoisted(() => ({
  installed: new Set<string>(),
  issued: [] as string[],
  guid: 'guid-sqldb',
}));
vi.mock('../../account/free-license.js', () => ({
  issueFreeRepoLicense: vi.fn(
    (machine: string, _config: unknown, _key: unknown, params: { datastoreId: string }) => {
      lic.issued.push(params.datastoreId);
      lic.installed.add(`${machine}|${params.datastoreId}`);
      return Promise.resolve();
    }
  ),
  resolveLicenseAuthority: vi.fn().mockResolvedValue('free'),
}));
vi.mock('../../account/license.js', () => ({
  refreshRepoLicenseIdentity: vi.fn().mockResolvedValue(true),
  readRuntimeRepoLicenseStatuses: vi.fn((machine: string) =>
    Promise.resolve(
      [...lic.installed]
        .filter((key) => key.startsWith(`${machine}|`))
        .map((key) => ({
          repositoryGuid: lic.guid,
          datastoreId: key.slice(machine.length + 1),
          status: 'valid',
        }))
    )
  ),
}));
vi.mock('../../account/license-preflight.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../account/license-preflight.js')>()),
  assertMachineSlotsAvailable: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: vi.fn(),
}));
vi.mock('../../machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn(() =>
      Promise.resolve({ machine: {}, sshPrivateKey: 'key', sftp: {}, release: vi.fn() })
    ),
  },
}));

interface Call {
  functionName: string;
  machineName: string;
  params: Record<string, unknown>;
  jobSteps?: { name: string }[];
  captureOutput?: boolean;
}

interface ForkRecord {
  name: string;
  datastoreId: string;
  fork: { clonedFrom: string };
  attached: boolean;
}

/** One machine fleet. */
interface Model {
  registries: Map<string, Map<string, ForkRecord>>;
  images: Set<string>;
  snapshots: Set<string>;
  labels: Set<string>;
  opened: Set<string>;
  manifests: string[];
  nextId: number;
}

function newModel(): Model {
  return {
    registries: new Map(),
    images: new Set(),
    snapshots: new Set(),
    labels: new Set(),
    opened: new Set(),
    manifests: [],
    nextId: 1,
  };
}

function registry(model: Model, machine: string): Map<string, ForkRecord> {
  let reg = model.registries.get(machine);
  if (!reg) {
    reg = new Map();
    model.registries.set(machine, reg);
  }
  return reg;
}

const ok = (stdout?: string) => ({
  success: true,
  exitCode: 0,
  durationMs: 1,
  state: 'succeeded',
  jobId: 'job',
  ...(stdout === undefined ? {} : { stdout }),
});
const failed = (error: string) => ({
  success: false,
  exitCode: 1,
  durationMs: 1,
  state: 'failed',
  jobId: 'job',
  error,
});
const running = {
  success: true,
  exitCode: 0,
  durationMs: 0,
  state: 'running',
  jobId: 'job-running',
};

function replicaFork(model: Model, call: Call): ReturnType<typeof ok | typeof failed> {
  const parent = String(call.params.parent);
  const snapshot = String(call.params.snapshot);
  model.snapshots.add(snapshot);
  const tags = typeof call.params.tags === 'string' ? call.params.tags.split(',') : [];
  const reg = registry(model, call.machineName);
  const entries = [];
  for (const tag of tags) {
    const name = `${parent}:${tag}`;
    const existing = reg.get(name);
    if (existing) {
      if (existing.fork.clonedFrom !== snapshot)
        return failed(`fork ${name} from another snapshot`);
      entries.push({ tag, name, state: 'reused', record: existing });
    } else if (model.images.has(name)) {
      entries.push({ tag, name, state: 'placed' });
    } else {
      const record: ForkRecord = {
        name,
        datastoreId: `id-${model.nextId++}`,
        fork: { clonedFrom: snapshot },
        attached: false,
      };
      model.images.add(name);
      reg.set(name, record);
      entries.push({ tag, name, state: 'forked', record });
    }
  }
  return ok(JSON.stringify(entries));
}

function replicaAttach(model: Model, call: Call): ReturnType<typeof ok | typeof failed> {
  const name = String(call.params.name);
  const reg = registry(model, call.machineName);
  if (!reg.has(name) && typeof call.params.record_b64 === 'string') {
    reg.set(
      name,
      JSON.parse(Buffer.from(call.params.record_b64, 'base64').toString()) as ForkRecord
    );
  }
  const record = reg.get(name);
  if (!record) return failed(`datastore ${name} is not registered on ${call.machineName}`);
  record.attached = true;
  return ok(JSON.stringify(record));
}

function replicaDiscard(model: Model, call: Call): ReturnType<typeof ok> {
  const name = String(call.params.name);
  const reg = registry(model, call.machineName);
  if (reg.delete(name)) model.images.delete(name);
  for (const key of model.opened) if (key.startsWith(`${name}|`)) model.opened.delete(key);
  return ok();
}

function volumesOpen(model: Model, call: Call): ReturnType<typeof ok | typeof failed> {
  const name = String(call.params.name);
  const record = registry(model, call.machineName).get(name);
  if (!record?.attached) return failed(`${name} is not attached`);
  if (!lic.installed.has(`${call.machineName}|${record.datastoreId}`)) {
    return failed(`${name}: missing licence`);
  }
  model.opened.add(`${name}|${String(call.params.repo)}`);
  return ok();
}

function replicaPublish(model: Model, call: Call): ReturnType<typeof ok> {
  const labels = typeof call.params.labels === 'string' ? call.params.labels.split(',') : [];
  for (const label of labels) model.labels.add(label);
  if (typeof call.params.manifest === 'string') model.manifests.push(call.params.manifest);
  const forget = typeof call.params.forget === 'string' ? call.params.forget.split(',') : [];
  for (const name of forget) registry(model, call.machineName).delete(name);
  return ok();
}

function apply(model: Model, call: Call): ReturnType<typeof ok | typeof failed> {
  switch (call.functionName) {
    case 'replica_fork':
      return replicaFork(model, call);
    case 'replica_attach':
      return replicaAttach(model, call);
    case 'replica_discard':
      return replicaDiscard(model, call);
    case 'datastore_volumes_open':
      return volumesOpen(model, call);
    case 'replica_publish':
      return replicaPublish(model, call);
    case 'kube_node_label':
      for (const label of model.labels) {
        if (label.startsWith(`${String(call.params.datastore)}@`)) model.labels.delete(label);
      }
      return ok();
    case 'datastore_snapshot_delete':
      model.snapshots.delete(String(call.params.snapshot));
      return ok();
    case 'datastore_list':
      return ok(JSON.stringify([...registry(model, call.machineName).values()]));
    default:
      return ok();
  }
}

/** How the client dies at a hop: before the job starts, or with the job done and its answer lost. */
type Kill = 'before' | 'after';

function killAt(hop: number, kill: Kill): (call: Call, at: number) => unknown {
  return (call, at) => {
    if (at !== hop) return undefined;
    if (kill === 'after') apply(model, call);
    return new Error('client gone');
  };
}

let model: Model;
let calls: Call[];
let dir: string;
let store: TicketStore;
let warnings: string[];
let answer: ((call: Call, hop: number) => unknown) | undefined;
let stored: Record<string, ReplicaSet> | undefined;

const stepDeps: StepRunnerDeps = {
  observer: { configName: 'test' },
  warn: (line) => warnings.push(line),
  claim: ({ steps }) =>
    Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const }))),
};

const CREATE = {
  repo: 'sqldb',
  cluster: 'prod',
  datastore: 'ds-data',
  replicas: 2,
  image: 'postgres:16',
  port: 5432,
  refresh: '1h',
};
const SET = 'sqldb-replicas';
const R1 = 'ds-data:sqldb-replicas-r1';
const R2 = 'ds-data:sqldb-replicas-r2';
const NEW_SNAPSHOT = 'replicate-sqldb-replicas-1800000000000';
const OLD_SNAPSHOT = 'replicate-sqldb-replicas';

const names = (): string[] => calls.map((c) => c.functionName);
const set = (): ReplicaSet | undefined => stored?.[SET];

beforeEach(() => {
  model = newModel();
  calls = [];
  warnings = [];
  answer = undefined;
  stored = undefined;
  lic.installed.clear();
  lic.issued.length = 0;
  dir = mkdtempSync(join(tmpdir(), 'repo-replicate-ops-'));
  store = new TicketStore('test', dir);
  setCommandJobDeps({
    executor: () => ({
      execute: (options) => {
        const call = options as unknown as Call;
        calls.push(call);
        const override = answer?.(call, calls.length - 1);
        if (override instanceof Error) return Promise.reject(override);
        return Promise.resolve((override ?? apply(model, call)) as never);
      },
    }),
    store: () => store,
    stepDeps: () => Promise.resolve(stepDeps),
  });
  vi.spyOn(outputService, 'info').mockReturnValue(undefined);
  vi.spyOn(outputService, 'warn').mockReturnValue(undefined);
  vi.spyOn(outputService, 'success').mockReturnValue(undefined);
  vi.spyOn(configService, 'getCurrent').mockImplementation(
    () => Promise.resolve({ state: { replicaSets: stored } }) as never
  );
  vi.spyOn(configService, 'setStateBucket').mockImplementation((_key, sets) => {
    stored = sets as Record<string, ReplicaSet>;
    return Promise.resolve();
  });
  vi.spyOn(configService, 'getLocalMachine').mockImplementation(
    (name: string) => Promise.resolve({ ip: `10.0.0.${name.slice(-1)}` }) as never
  );
  vi.spyOn(configService, 'getRepository').mockImplementation((repoKey: string) =>
    Promise.resolve({ repositoryGuid: `guid-${repoKey.replaceAll(':', '-')}` })
  );
  __setReplicateClock(() => 1_800_000_000_000);
});

afterEach(() => {
  setCommandJobDeps();
  rmSync(dir, { recursive: true, force: true });
  vi.restoreAllMocks();
});

/** What `rdc job wait` does for a ticket: run what it owes, with the given job output. */
function settleOwed(requestId: string, output?: string) {
  const ticket = store.find(requestId);
  if (!ticket) throw new Error('no such ticket');
  return runTicketSteps(store, ticket, { state: 'succeeded', output }, stepDeps);
}

/** The handler itself, past the claim: what a retake of a stale claim runs. */
async function runHandler(step: string, params?: Record<string, string | number | boolean>) {
  const handler = await resolveStepHandler(step);
  await handler({ jobId: 'job', machine: 'cp1', params: params ?? {}, state: 'succeeded' });
}

function ticketOwing(step: string) {
  const ticket = store.tickets().find((t) => t.steps?.some((s) => s.name === step));
  if (!ticket) throw new Error(`no ticket owes ${step}`);
  return ticket;
}

function expectSettledCreate(): void {
  expect(set()?.phase).toBe('ready');
  expect(set()?.replicas.map((r) => r.fork)).toEqual([R1, R2]);
  // Both forks live on their nodes, attached and opened; control keeps no copy.
  expect(registry(model, 'prod-w-1').get(R1)?.attached).toBe(true);
  expect(registry(model, 'prod-w-2').get(R2)?.attached).toBe(true);
  expect([...registry(model, 'cp1').keys()]).toEqual([]);
  expect(model.opened).toEqual(new Set([`${R1}|guid-sqldb`, `${R2}|guid-sqldb`]));
  expect(model.labels).toEqual(
    new Set(['ds-data-sqldb-replicas-r1@10.0.0.1', 'ds-data-sqldb-replicas-r2@10.0.0.2'])
  );
  expect(model.manifests.at(-1)).toContain('kind: StatefulSet');
}

describe('replicateRepo (create)', () => {
  it('runs the fork, then per replica attach and open, then the publish, and records ready', async () => {
    await replicateRepo(CREATE);

    expect(names()).toEqual([
      'replica_fork',
      'replica_attach',
      'datastore_volumes_open',
      'replica_attach',
      'datastore_volumes_open',
      'replica_publish',
    ]);
    expectSettledCreate();
    expect(lic.issued).toEqual(['id-1', 'id-2']);
    expect(set()).toMatchObject({
      repo: 'sqldb',
      repoGuid: 'guid-sqldb',
      datastore: 'ds-data',
      cluster: 'prod',
      snapshot: OLD_SNAPSHOT,
      refresh: '1h',
      replicas: [
        { index: 1, fork: R1, node: 'prod-w-1' },
        { index: 2, fork: R2, node: 'prod-w-2' },
      ],
    });
    // #93: every storage verb speaks the GUID, every k8s object the name.
    const opens = calls.filter((c) => c.functionName === 'datastore_volumes_open');
    expect(opens.every((c) => c.params.repo === 'guid-sqldb')).toBe(true);
    const publish = calls.find((c) => c.functionName === 'replica_publish');
    expect(publish).toMatchObject({
      machineName: 'cp1',
      params: {
        mount_path: '/mnt/rediacc-ds/ds-control-prod',
        namespace: 'sqldb',
        name: 'replicate-sqldb-replicas.yaml',
        cluster: 'prod',
        datastore: '/mnt/rediacc-ds/ds-data',
        forget: `${R1},${R2}`,
      },
    });
  });

  it('ferries the fork record to an off-control node as the fork job reported it', async () => {
    await replicateRepo(CREATE);
    const attach = calls.find((c) => c.functionName === 'replica_attach');
    const record = JSON.parse(
      Buffer.from(String(attach?.params.record_b64), 'base64').toString()
    ) as ForkRecord;
    expect(record).toMatchObject({ name: R1, datastoreId: 'id-1' });
    expect(attach?.params.writes).toBe('local');
  });

  it('opens before the publish stamps the label, and licenses before the open', async () => {
    const order: string[] = [];
    answer = (call) => {
      order.push(
        call.functionName === 'datastore_volumes_open'
          ? `open:${lic.issued.length}`
          : call.functionName
      );
      return undefined;
    };
    await replicateRepo(CREATE);
    // `open:1` and `open:2`: the replica's licence was already issued when its open started.
    expect(order).toEqual([
      'replica_fork',
      'replica_attach',
      'open:1',
      'replica_attach',
      'open:2',
      'replica_publish',
    ]);
  });

  it('--background returns at the first job, having spent nothing; the ticket finishes it', async () => {
    answer = (call) => (call.functionName === 'replica_fork' ? running : undefined);

    await replicateRepo(CREATE);

    expect(names()).toEqual(['replica_fork']);
    expect(set()?.phase).toBe('placing');
    expect(lic.issued).toEqual([]);
    expect(model.labels.size).toBe(0);

    // The machine job finishes while the client is gone; `rdc job wait` then runs the tail from the job's replayed log.
    answer = undefined;
    const fork = replicaFork(model, calls[0]);
    const report = await settleOwed(
      ticketOwing('replicateTail').requestId,
      'stdout' in fork ? fork.stdout : undefined
    );

    expect(report.failed).toEqual([]);
    expectSettledCreate();
    expect(lic.issued).toEqual(['id-1', 'id-2']);
  });

  it('the tail reads the forks again when the observer has no log of the first job', async () => {
    answer = (call) => (call.functionName === 'replica_fork' ? running : undefined);
    await replicateRepo(CREATE);
    answer = undefined;
    replicaFork(model, calls[0]);

    await settleOwed(ticketOwing('replicateTail').requestId, undefined);

    expect(names().filter((n) => n === 'replica_fork')).toHaveLength(2);
    expectSettledCreate();
    expect(lic.issued).toEqual(['id-1', 'id-2']);
  });

  it('a retried step spends no licence slot', async () => {
    // The second open fails after both licences went in, so the step stays owed.
    let refused = false;
    answer = (call) => {
      if (call.functionName === 'datastore_volumes_open' && call.params.name === R2 && !refused) {
        refused = true;
        return failed('transient');
      }
      return undefined;
    };

    await expect(replicateRepo(CREATE)).rejects.toThrow(/not finished/);
    expect(lic.issued).toEqual(['id-1', 'id-2']);
    expect(set()?.phase).toBe('placing');
    // The failure keeps its partial-placement guidance, naming what to run.
    expect(warnings.join('\n')).toContain('transient');
    expect(warnings.join('\n')).toContain('rdc repo replicate sqldb --replicas 2');

    // The owed step retaken on its own ticket issues nothing, and neither does a rerun.
    const report = await settleOwed(ticketOwing('replicateTail').requestId);
    expect(report.failed).toEqual([]);
    expectSettledCreate();
    expect(lic.issued).toEqual(['id-1', 'id-2']);
  });

  it('a rerun of a placing set resumes it on the same plan and the same forks', async () => {
    answer = (call) =>
      call.functionName === 'replica_publish' ? failed('apply failed') : undefined;
    await expect(replicateRepo(CREATE)).rejects.toThrow(/not finished/);
    expect(set()?.phase).toBe('placing');
    answer = undefined;

    await replicateRepo(CREATE);

    expectSettledCreate();
    expect(lic.issued).toEqual(['id-1', 'id-2']);
    expect(model.nextId).toBe(3);
  });

  it('a stale retake of the tail after the set is ready does nothing', async () => {
    await replicateRepo(CREATE);
    const before = calls.length;
    const { params } = ticketOwing('replicateTail').steps?.[0] ?? {};
    await runHandler('replicateTail', params);
    expect(calls.length).toBe(before);
  });

  it('a rerun with another replica count is refused while placing', async () => {
    answer = (call) => (call.functionName === 'replica_fork' ? running : undefined);
    await replicateRepo(CREATE);
    await expect(replicateRepo({ ...CREATE, replicas: 3 })).rejects.toThrow(
      /being placed with 2 replica\(s\), not 3/
    );
  });

  it('refuses a second set on a ready one (ONE set per repo, §4.4)', async () => {
    await replicateRepo(CREATE);
    await expect(replicateRepo(CREATE)).rejects.toThrow(/already has a replica set/);
  });

  it('records nothing and starts nothing for a cluster with no nodes', async () => {
    const { getCluster } = await import('../../config/config-cluster-ops.js');
    vi.mocked(getCluster).mockResolvedValueOnce({ pools: [] } as never);
    await expect(replicateRepo(CREATE)).rejects.toThrow(/no nodes to host replicas/);
    expect(calls).toEqual([]);
    expect(stored).toBeUndefined();
  });

  it('derives the set name from the repo ref, colon and all', async () => {
    await replicateRepo({ ...CREATE, repo: 'sqldb:test', replicas: 1 });
    expect(Object.keys(stored ?? {})).toEqual(['sqldb-test-replicas']);
    expect(calls[0].params.tags).toBe('sqldb-test-replicas-r1');
  });

  it('keeps licences out of every job vault and step plan', async () => {
    await replicateRepo(CREATE);
    for (const call of calls) {
      expect(Object.keys(call.params).filter((k) => /licen[cs]e/i.test(k))).toEqual([]);
      expect(JSON.stringify(call.jobSteps ?? [])).not.toMatch(/licen[cs]e/i);
    }
  });

  describe('a client killed at each hop leaves nothing a rerun cannot finish', () => {
    const hops = [...Array(6).keys()];
    for (const kill of ['before', 'after'] as Kill[]) {
      for (const hop of hops) {
        it(`hop ${hop}, ${kill} the job`, async () => {
          answer = killAt(hop, kill);
          await replicateRepo(CREATE).catch(() => undefined);
          expect(calls.length, 'the kill was reached').toBeGreaterThan(hop);
          expect(set()?.phase).toBe('placing');

          answer = undefined;
          await replicateRepo(CREATE);

          expectSettledCreate();
          // Each fork id is licensed once, whichever hop died.
          expect(lic.issued).toHaveLength(2);
          expect(new Set(lic.issued)).toEqual(new Set(['id-1', 'id-2']));
        });

        it(`hop ${hop}, ${kill} the job: the set is removable instead`, async () => {
          answer = killAt(hop, kill);
          await replicateRepo(CREATE).catch(() => undefined);
          answer = undefined;

          await removeReplicaSet('sqldb');

          expect(stored).toEqual({});
          expect(model.images.size).toBe(0);
          for (const machine of ['cp1', 'prod-w-1', 'prod-w-2']) {
            expect([...registry(model, machine).keys()]).toEqual([]);
          }
        });
      }
    }
  });
});

const seededSet: ReplicaSet = {
  repo: 'sqldb',
  repoGuid: 'guid-sqldb',
  datastore: 'ds-data',
  cluster: 'prod',
  snapshot: OLD_SNAPSHOT,
  createdAt: '2026-07-11T00:00:00Z',
  phase: 'ready',
  replicas: [
    { index: 1, fork: R1, node: 'prod-w-1' },
    { index: 2, fork: R2, node: 'prod-w-2' },
  ],
};

function seedPlaced(): void {
  stored = { [SET]: seededSet };
  model.snapshots.add(OLD_SNAPSHOT);
  for (const [i, r] of seededSet.replicas.entries()) {
    registry(model, r.node).set(r.fork, {
      name: r.fork,
      datastoreId: `old-${i + 1}`,
      fork: { clonedFrom: OLD_SNAPSHOT },
      attached: true,
    });
    model.images.add(r.fork);
    model.opened.add(`${r.fork}|guid-sqldb`);
    model.labels.add(`${r.fork.replace(':', '-')}@10.0.0.${i + 1}`);
    lic.installed.add(`${r.node}|old-${i + 1}`);
  }
  model.nextId = 10;
}

describe('removeReplicaSet', () => {
  it('deletes the overlay, then discards, strips labels, drops the snapshot, then forgets', async () => {
    seedPlaced();

    await removeReplicaSet('sqldb');

    expect(names()).toEqual([
      'kube_delete',
      'replica_discard',
      'replica_discard',
      'kube_node_label',
      'kube_node_label',
      'datastore_snapshot_delete',
    ]);
    expect(calls[0]).toMatchObject({
      machineName: 'cp1',
      captureOutput: true,
      params: { namespace: 'sqldb', replica_set: SET },
    });
    expect(calls[0].params.pod_ordinal).toBeUndefined();
    expect(calls[1]).toMatchObject({
      machineName: 'prod-w-1',
      params: { name: R1, repo: 'guid-sqldb' },
    });
    expect(calls[3].params).toMatchObject({ datastore: 'ds-data-sqldb-replicas-r1', remove: true });
    expect(calls[5].params).toMatchObject({ name: 'ds-data', snapshot: OLD_SNAPSHOT });
    expect(stored).toEqual({});
  });

  it('is a no-op without a set', async () => {
    await removeReplicaSet('sqldb');
    expect(calls).toEqual([]);
  });

  it('REJECTS and PRESERVES state when a discard fails, naming the survivor (bug #95)', async () => {
    seedPlaced();
    answer = (call) =>
      call.functionName === 'replica_discard' && call.params.name === R2
        ? failed('the fork is still registered on this machine after its discard')
        : undefined;

    await expect(removeReplicaSet('sqldb')).rejects.toThrow(/NOT removed.*PRESERVED/);

    expect(warnings.join('\n')).toMatch(/fork ds-data:sqldb-replicas-r2 could not be discarded/);
    expect(stored?.[SET]).toEqual(seededSet);
    expect(names()).not.toContain('datastore_snapshot_delete');
  });

  it('a best-effort step failing still ends with the set gone, and says so', async () => {
    seedPlaced();
    answer = (call) =>
      call.functionName === 'datastore_snapshot_delete' ? failed('snapshot busy') : undefined;
    await removeReplicaSet('sqldb');
    expect(stored).toEqual({});
    expect(outputService.warn).toHaveBeenCalledWith(expect.stringContaining('snapshot busy'));
  });

  it('a placing set also discards the control copies of its forks; a placed one does not', async () => {
    seedPlaced();
    stored = { [SET]: { ...seededSet, phase: 'placing' } };
    await removeReplicaSet('sqldb');
    expect(
      calls.filter((c) => c.functionName === 'replica_discard').map((c) => c.machineName)
    ).toEqual(['prod-w-1', 'cp1', 'prod-w-2', 'cp1']);
  });

  it('--background returns at the overlay delete; the ticket finishes it', async () => {
    seedPlaced();
    answer = (call) => (call.functionName === 'kube_delete' ? running : undefined);
    await removeReplicaSet('sqldb');
    expect(names()).toEqual(['kube_delete']);
    expect(stored?.[SET]).toEqual(seededSet);

    answer = undefined;
    await settleOwed(ticketOwing('removeTail').requestId, 'deleted');
    expect(stored).toEqual({});
  });

  it('issues no licence', async () => {
    seedPlaced();
    await removeReplicaSet('sqldb');
    expect(lic.issued).toEqual([]);
  });
});

function expectSettledRefresh(): void {
  expect(set()?.snapshot).toBe(NEW_SNAPSHOT);
  expect(set()?.refreshing).toBeUndefined();
  expect(set()?.refreshedAt).toBe(new Date(1_800_000_000_000).toISOString());
  expect(registry(model, 'prod-w-1').get(R1)?.fork.clonedFrom).toBe(NEW_SNAPSHOT);
  expect(registry(model, 'prod-w-2').get(R2)?.fork.clonedFrom).toBe(NEW_SNAPSHOT);
  expect([...registry(model, 'cp1').keys()]).toEqual([]);
  expect(model.opened).toEqual(new Set([`${R1}|guid-sqldb`, `${R2}|guid-sqldb`]));
  expect(model.labels).toEqual(
    new Set(['ds-data-sqldb-replicas-r1@10.0.0.1', 'ds-data-sqldb-replicas-r2@10.0.0.2'])
  );
  expect(model.snapshots).toEqual(new Set([NEW_SNAPSHOT]));
}

const REPLICA_ROLL = [
  'datastore_list',
  'kube_node_label',
  'kube_delete',
  'replica_discard',
  'replica_fork',
  'replica_attach',
  'datastore_volumes_open',
  'replica_publish',
] as const;

describe('refreshReplicaSet (rolling one-at-a-time)', () => {
  it('takes the snapshot, then per replica HOLD -> bounce -> discard -> re-fork -> open -> re-open the gate', async () => {
    seedPlaced();

    await refreshReplicaSet('sqldb');

    expect(names()).toEqual([
      'replica_fork',
      ...REPLICA_ROLL,
      ...REPLICA_ROLL,
      'datastore_snapshot_delete',
    ]);
    expectSettledRefresh();
    expect(calls[0].params).toEqual({ parent: 'ds-data', snapshot: NEW_SNAPSHOT });
    // The hold: strip BEFORE the bounce (bug #41), re-stamp through the publish.
    expect(calls[2].params).toMatchObject({ datastore: 'ds-data-sqldb-replicas-r1', remove: true });
    expect(calls[3].params.pod_ordinal).toBe(0);
    // Same tag, so the PV path never changes; each re-fork clones the new snapshot.
    expect(calls[5].params).toMatchObject({ snapshot: NEW_SNAPSHOT, tags: 'sqldb-replicas-r1' });
    expect(calls[8].params).toMatchObject({
      labels: 'ds-data-sqldb-replicas-r1@10.0.0.1',
      forget: R1,
    });
    expect(calls[8].params.manifest).toBeUndefined();
    // A re-fork mints a new id, so each replica needs its licence: one issuance each.
    expect(lic.issued).toEqual(['id-10', 'id-11']);
  });

  it('--background returns at the snapshot job; the ticket rolls the set', async () => {
    seedPlaced();
    answer = (call) => (call.functionName === 'replica_fork' ? running : undefined);

    await refreshReplicaSet('sqldb');

    expect(names()).toEqual(['replica_fork']);
    expect(set()?.refreshing).toBe(NEW_SNAPSHOT);
    expect(lic.issued).toEqual([]);

    answer = undefined;
    replicaFork(model, calls[0]);
    await settleOwed(ticketOwing('refreshTail').requestId);
    expectSettledRefresh();
  });

  it('a rerun resumes on the recorded snapshot and leaves a finished replica in place', async () => {
    seedPlaced();
    __setReplicateClock(() => 1_800_000_000_000);
    answer = (call) =>
      call.functionName === 'datastore_volumes_open' && call.params.name === R2
        ? failed('transient')
        : undefined;

    await expect(refreshReplicaSet('sqldb')).rejects.toThrow(/not finished/);

    // N-1 keep serving: r1 is on the new snapshot and labelled, and the gate stays closed on r2.
    expect(model.labels).toEqual(new Set(['ds-data-sqldb-replicas-r1@10.0.0.1']));
    expect(set()?.refreshing).toBe(NEW_SNAPSHOT);
    const issued = lic.issued.length;

    answer = undefined;
    calls.length = 0;
    __setReplicateClock(() => 1_900_000_000_000);
    await refreshReplicaSet('sqldb');

    // No second snapshot, and no replica bounced again.
    expect(calls[0].params.snapshot).toBe(NEW_SNAPSHOT);
    expect(names()).not.toContain('kube_delete');
    expect(lic.issued.length).toBe(issued);
    expect(set()?.snapshot).toBe(NEW_SNAPSHOT);
  });

  it('a stale retake after the refresh settled does nothing', async () => {
    seedPlaced();
    await refreshReplicaSet('sqldb');
    const before = calls.length;
    const { params } = ticketOwing('refreshTail').steps?.[0] ?? {};
    await runHandler('refreshTail', params);
    expect(calls.length).toBe(before);
  });

  it('a set recorded before the phase field reads as ready: refresh rolls it, create refuses it, remove leaves control alone', async () => {
    seedPlaced();
    // The key is absent, as in a record stored before the field existed (not present with an undefined value).
    const legacy = Object.fromEntries(
      Object.entries(seededSet).filter(([key]) => key !== 'phase')
    ) as ReplicaSet;
    expect('phase' in legacy).toBe(false);
    stored = { [SET]: legacy };
    await expect(replicateRepo(CREATE)).rejects.toThrow(/already has a replica set/);
    await refreshReplicaSet('sqldb');
    expect(set()?.snapshot).not.toBe(OLD_SNAPSHOT);

    seedPlaced();
    stored = { [SET]: legacy };
    calls.length = 0;
    await removeReplicaSet('sqldb');
    expect(
      calls.filter((c) => c.functionName === 'replica_discard').map((c) => c.machineName)
    ).toEqual(['prod-w-1', 'prod-w-2']);
  });

  it('refuses a set still placing, and a repo with none', async () => {
    seedPlaced();
    stored = { [SET]: { ...seededSet, phase: 'placing' } };
    await expect(refreshReplicaSet('sqldb')).rejects.toThrow(/still being placed/);
    stored = {};
    await expect(refreshReplicaSet('sqldb')).rejects.toThrow(/has no replica set/);
  });

  describe('a client killed at each hop leaves nothing a rerun cannot finish', () => {
    const hops = [...Array(1 + REPLICA_ROLL.length * 2 + 1).keys()];
    for (const kill of ['before', 'after'] as Kill[]) {
      for (const hop of hops) {
        it(`hop ${hop}, ${kill} the job`, async () => {
          seedPlaced();
          answer = killAt(hop, kill);
          await refreshReplicaSet('sqldb').catch(() => undefined);
          expect(calls.length, 'the kill was reached').toBeGreaterThan(hop);

          answer = undefined;
          __setReplicateClock(() => 1_800_000_000_000);
          await refreshReplicaSet('sqldb');

          expect(set()?.snapshot).toBe(NEW_SNAPSHOT);
          expect(registry(model, 'prod-w-1').get(R1)?.fork.clonedFrom).toBe(NEW_SNAPSHOT);
          expect(registry(model, 'prod-w-2').get(R2)?.fork.clonedFrom).toBe(NEW_SNAPSHOT);
          expect(model.labels.size).toBe(2);
          // One licence per new fork id, whichever hop died.
          expect(new Set(lic.issued).size).toBe(lic.issued.length);
        });
      }
    }
  });
});
