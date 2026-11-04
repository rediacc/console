/**
 * PLAN-detached-jobs J18: the converted machine verbs each run as ONE machine job with their tails as ticket steps.
 * `machine setup` keeps the bootstrap upload outside the job (renet must be on the machine before its own `setup`
 * runs), then starts one `setup` command-kind job; `machine gpu list`, `converge` and `restart-services` make one job
 * and render in a step. The executor is a recording fake behind the runCommandJob seam.
 */
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installJobDeps } from './job-deps.js';

const mocks = vi.hoisted(() => ({
  format: 'table' as 'json' | 'table',
  print: vi.fn(),
  info: vi.fn(),
  success: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
  setExitCode: vi.fn(),
  acquireRemoteRenet: vi.fn(),
  order: [] as string[],
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getOutputFormat: () => mocks.format,
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: async () => undefined }));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    print: mocks.print,
    info: mocks.info,
    success: mocks.success,
    warn: mocks.warn,
    error: mocks.error,
  },
}));
vi.mock('../../services/core/request-context.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  setExitCode: mocks.setExitCode,
  writeStdout: vi.fn(),
  writeStderr: vi.fn(),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getLocalConfig: async () => ({
      sshPrivateKey: 'key',
      sshPublicKey: 'ssh-ed25519 AAAA',
      ssh: {},
      machines: {},
    }),
    getLocalMachine: async () => ({ ip: '10.0.0.1' }),
    listRepositories: async () => [],
    getCurrent: async () => ({
      resources: { cloudProviders: { hetzner: { provider: 'hetzner' } } },
    }),
    addMachine: vi.fn(async () => undefined),
    updateMachine: vi.fn(async () => undefined),
  },
}));
// The tofu leg runs locally and stays out of the job; these stand in for the binary, the plan and the SSH wait.
vi.mock('../../services/tofu/executor.js', () => ({
  TofuExecutor: class {
    static resolveBinary = vi.fn(async () => undefined);
    writeConfig = async () => undefined;
    init = async () => undefined;
    apply = async () => undefined;
    getOutputs = async () => ({ ipv4: { value: '203.0.113.7' } });
  },
}));
vi.mock('../../services/tofu/provider-resolver.js', () => ({
  resolveProviderMapping: () => ({ defaults: {}, regionAttr: 'region' }),
}));
vi.mock('../../services/tofu/tf-generator.js', () => ({ generateTfJson: () => ({}) }));
vi.mock('../../services/renet/machine-bootstrap.js', () => ({
  scanHostKeys: () => '',
  waitForSSH: async () => undefined,
}));
vi.mock('../../services/renet/renet-execution.js', () => ({
  acquireRemoteRenet: mocks.acquireRemoteRenet,
  readSSHKey: vi.fn(),
}));
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: { acquireFor: vi.fn(), acquire: vi.fn() },
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../services/machine/machine-remove-guard.js', () => ({ guardMachineRemoval: vi.fn() }));
vi.mock('../../services/provision/infra-provision.js', () => ({
  pushInfraConfig: vi.fn(),
  removeMachineDnsRecords: vi.fn(),
}));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({ deployAllRepoKeys: vi.fn() }));

const { registerGpuCommands } = await import('../machine/gpu.js');
const { registerConvergeCommand } = await import('../machine/converge.js');
const { registerRestartServicesCommand } = await import('../machine/restart-services.js');
const { registerMachineRegistrationCommands } = await import('../machine/register.js');
const { registerPruneCommand } = await import('../machine/prune.js');
const { registerCloudCommands } = await import('../machine/provision.js');

type Executed = {
  functionName: string;
  machineName: string;
  verb?: string;
  commandKind?: { name: string; args?: Record<string, unknown> };
  jobSteps?: { name: string; on: string; params: Record<string, unknown> }[];
};

const OK = { success: true, exitCode: 0, durationMs: 1, state: 'succeeded' as const };
const RUNNING = { ...OK, state: 'running' as const };

let executed: Executed[];
let answer: Record<string, unknown>;
let restoreJobDeps: () => void;

beforeEach(() => {
  vi.clearAllMocks();
  mocks.format = 'table';
  mocks.order.length = 0;
  executed = [];
  answer = OK;
  mocks.acquireRemoteRenet.mockImplementation(() => {
    mocks.order.push('bootstrap');
    return Promise.resolve({
      remotePath: '/usr/bin/renet',
      uploaded: true,
      routerRefreshDue: true,
    });
  });
  restoreJobDeps = installJobDeps((options) => {
    mocks.order.push('job');
    executed.push(options as unknown as Executed);
    return Promise.resolve(answer as never);
  });
});

afterEach(() => {
  restoreJobDeps();
});

async function run(register: (machine: Command, program: Command) => void, ...argv: string[]) {
  const program = new Command();
  program.exitOverride();
  register(program.command('machine'), program);
  await program.parseAsync(['machine', ...argv], { from: 'user' });
}

const stepNames = (call: Executed): string[] => (call.jobSteps ?? []).map((s) => s.name);

describe('machine gpu list', () => {
  const REPORT = { inventory: { gpus: [], specs: [] }, recorded: true, grants: [] };

  it('makes one machine_gpu_list job with its render as the step, and prints from the job output', async () => {
    answer = { ...OK, stdout: JSON.stringify(REPORT) };
    mocks.format = 'json';

    await run(registerGpuCommands, 'gpu', 'list', 'm1');

    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({ functionName: 'machine_gpu_list', machineName: 'm1' });
    expect(stepNames(executed[0])).toEqual(['renderGpuList']);
    expect(mocks.print).toHaveBeenCalledWith(REPORT, 'json');
  });

  it('prints nothing while the job is still running: the step runs when it is seen to finish', async () => {
    answer = RUNNING;

    await run(registerGpuCommands, 'gpu', 'list', 'm1');

    expect(executed).toHaveLength(1);
    expect(mocks.print).not.toHaveBeenCalled();
  });
});

describe('machine converge', () => {
  it('makes one job carrying the settle step and its failure counterpart, with --json in the plan', async () => {
    await run(registerConvergeCommand, 'converge', 'm1', '--json');

    expect(executed).toHaveLength(1);
    expect(executed[0].functionName).toBe('machine_converge_runtime');
    expect(stepNames(executed[0])).toEqual(['settleConverge', 'settleConvergeFailed']);
    expect(executed[0].jobSteps?.[0].params).toEqual({ json: true });
  });

  it('a failed pass with no report renders through the failure step, not a second job', async () => {
    answer = { success: false, exitCode: 1, durationMs: 1, state: 'failed', stdout: '' };

    await run(registerConvergeCommand, 'converge', 'm1');

    expect(executed).toHaveLength(1);
  });
});

describe('machine restart-services', () => {
  const REPORT = { processes: [], repos: [] };

  it('makes one daemons-restart command-kind job, carrying --include-docker as an argument', async () => {
    answer = { ...OK, stdout: JSON.stringify(REPORT) };

    await run(registerRestartServicesCommand, 'restart-services', 'm1', '--include-docker');

    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({
      functionName: 'daemons-restart',
      commandKind: { name: 'daemons-restart', args: { 'include-docker': true } },
    });
    expect(stepNames(executed[0])).toEqual(['renderRestartServices']);
    expect(mocks.success).toHaveBeenCalled();
  });

  it('names no argument without the flag', async () => {
    answer = { ...OK, stdout: JSON.stringify(REPORT) };

    await run(registerRestartServicesCommand, 'restart-services', 'm1');

    expect(executed[0].commandKind?.args).toEqual({});
  });
});

describe('machine setup', () => {
  it('makes one bootstrap upload, then one setup job carrying the tails as steps', async () => {
    await run(registerMachineRegistrationCommands, 'setup', 'm1');

    expect(mocks.order).toEqual(['bootstrap', 'job']);
    expect(mocks.acquireRemoteRenet).toHaveBeenCalledTimes(1);
    expect(mocks.acquireRemoteRenet.mock.calls[0][0]).toBe('provision');
    expect(mocks.acquireRemoteRenet.mock.calls[0][4]).toMatchObject({ deferRouterRefresh: true });
    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({
      functionName: 'setup',
      machineName: 'm1',
      commandKind: { name: 'setup' },
    });
    expect(stepNames(executed[0])).toEqual([
      'postSetupMachineTasks',
      'convergeAfterSetup',
      'settleSetupFailed',
    ]);
  });

  it('records the owed router refresh and the converge choice in the plan, as scalars', async () => {
    await run(registerMachineRegistrationCommands, 'setup', 'm1', '--no-converge');

    const converge = executed[0].jobSteps?.find((s) => s.name === 'convergeAfterSetup');
    expect(converge?.params).toMatchObject({
      machine: 'm1',
      converge: false,
      routerRefreshDue: true,
    });
  });

  it('returns the ticket past the attach window without running a tail', async () => {
    answer = RUNNING;

    await run(registerMachineRegistrationCommands, 'setup', 'm1');

    expect(executed).toHaveLength(1);
    expect(mocks.success).not.toHaveBeenCalled();
  });
});

describe('machine prune', () => {
  const STDOUT = [
    '{"prune_phase":"datastore"}',
    '{"removed":[]}',
    '{"prune_phase":"units"}',
    'nothing to prune',
  ].join('\n');

  it('makes one machine_prune job, splits its two phases in the step and prints one document', async () => {
    answer = { ...OK, stdout: STDOUT };
    mocks.format = 'json';

    await run(registerPruneCommand, 'prune', 'm1', '--dry-run');

    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({
      functionName: 'machine_prune',
      machineName: 'm1',
      params: { dry_run: true },
    });
    expect(stepNames(executed[0])).toEqual(['renderPruneOutcome']);
    expect(mocks.print).toHaveBeenCalledTimes(1);
    expect(mocks.print.mock.calls[0][0]).toMatchObject({
      datastore: { removed: [] },
      units: 'nothing to prune',
    });
  });

  it('the orphaned-repos form plans no ssh cleanup: it follows a real deletion, on the client', async () => {
    answer = RUNNING;

    await run(registerPruneCommand, 'prune', 'm1', '--orphaned-repos');
    await run(registerPruneCommand, 'prune', 'm1', '--orphaned-repos', '--dry-run');

    expect(stepNames(executed[0])).toEqual(['renderPruneOutcome']);
    expect(stepNames(executed[1])).toEqual(['renderPruneOutcome']);
    expect(mocks.warn).toHaveBeenCalled();
  });

  it('control: a job still running prints nothing', async () => {
    answer = RUNNING;

    await run(registerPruneCommand, 'prune', 'm1');

    expect(mocks.print).not.toHaveBeenCalled();
    expect(mocks.success).not.toHaveBeenCalled();
  });
});

describe('machine provision', () => {
  const provision = (...extra: string[]) =>
    run(registerCloudCommands, 'provision', 'edge1', '--provider', 'hetzner', ...extra);

  it('makes no job for its tofu leg and exactly one setup job for its setup leg, after the bootstrap upload', async () => {
    await provision('--no-infra');

    expect(mocks.order).toEqual(['bootstrap', 'job']);
    expect(executed).toHaveLength(1);
    expect(executed[0]).toMatchObject({
      functionName: 'setup',
      machineName: 'edge1',
      verb: 'machine provision',
      commandKind: { name: 'setup' },
    });
    expect(stepNames(executed[0])).toEqual([]);
    expect(mocks.success).toHaveBeenCalledTimes(1);
  });

  it('records the infra source and pushes it as steps of the setup job, not as calls after it', async () => {
    await provision('--base-domain', 'example.com');

    expect(executed).toHaveLength(1);
    expect(stepNames(executed[0])).toEqual(['setMachineInfra', 'pushProvisionedInfra']);
    const infra = JSON.parse(String(executed[0].jobSteps?.[0].params.infra));
    expect(infra).toMatchObject({ baseDomain: 'example.com', publicIPv4: '203.0.113.7' });
  });

  it('returns the ticket past the attach window without announcing completion', async () => {
    answer = RUNNING;

    await provision('--no-infra');

    expect(executed).toHaveLength(1);
    expect(mocks.success).not.toHaveBeenCalled();
  });

  it('a failed setup warns, sets the exit code and announces no completion', async () => {
    answer = { ...OK, success: false, exitCode: 3, state: 'failed' as const };

    await provision('--no-infra');

    expect(mocks.warn).toHaveBeenCalledWith('Machine setup exited with code 3');
    expect(mocks.setExitCode).toHaveBeenCalledWith(3);
    expect(mocks.success).not.toHaveBeenCalled();
  });
});
