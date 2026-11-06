/**
 * PLAN-detached-jobs J16 (half B): the repo verbs outside J4 that run their main call as one machine job, with the
 * render, the mirror or the record as a ticket step. Each case drives the real command, with a recording executor behind
 * the runCommandJob seam, a real ticket store in a temp directory and a claim that grants every step. A case asserts one
 * job start on the one machine with the declared steps; its control runs the same command under `--background` (the
 * executor answers `running`) and asserts the step's effect did not happen, so the effect lives in the step and
 * not in the command body.
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

const mockSetGpuDevices = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockAddRepository = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockSetStateBucket = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockGetCurrent = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  MachineNotFoundError: class MachineNotFoundError extends Error {},
  configService: {
    getCurrent: mockGetCurrent,
    getRepository: vi.fn((name: string) =>
      Promise.resolve({
        repositoryGuid: `guid-${name}`,
        networkId: 2816,
        credential: 'c',
        gpuDevices: ['nvidia.com/gpu=0'],
      })
    ),
    getRepositoryKey: (ref: string) => Promise.resolve(ref),
    setRepositoryGpuDevices: mockSetGpuDevices,
    setStateBucket: mockSetStateBucket,
    addRepository: mockAddRepository,
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock('../../services/config/network-id-discovery.js', () => ({
  ensureRepositoryNetworkId: vi.fn().mockResolvedValue(2816),
}));

const mockPrint = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    print: mockPrint,
    format: vi.fn(),
    setTimelineRendered: vi.fn(),
  },
}));
const mockWriteStdout = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/request-context.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  writeStdout: mockWriteStdout,
  setExitCode: vi.fn(),
}));

/** Every call that reached the executor: the job starts (with `jobSteps`) and the step's own direct calls (without). */
type Executed = {
  functionName: string;
  machineName: string;
  params?: Record<string, unknown>;
  jobSteps?: {
    name: string;
    on: string;
    params: Record<string, unknown>;
    needs_output?: boolean;
  }[];
};
const executed: Executed[] = [];
const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getExecutor: () => ({ execute: mockExecute }),
}));

const mockResolveRepoRef = vi.hoisted(() => vi.fn());
const mockResolveRepoTarget = vi.hoisted(() => vi.fn());
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: mockResolveRepoRef,
  resolveRepoTarget: mockResolveRepoTarget,
}));
vi.mock('../../utils/command-policy.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../utils/guid-resolver.js', () => ({
  loadGuidMap: vi.fn().mockResolvedValue({}),
  createGuidResolver: () => (guid: string) => guid,
  createRepoNameResolver: () => (guid: string, serverName?: string) => ({
    name: serverName ?? guid,
    source: 'server',
  }),
}));
vi.mock('../../services/cluster/cluster-target.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  resolveExecutionTarget: vi.fn().mockResolvedValue({ machineName: 'ctl' }),
}));
vi.mock('../../services/cluster/cluster-kube.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  controlDatastoreMount: () => '/mnt/ctl',
}));
vi.mock('../function-params.js', () => ({
  coerceCliParams: (_fn: string, params: Record<string, unknown>) => params,
  validateFunctionParams: vi.fn(),
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getOutputFormat: () => 'table',
  handleError: (e: unknown) => {
    throw e;
  },
}));

const { configService } = await import('../../services/config/config-resources.js');
const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const { registerRepoCatCommand } = await import('../repo-cat.js');
const { registerRepoBranchingCommands } = await import('../repo-branching.js');
const { registerRepoCommands } = await import('../repo.js');
const { registerRepoDiffCommand } = await import('../repo-diff.js');
const { registerRepoGpuCommands } = await import('../repo-gpu.js');
const { registerRepoPolicyCommand } = await import('../repo-policy.js');
const { registerRepoCanaryCommands } = await import('../repo-canary.js');
const { handleRepoList } = await import('../repo-batch-utils.js');
const { listBackups } = await import('../repo-backup-list.js');

const BACKGROUND = {
  success: true,
  exitCode: 0,
  durationMs: 0,
  state: 'running' as const,
  jobId: 'job-1',
  attached: false,
};
const finished = (stdout?: string) => ({
  ...BACKGROUND,
  durationMs: 5,
  state: 'succeeded' as const,
  attached: true,
  ...(stdout === undefined ? {} : { stdout }),
});

let dir: string;
let store: InstanceType<typeof TicketStore>;
let answer: Record<string, unknown>;

/** The job starts: calls that carried a step plan (a step's own `dispatch` carries none). */
const jobStarts = () => executed.filter((o) => o.jobSteps !== undefined);
const stepNames = () => jobStarts()[0]?.jobSteps?.map((s) => [s.name, s.on]);

async function run(register: (repo: Command) => void, ...argv: string[]): Promise<void> {
  const repo = new Command('repo').exitOverride();
  register(repo);
  await repo.parseAsync(argv, { from: 'user' });
}

beforeEach(() => {
  vi.clearAllMocks();
  executed.length = 0;
  answer = finished();
  mockExecute.mockImplementation((options: Executed) => {
    executed.push(options);
    return Promise.resolve(options.jobSteps === undefined ? finished() : answer);
  });
  mockResolveRepoRef.mockResolvedValue({
    name: 'shop',
    repoKey: 'shop',
    machineName: 'm1',
    tag: 'latest',
  });
  mockResolveRepoTarget.mockResolvedValue({ machineName: 'm1' });
  mockGetCurrent.mockResolvedValue({ state: { canaries: {} }, resources: { repositories: {} } });
  dir = mkdtempSync(join(tmpdir(), 'job-plan-repo-more-'));
  store = new TicketStore('test', dir);
  setCommandJobDeps({
    executor: () => ({ execute: mockExecute }),
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
});

describe('repo cat', () => {
  const payload = `RDC_CAT_B64:${Buffer.from('hello').toString('base64')}\n`;

  it('one job start on the machine; the file bytes are written by the step', async () => {
    answer = finished(payload);
    await run(registerRepoCatCommand, 'cat', 'shop', '--remote-file', '/etc/motd');

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['repository_cat', 'm1'],
    ]);
    expect(stepNames()).toEqual([['printRepoCat', 'success']]);
    expect(jobStarts()[0].jobSteps?.[0].needs_output).toBe(true);
    expect(mockWriteStdout).toHaveBeenCalledExactlyOnceWith(Buffer.from('hello'));
  });

  it('control: under --background the bytes are not written', async () => {
    answer = BACKGROUND;
    await run(registerRepoCatCommand, 'cat', 'shop', '--remote-file', '/etc/motd');

    expect(jobStarts()).toHaveLength(1);
    expect(mockWriteStdout).not.toHaveBeenCalled();
  });
});

describe('repo diff', () => {
  const diff = JSON.stringify({
    base: 'b',
    target: 't',
    entries: [{ status: 'A', path: 'a.txt', type: 'file', size: 1, content_changed: true }],
    added: 1,
    modified: 0,
    deleted: 0,
    renamed: 0,
    strategy: 'x',
  });

  beforeEach(() => {
    mockGetCurrent.mockResolvedValue({
      resources: { repositories: {} },
    });
  });

  it('one job start; the rendering mode rides the step params', async () => {
    answer = finished(diff);
    await run(registerRepoDiffCommand, 'diff', 'shop', '--base', 'other', '--name-only');

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['repository_diff', 'm1'],
    ]);
    expect(stepNames()).toEqual([['renderRepoDiff', 'success']]);
    expect(jobStarts()[0].jobSteps?.[0].params).toMatchObject({
      mode: 'name-only',
      format: 'table',
    });
  });

  it('control: under --background nothing is rendered', async () => {
    answer = BACKGROUND;
    await run(registerRepoDiffCommand, 'diff', 'shop', '--base', 'other');

    expect(jobStarts()).toHaveLength(1);
    expect(mockWriteStdout).not.toHaveBeenCalled();
  });
});

describe('repo gpu grant and revoke', () => {
  const listing = JSON.stringify({ devices: [{ name: 'nvidia.com/gpu=1' }] });

  it.each([
    ['grant', 'repository_gpu_grant'],
    ['revoke', 'repository_gpu_revoke'],
  ])('%s: one job start; the config mirror is the step', async (verb, fn) => {
    answer = finished(listing);
    await run(registerRepoGpuCommands, 'gpu', verb, 'shop', '--device', 'nvidia.com/gpu=1');

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([[fn, 'm1']]);
    expect(stepNames()).toEqual([['mirrorGpuGrants', 'success']]);
    expect(jobStarts()[0].jobSteps?.[0].params).toMatchObject({ repo: 'shop', verb });
    expect(mockSetGpuDevices).toHaveBeenCalledExactlyOnceWith('shop', ['nvidia.com/gpu=1']);
  });

  it('control: under --background the mirror is not written', async () => {
    answer = BACKGROUND;
    await run(registerRepoGpuCommands, 'gpu', 'grant', 'shop', '--device', 'nvidia.com/gpu=1');

    expect(jobStarts()).toHaveLength(1);
    expect(mockSetGpuDevices).not.toHaveBeenCalled();
  });
});

describe('repo policy get and set', () => {
  const policy = JSON.stringify({ effective: { auto_grow: true }, repo_override: null });

  it('set: one job start; the settings table is the step', async () => {
    answer = finished(policy);
    await run(registerRepoPolicyCommand, 'policy', 'set', 'shop', '--auto-grow', 'true');

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['repository_policy_set', 'm1'],
    ]);
    expect(stepNames()).toEqual([['renderPolicyResult', 'success']]);
    expect(mockPrint).toHaveBeenCalledOnce();
  });

  it('get <ref>: the size policy job, then the limits job; each table is its step', async () => {
    // PLAN-repo-resource-limits Decision 2: a single-repo get adds the repository's limits table.
    answer = finished(policy);
    await run(registerRepoPolicyCommand, 'policy', 'get', 'shop');

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['repository_policy_get', 'm1'],
      ['repository_limits_show', 'm1'],
    ]);
    expect(jobStarts().map((o) => o.jobSteps?.map((s) => [s.name, s.on]))).toEqual([
      [['renderPolicyResult', 'success']],
      [['renderLimitsResult', 'success']],
    ]);
    expect(mockPrint).toHaveBeenCalledTimes(2);
  });

  it('control: under --background no table is printed', async () => {
    answer = BACKGROUND;
    await run(registerRepoPolicyCommand, 'policy', 'get', 'shop');

    expect(jobStarts()).toHaveLength(2);
    expect(mockPrint).not.toHaveBeenCalled();
  });
});

describe('repo list', () => {
  const list = JSON.stringify([{ name: 'guid-1', repo_name: 'shop', size: 1 }]);

  it('one job start; the name resolution and table are the step', async () => {
    answer = finished(list);
    await handleRepoList({ machine: 'm1' });

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['repository_list', 'm1'],
    ]);
    expect(stepNames()).toEqual([['renderRepoList', 'success']]);
    expect(mockPrint).toHaveBeenCalledOnce();
  });

  it('control: the listing it prints is the pre-job table, byte for byte', async () => {
    const { outputService } = await import('../../services/core/output.js');
    answer = finished(
      JSON.stringify([
        {
          name: 'guid-1',
          repo_name: 'shop',
          size_human: '1.0 GB',
          mounted: true,
          docker_running: false,
          containers_running: false,
          container_count: 2,
          service_count: 1,
          modified_human: '3h ago',
          is_fork: false,
        },
      ])
    );
    await handleRepoList({ machine: 'm1' });

    expect(mockPrint).toHaveBeenCalledTimes(1);
    const [rows, format] = mockPrint.mock.calls[0];
    expect(format).toBe('table');
    // Key order is the column order of the rendered table, so the serialisation pins it.
    expect(JSON.stringify(rows)).toBe(
      '[{"name":"shop *","tag":"latest","type":"unknown","size":"1.0 GB","mounted":"Yes","docker":"No","running":"No","containers":2,"services":1,"modified":"3h ago","gpu":"-","lifecycle":"-"}]'
    );
    expect(vi.mocked(outputService.info).mock.calls.map((c) => c[0])).toContain(
      'commands.repo.list.serverNameLegend'
    );
    expect(vi.mocked(outputService.success)).toHaveBeenCalledWith('commands.repo.list.completed');
  });

  it('control: under --background nothing is printed', async () => {
    answer = BACKGROUND;
    await handleRepoList({ machine: 'm1' });

    expect(jobStarts()).toHaveLength(1);
    expect(mockPrint).not.toHaveBeenCalled();
  });
});

describe('backup list', () => {
  it('one job start on the machine; the table is the step, narrowed by the ref', async () => {
    const entries = JSON.stringify({
      entries: [
        { name: 'wanted', size: 1 },
        { name: 'other', size: 1 },
      ],
    });
    answer = finished(entries);
    const { outputService } = await import('../../services/core/output.js');
    vi.mocked(outputService.format).mockImplementation(((rows: unknown) => rows) as never);

    await listBackups({ sourceType: 'local', from: 'm1' }, { machine: 'm1' }, 'wanted');

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['backup_list', 'm1'],
    ]);
    expect(stepNames()).toEqual([['renderBackupList', 'success']]);
    const rows = mockPrint.mock.calls[0][0] as { guid: string }[];
    expect(rows.map((r) => r.guid)).toEqual(['wanted']);
  });

  it('a failed listing throws with the engine reason and prints no table', async () => {
    answer = {
      ...finished(),
      success: false,
      exitCode: 1,
      state: 'failed' as const,
      stderr: 'datastore unreadable',
    };

    await expect(
      listBackups({ sourceType: 'local', from: 'm1' }, { machine: 'm1' })
    ).rejects.toThrow(/backup list failed: datastore unreadable/);
    expect(mockPrint).not.toHaveBeenCalled();
  });

  it('control: under --background nothing is printed', async () => {
    answer = BACKGROUND;
    await listBackups({ sourceType: 'local', from: 'm1' }, { machine: 'm1' });

    expect(jobStarts()).toHaveLength(1);
    expect(mockPrint).not.toHaveBeenCalled();
  });
});

describe('repo canary create, weight and remove', () => {
  const canary = {
    repo: 'web',
    cluster: 'c1',
    service: 'web',
    image: 'img:2',
    port: 80,
    replicas: 1,
    weight: 10,
    undoSnapshot: 'release-undo-1',
    createdAt: '2026-01-01T00:00:00.000Z',
  };

  beforeEach(() => {
    mockResolveRepoRef.mockResolvedValue({
      name: 'web',
      repoKey: 'web',
      machineName: 'ctl',
      kubeCluster: 'c1',
      tag: 'latest',
    });
  });

  it('create: the undo snapshot is the one job on the control machine; apply and record are the step', async () => {
    await run(
      registerRepoCanaryCommands,
      'canary',
      'create',
      'web',
      '--image',
      'img:2',
      '--port',
      '80',
      '--weight',
      '10'
    );

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['datastore_snapshot_create', 'ctl'],
    ]);
    expect(stepNames()).toEqual([['recordCanary', 'success']]);
    // The step then applies the overlay on the control machine and records the set, in that order.
    expect(executed.map((o) => o.functionName)).toEqual([
      'datastore_snapshot_create',
      'kube_apply',
    ]);
    expect(executed[1].machineName).toBe('ctl');
    expect(mockSetStateBucket).toHaveBeenCalledExactlyOnceWith('canaries', {
      'web-canary': expect.objectContaining({ repo: 'web', weight: 10 }),
    });
  });

  it('control: under --background neither the apply nor the record happens', async () => {
    answer = BACKGROUND;
    await run(
      registerRepoCanaryCommands,
      'canary',
      'create',
      'web',
      '--image',
      'img:2',
      '--port',
      '80',
      '--weight',
      '10'
    );

    expect(executed.map((o) => o.functionName)).toEqual(['datastore_snapshot_create']);
    expect(mockSetStateBucket).not.toHaveBeenCalled();
  });

  it('weight: a fresh undo snapshot is the job; the re-apply and record are the step', async () => {
    mockGetCurrent.mockResolvedValue({ state: { canaries: { 'web-canary': canary } } });
    await run(registerRepoCanaryCommands, 'canary', 'weight', 'web', '--weight', '50');

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['datastore_snapshot_create', 'ctl'],
    ]);
    expect(stepNames()).toEqual([['recordCanary', 'success']]);
    expect(executed.map((o) => o.functionName)).toEqual([
      'datastore_snapshot_create',
      'kube_apply',
    ]);
    expect(mockSetStateBucket).toHaveBeenCalledExactlyOnceWith('canaries', {
      'web-canary': expect.objectContaining({ weight: 50 }),
    });
  });

  it('remove: kube_delete is the one job; forgetting the record is the step', async () => {
    mockGetCurrent.mockResolvedValue({ state: { canaries: { 'web-canary': canary } } });
    await run(registerRepoCanaryCommands, 'canary', 'remove', 'web');

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['kube_delete', 'ctl'],
    ]);
    expect(stepNames()).toEqual([['forgetCanary', 'success']]);
    expect(mockSetStateBucket).toHaveBeenCalledExactlyOnceWith('canaries', {});
  });

  it('control: a failed kube_delete leaves the record in place', async () => {
    mockGetCurrent.mockResolvedValue({ state: { canaries: { 'web-canary': canary } } });
    answer = { ...finished(), success: false, exitCode: 1, state: 'failed' };
    await run(registerRepoCanaryCommands, 'canary', 'remove', 'web');

    expect(mockSetStateBucket).not.toHaveBeenCalled();
  });
});

describe('repo log, repo merge and repo status', () => {
  const entries = JSON.stringify({ entries: [{ commit: 'c1', message: 'first' }] });

  beforeEach(() => {
    vi.mocked(configService.getRepository).mockImplementation((name: string) =>
      Promise.resolve({
        repositoryGuid: `guid-${name}`,
        networkId: 2816,
        credential: 'c',
        headCommit: `head-${name}`,
      } as never)
    );
    mockGetCurrent.mockResolvedValue({ state: {}, resources: { repositories: {} } });
  });

  it('log: one repository_log job on the tip; the listing is the step', async () => {
    answer = finished(entries);
    await run(registerRepoBranchingCommands, 'log', 'shop');

    expect(jobStarts().map((o) => [o.functionName, o.machineName, o.params])).toEqual([
      ['repository_log', 'm1', { repository: 'head-shop' }],
    ]);
    expect(stepNames()).toEqual([['renderRepoLog', 'success']]);
    expect(jobStarts()[0].jobSteps?.[0].needs_output).toBe(true);
  });

  it('log control: under --background nothing is rendered', async () => {
    answer = BACKGROUND;
    await run(registerRepoBranchingCommands, 'log', 'shop');

    expect(jobStarts()).toHaveLength(1);
    expect(mockPrint).not.toHaveBeenCalled();
  });

  it('merge: one repository_merge job; advancing the tip is the step, and nothing else touches the config', async () => {
    answer = finished();
    await run(registerRepoBranchingCommands, 'merge', 'shop', '--from', 'other');

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['repository_merge', 'm1'],
    ]);
    expect(jobStarts()[0].params).toMatchObject({ repository: 'shop', from: 'guid-other' });
    expect(jobStarts()[0].jobSteps?.map((st) => [st.name, st.on, st.params])).toEqual([
      ['advanceHeadCommit', 'success', { repo: 'shop', commit: 'guid-other' }],
    ]);
    expect(mockAddRepository).toHaveBeenCalledExactlyOnceWith(
      'shop',
      expect.objectContaining({ headCommit: 'guid-other' })
    );
  });

  it('merge control: under --background the tip is not advanced', async () => {
    answer = BACKGROUND;
    await run(registerRepoBranchingCommands, 'merge', 'shop', '--from', 'other');

    expect(jobStarts()).toHaveLength(1);
    expect(mockAddRepository).not.toHaveBeenCalled();
  });

  it('merge control: a failed job leaves the tip alone', async () => {
    answer = { ...finished(), success: false, exitCode: 1, state: 'failed' };
    await run(registerRepoBranchingCommands, 'merge', 'shop', '--from', 'other');

    expect(mockAddRepository).not.toHaveBeenCalled();
  });

  it('status: one repository_status job; printing the record is the step', async () => {
    answer = finished(JSON.stringify({ repository: 'shop', mounted: true }));
    const program = new Command().exitOverride();
    registerRepoCommands(program);
    await program.parseAsync(['repo', 'status', 'shop'], { from: 'user' });

    expect(jobStarts().map((o) => [o.functionName, o.machineName])).toEqual([
      ['repository_status', 'm1'],
    ]);
    expect(jobStarts()[0].jobSteps?.map((st) => [st.name, st.on, st.params])).toEqual([
      ['printRepoStatus', 'success', { name: 'shop' }],
    ]);
    expect(mockPrint).toHaveBeenCalledWith({ repository: 'shop', mounted: true }, 'json');
  });

  it('status control: under --background the record is not printed', async () => {
    answer = BACKGROUND;
    const program = new Command().exitOverride();
    registerRepoCommands(program);
    await program.parseAsync(['repo', 'status', 'shop'], { from: 'user' });

    expect(jobStarts()).toHaveLength(1);
    expect(mockPrint).not.toHaveBeenCalled();
  });
});
