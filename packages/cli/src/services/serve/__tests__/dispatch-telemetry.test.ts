/**
 * Telemetry across concurrent executor dispatches.
 *
 * The container executor is one process serving many callers. The telemetry
 * service is a process singleton, so three things had to stop assuming one command
 * per process: a failing request must not shut the SDK down for everyone, each
 * request needs its own command span (two `repo status` share a name), and a span
 * carries the introspected caller, not the executor's own token.
 *
 * The real Commander tree and the real dispatchCommand run. Only the OTel SDK
 * factory, the executor and the config are faked.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../config/config-resources.js', () => ({
  configService: {
    resetResourceView: vi.fn(),
    getRepository: vi.fn((name: string) =>
      Promise.resolve({ repositoryGuid: `guid-${name}`, credential: 'set', networkId: 7 })
    ),
    ensureRepositoryNetworkId: vi.fn(() => Promise.resolve(7)),
    getLanguage: vi.fn(() => Promise.resolve('en')),
    applyDefaults: vi.fn((options: Record<string, unknown>) => Promise.resolve(options)),
    setRuntimeConfig: vi.fn(),
    getLocalConfig: vi.fn(() => Promise.resolve({ machines: {}, repositories: {} })),
    getLocalMachine: vi.fn((name: string) =>
      Promise.resolve({ ip: '10.0.0.1', user: 'root', name })
    ),
    getUserEmail: vi.fn(() => Promise.resolve('executor@rediacc.test')),
    getTeam: vi.fn(() => Promise.resolve('executor-team')),
    getCurrent: vi.fn(() =>
      Promise.resolve({
        state: {},
        resources: {
          repositories: {
            alpha: { grand: 'base', tags: { base: {} }, placement: { machine: 'm1' } },
            beta: { grand: 'base', tags: { base: {} }, placement: { machine: 'm2' } },
          },
        },
      })
    ),
  },
}));

const sdk = vi.hoisted(() => {
  interface FakeSpan {
    name: string;
    attributes: Record<string, unknown>;
    status?: { code: number; message?: string };
    ended: boolean;
  }
  const spans: FakeSpan[] = [];
  const state = {
    spans,
    shutdown: vi.fn(() => Promise.resolve()),
    setup: vi.fn(),
  };
  return state;
});

vi.mock('../../telemetry/telemetry-setup.js', () => ({
  setupOtelSdk: (opts: unknown) => {
    sdk.setup(opts);
    const counter = { add: vi.fn() };
    return {
      sdk: { shutdown: sdk.shutdown },
      tracer: {
        startSpan: (name: string) => {
          const span = { name, attributes: {} as Record<string, unknown>, ended: false } as {
            name: string;
            attributes: Record<string, unknown>;
            status?: { code: number; message?: string };
            ended: boolean;
          };
          sdk.spans.push(span);
          return {
            setAttributes: (attrs: Record<string, unknown>) =>
              Object.assign(span.attributes, attrs),
            setStatus: (status: { code: number; message?: string }) => {
              span.status = status;
            },
            end: () => {
              span.ended = true;
            },
          };
        },
      },
      logger: { emit: vi.fn() },
      metricReader: { forceFlush: () => Promise.resolve() },
      commandCounter: counter,
      commandDuration: { record: vi.fn() },
      errorCounter: counter,
      apiCallDuration: { record: vi.fn() },
    };
  },
}));

const profiling = vi.hoisted(() => ({ start: vi.fn(), stop: vi.fn(() => Promise.resolve()) }));
vi.mock('../../telemetry/profiling.js', () => ({
  startProfiling: profiling.start,
  stopProfiling: profiling.stop,
}));

const credentialFetch = vi.hoisted(() => ({ command: vi.fn(), plain: vi.fn() }));
vi.mock('../../telemetry/otlp-credentials.js', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  fetchCommandOtlpCredentials: credentialFetch.command,
  fetchOtlpCredentials: credentialFetch.plain,
}));

import { SpanStatusCode } from '@opentelemetry/api';
import type { ExecuteOptions, ExecuteResult, Executor } from '../../executor/types.js';
import { containerTelemetryConfig } from '../../telemetry/container-telemetry.js';
import { telemetryService } from '../../telemetry/telemetry.js';
import { dispatchCommand, prepareCommand } from '../command-dispatch.js';

const SAVED_ENV = { ...process.env };

/** An executor whose calls all wait on one gate, so every dispatch is in flight together. */
function gatedExecutor(failMachine: string) {
  let open!: () => void;
  const gate = new Promise<void>((resolve) => {
    open = resolve;
  });
  let waiting = 0;
  const executor: Executor = {
    async execute(options: ExecuteOptions): Promise<ExecuteResult> {
      waiting += 1;
      if (waiting === 2) open();
      await gate;
      const failed = options.machineName === failMachine;
      return failed
        ? { success: false, exitCode: 7, durationMs: 1, error: 'the machine said no' }
        : { success: true, exitCode: 0, durationMs: 1, stdout: 'ok' };
    },
  };
  return executor;
}

function dispatchStatus(ref: string, executor: Executor, userId: string) {
  return dispatchCommand({
    prepared: prepareCommand('repo status', {}, { ref }),
    executor,
    onEvent: () => {},
    caller: { userId, orgId: `org-${userId}`, userEmail: `${userId}@customer.test` },
  });
}

describe('container executor telemetry', () => {
  beforeEach(async () => {
    delete process.env.CI;
    delete process.env.REDIACC_TELEMETRY_DISABLED;
    process.env.REDIACC_REGION = 'eu';
    sdk.spans.length = 0;
    vi.clearAllMocks();
    telemetryService.setRuntimeOtlpCredentials({ user: 'u', pass: 'p' });
    // What `serve --mode container` does once, at process start.
    await telemetryService.initialize(containerTelemetryConfig());
  });

  afterEach(() => {
    process.env = { ...SAVED_ENV };
  });

  it('runs one SDK, under the executor service name, whatever the dispatches do', async () => {
    const executor = gatedExecutor('m1');

    const [failed, ok] = await Promise.all([
      dispatchStatus('alpha', executor, 'caller-a'),
      dispatchStatus('beta', executor, 'caller-b'),
    ]);

    // One of the two failed, and the other did not notice.
    expect(failed.result.success).toBe(false);
    expect(ok.result.success).toBe(true);

    // One SDK, built once, as the container executor in production in the Worker's region.
    expect(sdk.setup).toHaveBeenCalledTimes(1);
    expect(sdk.setup).toHaveBeenCalledWith(
      expect.objectContaining({
        serviceName: 'rediacc-proxy-executor',
        environment: 'production',
        region: 'eu',
      })
    );

    // The failing request did not shut it down.
    expect(sdk.shutdown).not.toHaveBeenCalled();
    expect(telemetryService.isRunning()).toBe(true);
  });

  it('opens one command span per request, each carrying its own caller', async () => {
    const executor = gatedExecutor('m1');

    await Promise.all([
      dispatchStatus('alpha', executor, 'caller-a'),
      dispatchStatus('beta', executor, 'caller-b'),
    ]);

    const commandSpans = sdk.spans.filter((s) => s.name === 'cli.command.repo status');
    expect(commandSpans).toHaveLength(2);
    expect(commandSpans.map((s) => s.attributes['user.id']).sort()).toEqual([
      'caller-a',
      'caller-b',
    ]);
    // The executor's own identity never leaks onto a caller's span.
    for (const span of commandSpans) {
      expect(span.attributes['user.email_domain']).toBe('customer.test');
      expect(span.attributes['user.team']).toBeUndefined();
    }

    // Both spans were closed, the failing one as an error, the other as success. Neither overwrote the other under the shared command name.
    expect(commandSpans.every((s) => s.ended)).toBe(true);
    const byCaller = Object.fromEntries(commandSpans.map((s) => [s.attributes['user.id'], s]));
    expect(byCaller['caller-a'].status?.code).toBe(SpanStatusCode.ERROR);
    expect(byCaller['caller-b'].status?.code).toBe(SpanStatusCode.OK);
  });

  it('leaves credentials, SDK start and profiling to the process, not the request', async () => {
    const executor = gatedExecutor('none');

    await Promise.all([
      dispatchStatus('alpha', executor, 'caller-a'),
      dispatchStatus('beta', executor, 'caller-b'),
    ]);

    expect(credentialFetch.command).not.toHaveBeenCalled();
    expect(credentialFetch.plain).not.toHaveBeenCalled();
    expect(profiling.start).not.toHaveBeenCalled();
  });
});
