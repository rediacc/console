import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  executeRepoFunction: vi.fn(),
  setRepositoryLifecycle: vi.fn(),
  getRepository: vi.fn(),
  print: vi.fn(),
  isAgentEnvironment: vi.fn(),
  isRepoAllowedByGrandEnv: vi.fn(),
  isOverrideLegitimate: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    handleError: (error: unknown) => {
      throw error;
    },
  };
});
vi.mock('../_validate.js', () => ({ assertMachineExists: async () => undefined }));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: async () => ({ name: 'app', repoKey: 'app:latest', machineName: 'm1' }),
}));
vi.mock('../../utils/repo-executor.js', () => ({
  executeRepoFunction: mocks.executeRepoFunction,
}));
vi.mock('../../utils/agent-guard.js', () => ({ isAgentEnvironment: mocks.isAgentEnvironment }));
vi.mock('../../utils/grand-env.js', () => ({
  isRepoAllowedByGrandEnv: mocks.isRepoAllowedByGrandEnv,
}));
vi.mock('../../utils/process-ancestry.js', () => ({
  isOverrideLegitimate: mocks.isOverrideLegitimate,
}));
vi.mock('../../services/core/output.js', () => ({ outputService: { print: mocks.print } }));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    setRepositoryLifecycle: mocks.setRepositoryLifecycle,
    getRepository: mocks.getRepository,
  },
}));

const { registerRepoPermissionCommands } = await import('../repo-permission.js');

async function run(argv: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerRepoPermissionCommands(program.command('repo'));
  await program.parseAsync(['repo', 'permission', ...argv], { from: 'user' });
  await settleJobSteps();
}

/** The mirror and the render are the job's steps: run them the way a finished job owes them. */
async function settleJobSteps(): Promise<void> {
  const call = mocks.executeRepoFunction.mock.calls.at(-1);
  if (!call) return;
  const result = (await mocks.executeRepoFunction.mock.results.at(-1)?.value) as {
    success: boolean;
    stdout?: string;
  };
  if (!result.success) return;
  const { resolveStepHandler } = await import('../../services/jobs/steps.js');
  for (const step of call[4].job.steps as { name: string; params: Record<string, string> }[]) {
    const handler = await resolveStepHandler(step.name);
    await handler({
      jobId: '',
      machine: 'm1',
      params: step.params,
      state: 'succeeded',
      output: result.stdout,
    });
  }
}

const GRANT_STDOUT = JSON.stringify({
  lifecycle: { root: true, paths: [{ path: '/srv/a' }, { path: '/srv/b', read_write: true }] },
});

beforeEach(() => {
  vi.clearAllMocks();
  mocks.isAgentEnvironment.mockReturnValue(false);
  mocks.isRepoAllowedByGrandEnv.mockReset();
  mocks.isOverrideLegitimate.mockReset();
  // A grand repository: no grandGuid of its own to differ from.
  mocks.getRepository.mockResolvedValue({ repositoryGuid: 'g-app' });
  mocks.executeRepoFunction.mockResolvedValue({ success: true, stdout: GRANT_STDOUT });
});

describe('rdc repo permission grant|revoke|show', () => {
  it('grant dispatches repository_permission_grant with root and path', async () => {
    await run(['grant', 'app', '--root', '--path', '/srv/b:rw']);
    const [fn, repoKey, machine, params] = mocks.executeRepoFunction.mock.calls[0];
    expect([fn, repoKey, machine]).toEqual(['repository_permission_grant', 'app:latest', 'm1']);
    expect(params).toEqual({ root: true, path: '/srv/b:rw' });
  });

  it('mirrors the lifecycle grant renet reports into state.repos', async () => {
    await run(['grant', 'app', '--path', '/srv/a']);
    expect(mocks.setRepositoryLifecycle).toHaveBeenCalledWith('app:latest', {
      root: true,
      paths: ['/srv/a', '/srv/b:rw'],
    });
  });

  it('revoke dispatches repository_permission_revoke and clears the mirror on the default tier', async () => {
    mocks.executeRepoFunction.mockResolvedValue({ success: true, stdout: '{}' });
    await run(['revoke', 'app', '--root']);
    expect(mocks.executeRepoFunction.mock.calls[0][0]).toBe('repository_permission_revoke');
    expect(mocks.setRepositoryLifecycle).toHaveBeenCalledWith('app:latest', {
      root: false,
      paths: [],
    });
  });

  it('refuses a grant that names neither --root nor --path, before any call', async () => {
    await expect(run(['grant', 'app'])).rejects.toThrow('nothingToChange');
    expect(mocks.executeRepoFunction).not.toHaveBeenCalled();
  });

  it('refuses --root to an agent without the operator override, and with an injected one', async () => {
    mocks.isAgentEnvironment.mockReturnValue(true);
    mocks.isRepoAllowedByGrandEnv.mockReturnValue(false);
    await expect(run(['grant', 'app', '--root'])).rejects.toThrow('rootGrantBlocked');
    mocks.isRepoAllowedByGrandEnv.mockReturnValue(true);
    mocks.isOverrideLegitimate.mockReturnValue(false);
    await expect(run(['grant', 'app', '--root'])).rejects.toThrow('rootGrantOverride');
    expect(mocks.executeRepoFunction).not.toHaveBeenCalled();
  });

  it('lets an agent grant --root once the operator override is verified', async () => {
    mocks.isAgentEnvironment.mockReturnValue(true);
    mocks.isRepoAllowedByGrandEnv.mockReturnValue(true);
    mocks.isOverrideLegitimate.mockReturnValue(true);
    await run(['grant', 'app', '--root']);
    expect(mocks.executeRepoFunction).toHaveBeenCalledTimes(1);
  });

  describe('--path on a grand repository under an agent (finding 9fd746cf.4)', () => {
    beforeEach(() => {
      mocks.isAgentEnvironment.mockReturnValue(true);
    });

    it.each(['grant', 'revoke'])(
      '%s is refused without the operator override and with an injected one',
      async (verb) => {
        mocks.isRepoAllowedByGrandEnv.mockReturnValue(false);
        await expect(run([verb, 'app', '--path', '/srv/a'])).rejects.toThrow('pathGrantBlocked');
        mocks.isRepoAllowedByGrandEnv.mockReturnValue(true);
        mocks.isOverrideLegitimate.mockReturnValue(false);
        await expect(run([verb, 'app', '--path', '/srv/a'])).rejects.toThrow('pathGrantOverride');
        expect(mocks.executeRepoFunction).not.toHaveBeenCalled();
      }
    );

    it('control: the verified operator override lets the agent grant a path', async () => {
      mocks.isRepoAllowedByGrandEnv.mockReturnValue(true);
      mocks.isOverrideLegitimate.mockReturnValue(true);
      await run(['grant', 'app', '--path', '/srv/a']);
      expect(mocks.executeRepoFunction).toHaveBeenCalledTimes(1);
    });

    it('control: a fork stays free, with no override at all', async () => {
      mocks.getRepository.mockResolvedValue({ repositoryGuid: 'g-fork', grandGuid: 'g-app' });
      mocks.isRepoAllowedByGrandEnv.mockReturnValue(false);
      await run(['grant', 'app', '--path', '/srv/a']);
      expect(mocks.executeRepoFunction).toHaveBeenCalledTimes(1);
    });

    it('control: a person (not an agent) is never gated', async () => {
      mocks.isAgentEnvironment.mockReturnValue(false);
      mocks.isRepoAllowedByGrandEnv.mockReturnValue(false);
      await run(['grant', 'app', '--path', '/srv/a']);
      expect(mocks.executeRepoFunction).toHaveBeenCalledTimes(1);
    });
  });

  it('fails the mirror step when renet output cannot be parsed, leaving no silent old lifecycle (9fd746cf.1)', async () => {
    mocks.executeRepoFunction.mockResolvedValue({ success: true, stdout: 'not json' });
    await expect(run(['grant', 'app', '--path', '/srv/a'])).rejects.toThrow('show.unreadable');
    expect(mocks.setRepositoryLifecycle).not.toHaveBeenCalled();
  });

  it('show prints the grant as one row', async () => {
    await run(['show', 'app']);
    expect(mocks.executeRepoFunction.mock.calls[0][0]).toBe('repository_permission_show');
    expect(mocks.print.mock.calls[0][0]).toEqual([{ root: 'Yes', paths: '/srv/a, /srv/b:rw' }]);
  });
});
