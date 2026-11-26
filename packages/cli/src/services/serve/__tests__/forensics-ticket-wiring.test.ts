/**
 * The forensics read ticket's hops on the executor (PLAN-forensics-investigation D8): a served
 * dispatch runs its command inside `withForensicsTicket` with the request's ticket, or with null
 * when it carries none, and the MCP-call dispatcher hands the ticket of its call to that dispatch.
 * `client-ticket.test.ts` drives the client; this pins the hops around it, since a dropped ticket
 * turns every forensics read into a refusal with nothing else failing.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

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
    getUserEmail: vi.fn(() => Promise.resolve('executor@rediacc.test')),
    getTeam: vi.fn(() => Promise.resolve('executor-team')),
    getCurrent: vi.fn(() =>
      Promise.resolve({
        state: {},
        resources: {
          repositories: {
            alpha: { grand: 'base', tags: { base: {} }, placement: { machine: 'm1' } },
          },
        },
      })
    ),
  },
}));

const seen = vi.hoisted(() => ({ tickets: [] as unknown[] }));
vi.mock('../../forensics/client.js', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../forensics/client.js')>();
  return {
    ...real,
    withForensicsTicket: <T>(ticket: unknown, fn: () => T): T => {
      seen.tickets.push(ticket);
      return real.withForensicsTicket(ticket as never, fn);
    },
  };
});

process.env.REDIACC_TELEMETRY_DISABLED = '1';

import type { ExecuteOptions, ExecuteResult, Executor } from '../../executor/types.js';
import { ForensicsTicket } from '../../forensics/client.js';
import { dispatchCommand, prepareCommand } from '../command-dispatch.js';
import { dispatcher } from '../mcp-call-dispatch.js';

const executor: Executor = {
  execute: (_options: ExecuteOptions): Promise<ExecuteResult> =>
    Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'ok' }),
};

function dispatch(forensicsTicket?: ForensicsTicket) {
  return dispatchCommand({
    prepared: prepareCommand('repo status', {}, { ref: 'alpha' }),
    executor,
    onEvent: () => {},
    ...(forensicsTicket ? { forensicsTicket } : {}),
  });
}

describe('dispatchCommand and the forensics ticket', () => {
  beforeEach(() => {
    seen.tickets.length = 0;
  });

  it('runs the command inside the request ticket', async () => {
    const ticket = new ForensicsTicket('the-ticket');
    await dispatch(ticket);
    expect(seen.tickets).toHaveLength(1);
    expect(seen.tickets[0]).toBe(ticket);
  });

  it('control: a request without a ticket runs with null, so its forensics reads refuse', async () => {
    await dispatch();
    expect(seen.tickets).toEqual([null]);
  });
});

describe('the MCP-call dispatcher and the forensics ticket', () => {
  beforeEach(() => {
    seen.tickets.length = 0;
  });

  function mcpCall(forensicsTicket?: ForensicsTicket) {
    const call = {
      deps: { executor, auth: { canWriteAudit: () => Promise.resolve({ ok: true }) } },
      busy: { track: <T>(fn: () => Promise<T>) => fn() },
      handle: {
        config: {},
        principal: { userId: 'u1', orgId: 'o1', userEmail: 'u1@customer.test' },
      },
      requestId: 'req-1',
      windowMs: 10_000,
      ...(forensicsTicket ? { forensicsTicket } : {}),
    };
    const request = { params: {}, positionals: { ref: 'alpha' } };
    return dispatcher(
      call as never,
      request as never
    )({
      prepared: prepareCommand('repo status', {}, { ref: 'alpha' }),
      onEvent: () => {},
      background: false,
    } as never);
  }

  it('hands the ticket of the call to the dispatch', async () => {
    const ticket = new ForensicsTicket('the-ticket');
    await mcpCall(ticket);
    expect(seen.tickets).toHaveLength(1);
    expect(seen.tickets[0]).toBe(ticket);
  });

  it('control: a call without a ticket reaches the dispatch with null', async () => {
    await mcpCall();
    expect(seen.tickets).toEqual([null]);
  });
});
