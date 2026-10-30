/**
 * Tests for the two silent-corruption bugs the detached-job wiring exposes, plus
 * the license-recovery restructure that now covers the detached path too.
 *
 *   - #31/#32: an events-mode run (every --proxy dispatch, and every detached
 *     job) must reconstruct its stdout from the NDJSON stream. Handing the raw
 *     events to parseCapturedJson is exactly what breaks --proxy cluster fork.
 *   - #33: a detached job that exits 10 (LICENSE_REQUIRED) must flow through the
 *     same license recovery + retry a synchronous run does. Retrying is safe:
 *     exit 10 means renet refused before doing any work.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseRenetLicenseFailure } from '../../renet/renet-license-contract.js';
import {
  createEventLineReader,
  createJobOutputCollector,
  jobStatusToExecuteResult,
  parseJobStatus,
} from '../job-client.js';
import { DATA_TRANSFER_TIMEOUT_MS } from '../renet-command.js';
import type { RenetEvent } from '../types.js';

const {
  mockConnect,
  mockClose,
  mockExec,
  mockExecStreaming,
  mockGetLocalConfig,
  mockGetLocalMachine,
  mockGetRepository,
  mockListStorages,
  mockListRepositories,
  mockIssueRepoLicense,
  mockRefreshRepoLicensesBatch,
  mockRefreshRepoLicenseIdentity,
  mockAuthorizeSubscriptionViaDeviceCode,
  mockGetSubscriptionTokenState,
  mockBuildLocalVault,
  mockAcquireRemoteRenet,
  mockReadSSHKey,
  mockReadOptionalSSHKey,
  mockVerifyMachineSetup,
} = vi.hoisted(() => ({
  mockConnect: vi.fn(),
  mockClose: vi.fn(),
  mockExec: vi.fn(),
  mockExecStreaming: vi.fn(),
  mockGetLocalConfig: vi.fn(),
  mockGetLocalMachine: vi.fn(),
  mockGetRepository: vi.fn(),
  mockListStorages: vi.fn(),
  mockListRepositories: vi.fn(),
  mockIssueRepoLicense: vi.fn(),
  mockRefreshRepoLicensesBatch: vi.fn(),
  mockRefreshRepoLicenseIdentity: vi.fn(),
  mockAuthorizeSubscriptionViaDeviceCode: vi.fn(),
  mockGetSubscriptionTokenState: vi.fn(),
  mockBuildLocalVault: vi.fn(() => '{"vault":"ok"}'),
  mockAcquireRemoteRenet: vi.fn(() => ({ remotePath: '/usr/bin/renet', uploaded: false })),
  mockReadSSHKey: vi.fn(() => 'PRIVATE_KEY'),
  mockReadOptionalSSHKey: vi.fn(() => 'PUBLIC_KEY'),
  mockVerifyMachineSetup: vi.fn(),
}));

vi.mock('../../../remote/sftp/index.js', () => ({
  SFTPClient: class MockSFTPClient {
    connect = mockConnect;
    close = mockClose;
    exec = mockExec;
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
  refreshRepoLicensesBatch: mockRefreshRepoLicensesBatch,
  issueRepoLicense: mockIssueRepoLicense,
  refreshRepoLicenseIdentity: mockRefreshRepoLicenseIdentity,
}));

vi.mock('../../account/subscription-device-auth.js', () => ({
  authorizeSubscriptionViaDeviceCode: mockAuthorizeSubscriptionViaDeviceCode,
}));

vi.mock('../../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: mockGetSubscriptionTokenState,
}));

vi.mock('../../../utils/agent-guard.js', () => ({
  isAgentEnvironment: vi.fn().mockReturnValue(false),
}));

// Opportunistic licence refresh is cooldown-gated against a file in the real user state dir. Left unmocked, whether it runs depends on when the developer last used the CLI on this machine, so a licence-recovery assertion would pass or fail based on unrelated local history.
//
// Defaulted to "not due" so these tests observe only the REACTIVE path they are about. Otherwise every command here would also refresh during setup, and `toHaveBeenCalledTimes(1)` below would be counting two unrelated things.
vi.mock('../../account/license-refresh-state.js', () => ({
  isRefreshDue: vi.fn().mockResolvedValue(false),
  markRefreshAttempted: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../renet/renet-execution.js', () => ({
  buildLocalVault: mockBuildLocalVault,
  acquireRemoteRenet: mockAcquireRemoteRenet,
  readSSHKey: mockReadSSHKey,
  readOptionalSSHKey: mockReadOptionalSSHKey,
  verifyMachineSetup: mockVerifyMachineSetup,
  getLocalRenetPath: vi.fn(),
}));

const { localExecutorService, parseCapturedJson, needsLicenseRecovery } = await import(
  '../local-executor.js'
);

const JOB_ID = 'j18c1994eaa33d30d-3d9813b2';

/** One NDJSON line for an event stream. */
function eventLine(event: RenetEvent): string {
  return `${JSON.stringify(event)}\n`;
}

describe('reconstructing detached stdout for parseCapturedJson (bug #31/#32)', () => {
  const NDJSON =
    eventLine({ type: 'step_start', name: 'list' }) +
    eventLine({ type: 'output', msg: '[repository_list] [{"name":"mail"}]' }) +
    eventLine({ type: 'step_done', name: 'list', duration_ms: 5 }) +
    eventLine({ type: 'result' });

  it('raw NDJSON is exactly what breaks parseCapturedJson today', () => {
    // The whole reason the collector exists: an event stream is not a JSON value.
    expect(() => parseCapturedJson(NDJSON)).toThrow();
  });

  it('the collector reconstructs stdout that parseCapturedJson accepts', () => {
    const collector = createJobOutputCollector();
    const read = createEventLineReader((event) => collector.consume(event));
    read(Buffer.from(NDJSON));

    expect(collector.stdout).toBe('[repository_list] [{"name":"mail"}]\n');
    expect(parseCapturedJson(collector.stdout)).toEqual([{ name: 'mail' }]);
  });
});

describe('recovery decision for a detached exit-10 result (bug #33)', () => {
  it('a reconstructed detached result routes into license recovery', () => {
    // A detached job that hit LICENSE_REQUIRED carries the marker as an output event, which the collector puts back into stdout. Both the exit-code gate and the failure parse must fire, or the retry never happens.
    const collector = createJobOutputCollector();
    collector.consume({
      type: 'output',
      msg: JSON.stringify({ code: 'LICENSE_REQUIRED', reason: 'missing' }),
    });
    const status = parseJobStatus(
      JSON.stringify({
        job_id: JOB_ID,
        function: 'backup_push',
        state: 'failed',
        exit_code: 10,
        started_at: '2026-07-12T16:58:10.000Z',
        finished_at: '2026-07-12T16:58:11.000Z',
      })
    );

    const result = jobStatusToExecuteResult(status, 1000, collector);

    expect(needsLicenseRecovery(result)).toBe(true);
    expect(parseRenetLicenseFailure(result.stderr, result.stdout)?.reason).toBe('missing');
  });

  it('does not recover a detached job that exited for some other reason', () => {
    const status = parseJobStatus(
      JSON.stringify({
        job_id: JOB_ID,
        function: 'backup_push',
        state: 'failed',
        exit_code: 1,
        started_at: '2026-07-12T16:58:10.000Z',
        finished_at: '2026-07-12T16:58:11.000Z',
      })
    );
    expect(needsLicenseRecovery(jobStatusToExecuteResult(status, 1000))).toBe(false);
  });
});

/** One `job start --attach` stream: the handle, the events, the status trailer. */
function attachStream(events: string, state: string, exitCode: number): string {
  return (
    `${JSON.stringify({ type: 'job_handle', job_id: JOB_ID, unit: 'u', log_path: 'p' })}\n` +
    events +
    `${JSON.stringify({
      type: 'job_status',
      job_id: JOB_ID,
      function: 'backup_push',
      state,
      exit_code: exitCode,
      started_at: '2026-07-12T16:58:10.000Z',
      finished_at: '2026-07-12T16:58:11.000Z',
    })}\n`
  );
}

const stream =
  (payload: string) => (_cmd: string, handlers: { onStdout?: (d: Buffer) => void }) => {
    handlers.onStdout?.(Buffer.from(payload));
    return Promise.resolve(0);
  };

function baseMocks(): void {
  vi.clearAllMocks();
  mockExecStreaming.mockReset();
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
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
}

describe('foreground job runs', () => {
  const savedTelemetry = process.env.REDIACC_TELEMETRY_DISABLED;

  beforeEach(baseMocks);

  afterEach(() => {
    if (savedTelemetry === undefined) delete process.env.REDIACC_TELEMETRY_DISABLED;
    else process.env.REDIACC_TELEMETRY_DISABLED = savedTelemetry;
  });

  it('reconstructs stdout in events mode: text, not raw NDJSON, so parseCapturedJson works (bug #31)', async () => {
    mockExecStreaming.mockImplementationOnce(
      stream(
        attachStream(
          eventLine({ type: 'output', msg: '[repository_list] [{"name":"mail"}]' }),
          'succeeded',
          0
        )
      )
    );

    const events: RenetEvent[] = [];
    const result = await localExecutorService.execute({
      functionName: 'repository_list',
      machineName: 'hostinger',
      eventsMode: true,
      captureOutput: true,
      onEvent: (event) => events.push(event),
    });

    expect(result.success).toBe(true);
    expect(result.stdout).toBe('[repository_list] [{"name":"mail"}]\n');
    expect(result.stdout).not.toContain('"type":"output"');
    expect(parseCapturedJson(result.stdout)).toEqual([{ name: 'mail' }]);
    // The event still reaches the caller's renderer; capture is additive to it.
    expect(events).toHaveLength(1);
  });

  it('carries the data-transfer ceiling on a backup_snapshot job start', async () => {
    mockExecStreaming.mockImplementationOnce(stream(attachStream('', 'succeeded', 0)));

    await localExecutorService.execute({
      functionName: 'backup_snapshot',
      machineName: 'hostinger',
    });

    const command = String(mockExecStreaming.mock.calls[0]?.[0]);
    expect(command).toContain(
      `job start --executor local --json --timeout ${DATA_TRANSFER_TIMEOUT_MS}ms`
    );
  });
});

describe('job license recovery (bug #33)', () => {
  const savedTelemetry = process.env.REDIACC_TELEMETRY_DISABLED;

  beforeEach(() => {
    baseMocks();
    mockGetRepository.mockResolvedValue(undefined);
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'ready', token: { token: 'rdt_test' } });
    mockRefreshRepoLicensesBatch.mockResolvedValue({
      scanned: 1,
      issued: 1,
      refreshed: 0,
      unchanged: 0,
      failed: 0,
      valid: 1,
      invalidSignatureDetected: 0,
      failures: [],
      recoveryFailureMode: null,
      serverErrorSample: undefined,
    });
  });

  afterEach(() => {
    if (savedTelemetry === undefined) delete process.env.REDIACC_TELEMETRY_DISABLED;
    else process.env.REDIACC_TELEMETRY_DISABLED = savedTelemetry;
  });

  it('recovers the license and retries as a NEW job when a job exits 10', async () => {
    const licenseMarker = eventLine({
      type: 'output',
      msg: JSON.stringify({ code: 'LICENSE_REQUIRED', reason: 'missing' }),
    });

    mockExecStreaming
      // Attempt 1: the attached start streams the license marker and ends failed with exit 10.
      .mockImplementationOnce(stream(attachStream(licenseMarker, 'failed', 10)))
      // Attempt 2 after recovery: a clean run.
      .mockImplementationOnce(
        stream(attachStream(eventLine({ type: 'output', msg: 'done' }), 'succeeded', 0))
      );

    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      captureOutput: true,
      requestId: 'inv:hostinger:1',
    });

    expect(mockRefreshRepoLicensesBatch).toHaveBeenCalledTimes(1);
    expect(mockExecStreaming).toHaveBeenCalledTimes(2);
    // The retry is a second job: reusing the first request id would dedupe onto the job that refused.
    const ids = mockExecStreaming.mock.calls.map(
      (c) => /--request-id '([^']+)'/.exec(String(c[0]))?.[1]
    );
    expect(ids).toEqual(['inv:hostinger:1', 'inv:hostinger:1:r']);
    expect(result.success).toBe(true);
    expect(result.exitCode).toBe(0);
  });

  it('returns immediately with a zero attach window, carrying the job id (--background)', async () => {
    const handle = JSON.stringify({ job_id: JOB_ID, unit: 'u', log_path: 'p' });
    mockExecStreaming.mockImplementationOnce(stream(handle));

    const started: string[] = [];
    const result = await localExecutorService.execute({
      functionName: 'backup_push',
      machineName: 'hostinger',
      attachWindowMs: 0,
      onJobStarted: (id) => started.push(id),
    });

    // Only `job start` ran, without --attach: no follow, no status read.
    expect(mockExecStreaming).toHaveBeenCalledTimes(1);
    const command = String(mockExecStreaming.mock.calls[0]?.[0]);
    expect(command).toContain(
      `job start --executor local --json --timeout ${DATA_TRANSFER_TIMEOUT_MS}ms`
    );
    expect(command).not.toContain('--attach');
    expect(started).toEqual([JOB_ID]);
    expect(result.success).toBe(true);
    expect(result.jobId).toBe(JOB_ID);
    expect(result.state).toBe('running');
  });
});
