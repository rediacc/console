/**
 * The run recorder (agent/plans/PLAN-console-run-index.md D3, D4): one start and one end per run
 * with rising `seq`, a progress event at most every 15 s, a tail sealed under the session CEK, and
 * an unreachable account route that never reaches the command.
 */

import { generateCek } from '@rediacc/shared/config-crypto';
import { openRunTail } from '@rediacc/shared/config-crypto/run-tail';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createRunIndex, PROGRESS_INTERVAL_MS, RUN_EVENT_ATTEMPTS } from '../run-index.js';
import type { SessionPrincipal } from '../sessions.js';

const PRINCIPAL = {
  userId: 'user-1',
  orgId: 'org-1',
  teamId: 'team-1',
  userEmail: 'u@example.com',
  orgRole: 'owner',
  tokenId: 'tok-1',
} as unknown as SessionPrincipal;

interface Posted {
  runId: string;
  seq: number;
  state: string;
  lastStep?: string;
  jobId?: string;
  exitCode?: number;
  tail?: string;
  endedAt?: string;
  onBehalfOfTokenId?: string;
}

function capture(answer: () => Response | Promise<Response> = () => Response.json({ ok: true })) {
  const posted: Posted[] = [];
  const headers: Headers[] = [];
  const fetchImpl = ((url: string | URL, init?: RequestInit) => {
    expect(String(url)).toBe('https://account.test/account/api/v1/console/runs/events');
    posted.push(JSON.parse(init?.body as string) as Posted);
    headers.push(new Headers(init?.headers));
    return Promise.resolve(answer());
  }) as typeof fetch;
  return { posted, headers, fetchImpl };
}

afterEach(() => {
  vi.useRealTimers();
});

describe('run recorder', () => {
  it('posts one start and one end per run with rising seq under the executor token', async () => {
    const { posted, headers, fetchImpl } = capture();
    const index = createRunIndex({
      accountUrl: 'https://account.test/',
      executorToken: 'rdt_executor',
      fetchImpl,
    });
    const run = index.begin({ principal: PRINCIPAL, runId: 'run-1', pathKey: 'repo list' });
    await run.end({ state: 'succeeded', exitCode: 0 });

    expect(posted.map((event) => [event.state, event.seq])).toEqual([
      ['running', 0],
      ['succeeded', 1],
    ]);
    expect(posted.every((event) => event.runId === 'run-1')).toBe(true);
    expect(posted[0]?.onBehalfOfTokenId).toBe('tok-1');
    expect(posted[1]?.endedAt).toBeDefined();
    expect(headers[0]?.get('authorization')).toBe('Bearer rdt_executor');
  });

  it('control: a run begun without an id gets a minted one', async () => {
    const { posted, fetchImpl } = capture();
    const index = createRunIndex({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
    });
    const run = index.begin({ principal: PRINCIPAL, pathKey: 'repo list' });
    await run.end({ state: 'failed', exitCode: 1 });
    expect(run.runId.length).toBeGreaterThan(8);
    expect(posted[0]?.runId).toBe(run.runId);
  });

  it('reports a step at most every 15 s, the last one', async () => {
    vi.useFakeTimers();
    const { posted, fetchImpl } = capture();
    const index = createRunIndex({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
    });
    const run = index.begin({ principal: PRINCIPAL, runId: 'run-2', pathKey: 'repo up' });
    run.step('pull');
    run.step('start');
    await vi.advanceTimersByTimeAsync(PROGRESS_INTERVAL_MS - 1);
    expect(posted.filter((event) => event.lastStep)).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(2);
    expect(posted.filter((event) => event.lastStep).map((event) => event.lastStep)).toEqual([
      'start',
    ]);
    await run.end({ state: 'succeeded', exitCode: 0 });
    expect(posted.map((event) => event.seq)).toEqual([0, 1, 2]);
  });

  it('a step that flushes overdue progress cancels the pending timer (review b70d6146.2)', async () => {
    vi.useFakeTimers();
    let clock = 0;
    const { posted, fetchImpl } = capture();
    const index = createRunIndex({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
      now: () => clock,
    });
    const run = index.begin({ principal: PRINCIPAL, runId: 'run-timer', pathKey: 'repo up' });
    run.step('a');
    // The run clock passes the interval while the timer set for step a is still pending.
    await vi.advanceTimersByTimeAsync(5000);
    clock = PROGRESS_INTERVAL_MS;
    run.step('b');
    await vi.advanceTimersByTimeAsync(0);
    expect(posted.filter((event) => event.lastStep).map((event) => event.lastStep)).toEqual(['b']);
    run.step('c');
    // The first timer's deadline passes: step c is still inside the interval after b.
    await vi.advanceTimersByTimeAsync(PROGRESS_INTERVAL_MS - 5000);
    expect(posted.filter((event) => event.lastStep).map((event) => event.lastStep)).toEqual(['b']);
    await vi.advanceTimersByTimeAsync(5000);
    expect(posted.filter((event) => event.lastStep).map((event) => event.lastStep)).toEqual([
      'b',
      'c',
    ]);
    await run.end({ state: 'succeeded', exitCode: 0 });
  });

  it('announces the job and leaves a detached run for the terminal poll to end', async () => {
    const { posted, fetchImpl } = capture();
    const index = createRunIndex({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
    });
    const run = index.begin({ principal: PRINCIPAL, runId: 'run-3', pathKey: 'repo up' });
    run.job('j1-aa', 'm1');
    await run.end({ state: 'detached', exitCode: 0 });
    expect(posted.at(-1)).toMatchObject({ state: 'detached', jobId: 'j1-aa' });
    expect(posted.at(-1)?.endedAt).toBeUndefined();

    await index.endJob('j1-aa', { state: 'succeeded', exitCode: 0 });
    expect(posted.at(-1)).toMatchObject({ state: 'succeeded', jobId: 'j1-aa', seq: 3 });

    // Once only; a job this process never saw posts nothing.
    const count = posted.length;
    await index.endJob('j1-aa', { state: 'succeeded' });
    await index.endJob('j-unknown', { state: 'failed' });
    expect(posted).toHaveLength(count);
  });

  it('seals the tail so it opens with the CEK and not without it', async () => {
    const { posted, fetchImpl } = capture();
    const cek = new Uint8Array(await crypto.subtle.exportKey('raw', await generateCek()));
    const index = createRunIndex({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
    });
    const run = index.begin({
      principal: PRINCIPAL,
      runId: 'run-4',
      pathKey: 'repo list',
      cek: () => Promise.resolve(cek),
    });
    await run.end({ state: 'succeeded', exitCode: 0, stdout: 'hello out', stderr: 'oops err' });

    const tail = posted.at(-1)?.tail;
    expect(tail).toBeDefined();
    expect(tail).not.toContain('hello');
    expect(await openRunTail(cek, 'org-1', 'run-4', tail as string)).toBe('hello out\noops err');
    const other = new Uint8Array(32).fill(7);
    await expect(openRunTail(other, 'org-1', 'run-4', tail as string)).rejects.toThrow();
  });

  it('control: no CEK means no tail', async () => {
    const { posted, fetchImpl } = capture();
    const index = createRunIndex({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
    });
    const run = index.begin({ principal: PRINCIPAL, runId: 'run-5', pathKey: 'repo list' });
    await run.end({ state: 'succeeded', exitCode: 0, stdout: 'secret output' });
    expect(posted.at(-1)).not.toHaveProperty('tail');
  });

  it('retries a failing delivery twice, reports it and never throws', async () => {
    let calls = 0;
    const failures: string[] = [];
    const index = createRunIndex({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl: (() => {
        calls++;
        return Promise.reject(new Error('ECONNREFUSED'));
      }) as unknown as typeof fetch,
      onFailure: (reason) => failures.push(reason),
    });
    const run = index.begin({ principal: PRINCIPAL, runId: 'run-6', pathKey: 'repo list' });
    await expect(run.end({ state: 'succeeded', exitCode: 0 })).resolves.toBeUndefined();
    expect(calls).toBe(2 * RUN_EVENT_ATTEMPTS);
    expect(failures).toEqual(Array(2).fill('ECONNREFUSED'));
  });

  it('does not retry a refusal the server will repeat', async () => {
    const { posted, fetchImpl } = capture(() => Response.json({ error: 'no' }, { status: 403 }));
    const index = createRunIndex({
      accountUrl: 'https://account.test',
      executorToken: 't',
      fetchImpl,
    });
    const run = index.begin({ principal: PRINCIPAL, runId: 'run-7', pathKey: 'repo list' });
    await run.end({ state: 'succeeded', exitCode: 0 });
    expect(posted).toHaveLength(2);
  });
});
