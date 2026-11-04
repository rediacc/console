/**
 * PLAN-detached-jobs J16: a converted repo verb is one machine job whose client-side follow-up rides the ticket as
 * steps. `repo create` is the first row: under `--background` the job's start returns the ticket at once with the plan
 * recorded, and the finished job's `identityRefresh` step later refreshes the licence identity with the size the repo
 * was created with (review cac18e21.2). The executor is a recording fake behind the runCommandJob seam, the ticket
 * store is real in a temp directory, and the step claim grants every claim, so the test sees the command's own plan.
 */
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockAddRepository = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockRemoveRepository = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const mockListRepositories = vi.hoisted(() => vi.fn().mockResolvedValue([]));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: vi.fn().mockResolvedValue({ resources: { machines: {}, datastores: {} } }),
    getRepository: vi.fn().mockResolvedValue(undefined),
    getRepositoryKey: (ref: string) => Promise.resolve(`${ref}:latest`),
    allocateNetworkId: vi.fn(),
    addRepository: mockAddRepository,
    removeRepository: mockRemoveRepository,
    listRepositories: mockListRepositories,
    applyDefaults: () => Promise.resolve({ team: 't' }),
    resolveDestructiveTarget: (key: string) =>
      Promise.resolve({ key, config: { repositoryGuid: 'g-shop', parentGuid: 'g-grand' } }),
  },
}));
// The repo verbs below resolve their ref, policy and network id through these seams; each answers for the one repo `shop`.
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: () =>
    Promise.resolve({ name: 'shop', repoKey: 'shop:latest', machineName: 'm1' }),
  resolveRepoTarget: (target: { machine?: string }) =>
    Promise.resolve({ machineName: target.machine ?? 'm1' }),
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn(),
  CMD: new Proxy({}, { get: (_t, key) => String(key) }),
}));
vi.mock('../../services/config/network-id-discovery.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  ensureRepositoryNetworkId: vi.fn().mockResolvedValue(1),
}));
const settle = vi.hoisted(() => ({ entry: vi.fn(), backups: vi.fn(), license: vi.fn() }));
vi.mock('../repo-delete-settle.js', () => ({
  isFork: () => false,
  settleConfigEntry: settle.entry,
  settleCloudBackups: settle.backups,
  settleRepoLicense: settle.license,
}));
vi.mock('../../remote/vscode/index.js', () => ({
  generateConnectionName: () => 'c',
  removePersistedKeys: vi.fn(),
  removeSSHConfigEntry: vi.fn(),
}));
const mockRefreshIdentity = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/executor/local-executor.js', () => ({
  localExecutorService: { refreshIdentityFor: mockRefreshIdentity },
}));
const mockReconcile = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../services/backup/repo-change-hook.js', () => ({
  reconcileBackupSchedules: mockReconcile,
}));
// A call that does not go through runCommandJob (a probe read, a streaming form, a step's own call) lands here.
const plain = vi.hoisted(() => ({
  calls: [] as Record<string, unknown>[],
  /** Captured stdout by renet function, over the default answer. */
  stdoutFor: {} as Record<string, string>,
  answer: { success: true, exitCode: 0, durationMs: 0, state: 'succeeded', stdout: '' } as Record<
    string,
    unknown
  >,
}));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({
    execute: (options: Record<string, unknown>) => {
      plain.calls.push(options);
      return Promise.resolve({
        ...plain.answer,
        ...(plain.stdoutFor[String(options.functionName)] === undefined
          ? {}
          : { stdout: plain.stdoutFor[String(options.functionName)] }),
      });
    },
  }),
  requestNetworkIdAuto: vi.fn(),
}));
const mockPrint = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    print: mockPrint,
    setTimelineRendered: vi.fn(),
  },
}));
vi.mock('../../utils/agent-guard.js', () => ({ assertAgentRepoCreate: vi.fn() }));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../../utils/ssh-keygen.js', () => ({
  generateSSHKeyPair: () => ({ privateKey: 'priv', publicKey: 'pub' }),
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  handleError: (e: unknown) => {
    throw e;
  },
}));

const { configService } = await import('../../services/config/config-resources.js');
const { outputService } = await import('../../services/core/output.js');
const { setCommandJobDeps } = await import('../../services/jobs/command-job.js');
const { TicketStore } = await import('../../services/jobs/ticket-store.js');
const { resolveStepHandler } = await import('../../services/jobs/steps.js');
const { handleRepoCreate, registerRepoCreateDeleteCommands } = await import(
  '../repo-create-delete.js'
);
const { registerRepoPromoteCommand } = await import('../repo-promote.js');
const { registerRepoPruneCommand } = await import('../repo-prune.js');
const { registerRepoTrimCommand } = await import('../repo-trim.js');
const { registerRepoContainerCommands } = await import('../repo-container.js');
const { registerExtendedRepoCommands } = await import('../repo-extended.js');
const { registerRepoMaintenanceCommands } = await import('../repo-maintenance.js');
await import('../repo-delta.js');
const { Command } = await import('commander');

type Executed = {
  functionName: string;
  machineName?: string;
  params?: Record<string, unknown>;
  probe?: boolean;
  deferIdentityRefresh?: boolean;
  jobSteps?: { name: string; on: string; params: Record<string, unknown> }[];
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
let answer: Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  plain.calls.length = 0;
  plain.stdoutFor = {};
  plain.answer = { success: true, exitCode: 0, durationMs: 0, state: 'succeeded', stdout: '' };
  mockListRepositories.mockResolvedValue([]);
  vi.mocked(configService.getRepository).mockResolvedValue(undefined);
  dir = mkdtempSync(join(tmpdir(), 'job-plan-repo-'));
  store = new TicketStore('test', dir);
  executed = [];
  answer = FINISHED;
  setCommandJobDeps({
    executor: () => ({
      execute: (options) => {
        executed.push(options as unknown as Executed);
        return Promise.resolve(answer as never);
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

describe('repo create (one job; rollback, identity refresh and schedules as steps)', () => {
  it('makes one job start for the machine and defers the identity refresh to a step', async () => {
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });

    expect(executed.map((o) => o.functionName)).toEqual(['repository_create']);
    expect(executed[0].deferIdentityRefresh).toBe(true);
    expect(executed[0].jobSteps?.map((s) => [s.name, s.on])).toEqual([
      ['rollbackCreate', 'failure'],
      ['identityRefresh', 'success'],
      ['reconcileBackupSchedules', 'success'],
    ]);
  });

  it('control: followed, the success steps run once and the rollback does not', async () => {
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });

    expect(mockRefreshIdentity).toHaveBeenCalledExactlyOnceWith('repository_create', 'm1', {
      repository: 'shop',
      size: '5G',
    });
    expect(mockReconcile).toHaveBeenCalledExactlyOnceWith('m1');
    expect(mockRemoveRepository).not.toHaveBeenCalled();
    expect(store.tickets()[0].acknowledged).toBe(true);
  });

  it('a failed job rolls the registration back and refreshes nothing', async () => {
    answer = FAILED;
    // Absent until the create registers it, then the registered record: the rollback step removes it by GUID.
    vi.mocked(configService.getRepository).mockImplementation(() => {
      const added = mockAddRepository.mock.calls[0]?.[1] as { repositoryGuid: string } | undefined;
      return Promise.resolve(
        added ? ({ repositoryGuid: added.repositoryGuid } as never) : undefined
      );
    });
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });

    expect(mockRemoveRepository).toHaveBeenCalledExactlyOnceWith('shop');
    expect(mockRefreshIdentity).not.toHaveBeenCalled();
    expect(mockReconcile).not.toHaveBeenCalled();
  });

  it('under --background the ticket carries the plan, and the finished job refreshes the identity with its size', async () => {
    answer = BACKGROUND;
    await handleRepoCreate('shop', { machine: 'm1', size: '5G' });

    expect(mockRefreshIdentity).not.toHaveBeenCalled();
    expect(mockReconcile).not.toHaveBeenCalled();
    const ticket = store.tickets()[0];
    expect(ticket.steps.map((s) => s.name)).toEqual([
      'rollbackCreate',
      'identityRefresh',
      'reconcileBackupSchedules',
    ]);
    expect(ticket.stepsDone).toEqual([]);

    // The observer that sees the job finish runs the step from the ticket's recorded params.
    const refresh = ticket.steps.find((s) => s.name === 'identityRefresh');
    const handler = await resolveStepHandler('identityRefresh');
    expect(ticket.machine).toBe('m1');
    await handler({
      jobId: ticket.jobId ?? 'job-1',
      machine: ticket.machine as string,
      params: refresh?.params ?? {},
      state: 'succeeded',
    });
    expect(mockRefreshIdentity).toHaveBeenCalledExactlyOnceWith('repository_create', 'm1', {
      repository: 'shop',
      size: '5G',
    });
  });
});

type CommandT = InstanceType<typeof Command>;

/** Parse `repo <argv>` against the registered verbs; `admin` is `repo admin`. */
async function runVerb(
  register: (repo: CommandT, admin: CommandT) => void,
  ...argv: string[]
): Promise<void> {
  const program = new Command();
  program.exitOverride();
  const repo = program.command('repo');
  const admin = repo.command('admin');
  register(repo, admin);
  await program.parseAsync(['repo', ...argv], { from: 'user' });
}

const stepNames = (call: Executed): string[] => (call.jobSteps ?? []).map((s) => s.name);

describe('repo verbs outside J4: one job per machine, the follow-up as steps', () => {
  beforeEach(() => {
    // Every verb below acts on the repo `shop`, whose record the executor helper and the settle steps read.
    vi.mocked(configService.getRepository).mockImplementation((key: string) =>
      Promise.resolve(
        key === 'shop' || key === 'shop:latest'
          ? ({ repositoryGuid: 'g-shop', parentGuid: 'g-grand' } as never)
          : undefined
      )
    );
  });

  describe('repo delete', () => {
    const del = (repo: CommandT) => registerRepoCreateDeleteCommands(repo);

    it('makes one job with the settlement as its success step, and runs it when followed', async () => {
      await runVerb(del, 'delete', 'shop:latest', '-y');

      expect(executed.map((o) => o.functionName)).toEqual(['repository_delete']);
      expect(executed[0].machineName).toBe('m1');
      expect(stepNames(executed[0])).toEqual(['settleRepoDelete']);
      expect(settle.entry).toHaveBeenCalledTimes(1);
      expect(mockReconcile).toHaveBeenCalledExactlyOnceWith('m1');
    });

    it('control: a ticket handed back early settles nothing and keeps the step', async () => {
      answer = BACKGROUND;
      await runVerb(del, 'delete', 'shop:latest', '-y');

      expect(settle.entry).not.toHaveBeenCalled();
      expect(mockReconcile).not.toHaveBeenCalled();
      expect(store.tickets()[0].steps.map((s) => s.name)).toEqual(['settleRepoDelete']);
    });

    it('control: a failed job settles nothing', async () => {
      answer = FAILED;
      await runVerb(del, 'delete', 'shop:latest', '-y');

      expect(settle.entry).not.toHaveBeenCalled();
    });
  });

  describe('repo promote', () => {
    const promote = (repo: CommandT) => registerRepoPromoteCommand(repo);
    beforeEach(() => {
      mockListRepositories.mockResolvedValue([
        { name: 'grand', config: { repositoryGuid: 'g-grand' } },
      ]);
    });

    it('makes one job whose success step moves the fork to the backup entry and re-renders the units', async () => {
      await runVerb(promote, 'promote', 'shop:latest', '-y');

      expect(executed.map((o) => o.functionName)).toEqual(['repository_promote']);
      expect(stepNames(executed[0])).toEqual(['settlePromote']);
      expect(mockAddRepository).toHaveBeenCalledExactlyOnceWith(
        expect.stringMatching(/^shop:pre-promote-\d{8}$/),
        expect.anything()
      );
      expect(mockRemoveRepository).toHaveBeenCalledExactlyOnceWith('shop:latest');
      expect(mockReconcile).toHaveBeenCalledExactlyOnceWith('m1');
    });

    it('control: a ticket handed back early swaps no config, and a failed job swaps none either', async () => {
      answer = BACKGROUND;
      await runVerb(promote, 'promote', 'shop:latest', '-y');
      expect(mockAddRepository).not.toHaveBeenCalled();
      expect(mockRemoveRepository).not.toHaveBeenCalled();
      expect(store.tickets()[0].steps.map((s) => s.name)).toEqual(['settlePromote']);

      answer = FAILED;
      await runVerb(promote, 'promote', 'shop:latest', '-y');
      expect(mockRemoveRepository).not.toHaveBeenCalled();
    });
  });

  describe('repo prune', () => {
    const prune = (repo: CommandT) => registerRepoPruneCommand(repo);
    const RECORD = JSON.stringify({ mode: '', classes: {}, estimate: 0, estimate_online: 0 });

    it('the ref form is one job whose table is the success step', async () => {
      answer = { ...FINISHED, stdout: RECORD };
      await runVerb(prune, 'prune', 'shop:latest');

      expect(executed.map((o) => o.functionName)).toEqual(['repository_docker_prune']);
      expect(stepNames(executed[0])).toEqual(['renderRepoPrune']);
      expect(mockPrint).toHaveBeenCalledWith(expect.any(Array), 'table');
    });

    it('control: a ticket handed back early prints no table', async () => {
      answer = { ...BACKGROUND, stdout: RECORD };
      await runVerb(prune, 'prune', 'shop:latest');

      expect(mockPrint).not.toHaveBeenCalled();
    });

    it('the machine survey stays client-driven: every call is an attached probe, none a ticketed job', async () => {
      plain.stdoutFor = {
        repository_list: '[{"name":"g1","mounted":true}]',
        repository_docker_prune: '{"mode":"","classes":{}}',
      };
      await runVerb(prune, 'prune', '-m', 'm1');

      expect(executed).toEqual([]);
      expect(plain.calls.map((c) => c.functionName)).toEqual([
        'repository_list',
        'repository_docker_prune',
      ]);
      expect(plain.calls.every((c) => c.probe === true)).toBe(true);
    });
  });

  describe('repo trim', () => {
    const trim = (repo: CommandT) => registerRepoTrimCommand(repo);

    it('the ref form is one job with the render as its step', async () => {
      answer = { ...FINISHED, stdout: '{"repos":[]}' };
      await runVerb(trim, 'trim', 'shop:latest');

      expect(executed.map((o) => o.functionName)).toEqual(['repository_trim']);
      expect(executed[0].params).toMatchObject({ name: 'g-shop' });
      expect(stepNames(executed[0])).toEqual(['renderRepoTrim']);
    });

    it('the -m form is one machine job without a repository, and a ticket handed back early renders nothing', async () => {
      answer = { ...FINISHED, stdout: '{"repos":[]}' };
      await runVerb(trim, 'trim', '-m', 'm1');
      expect(executed).toHaveLength(1);
      expect(executed[0].params?.name).toBeUndefined();
      expect(executed[0].machineName).toBe('m1');

      const renders = () =>
        vi
          .mocked(outputService.info)
          .mock.calls.filter(([text]) => String(text).includes('trim.noMountedRepos'));
      expect(renders()).toHaveLength(1);
      answer = { ...BACKGROUND, stdout: '{"repos":[]}' };
      await runVerb(trim, 'trim', '-m', 'm1');
      expect(renders()).toHaveLength(1);
    });
  });

  describe('repo exec and repo logs', () => {
    const container = (repo: CommandT) => registerRepoContainerCommands(repo);

    it('exec is one job with no steps, and the remote exit code is the result', async () => {
      answer = { ...FAILED, exitCode: 7 };
      await runVerb(container, 'exec', 'shop:latest', '--', 'test', '-f', '/x');

      expect(executed.map((o) => o.functionName)).toEqual(['container_exec']);
      expect(stepNames(executed[0])).toEqual([]);
      expect(plain.calls).toEqual([]);
      expect(process.exitCode).toBe(7);
    });

    it('control: the interactive form keeps the terminal and starts no ticketed job', async () => {
      await runVerb(container, 'exec', 'shop:latest', '-i', '--', 'sh');

      expect(executed).toEqual([]);
      expect(plain.calls.map((c) => c.functionName)).toEqual(['container_exec']);
    });

    it('logs is one read job, and the -f form streams without one', async () => {
      await runVerb(container, 'logs', 'shop:latest');
      expect(executed.map((o) => o.functionName)).toEqual(['container_logs']);
      expect(plain.calls).toEqual([]);

      executed = [];
      await runVerb(container, 'logs', 'shop:latest', '-f');
      expect(executed).toEqual([]);
      expect(plain.calls.map((c) => c.functionName)).toEqual(['container_logs']);
    });
  });

  describe('repo resize, expand and the admin verbs (single calls, no steps)', () => {
    const extended = (repo: CommandT, admin: CommandT) => registerExtendedRepoCommands(repo, admin);

    const CASES: [string, string[], string][] = [
      ['repo resize', ['resize', 'shop:latest', '--size', '10G'], 'repository_resize'],
      ['repo expand', ['expand', 'shop:latest', '--size', '10G'], 'repository_expand'],
      ['repo admin validate', ['admin', 'validate', 'shop:latest'], 'repository_validate'],
      ['repo admin ownership', ['admin', 'ownership', 'shop:latest'], 'repository_ownership'],
      [
        'repo admin autostart enable',
        ['admin', 'autostart', 'enable', 'shop:latest'],
        'repository_autostart_enable',
      ],
      [
        'repo admin autostart disable',
        ['admin', 'autostart', 'disable', 'shop:latest'],
        'repository_autostart_disable',
      ],
    ];

    it.each(CASES)(
      '%s makes one job for the machine and no renet execute',
      async (_verb, argv, fn) => {
        await runVerb(extended, ...argv);

        expect(executed.map((o) => o.functionName)).toEqual([fn]);
        expect(executed[0].machineName).toBe('m1');
        expect(stepNames(executed[0])).toEqual([]);
        expect(plain.calls).toEqual([]);
      }
    );

    it('control: the job is recorded on a ticket under the verb name', async () => {
      await runVerb(extended, 'resize', 'shop:latest', '--size', '10G');

      expect(store.tickets().map((ticket) => ticket.verb)).toEqual(['repo resize']);
    });

    it('repo admin template apply makes one job carrying the template', async () => {
      const file = join(dir, 'tmpl.json');
      writeFileSync(file, '{}');
      await runVerb(
        extended,
        'admin',
        'template',
        'apply',
        'shop:latest',
        '--template',
        'x',
        '--file',
        file
      );

      expect(executed.map((o) => o.functionName)).toEqual(['repository_template_apply']);
      expect(stepNames(executed[0])).toEqual([]);
      expect(typeof executed[0].params?.tmpl).toBe('string');
    });

    it('the -m form of autostart enable is one machine job over the _all function', async () => {
      const program = new Command();
      program.exitOverride();
      const repo = program.command('repo');
      const admin = repo.command('admin');
      extended(repo, admin);
      const enable = admin.commands
        .find((c) => c.name() === 'autostart')
        ?.commands.find((c) => c.name() === 'enable');
      enable?.option('-m, --machine <name>');
      await program.parseAsync(['repo', 'admin', 'autostart', 'enable', '-m', 'm1'], {
        from: 'user',
      });

      expect(executed.map((o) => [o.functionName, o.machineName])).toEqual([
        ['repository_autostart_enable_all', 'm1'],
      ]);
    });

    it('repo admin autostart list is one read job with the table as its step', async () => {
      answer = { ...FINISHED, stdout: '{"service_installed":true,"repositories":[]}' };
      await runVerb(extended, 'admin', 'autostart', 'list', '-m', 'm1');

      expect(executed.map((o) => o.functionName)).toEqual(['repository_autostart_list']);
      expect(stepNames(executed[0])).toEqual(['renderAutostartList']);
      expect(vi.mocked(outputService.info)).toHaveBeenCalledWith(
        expect.stringContaining('autostart.list.service')
      );
    });

    it('control: a failed job renders no table', async () => {
      answer = FAILED;
      await runVerb(extended, 'admin', 'autostart', 'list', '-m', 'm1');

      expect(vi.mocked(outputService.info)).not.toHaveBeenCalledWith(
        expect.stringContaining('autostart.list.service')
      );
    });
  });

  describe('repo gc and repo admin fsck (the set is computed from the config)', () => {
    const maintenance = (repo: CommandT, admin: CommandT) =>
      registerRepoMaintenanceCommands(repo, admin);
    beforeEach(() => {
      mockListRepositories.mockResolvedValue([
        { name: 'c1', config: { repositoryGuid: 'g-c1', immutable: true } },
      ]);
      plain.answer = { ...plain.answer, stdout: '[{"name":"g-c1","mounted":false}]' };
    });

    it('gc reads the machine as an attached probe, then runs one job per deletion', async () => {
      await runVerb(maintenance, 'gc', '-m', 'm1', '--apply');

      expect(plain.calls.map((c) => [c.functionName, c.probe])).toEqual([
        ['repository_list', true],
      ]);
      expect(executed.map((o) => [o.functionName, o.params])).toEqual([
        ['repository_delete', { repository: 'g-c1' }],
      ]);
      expect(stepNames(executed[0])).toEqual([]);
      expect(vi.mocked(outputService.success)).toHaveBeenCalledWith(
        expect.stringContaining('gc.deleted')
      );
    });

    it('control: a deletion handed back as a ticket is counted as started, never as deleted', async () => {
      answer = BACKGROUND;
      await runVerb(maintenance, 'gc', '-m', 'm1', '--apply');

      expect(vi.mocked(outputService.success)).not.toHaveBeenCalledWith(
        expect.stringContaining('gc.deleted')
      );
      expect(vi.mocked(outputService.info)).toHaveBeenCalledWith(
        expect.stringContaining('gc.started')
      );
    });

    it('fsck is reads only: attached probes, no ticketed job', async () => {
      await runVerb(maintenance, 'admin', 'fsck', '-m', 'm1');

      expect(executed).toEqual([]);
      expect(plain.calls.map((c) => [c.functionName, c.probe])).toEqual([
        ['repository_list', true],
      ]);
    });
  });

  describe('repo push: repository_commit_meta after an immutable push', () => {
    it('is the syncCommitMeta step, one call to the push target with no source datastore', async () => {
      const handler = await resolveStepHandler('syncCommitMeta');
      await handler({
        jobId: 'job-1',
        machine: 'm1',
        params: { target: 'm2', commit: 'c1', message: 'msg', parent: 'p1' },
        state: 'succeeded',
      });

      expect(plain.calls).toHaveLength(1);
      expect(plain.calls[0]).toMatchObject({
        functionName: 'repository_commit_meta',
        machineName: 'm2',
        params: { repository: 'c1', message: 'msg', commitParent: 'p1' },
      });
      expect(plain.calls[0].datastore).toBeUndefined();
    });
  });
});
