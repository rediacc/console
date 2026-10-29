/**
 * The executor reports an unanswered machine connect through the account egress,
 * and only that failure: a refused or rejected connect is a different problem.
 * The report's body names the address the connect never reached, which the proxy
 * probes before the report counts (PLAN-org-executor-connect-timeout-relocate E11).
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../config/network-id-discovery.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../config/network-id-discovery.js')>()),
  ensureRepositoryNetworkId: vi.fn(() => Promise.resolve(7)),
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    resetResourceView: vi.fn(),
    getRepository: vi.fn((name: string) =>
      Promise.resolve({ repositoryGuid: `guid-${name}`, credential: 'set', networkId: 7 })
    ),
    getLanguage: vi.fn(() => Promise.resolve('en')),
    applyDefaults: vi.fn((options: Record<string, unknown>) => Promise.resolve(options)),
    setRuntimeConfig: vi.fn(),
    getLocalConfig: vi.fn(() => Promise.resolve({ machines: {}, repositories: {} })),
    getLocalMachine: vi.fn((name: string) =>
      Promise.resolve({ ip: '10.0.0.1', user: 'root', name })
    ),
    getCurrent: vi.fn(() =>
      Promise.resolve({
        state: {},
        resources: {
          repositories: {
            demo: { grand: 'base', tags: { base: {} }, placement: { machine: 'hostinger' } },
          },
        },
      })
    ),
  },
}));

process.env.REDIACC_TELEMETRY_DISABLED = '1';

import { SshConnectError } from '../../../remote/sftp/connect-error.js';
import type { ExecuteOptions, ExecuteResult } from '../../executor/types.js';
import { AuthVerifier } from '../auth.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import {
  createEgressReporter,
  EGRESS_REPORT_URL,
  type EgressUnreachableAnswer,
} from '../egress-report.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

const TOKEN = 'rdt_owner';

function fakeAccount() {
  return vi.fn(() =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          active: true,
          scopes: ['proxy:exec'],
          orgId: 'org-1',
          teamId: 'team-1',
          createdByUserId: 'user-owner',
          userEmail: 'owner@example.com',
          orgRole: 'owner',
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      )
    )
  ) as unknown as typeof fetch;
}

const config = {
  schemaVersion: 3,
  id: '00000000-0000-0000-0000-000000000001',
  version: 1,
  defaults: { language: 'en', datastoreSize: '95%' },
  encryption: { mode: 'plaintext' },
} as RdcConfig;

const TARGET = { host: '192.0.2.10', port: 2222 };

/** A failed result; an EGRESS_UNREACHABLE one carries the connect target unless `withTarget` is false. */
function failing(errorCode?: string, withTarget = true): ServeDeps['executor'] {
  return {
    execute(_options: ExecuteOptions): Promise<ExecuteResult> {
      return Promise.resolve({
        success: false,
        exitCode: 6,
        durationMs: 3,
        error: 'down',
        ...(errorCode ? { errorCode } : {}),
        ...(errorCode === 'EGRESS_UNREACHABLE' && withTarget ? { connectTarget: TARGET } : {}),
      });
    },
  };
}

/** A command whose own SSH connect throws, bypassing executor.execute's result path. */
function throwing(kind: 'unreachable' | 'refused'): ServeDeps['executor'] {
  return {
    execute(): Promise<ExecuteResult> {
      return Promise.reject(
        new SshConnectError({ kind, host: '10.0.0.1', port: 22, timeoutMs: 5000, cause: 'x' })
      );
    },
  };
}

function answerFetch(answer: unknown, status = 200) {
  return vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(answer), { status }))
  ) as unknown as typeof fetch & ReturnType<typeof vi.fn>;
}

describe('egress-unreachable report', () => {
  let server: ReturnType<typeof serve>;

  async function postCommand(
    executor: ServeDeps['executor'],
    reporter: ServeDeps['reportEgressUnreachable'],
    mode: ServeDeps['mode'] = 'container'
  ): Promise<{ result: ExecuteResult; order: string[]; targets: unknown[] }> {
    const order: string[] = [];
    const targets: unknown[] = [];
    const deps: ServeDeps = {
      mode,
      auth: new AuthVerifier({
        accountUrl: 'https://account.test',
        executorToken: 'rdt_executor',
        fetchImpl: fakeAccount(),
      }),
      sessions: new SessionStore(),
      crypto: serveCrypto,
      loadConfig: () => Promise.resolve(config),
      authorize,
      executor,
      audit: () => Promise.resolve(),
      ...(reporter
        ? {
            reportEgressUnreachable: (target) => {
              order.push('report');
              targets.push(target);
              return reporter(target);
            },
          }
        : {}),
    };
    const app = createServeApp(deps);
    server = serve({ fetch: app.fetch, port: 0 });
    const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    const response = await fetch(`${base}/v1/command`, {
      method: 'POST',
      headers: { authorization: `Bearer ${TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: 'repo status',
        positionals: { ref: 'demo' },
      }),
    });
    const lines = (await response.text())
      .split('\n')
      .filter(Boolean)
      .map((l) => JSON.parse(l) as { kind: string; result?: ExecuteResult });
    order.push('result-line');
    const result = lines.find((l) => l.kind === 'result')?.result;
    if (!result) throw new Error('no result line');
    return { result, order, targets };
  }

  afterEach(async () => {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  const answers: [string, Record<string, unknown> | undefined, string][] = [
    [
      'relocated',
      { count: 3, threshold: 3, relocated: true, counted: true, probe: 'reachable' },
      "This org's executor has moved to a new instance. Retry the command now.",
    ],
    [
      'counted',
      { count: 2, threshold: 3, relocated: false, counted: true, probe: 'reachable' },
      'Attempt 2 of 3 before the executor moves to a new instance. Retry the command.',
    ],
    [
      'a target the proxy could not reach either',
      { count: 0, threshold: 3, relocated: false, counted: false, probe: 'target-unreachable' },
      '192.0.2.10:2222 did not answer an SSH connection from outside the executor either, so the executor is not moving. Check that the machine is up and accepts SSH on that port.',
    ],
    [
      'a skipped probe',
      { count: 0, threshold: 3, relocated: false, counted: false, probe: 'skipped' },
      'Retry the command. If it keeps failing, check that the machine accepts SSH from the internet.',
    ],
    [
      'an old-shape relocated answer',
      { count: 3, threshold: 3, relocated: true },
      "This org's executor has moved to a new instance. Retry the command now.",
    ],
    [
      'an old-shape counted answer',
      { count: 1, threshold: 3, relocated: false },
      'Attempt 1 of 3 before the executor moves to a new instance. Retry the command.',
    ],
    [
      'no answer',
      undefined,
      'Retry the command. If it keeps failing, check that the machine accepts SSH from the internet.',
    ],
  ];

  it.each(answers)(
    'EGRESS_UNREACHABLE with %s sends one JSON POST naming the target and carries the guidance',
    async (_n, answer, guidance) => {
      const fetchImpl = answerFetch(answer ?? {}, answer ? 200 : 503);
      const reporter = createEgressReporter({ fetchImpl });
      const { result, order } = await postCommand(failing('EGRESS_UNREACHABLE'), reporter);

      expect(fetchImpl).toHaveBeenCalledTimes(1);
      const [url, init] = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [
        string,
        RequestInit,
      ];
      expect(url).toBe('http://account.internal/executor/v1/egress-unreachable');
      expect(url).toBe(EGRESS_REPORT_URL);
      expect(init.method).toBe('POST');
      expect(JSON.parse(String(init.body))).toEqual({ host: '192.0.2.10', port: 2222 });
      expect(new Headers(init.headers).get('content-type')).toBe('application/json');
      expect(result.errorCode).toBe('EGRESS_UNREACHABLE');
      expect(result.errorGuidance).toBe(guidance);
      expect(order).toEqual(['report', 'result-line']);
      // The address goes to the report only, never into the served result.
      expect(result).not.toHaveProperty('connectTarget');
    }
  );

  it.each(['SSH_REFUSED', 'SSH_AUTH_FAILED', undefined])('sends nothing for %s', async (code) => {
    const fetchImpl = answerFetch({ count: 1, threshold: 3, relocated: false });
    const { result } = await postCommand(failing(code), createEgressReporter({ fetchImpl }));
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(result.errorGuidance).toBeUndefined();
  });

  it('an EGRESS_UNREACHABLE result that names no target sends nothing', async () => {
    const fetchImpl = answerFetch({ count: 1, threshold: 3, relocated: false });
    const { result } = await postCommand(
      failing('EGRESS_UNREACHABLE', false),
      createEgressReporter({ fetchImpl })
    );
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(result.errorCode).toBe('EGRESS_UNREACHABLE');
    expect(result.errorGuidance).toBeUndefined();
  });

  it('a thrown unreachable SshConnectError yields EGRESS_UNREACHABLE with its own guidance and no report, since it carries no target', async () => {
    const fetchImpl = answerFetch({ count: 1, threshold: 3, relocated: false });
    const { result } = await postCommand(
      throwing('unreachable'),
      createEgressReporter({ fetchImpl })
    );
    expect(result.success).toBe(false);
    expect(result.exitCode).toBe(6);
    expect(result.errorCode).toBe('EGRESS_UNREACHABLE');
    expect(result.errorGuidance).toMatch(/check that the machine accepts SSH from the internet/);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('a thrown refused SshConnectError yields SSH_REFUSED and no report', async () => {
    const fetchImpl = answerFetch({ count: 1, threshold: 3, relocated: false });
    const { result } = await postCommand(throwing('refused'), createEgressReporter({ fetchImpl }));
    expect(result.errorCode).toBe('SSH_REFUSED');
    expect(result.errorGuidance).toMatch(/SSH service is running/);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('never reports from the daemon tier, and still strips the target from the result line', async () => {
    const fetchImpl = answerFetch({ count: 1, threshold: 3, relocated: false });
    const { result } = await postCommand(
      failing('EGRESS_UNREACHABLE'),
      createEgressReporter({ fetchImpl }),
      'daemon'
    );
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(result.errorCode).toBe('EGRESS_UNREACHABLE');
    expect(result).not.toHaveProperty('connectTarget');
  });

  it('still writes the result line when the report hangs past its deadline', async () => {
    const hanging = vi.fn(() => new Promise<Response>(() => undefined)) as unknown as typeof fetch;
    const started = Date.now();
    const { result } = await postCommand(
      failing('EGRESS_UNREACHABLE'),
      createEgressReporter({ fetchImpl: hanging, deadlineMs: 100 })
    );
    expect(Date.now() - started).toBeLessThan(3000);
    expect(result.errorGuidance).toMatch(/check that the machine accepts SSH/);
  });
});

describe('createEgressReporter', () => {
  it('never throws, and answers undefined on a network error or a malformed body', async () => {
    const boom = vi.fn(() => Promise.reject(new Error('net'))) as unknown as typeof fetch;
    expect(await createEgressReporter({ fetchImpl: boom })(TARGET)).toBeUndefined();
    expect(
      await createEgressReporter({ fetchImpl: answerFetch({ nope: 1 }) })(TARGET)
    ).toBeUndefined();
    const badProbe = { count: 1, threshold: 3, relocated: false, counted: false, probe: 'maybe' };
    expect(
      await createEgressReporter({ fetchImpl: answerFetch(badProbe) })(TARGET)
    ).toBeUndefined();
  });

  it('reads an old-shape answer as counted and reachable', async () => {
    const answer: EgressUnreachableAnswer | undefined = await createEgressReporter({
      fetchImpl: answerFetch({ count: 2, threshold: 3, relocated: false }),
    })(TARGET);
    expect(answer).toEqual({
      count: 2,
      threshold: 3,
      relocated: false,
      counted: true,
      probe: 'reachable',
    });
  });

  it('allows 12 s for the proxy, which probes the target before it answers', async () => {
    vi.useFakeTimers();
    try {
      const hanging = vi.fn(
        () => new Promise<Response>(() => undefined)
      ) as unknown as typeof fetch;
      let settled = false;
      const pending = createEgressReporter({ fetchImpl: hanging })(TARGET).then((a) => {
        settled = true;
        return a;
      });
      await vi.advanceTimersByTimeAsync(11_999);
      expect(settled).toBe(false);
      await vi.advanceTimersByTimeAsync(1);
      expect(await pending).toBeUndefined();
    } finally {
      vi.useRealTimers();
    }
  });
});
