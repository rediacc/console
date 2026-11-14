/**
 * The proxy client over the attach window (PLAN-detached-jobs J6b).
 *
 * A job that finishes inside the window is one request: no job line, no poll, no ticket. A POST that
 * dropped before the job line is retried with the same request id on the poll ladder, at most three
 * times, and the executor (here a fake that dedupes on the id) starts one job. The sleeps are recorded.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import { afterEach, describe, expect, it } from 'vitest';
import { TicketStore } from '../../jobs/ticket-store.js';
import { ProxyClient } from '../proxy-client.js';

const JOB = 'j18c1c04dd251ce26-0ccf9fe5';

function ndjson(lines: unknown[]): Response {
  return new Response(lines.map((l) => `${JSON.stringify(l)}\n`).join(''), { status: 200 });
}

const finishedInWindow = () =>
  ndjson([
    { kind: 'event', event: { type: 'output', msg: 'done\n' } },
    {
      kind: 'result',
      result: { success: true, exitCode: 0, durationMs: 2000, state: 'succeeded', attached: true },
      stdout: 'ok',
    },
  ]);

describe('ProxyClient over the attach window', () => {
  const dirs: string[] = [];
  afterEach(() => {
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });

  function setup(command: (call: number, requestId: string) => Response | Promise<Response>) {
    const dir = mkdtempSync(join(tmpdir(), 'attach-'));
    dirs.push(dir);
    const store = new TicketStore('cfg', dir);
    const sleeps: number[] = [];
    const urls: string[] = [];
    const ids: string[] = [];
    const client = new ProxyClient({
      baseUrl: 'https://executor.test',
      getToken: () => Promise.resolve('rdt_token'),
      contractVersion: 'contract-v1',
      ticketStore: store,
      random: () => 0.5,
      lostBudgetMs: 0,
      sleep: (ms) => {
        sleeps.push(ms);
        return Promise.resolve();
      },
      fetchImpl: ((input: string | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        urls.push(url.pathname);
        if (url.pathname !== PROXY_ROUTES.command) {
          return Promise.resolve(
            Response.json({
              events: [],
              nextLine: 0,
              more: false,
              status: { state: 'succeeded', function: 'repository_up', exitCode: 0 },
            })
          );
        }
        const requestId = (JSON.parse(String(init?.body)) as { requestId: string }).requestId;
        ids.push(requestId);
        return Promise.resolve(command(ids.length, requestId));
      }) as typeof fetch,
    });
    return { client, store, sleeps, urls, ids };
  }

  it('returns a job that finished inside the window in one request, with no poll and no ticket', async () => {
    const { client, store, urls, sleeps } = setup(() => finishedInWindow());
    const rendered: string[] = [];
    const outcome = await client.run('repo create', {}, {}, (e) => {
      if (e.type === 'output' && e.msg) rendered.push(e.msg);
    });
    expect(outcome).toMatchObject({ success: true, exitCode: 0, stdout: 'ok' });
    expect(rendered).toEqual(['done\n']);
    expect(urls.filter((u) => u === PROXY_ROUTES.command)).toHaveLength(1);
    expect(urls.some((u) => u.includes('/poll') || u.includes('/jobs/'))).toBe(false);
    expect(sleeps).toEqual([]);
    expect(store.tickets()).toHaveLength(0);
  });

  it('retries a POST dropped before the job line with the same request id, and the fake starts one job', async () => {
    const started = new Map<string, string>();
    const { client, ids, sleeps } = setup((call, requestId) => {
      if (call === 1) throw new TypeError('fetch failed');
      if (call === 2) {
        // The first request reached the executor and started the job before its answer was lost.
        started.set(requestId, JOB);
        return new Response('{"kind":"heartbeat"}\n', { status: 200 });
      }
      started.set(requestId, started.get(requestId) ?? 'a-second-job');
      return finishedInWindow();
    });
    const outcome = await client.run('repo create', {}, {}, () => {});
    expect(outcome.success).toBe(true);
    expect(new Set(ids).size).toBe(1);
    expect(ids).toHaveLength(3);
    expect([...started.values()]).toEqual([JOB]);
    expect(sleeps).toEqual([2000, 3000]);
  });

  it('gives up after three retries, surfacing the last failure', async () => {
    const { client, ids, sleeps } = setup(() => {
      throw new TypeError('fetch failed');
    });
    await expect(client.run('repo create', {}, {}, () => {})).rejects.toThrow();
    expect(ids).toHaveLength(4);
    expect(new Set(ids).size).toBe(1);
    expect(sleeps).toEqual([2000, 3000, 4500]);
  });

  it('does not retry once a job line arrived: the polls follow the job', async () => {
    const { client, ids, urls } = setup(() =>
      ndjson([{ kind: 'job', jobId: JOB, machine: 'prod-1', sinceLine: 0 }])
    );
    const outcome = await client.run('repo up', {}, {}, () => {});
    expect(ids).toHaveLength(1);
    expect(urls.some((u) => u.includes(JOB))).toBe(true);
    expect(outcome).toMatchObject({ success: true, jobId: JOB });
  });

  it('does not re-send a clean close that printed output: the command may have run', async () => {
    const { client, ids } = setup(() =>
      ndjson([{ kind: 'event', event: { type: 'output', msg: 'partial\n' } }])
    );
    await expect(client.run('repo create', {}, {}, () => {})).rejects.toThrow(/without reporting/);
    expect(ids).toHaveLength(1);
  });

  it('re-sends a clean close of heartbeats only (the case that motivated the retry)', async () => {
    const { client, ids } = setup((call) =>
      call === 1 ? new Response('{"kind":"heartbeat"}\n', { status: 200 }) : finishedInWindow()
    );
    const outcome = await client.run('repo create', {}, {}, () => {});
    expect(outcome.success).toBe(true);
    expect(ids).toHaveLength(2);
  });

  it('does not re-send a silent clean close of a command the request id cannot dedupe', async () => {
    const { client, ids } = setup(() => new Response('{"kind":"heartbeat"}\n', { status: 200 }));
    await expect(client.run('config current', {}, {}, () => {})).rejects.toThrow(
      /without reporting/
    );
    expect(ids).toHaveLength(1);
  });

  it('a retried stream does not render again what the broken one already printed', async () => {
    const event = (msg: string) => ({ kind: 'event', event: { type: 'output', msg } });
    const { client, ids } = setup((call) => {
      if (call === 1) {
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(`${JSON.stringify(event('one\n'))}\n`));
            controller.error(new TypeError('terminated'));
          },
        });
        return new Response(body, { status: 200 });
      }
      return ndjson([
        event('one\n'),
        event('two\n'),
        {
          kind: 'result',
          result: { success: true, exitCode: 0, durationMs: 1, state: 'succeeded', attached: true },
        },
      ]);
    });
    const rendered: string[] = [];
    await client.run('repo create', {}, {}, (e) => {
      if (e.type === 'output' && e.msg) rendered.push(e.msg);
    });
    expect(ids).toHaveLength(2);
    expect(rendered).toEqual(['one\n', 'two\n']);
  });
});
