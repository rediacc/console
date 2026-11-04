/**
 * The proxy client follows a job by short polls (PLAN-detached-jobs J6, Design 4 and 5).
 *
 * The executor is a fake `fetch`; the sleeps are recorded, not waited. The backoff is 2, 3, 4.5 ... 30 s on
 * empty polls (jitter off with random = 0.5), a page that says `more` is followed at once, and the ticket
 * (`via: proxy`) is written to a real store in a temp directory.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EXIT_CODES } from '../../../types/index.js';
import { TicketStore } from '../../jobs/ticket-store.js';
import { telemetryService } from '../../telemetry/telemetry.js';
import { nextPollDelayMs, ProxyClient } from '../proxy-client.js';

const JOB = 'j18c1c04dd251ce26-0ccf9fe5';

function ndjson(lines: unknown[]): Response {
  return new Response(lines.map((l) => `${JSON.stringify(l)}\n`).join(''), { status: 200 });
}

const handedBack = () =>
  ndjson([
    { kind: 'job', jobId: JOB, machine: 'prod-1', sinceLine: 0 },
    {
      kind: 'result',
      result: { success: true, exitCode: 0, durationMs: 20_000, state: 'running', jobId: JOB },
      stdout: 'started',
    },
  ]);

function poll(
  state: string,
  extra: { events?: number; more?: boolean; nextLine?: number; exitCode?: number } = {}
): Response {
  return Response.json({
    events: Array.from({ length: extra.events ?? 0 }, (_, i) => ({
      line: i,
      event: { type: 'output', msg: `l${i}\n` },
    })),
    nextLine: extra.nextLine ?? extra.events ?? 0,
    more: extra.more ?? false,
    status: {
      state,
      function: 'repository_up',
      ...(extra.exitCode === undefined ? {} : { exitCode: extra.exitCode }),
    },
  });
}

describe('ProxyClient follows by polls', () => {
  const dirs: string[] = [];
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
  });

  function setup(
    handler: (url: URL, call: number) => Response | Promise<Response>,
    options: { clock?: boolean } = {}
  ) {
    const dir = mkdtempSync(join(tmpdir(), 'poll-'));
    dirs.push(dir);
    const store = new TicketStore('cfg', dir);
    const sleeps: number[] = [];
    const urls: string[] = [];
    let polls = 0;
    const client = new ProxyClient({
      baseUrl: 'https://executor.test',
      getToken: () => Promise.resolve('rdt_token'),
      contractVersion: 'contract-v1',
      ticketStore: store,
      random: () => 0.5,
      // The clock variant keeps the default budget and advances a fake Date by each recorded sleep.
      ...(options.clock ? {} : { lostBudgetMs: 0 }),
      sleep: (ms) => {
        sleeps.push(ms);
        if (options.clock) vi.setSystemTime(Date.now() + ms);
        return Promise.resolve();
      },
      fetchImpl: ((input: string | URL) => {
        const url = new URL(String(input));
        urls.push(`${url.pathname}${url.search}`);
        if (url.pathname === PROXY_ROUTES.command) return Promise.resolve(handedBack());
        polls += 1;
        return Promise.resolve(handler(url, polls));
      }) as typeof fetch,
    });
    return { client, store, sleeps, urls };
  }

  it('paces empty polls 2, 3, 4.5 ... up to the 30 s cap', async () => {
    const { client, sleeps } = setup((_url, call) =>
      call <= 8 ? poll('running') : poll('succeeded', { exitCode: 0 })
    );
    const outcome = await client.run('repo up', {}, {}, () => {});
    expect(outcome.success).toBe(true);
    expect(sleeps).toEqual([2000, 3000, 4500, 6750, 10125, 15188, 22782, 30000]);
    expect(nextPollDelayMs(30_000)).toBe(30_000);
  });

  it('follows a page that says more at once, and resets the pacing when lines arrive', async () => {
    const { client, sleeps, urls } = setup((_url, call) => {
      if (call === 1) return poll('running', { events: 2, more: true, nextLine: 2 });
      if (call === 2) return poll('running', { events: 1, nextLine: 3 });
      return poll('succeeded', { exitCode: 0, nextLine: 3 });
    });
    const rendered: string[] = [];
    await client.run('repo up', {}, {}, (e) => {
      if (e.type === 'output' && e.msg) rendered.push(e.msg);
    });
    // No wait after the `more` page; one first-delay wait after the page that carried a line.
    expect(sleeps).toEqual([2000]);
    expect(rendered).toEqual(['l0\n', 'l1\n', 'l0\n']);
    const pollUrls = urls.filter((u) => u.includes('/poll'));
    expect(pollUrls[0]).toContain('sinceLine=0');
    expect(pollUrls[1]).toContain('sinceLine=2');
    expect(pollUrls[2]).toContain('sinceLine=3');
    expect(pollUrls[0]).toContain('machine=prod-1');
  });

  it('writes the proxy ticket and finishes it on the terminal poll', async () => {
    const { client, store } = setup(() => poll('failed', { exitCode: 3 }));
    const outcome = await client.run('repo up', {}, {}, () => {});
    expect(outcome).toMatchObject({ success: false, exitCode: 3, jobId: JOB, stdout: 'started' });
    const [ticket] = store.tickets();
    expect(ticket).toMatchObject({
      jobId: JOB,
      machine: 'prod-1',
      verb: 'repo up',
      via: { kind: 'proxy', url: 'https://executor.test/' },
      state: 'failed',
      exitCode: 3,
    });
  });

  it('keeps retrying failed polls for the 10 minute default, past the old 2 minute budget', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    const { client, sleeps } = setup(() => new Response('bad gateway', { status: 502 }), {
      clock: true,
    });
    const outcome = await client.run('repo up', {}, {}, () => {});
    expect(outcome.exitCode).toBe(EXIT_CODES.FOLLOW_LOST);
    const waited = sleeps.reduce((a, b) => a + b, 0);
    expect(waited).toBeGreaterThanOrEqual(600_000 - 30_000);
    expect(waited).toBeLessThan(600_000 + 30_000);
  });

  it('leaves the function and outcome off the span when the follow is lost before any poll answered', async () => {
    const spy = vi.spyOn(telemetryService, 'annotateCommand').mockImplementation(() => {});
    const { client } = setup(() => new Response('bad gateway', { status: 502 }));
    await client.run('repo up', {}, {}, () => {});
    const attrs = spy.mock.calls.at(-1)?.[0] ?? {};
    expect(attrs).toMatchObject({ 'rediacc.job.follow': 'poll' });
    expect(attrs).not.toHaveProperty('rediacc.job.function');
    expect(attrs).not.toHaveProperty('rediacc.job.outcome');
  });

  it('control: a terminal poll writes the function and the outcome onto the span', async () => {
    const spy = vi.spyOn(telemetryService, 'annotateCommand').mockImplementation(() => {});
    const { client } = setup(() => poll('succeeded', { exitCode: 0 }));
    await client.run('repo up', {}, {}, () => {});
    expect(spy.mock.calls.at(-1)?.[0]).toMatchObject({
      'rediacc.job.function': 'repository_up',
      'rediacc.job.outcome': 'succeeded',
    });
  });

  it('gives up with FOLLOW_LOST and the job id when polls keep failing past the budget', async () => {
    const { client, store } = setup(() => new Response('bad gateway', { status: 502 }));
    const outcome = await client.run('repo up', {}, {}, () => {});
    expect(outcome.exitCode).toBe(EXIT_CODES.FOLLOW_LOST);
    expect(outcome.error).toContain(`rdc job wait ${JOB} -m prod-1`);
    // The ticket stays open: the job still runs.
    expect(store.tickets()[0]?.state).toBe('running');
  });

  it('treats a 403 poll as final, not as a flaky link', async () => {
    const { client } = setup(() => new Response('policy denied', { status: 403 }));
    await expect(client.run('repo up', {}, {}, () => {})).rejects.toThrow(/403/);
  });
});
