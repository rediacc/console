/**
 * The executor reports an unanswered machine connect through the account egress,
 * and only that failure: a refused or rejected connect is a different problem.
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

function failing(errorCode?: string): ServeDeps['executor'] {
  return {
    execute(_options: ExecuteOptions): Promise<ExecuteResult> {
      return Promise.resolve({
        success: false,
        exitCode: 6,
        durationMs: 3,
        error: 'down',
        ...(errorCode ? { errorCode } : {}),
      });
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
  ): Promise<{ result: ExecuteResult; order: string[] }> {
    const order: string[] = [];
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
            reportEgressUnreachable: () => {
              order.push('report');
              return reporter();
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
    return { result, order };
  }

  afterEach(async () => {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  const answers: [string, EgressUnreachableAnswer | undefined, RegExp][] = [
    [
      'relocated',
      { count: 3, threshold: 3, relocated: true },
      /moved to a new instance\. Retry the command now/,
    ],
    [
      'counted',
      { count: 2, threshold: 3, relocated: false },
      /Attempt 2 of 3 before the executor moves/,
    ],
    ['no answer', undefined, /check that the machine accepts SSH from the internet/],
  ];

  it.each(answers)(
    'EGRESS_UNREACHABLE with %s sends one bodiless POST and carries the guidance',
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
      expect(init.body).toBeUndefined();
      expect(result.errorCode).toBe('EGRESS_UNREACHABLE');
      expect(result.errorGuidance).toMatch(guidance);
      expect(order).toEqual(['report', 'result-line']);
    }
  );

  it.each(['SSH_REFUSED', 'SSH_AUTH_FAILED', undefined])('sends nothing for %s', async (code) => {
    const fetchImpl = answerFetch({ count: 1, threshold: 3, relocated: false });
    const { result } = await postCommand(failing(code), createEgressReporter({ fetchImpl }));
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(result.errorGuidance).toBeUndefined();
  });

  it('never reports from the daemon tier', async () => {
    const fetchImpl = answerFetch({ count: 1, threshold: 3, relocated: false });
    const { result } = await postCommand(
      failing('EGRESS_UNREACHABLE'),
      createEgressReporter({ fetchImpl }),
      'daemon'
    );
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(result.errorCode).toBe('EGRESS_UNREACHABLE');
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
    expect(await createEgressReporter({ fetchImpl: boom })()).toBeUndefined();
    expect(await createEgressReporter({ fetchImpl: answerFetch({ nope: 1 }) })()).toBeUndefined();
  });
});
