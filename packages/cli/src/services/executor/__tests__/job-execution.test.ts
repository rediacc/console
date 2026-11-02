/**
 * Every renet call through the executor runs as a machine job
 * (agent/plans/PLAN-detached-jobs.md J3, J3b): one `job start --request-id
 * --attach` exec, the attach window from the entry point, a retried start that
 * reuses its request id, a reattach from the last line received, the ticket
 * kept whenever the client stops watching, and the refusals (old renet,
 * overlap) that make no further call.
 *
 * The SSH layer is a recording fake: each `execStreaming` call is scripted, and
 * the commands it saw are asserted.
 */

import { BackgroundEnvelopeSchema } from '@rediacc/shared/cli-contract/wire';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setOutputFormat } from '../../../utils/errors.js';
import { getEffectiveConfigName } from '../../config/config-name.js';
import { resetInvocationMinter } from '../../jobs/attach.js';
import { TicketStore } from '../../jobs/ticket-store.js';
import { setJobExecutionTiming } from '../detached-execution.js';
import type { RenetEvent } from '../types.js';

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

vi.mock('../../renet/renet-execution.js', () => ({
  buildLocalVault: vi.fn(() => '{"vault":"ok"}'),
  acquireRemoteRenet: vi.fn(() => ({ remotePath: '/usr/bin/renet', uploaded: false })),
  readSSHKey: vi.fn(() => 'PRIVATE_KEY'),
  readOptionalSSHKey: vi.fn(() => 'PUBLIC_KEY'),
  verifyMachineSetup: vi.fn(),
  getLocalRenetPath: vi.fn(),
}));

const { localExecutorService } = await import('../local-executor.js');

const JOB_ID = 'j18c1994eaa33d30d-3d9813b2';
const OTHER_JOB = 'j18c1994eaa33d30e-0badcafe';
const STARTED = '2026-10-29T10:00:00Z';
const FINISHED = '2026-10-29T10:00:01Z';

type Handlers = {
  stdin?: string;
  onStdout?: (data: Buffer) => void;
  onStderr?: (data: Buffer) => void;
};
type Step = (cmd: string, handlers: Handlers) => Promise<number | undefined>;

const line = (value: unknown) => `${JSON.stringify(value)}\n`;
const handleLine = (extra: Record<string, unknown> = {}) =>
  line({ type: 'job_handle', job_id: JOB_ID, unit: 'u', log_path: 'p', ...extra });
const event = (e: RenetEvent) => line(e);
const trailer = (state: string, exitCode: number | null, extra: Record<string, unknown> = {}) =>
  line({
    type: 'job_status',
    job_id: JOB_ID,
    function: 'repository_up',
    state,
    exit_code: exitCode,
    started_at: STARTED,
    ...(state === 'running' ? {} : { finished_at: FINISHED }),
    unit: 'u',
    log_path: 'p',
    pid: 1,
    ...extra,
  });

/** A scripted exec that writes `stdout` (and `stderr`) and exits `code`. */
function answer(stdout: string, code: number | undefined = 0, stderr = ''): Step {
  return (_cmd, handlers) => {
    if (stdout) handlers.onStdout?.(Buffer.from(stdout));
    if (stderr) handlers.onStderr?.(Buffer.from(stderr));
    return Promise.resolve(code);
  };
}

/** An exec that writes `stdout` and then loses its channel. */
function drop(stdout = ''): Step {
  return (_cmd, handlers) => {
    if (stdout) handlers.onStdout?.(Buffer.from(stdout));
    return Promise.reject(new Error('channel closed'));
  };
}

function script(...steps: Step[]): void {
  for (const step of steps) mockExecStreaming.mockImplementationOnce(step);
}

const commands = () => mockExecStreaming.mock.calls.map((c) => String(c[0]));
const store = () => new TicketStore(getEffectiveConfigName());

let configSeq = 0;
const stdoutWrites: string[] = [];
const stderrWrites: string[] = [];

beforeEach(() => {
  vi.clearAllMocks();
  mockExecStreaming.mockReset();
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
  process.env.REDIACC_CONFIG = `jobexec${++configSeq}`;
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
  mockListRepositories.mockResolvedValue([]);
  mockGetRepository.mockResolvedValue(undefined);
  stdoutWrites.length = 0;
  stderrWrites.length = 0;
  vi.spyOn(process.stdout, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stdoutWrites.push(String(chunk));
    return true;
  });
  vi.spyOn(process.stderr, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stderrWrites.push(String(chunk));
    return true;
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  delete process.env.REDIACC_TELEMETRY_DISABLED;
  delete process.env.REDIACC_CONFIG;
  setJobExecutionTiming();
  resetInvocationMinter();
  setOutputFormat('table');
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

describe('every call is a job', () => {
  it('runs repository_list as one `job start --attach 0s` exec and never `renet execute`', async () => {
    script(answer(handleLine() + event({ type: 'output', msg: '[]' }) + trailer('succeeded', 0)));

    const result = await run({ functionName: 'repository_list' });

    expect(commands()).toHaveLength(1);
    expect(commands()[0]).toContain('job start --executor local --json');
    expect(commands()[0]).toContain("--attach '0s'");
    expect(commands()[0]).toContain("--request-id 'inv-1:hostinger:1'");
    expect(commands()[0]).not.toContain(' execute ');
    expect(result.stdout).toBe('[]\n');
  });

  it('keeps an interactive exec (tty) on `renet execute`', async () => {
    script(answer(''));

    await run({ functionName: 'container_exec', params: { tty: true, repository: 'mail' } });

    expect(commands()).toHaveLength(1);
    expect(commands()[0]).toContain('execute --executor local');
    expect(commands()[0]).not.toContain('job start');
  });

  it('passes a runJob step plan as --steps and leaves the ticket to runJob', async () => {
    script(answer(handleLine() + trailer('running', null)));

    await run({
      attachWindowMs: 20_000,
      jobSteps: [{ name: 'post-repo-up', on: 'success' }],
      externalTicket: true,
    });

    expect(commands()[0]).toContain(`--steps '[{"name":"post-repo-up","on":"success"}]'`);
    expect(store().tickets()).toEqual([]);
  });

  it('records the origin of the start', async () => {
    script(answer(handleLine() + trailer('succeeded', 0)));
    await run();
    expect(commands()[0]).toMatch(
      /--origin '\{"client":"rdc","version":"[^"]+","config":\{"name":"jobexec\d+"\}\}'/
    );
  });
});

describe('the attach window', () => {
  it('returns a fast job inside the window with no ticket follow and nothing pending', async () => {
    script(answer(handleLine() + event({ type: 'output', msg: 'up' }) + trailer('succeeded', 0)));

    const result = await run({ attachWindowMs: 20_000 });

    expect(commands()).toHaveLength(1);
    expect(commands()[0]).toContain("--attach '20000ms'");
    expect(result).toMatchObject({
      success: true,
      exitCode: 0,
      state: 'succeeded',
      attached: true,
      jobId: JOB_ID,
    });
    expect(store().pending()).toEqual([]);
  });

  it('returns the ticket when a slow job outlives the window', async () => {
    script(
      answer(handleLine() + event({ type: 'log', msg: 'pulling' }) + trailer('running', null))
    );

    const result = await run({ attachWindowMs: 20_000 });

    expect(commands()).toHaveLength(1);
    expect(result).toMatchObject({
      success: true,
      state: 'running',
      attached: false,
      jobId: JOB_ID,
    });
    const [ticket] = store().pending();
    expect(ticket).toMatchObject({
      jobId: JOB_ID,
      requestId: 'inv-1:hostinger:1',
      state: 'running',
      lastSeenLine: 1,
    });
  });

  it('control: a job that fails inside the window returns its exit code, with no ticket pending', async () => {
    script(answer(handleLine() + trailer('failed', 3, { error: 'boom' })));

    const result = await run();

    expect(result).toMatchObject({ success: false, exitCode: 3, state: 'failed' });
    expect(store().pending()).toEqual([]);
  });
});

describe('no double execution', () => {
  it('retries a start whose handle was lost with the same request id, and yields one job', async () => {
    // The first exec dies before renet's handle arrives: the client cannot tell whether the job started. The retry carries the same id, so renet dedupes onto the first job instead of starting a second.
    script(drop(), answer(handleLine({ deduped: true }) + trailer('succeeded', 0)));

    const started: string[] = [];
    const result = await run({ onJobStarted: (id: string) => started.push(id) });

    expect(commands()).toHaveLength(2);
    const ids = commands().map((c) => /--request-id '([^']+)'/.exec(c)?.[1]);
    expect(ids).toEqual(['inv-1:hostinger:1', 'inv-1:hostinger:1']);
    expect(started).toEqual([JOB_ID]);
    expect(result).toMatchObject({ success: true, jobId: JOB_ID });
  });

  it('reattaches from the last line received when the exec drops after the handle', async () => {
    script(
      drop(
        handleLine() + event({ type: 'output', msg: 'a' }) + event({ type: 'output', msg: 'b' })
      ),
      answer(event({ type: 'output', msg: 'c' })),
      answer(trailer('succeeded', 0).replace('"type":"job_status",', ''))
    );

    const result = await run();

    expect(commands()[1]).toContain(`job logs --id ${JOB_ID} --since-line 2 --follow`);
    expect(commands()[2]).toContain(`job status --id ${JOB_ID}`);
    // One start only: a drop after the handle reattaches, it never starts again.
    expect(commands().filter((c) => c.includes('job start'))).toHaveLength(1);
    expect(result).toMatchObject({ success: true, stdout: 'a\nb\nc\n' });
  });

  it('exits FOLLOW_LOST with the ticket kept when the transport stays gone past the budget', async () => {
    let clock = 0;
    setJobExecutionTiming({
      now: () => clock,
      sleep: (ms) => {
        clock += ms;
        return Promise.resolve();
      },
      budgetMs: 10_000,
    });
    script(drop(handleLine() + event({ type: 'output', msg: 'a' })));
    mockExecStreaming.mockImplementation(drop());

    const result = await run();

    expect(result.exitCode).toBe(16);
    expect(result.state).toBe('running');
    const [ticket] = store().pending();
    expect(ticket).toMatchObject({ jobId: JOB_ID, lastSeenLine: 1, state: 'running' });
    expect(stderrWrites.join('')).toContain(`rdc job wait ${JOB_ID}`);
  });
});

describe('refusals make no further call', () => {
  it('refuses an old renet with the upgrade message and no `renet execute` fallback', async () => {
    script(answer('', 1, 'Error: unknown flag: --request-id\nUsage: renet job start [flags]\n'));

    const result = await run();

    expect(commands()).toHaveLength(1);
    expect(result.exitCode).toBe(1);
    expect(result.error).toContain(
      "renet on 'hostinger' is older than this CLI and cannot run repository_up as a job. Upgrade it: rdc machine setup hostinger"
    );
  });

  it('names the verb the caller passed, not the process command, in the refusal', async () => {
    // Inside the executor daemon the output service names `executor-daemon run`; the daemon client carries the caller's verb across the socket.
    script(answer('', 1, 'Error: unknown flag: --request-id\n'));
    const result = await run({ verb: 'repo create' });
    expect(result.error).toContain('cannot run repo create as a job');
  });

  it('refuses a renet with no `job` command the same way', async () => {
    script(answer('', 1, 'Error: unknown command "job" for "renet"\n'));
    const result = await run();
    expect(commands()).toHaveLength(1);
    expect(result.error).toContain('Upgrade it: rdc machine setup hostinger');
  });

  it('exits 15 on an overlap refusal, names the attach command, and exposes the overlaps', async () => {
    const overlap = {
      job_id: OTHER_JOB,
      function: 'repository_up',
      repo_guid: 'g1',
      lock_class: 'repo-exclusive',
      state: 'running',
      action: 'refuse',
      attach: `rdc job logs ${OTHER_JOB} -m hostinger --follow`,
      origin: { client: 'rdc', ssh_user: 'ops' },
    };
    script(answer(line({ refused: 'overlap', overlaps: [overlap] }), 15, 'job start refused'));

    const error = await run().catch((e: unknown) => e);

    expect(commands()).toHaveLength(1);
    expect(error).toMatchObject({ exitCode: 15, code: 'BUSY' });
    const refused = error as {
      details: string[];
      overlaps: { jobId?: string; sshUser?: string }[];
    };
    expect(refused.details.join('\n')).toContain(`rdc job logs ${OTHER_JOB} -m hostinger --follow`);
    expect(refused.overlaps[0]).toMatchObject({ jobId: OTHER_JOB, action: 'refuse' });
  });

  it('warns on stderr about an overlap it was allowed past, and carries it on the result', async () => {
    const overlap = {
      job_id: OTHER_JOB,
      function: 'backup_snapshot',
      state: 'running',
      action: 'warn',
      attach: `rdc job logs ${OTHER_JOB} -m hostinger --follow`,
    };
    script(answer(handleLine({ overlaps: [overlap] }) + trailer('succeeded', 0)));

    const result = await run();

    expect(result.overlaps).toEqual([
      expect.objectContaining({ jobId: OTHER_JOB, function: 'backup_snapshot', action: 'warn' }),
    ]);
    expect(stderrWrites.join('')).toContain(
      `See it: rdc job logs ${OTHER_JOB} -m hostinger --follow`
    );
  });
});

describe('--background', () => {
  it('prints one parseable JSON envelope on stdout under -o json, with no hint text', async () => {
    setOutputFormat('json');
    script(answer(JSON.stringify({ job_id: JOB_ID, unit: 'u', log_path: 'p' }, null, 2)));

    const result = await run({ attachWindowMs: 0 });

    expect(commands()).toHaveLength(1);
    expect(commands()[0]).not.toContain('--attach');
    expect(result).toMatchObject({ success: true, state: 'running', jobId: JOB_ID });
    const out = stdoutWrites.join('');
    expect(out).not.toContain('Started job');
    const envelope = BackgroundEnvelopeSchema.parse(JSON.parse(out));
    expect(envelope).toMatchObject({
      jobId: JOB_ID,
      machine: 'hostinger',
      repo: 'mail',
      state: 'running',
      follow: `rdc job wait ${JOB_ID}`,
      overlaps: [],
    });
  });

  it('sends the text hint to stderr, never stdout, in text mode', async () => {
    script(answer(JSON.stringify({ job_id: JOB_ID, unit: 'u', log_path: 'p' })));

    await run({ attachWindowMs: 0 });

    expect(stdoutWrites.join('')).toBe('');
    expect(stderrWrites.join('')).toContain(`rdc job wait ${JOB_ID}`);
  });
});
