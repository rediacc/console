/**
 * The start directives of agent/plans/PLAN-detached-jobs.md section 14, J3b:
 *
 *   - `expect` in the vault replaces the client-side `repository_list` presence
 *     probe. renet checks it in `job start` before any unit exists and refuses
 *     with `{"refused":"precondition",...}` and exit 15; the CLI exits 12, the
 *     code the probe refused with, and makes no further call.
 *   - `network_id: "auto"` replaces the client's `network_used` probe and
 *     allocation. renet allocates the ID under its spool lock and reports it on
 *     the handle; the result carries it.
 *
 * The SSH layer is the recording fake job-execution.test.ts uses; the vault
 * each start received is read back from its stdin.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setOutputFormat } from '../../../utils/errors.js';
import { resetInvocationMinter } from '../../jobs/attach.js';
import { setJobExecutionTiming } from '../detached-execution.js';

const GUID = '22222222-2222-4222-8222-222222222222';

const {
  mockExecStreaming,
  mockGetLocalConfig,
  mockGetLocalMachine,
  mockListStorages,
  mockListRepositories,
  mockGetRepository,
} = vi.hoisted(() => ({
  mockExecStreaming: vi.fn(),
  mockGetLocalConfig: vi.fn(),
  mockGetLocalMachine: vi.fn(),
  mockListStorages: vi.fn(),
  mockListRepositories: vi.fn(),
  mockGetRepository: vi.fn(),
}));

vi.mock('../../../remote/sftp/index.js', () => ({
  SFTPClient: class MockSFTPClient {
    connect = vi.fn();
    close = vi.fn();
    exec = vi.fn();
    execStreaming = mockExecStreaming;
    isConnected = () => true;
  },
}));

vi.mock('../../config/config-resources.js', () => ({
  configService: {
    getLocalConfig: mockGetLocalConfig,
    getLocalMachine: mockGetLocalMachine,
    getRepository: mockGetRepository,
    listStorages: mockListStorages,
    listRepositories: mockListRepositories,
  },
}));

vi.mock('../../account/license.js', () => ({
  refreshRepoLicensesBatch: vi.fn(),
  issueRepoLicense: vi.fn(),
  refreshRepoLicenseIdentity: vi.fn(),
}));

vi.mock('../../../utils/agent-guard.js', () => ({
  isAgentEnvironment: vi.fn().mockReturnValue(false),
}));

vi.mock('../../account/license-refresh-state.js', () => ({
  isRefreshDue: vi.fn().mockResolvedValue(false),
  markRefreshAttempted: vi.fn().mockResolvedValue(undefined),
}));

// A vault shaped like buildLocalVault's (task, params, repositories keyed by GUID), so the directives have their real targets.
vi.mock('../../renet/renet-execution.js', () => ({
  buildLocalVault: vi.fn((opts: { functionName: string; params: Record<string, unknown> }) =>
    JSON.stringify({
      marker: 'vault',
      task: { function: opts.functionName, repository: GUID },
      params: opts.params,
      repositories: {
        [GUID]: {
          guid: GUID,
          name: 'mail',
          ...(typeof opts.params.network_id === 'number'
            ? { network_id: opts.params.network_id }
            : {}),
        },
      },
    })
  ),
  acquireRemoteRenet: vi.fn(() => ({ remotePath: '/usr/bin/renet', uploaded: false })),
  readSSHKey: vi.fn(() => 'PRIVATE_KEY'),
  readOptionalSSHKey: vi.fn(() => 'PUBLIC_KEY'),
  verifyMachineSetup: vi.fn(),
  getLocalRenetPath: vi.fn(),
}));

const { localExecutorService, applyVaultDirectives } = await import('../local-executor.js');
const { parseAttachLine, parsePreconditionRefusal } = await import('../job-client.js');

const JOB_ID = 'j18c1994eaa33d30d-3d9813b2';

type Handlers = { stdin?: string; onStdout?: (data: Buffer) => void };
const line = (value: unknown) => `${JSON.stringify(value)}\n`;
const handleLine = (extra: Record<string, unknown> = {}) =>
  line({ type: 'job_handle', job_id: JOB_ID, unit: 'u', log_path: 'p', ...extra });
const trailer = () =>
  line({
    type: 'job_status',
    job_id: JOB_ID,
    function: 'repository_up',
    state: 'succeeded',
    exit_code: 0,
    started_at: '2026-10-29T10:00:00Z',
    finished_at: '2026-10-29T10:00:01Z',
  });

function answer(stdout: string, code = 0) {
  return (_cmd: string, handlers: Handlers) => {
    if (stdout) handlers.onStdout?.(Buffer.from(stdout));
    return Promise.resolve(code);
  };
}

const commands = () => mockExecStreaming.mock.calls.map((c) => String(c[0]));

/** The vault the n-th exec received on stdin (it follows the env prefix). */
function sentVault(n = 0): Record<string, unknown> {
  const stdin = String((mockExecStreaming.mock.calls[n][1] as Handlers).stdin);
  return JSON.parse(stdin.slice(stdin.indexOf('{"marker"'))) as Record<string, unknown>;
}

const refusalLine = line({
  refused: 'precondition',
  expect: 'repo_present',
  state: 'absent',
  repository: 'mail',
  repo_guid: GUID,
  machine: 'hostinger',
  message: 'repository mail is not on machine hostinger',
});

beforeEach(() => {
  vi.clearAllMocks();
  mockExecStreaming.mockReset();
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
  process.env.REDIACC_CONFIG = `jobdirectives${Date.now()}`;
  resetInvocationMinter('inv-1');
  setJobExecutionTiming({ sleep: () => Promise.resolve() });
  setOutputFormat('table');
  mockGetLocalConfig.mockResolvedValue({
    sshPrivateKey: 'PRIVATE_KEY',
    sshPublicKey: 'PUBLIC_KEY',
    ssh: { privateKeyPath: '/tmp/id', publicKeyPath: '/tmp/id.pub' },
  });
  mockGetLocalMachine.mockResolvedValue({
    machineName: 'hostinger',
    ip: '127.0.0.1',
    user: 'root',
    port: 22,
  });
  mockListStorages.mockResolvedValue([]);
  mockListRepositories.mockResolvedValue([
    { name: 'mail', config: { repositoryGuid: GUID } },
    { name: 'web', config: { repositoryGuid: 'g-web', networkId: 2880 } },
    { name: 'db', config: { repositoryGuid: 'g-db', networkId: 2816 } },
    { name: 'db:fork', config: { repositoryGuid: 'g-dbf', networkId: 2880 } },
  ]);
  mockGetRepository.mockResolvedValue(undefined);
  vi.spyOn(process.stdout, 'write').mockImplementation(() => true);
  vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
});

afterEach(() => {
  vi.restoreAllMocks();
  delete process.env.REDIACC_TELEMETRY_DISABLED;
  delete process.env.REDIACC_CONFIG;
  setJobExecutionTiming();
  resetInvocationMinter();
});

const run = (extra: Record<string, unknown> = {}) =>
  localExecutorService.execute({
    functionName: 'repository_up',
    machineName: 'hostinger',
    params: { repository: 'mail' },
    captureOutput: true,
    quietSpinners: true,
    requestId: 'inv-1:hostinger:1',
    ...extra,
  });

describe('expect: the presence probe as a start precondition', () => {
  it('puts expect at the vault root of the job start', async () => {
    mockExecStreaming.mockImplementationOnce(answer(handleLine() + trailer()));
    const result = await run({ expect: 'repo_present' });
    expect(result.exitCode).toBe(0);
    expect(sentVault().expect).toBe('repo_present');
  });

  it('a refused precondition exits 12 with the probe text and makes no further call', async () => {
    mockExecStreaming.mockImplementationOnce(answer(refusalLine, 15));
    const error = await run({ expect: 'repo_present' }).catch((e: unknown) => e);
    expect(commands()).toHaveLength(1);
    expect(error).toMatchObject({ exitCode: 12, code: 'STATE_MISMATCH' });
    expect((error as Error).message).toBe(
      'config places mail on hostinger, but hostinger does not have its image. Run "rdc config reconcile", then retry.'
    );
  });

  it('a refused repo_absent carries renet text', async () => {
    mockExecStreaming.mockImplementationOnce(
      answer(
        line({
          refused: 'precondition',
          expect: 'repo_absent',
          state: 'present',
          repository: 'mail',
          repo_guid: GUID,
          message: 'repository mail is already on machine hostinger',
        }),
        15
      )
    );
    const error = await run({ expect: 'repo_absent' }).catch((e: unknown) => e);
    expect(error).toMatchObject({ exitCode: 12 });
    expect((error as Error).message).toBe('repository mail is already on machine hostinger');
  });

  it('refuses under -b too, where the start does not stream', async () => {
    mockExecStreaming.mockImplementationOnce(answer(refusalLine, 15));
    const error = await run({ expect: 'repo_present', attachWindowMs: 0 }).catch((e: unknown) => e);
    expect(error).toMatchObject({ exitCode: 12 });
  });

  it('control: no expect leaves the vault without one', async () => {
    mockExecStreaming.mockImplementationOnce(answer(handleLine() + trailer()));
    await run();
    expect(sentVault()).not.toHaveProperty('expect');
  });
});

describe('network_id "auto": renet allocates the ID in job start', () => {
  it('writes auto and the config IDs as exclusions onto the task entry', async () => {
    mockExecStreaming.mockImplementationOnce(answer(handleLine({ network_id: 2944 }) + trailer()));
    await run({ networkIdAuto: true });
    const repos = sentVault().repositories as Record<string, Record<string, unknown>>;
    expect(repos[GUID].network_id).toBe('auto');
    expect(repos[GUID].network_id_exclude).toEqual([2816, 2880]);
  });

  it('carries the allocated ID on the result, attached or backgrounded', async () => {
    mockExecStreaming.mockImplementationOnce(answer(handleLine({ network_id: 2944 }) + trailer()));
    expect((await run({ networkIdAuto: true })).networkId).toBe(2944);

    mockExecStreaming.mockImplementationOnce(answer(handleLine({ network_id: 3008 })));
    const pending = await run({ networkIdAuto: true, attachWindowMs: 0 });
    expect(pending.state).toBe('running');
    expect(pending.networkId).toBe(3008);
  });

  it('control: an entry that already has an ID keeps it, and no ID comes back', async () => {
    mockExecStreaming.mockImplementationOnce(answer(handleLine() + trailer()));
    const result = await run({
      networkIdAuto: true,
      params: { repository: 'mail', network_id: 2752 },
    });
    const repos = sentVault().repositories as Record<string, Record<string, unknown>>;
    expect(repos[GUID].network_id).toBe(2752);
    expect(repos[GUID]).not.toHaveProperty('network_id_exclude');
    expect(result.networkId).toBeUndefined();
  });
});

describe('applyVaultDirectives', () => {
  const vault = JSON.stringify({
    task: { repository: GUID },
    params: { repository: 'mail', network_id: 'auto' },
    repositories: { [GUID]: { guid: GUID, name: 'mail', network_id: null } },
  });

  it('a params auto alone asks for the allocation', () => {
    const out = JSON.parse(
      applyVaultDirectives(
        vault,
        { functionName: 'repository_create', params: { network_id: 'auto' } },
        {
          a: { networkId: 2816 },
        }
      )
    );
    expect(out.repositories[GUID]).toMatchObject({
      network_id: 'auto',
      network_id_exclude: [2816],
    });
    expect(out.params.network_id).toBe('auto');
  });

  it('a params auto beside a concrete entry ID takes that ID', () => {
    const concrete = JSON.stringify({
      task: { repository: GUID },
      params: { network_id: 'auto' },
      repositories: { [GUID]: { guid: GUID, network_id: 2880 } },
    });
    const out = JSON.parse(
      applyVaultDirectives(
        concrete,
        { functionName: 'repository_up', params: { network_id: 'auto' } },
        {}
      )
    );
    expect(out.params.network_id).toBe(2880);
    expect(out.repositories[GUID].network_id).toBe(2880);
  });

  it('a section 24 exemption stays on renet execute untouched', () => {
    const out = applyVaultDirectives(
      vault,
      {
        functionName: 'repository_exec',
        params: { tty: true },
        expect: 'repo_present',
        networkIdAuto: true,
      },
      {}
    );
    expect(out).toBe(vault);
  });

  it('control: no directive returns the vault byte for byte', () => {
    expect(applyVaultDirectives(vault, { functionName: 'repository_up', params: {} }, {})).toBe(
      vault
    );
  });
});

describe('parsing the new start lines', () => {
  it('classifies a precondition refusal and never renders it as an event', () => {
    const parsed = parseAttachLine(refusalLine.trim());
    expect(parsed).toMatchObject({ kind: 'precondition', refusal: { expect: 'repo_present' } });
    expect(parsePreconditionRefusal(`noise\n${refusalLine}`)?.repository).toBe('mail');
    expect(parsePreconditionRefusal(handleLine())).toBeNull();
  });

  it('reads the allocated network ID off the handle', () => {
    expect(parseAttachLine(handleLine({ network_id: 2944 }).trim())).toMatchObject({
      kind: 'handle',
      networkId: 2944,
    });
    expect(parseAttachLine(handleLine().trim())).not.toHaveProperty('networkId');
  });
});
