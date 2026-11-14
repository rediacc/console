/**
 * `-b` through the proxy, client half (finding #d31b4054): the request carries
 * `background: true`, the client returns the ticket without polling, and a later
 * `job wait` follows the same job through the proxy. The trace prints flags
 * only under REDIACC_DEBUG=proxy and never a token.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { followProxyTicket } from '../../jobs/remote-deps.js';
import { TicketStore } from '../../jobs/ticket-store.js';
import { ProxyClient } from '../proxy-client.js';
import { proxyTraceLine, traceProxyRequest } from '../proxy-trace.js';

const JOB = 'j18c1c04dd251ce26-0ccf9fe5';
const SECRET = 'rdt_super_secret_token';

function ndjson(lines: unknown[]): Response {
  return new Response(lines.map((l) => `${JSON.stringify(l)}\n`).join(''), { status: 200 });
}

const runningTicket = () => [
  { kind: 'job', jobId: JOB, machine: 'hostinger', sinceLine: 0 },
  {
    kind: 'result',
    result: { success: true, exitCode: 0, durationMs: 5, jobId: JOB, state: 'running' },
  },
];

describe('ProxyClient background', () => {
  const dirs: string[] = [];
  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
    delete process.env.REDIACC_DEBUG;
    vi.restoreAllMocks();
  });

  function setup(answer: () => Response) {
    const dir = mkdtempSync(join(tmpdir(), 'bg-'));
    dirs.push(dir);
    const store = new TicketStore('cfg', dir);
    const bodies: Record<string, unknown>[] = [];
    const urls: string[] = [];
    const client = new ProxyClient({
      baseUrl: 'https://executor.test',
      getToken: () => Promise.resolve(SECRET),
      contractVersion: 'contract-v1',
      ticketStore: store,
      sleep: () => Promise.resolve(),
      fetchImpl: ((input: string | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        urls.push(url.pathname);
        if (url.pathname === PROXY_ROUTES.command) {
          bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
          return Promise.resolve(answer());
        }
        return Promise.resolve(
          Response.json({
            events: [],
            nextLine: 0,
            more: false,
            status: { state: 'succeeded', function: 'repository_up', exitCode: 0 },
          })
        );
      }) as typeof fetch,
    });
    return { client, store, bodies, urls };
  }

  it('B: sets background on the request for -b, and returns the ticket without polling', async () => {
    const { client, store, bodies, urls } = setup(() => ndjson(runningTicket()));
    const outcome = await client.run('repo up', {}, { ref: 'shop' }, () => {}, undefined, {
      background: true,
    });
    expect(bodies[0]).toMatchObject({ background: true, pathKey: 'repo up' });
    expect(outcome).toMatchObject({ jobId: JOB, running: true, machine: 'hostinger' });
    expect(urls.some((u) => u.includes('/jobs/'))).toBe(false);
    const [ticket] = store.tickets();
    expect(ticket).toMatchObject({ jobId: JOB, machine: 'hostinger', state: 'running' });
    expect(ticket.via?.kind).toBe('proxy');
  });

  it('D: without -b the request omits the flag and the client follows the job by polls', async () => {
    const { client, bodies, urls } = setup(() => ndjson(runningTicket()));
    const outcome = await client.run('repo up', {}, { ref: 'shop' }, () => {});
    expect(bodies[0]).not.toHaveProperty('background');
    expect(urls.some((u) => u.includes(JOB))).toBe(true);
    expect(outcome.running).toBeUndefined();
  });

  it('a -b job that already finished returns its result, not a ticket', async () => {
    const { client } = setup(() =>
      ndjson([
        {
          kind: 'result',
          result: { success: true, exitCode: 0, durationMs: 5, state: 'succeeded' },
          stdout: 'done',
        },
      ])
    );
    const outcome = await client.run('repo up', {}, {}, () => {}, undefined, { background: true });
    expect(outcome).toMatchObject({ stdout: 'done' });
    expect(outcome.running).toBeUndefined();
  });

  it('followProxyTicket follows a proxy ticket to its terminal state through the proxy', async () => {
    const { client } = setup(() => ndjson(runningTicket()));
    const status = await followProxyTicket(
      {
        requestId: 'r',
        jobId: JOB,
        machine: 'hostinger',
        via: { kind: 'proxy', url: 'https://executor.test' },
        lastSeenLine: 0,
        state: 'running',
        thenStarted: false,
        steps: [],
        stepsDone: [],
        acknowledged: false,
        announced: false,
      },
      new AbortController().signal,
      () => {},
      () => client
    );
    expect(status).toMatchObject({ job_id: JOB, state: 'succeeded', exit_code: 0 });
  });

  describe('F: REDIACC_DEBUG=proxy trace', () => {
    const request = {
      pathKey: 'repo up',
      requestId: 'inv-1',
      background: true,
      params: { password: 'hunter2' },
      positionals: { ref: 'shop' },
    };

    it('prints the flags sent, never a value or a token, under REDIACC_DEBUG=proxy', async () => {
      process.env.REDIACC_DEBUG = 'proxy';
      const write = vi.spyOn(process.stderr, 'write').mockReturnValue(true);
      const { client } = setup(() => ndjson(runningTicket()));
      await client.run('repo up', { password: 'hunter2' }, { ref: 'shop' }, () => {}, undefined, {
        background: true,
      });
      const text = write.mock.calls.map((c) => String(c[0])).join('');
      expect(text).toContain('[proxy] sent path=repo up background=true');
      expect(text).toContain('params=[password]');
      expect(text).not.toContain('hunter2');
      expect(text).not.toContain(SECRET);
    });

    it('prints nothing without REDIACC_DEBUG, or under an unrelated scope', () => {
      const write = vi.spyOn(process.stderr, 'write').mockReturnValue(true);
      traceProxyRequest('sent', request);
      process.env.REDIACC_DEBUG = 'timing';
      traceProxyRequest('received', request);
      expect(write).not.toHaveBeenCalled();
    });

    it('the received line names the flag the same way, so a dropped flag shows as a difference', () => {
      expect(proxyTraceLine('received', request)).toContain(
        'received path=repo up background=true'
      );
      expect(proxyTraceLine('received', { ...request, background: undefined })).toContain(
        'background=false'
      );
    });
  });
});
