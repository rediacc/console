/**
 * `rdc vscode expose|unexpose <ref>` (PLAN-vscode-browser-exposure V3): each verb is one renet job on the ref's
 * machine, `repository_vscode_expose` or `repository_vscode_unexpose`, naming the repository. Expose prints the
 * editor's URL from its `printVscodeExpose` step, so under `--background` nothing is printed; a cluster-placed repo is
 * refused before any job starts. The real command runs, with a recording executor behind the runCommandJob seam and a
 * real ticket store in a temp directory.
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

const repoEntry = vi.hoisted(() => ({
  current: { repositoryGuid: 'guid-shop', networkId: 2816, credential: 'c' } as
    | Record<string, unknown>
    | undefined,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ resources: { repositories: {} } }),
    getRepository: vi.fn(() => Promise.resolve(repoEntry.current)),
    getRepositoryKey: (ref: string) => Promise.resolve(ref),
    listRepositories: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock('../../services/config/network-id-discovery.js', () => ({
  ensureRepositoryNetworkId: vi.fn().mockResolvedValue(2816),
}));

const out = vi.hoisted(() => ({
  success: vi.fn(),
  info: vi.fn(),
  error: vi.fn(),
  print: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { ...out, warn: vi.fn(), format: vi.fn(), setTimelineRendered: vi.fn() },
}));
const mockSetExitCode = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/request-context.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  setExitCode: mockSetExitCode,
}));

type Executed = {
  functionName: string;
  machineName: string;
  params?: Record<string, unknown>;
  captureOutput?: boolean;
  jobSteps?: { name: string; on: string; needs_output?: boolean }[];
};
const executed: Executed[] = [];
const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getExecutor: () => ({ execute: mockExecute }),
}));

const mockResolveRepoRef = vi.hoisted(() => vi.fn());
vi.mock('../../utils/repo-target.js', () => ({ resolveRepoRef: mockResolveRepoRef }));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
const outputFormat = vi.hoisted(() => ({ current: 'table' }));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getOutputFormat: () => outputFormat.current,
  handleError: (e: unknown) => {
    throw e;
  },
}));

const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const { registerVSCodeExposeCommands } = await import('../vscode-expose.js');
const { parseVSCodeExposeResult } = await import('../../services/core/vscode-server-remote.js');

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

const RESULT = {
  guid: 'guid-shop',
  hostname: 'vscode.shop.m1.example.io',
  url: 'https://vscode.shop.m1.example.io/?folder=/data/work',
  serviceIp: '127.0.11.62',
  folder: '/data/work',
};

let dir: string;
let store: InstanceType<typeof TicketStore>;
let answer: Record<string, unknown>;

const jobStarts = () => executed.filter((o) => o.jobSteps !== undefined);

async function rdcVscode(...argv: string[]): Promise<void> {
  const vscode = new Command('vscode').exitOverride();
  registerVSCodeExposeCommands(vscode);
  await vscode.parseAsync(argv, { from: 'user' });
}

beforeEach(() => {
  vi.clearAllMocks();
  executed.length = 0;
  outputFormat.current = 'table';
  repoEntry.current = { repositoryGuid: 'guid-shop', networkId: 2816, credential: 'c' };
  answer = finished(`[bridge] starting\n${JSON.stringify(RESULT)}\n`);
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
  dir = mkdtempSync(join(tmpdir(), 'vscode-expose-'));
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

describe('vscode expose', () => {
  it('one repository_vscode_expose job on the ref machine; the step prints the URL', async () => {
    await rdcVscode('expose', 'shop');

    expect(jobStarts().map((o) => [o.functionName, o.machineName, o.params])).toEqual([
      ['repository_vscode_expose', 'm1', { repository: 'shop' }],
    ]);
    expect(jobStarts()[0].jobSteps?.map((s) => [s.name, s.on, s.needs_output])).toEqual([
      ['printVscodeExpose', 'success', true],
    ]);
    expect(out.success).toHaveBeenCalledExactlyOnceWith(
      `commands.vscode.expose.exposed:${JSON.stringify({ url: RESULT.url })}`
    );
    expect(mockSetExitCode).not.toHaveBeenCalled();
  });

  it('prints the parsed result as a document under a structured output format', async () => {
    outputFormat.current = 'json';
    await rdcVscode('expose', 'shop');

    expect(out.print).toHaveBeenCalledExactlyOnceWith(RESULT, 'json');
    expect(out.success).not.toHaveBeenCalled();
  });

  it('control: under --background the URL is not printed', async () => {
    answer = BACKGROUND;
    await rdcVscode('expose', 'shop');

    expect(jobStarts()).toHaveLength(1);
    expect(out.success).not.toHaveBeenCalled();
    expect(out.print).not.toHaveBeenCalled();
  });

  it('a job that reports no result fails with exit code 1 instead of printing a blank URL', async () => {
    answer = finished('[bridge] done\n');
    await rdcVscode('expose', 'shop');

    expect(out.error).toHaveBeenCalledWith('commands.vscode.expose.noResult');
    expect(mockSetExitCode).toHaveBeenCalledWith(1);
    expect(out.success).not.toHaveBeenCalled();
  });

  it('refuses a cluster-placed repo before any job starts', async () => {
    mockResolveRepoRef.mockResolvedValue({
      name: 'shop',
      repoKey: 'shop',
      machineName: 'ctl',
      kubeCluster: 'k8s-main',
      tag: 'latest',
    });

    await expect(rdcVscode('expose', 'shop')).rejects.toThrow(/featureUnsupportedV1/);
    expect(executed).toEqual([]);
  });

  it('refuses a ref the config does not hold before any job starts', async () => {
    repoEntry.current = undefined;

    await expect(rdcVscode('expose', 'shop')).rejects.toThrow(/exposeRepoNotFound/);
    expect(executed).toEqual([]);
  });
});

describe('vscode unexpose', () => {
  it('one repository_vscode_unexpose job on the ref machine, then the stop is reported', async () => {
    answer = finished();
    await rdcVscode('unexpose', 'shop');

    expect(jobStarts().map((o) => [o.functionName, o.machineName, o.params])).toEqual([
      ['repository_vscode_unexpose', 'm1', { repository: 'shop' }],
    ]);
    expect(jobStarts()[0].jobSteps).toEqual([]);
    expect(out.success).toHaveBeenCalledExactlyOnceWith(
      `commands.vscode.unexpose.stopped:${JSON.stringify({ name: 'shop' })}`
    );
  });
});

describe('parseVSCodeExposeResult', () => {
  it('finds the result line among prefixed bridge log lines', () => {
    expect(
      parseVSCodeExposeResult(`[a] x {not json}\n[renet] ${JSON.stringify(RESULT)}\n`)
    ).toEqual(RESULT);
  });

  it('refuses an object missing a field', () => {
    const partial: Partial<typeof RESULT> = { ...RESULT };
    delete partial.url;
    expect(parseVSCodeExposeResult(JSON.stringify(partial))).toBeUndefined();
  });
});
