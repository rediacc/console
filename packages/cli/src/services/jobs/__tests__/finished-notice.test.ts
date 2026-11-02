import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  checkPendingTickets,
  NOTICE_MAX_TICKETS,
  type NoticeDeps,
  printFinishedNotices,
  shouldRunNotice,
} from '../finished-notice.js';
import { TicketStore } from '../ticket-store.js';

let base: string;
let store: TicketStore;

beforeEach(async () => {
  base = mkdtempSync(join(tmpdir(), 'rdc-notice-'));
  store = new TicketStore('rediacc', base);
  const { initI18n } = await import('../../../i18n/index.js');
  await initI18n('en');
});
afterEach(() => {
  rmSync(base, { recursive: true, force: true });
});

function addRunning(id: string, extra: Record<string, unknown> = {}): void {
  store.append('starting', `r-${id}`, {
    machine: 'm1',
    verb: 'repo up',
    repo: 'web',
    startedAt: '2026-01-01T00:00:00Z',
    ...extra,
  });
  store.append('started', `r-${id}`, { jobId: `j${id}-aaaaaaaa`, via: { kind: 'ssh' } });
}

function deps(observe: NoticeDeps['observe'], write = vi.fn()): NoticeDeps {
  return { store, observe, write };
}

describe('finished-while-away notice', () => {
  it('makes zero machine calls when there are no tickets', async () => {
    const observe = vi.fn();
    await checkPendingTickets(deps(observe));
    expect(observe).not.toHaveBeenCalled();
  });

  it('prints once per finished ticket, then acknowledges it', async () => {
    addRunning('1');
    const write = vi.fn();
    const d = deps(async () => ({ state: 'succeeded', exitCode: 0 }), write);

    await checkPendingTickets(d);
    printFinishedNotices(d);
    expect(write).toHaveBeenCalledTimes(1);
    expect(write.mock.calls[0][0]).toContain('succeeded');
    expect(write.mock.calls[0][0]).toContain('rdc job logs j1-aaaaaaaa');

    // A second invocation announces nothing: the ticket is acknowledged.
    await checkPendingTickets(d);
    printFinishedNotices(d);
    expect(write).toHaveBeenCalledTimes(1);
    expect(store.pending()).toHaveLength(0);
  });

  it('names the exit code of a failed job', async () => {
    addRunning('1');
    const write = vi.fn();
    const d = deps(async () => ({ state: 'failed', exitCode: 7 }), write);
    await checkPendingTickets(d);
    printFinishedNotices(d);
    expect(write.mock.calls[0][0]).toContain('7');
  });

  it('checks at most 5 tickets and skips ones checked within the last 60 s', async () => {
    for (let i = 0; i < 8; i++) addRunning(String(i));
    const observe = vi.fn(async () => ({ state: 'running' as const }));
    await checkPendingTickets(deps(observe));
    expect(observe).toHaveBeenCalledTimes(NOTICE_MAX_TICKETS);

    observe.mockClear();
    await checkPendingTickets(deps(observe));
    // the 5 just checked are throttled; the other 3 are due
    expect(observe).toHaveBeenCalledTimes(3);
  });

  it('a hung status read never stalls the command past the budget', async () => {
    addRunning('1');
    const started = Date.now();
    await checkPendingTickets(deps(() => new Promise(() => {})));
    expect(Date.now() - started).toBeLessThan(4000);
  });

  it('a failing read never throws and leaves the ticket pending', async () => {
    addRunning('1');
    await expect(
      checkPendingTickets(deps(async () => Promise.reject(new Error('ssh down'))))
    ).resolves.toBeUndefined();
    expect(store.pending()).toHaveLength(1);
  });

  it('writes through the injected stderr sink only, never stdout', async () => {
    addRunning('1');
    const out = vi.spyOn(process.stdout, 'write');
    const err = vi.fn();
    const d = deps(async () => ({ state: 'succeeded', exitCode: 0 }), err);
    await checkPendingTickets(d);
    printFinishedNotices(d);
    expect(err).toHaveBeenCalled();
    expect(out).not.toHaveBeenCalled();
    out.mockRestore();
  });
});

describe('shouldRunNotice', () => {
  const base = { commandPath: 'repo up', quiet: false, format: 'table', inExecutorRequest: false };

  it('runs for an ordinary text command', () => {
    expect(shouldRunNotice(base)).toBe(true);
  });

  it.each([
    ['rdc job *', { commandPath: 'job list' }],
    ['bare job', { commandPath: 'job' }],
    ['-q', { quiet: true }],
    ['-o json', { format: 'json' }],
    ['an executor request', { inExecutorRequest: true }],
  ])('is skipped for %s', (_name, patch) => {
    expect(shouldRunNotice({ ...base, ...patch })).toBe(false);
  });

  it('does not skip a command that merely starts with the letters job', () => {
    expect(shouldRunNotice({ ...base, commandPath: 'jobs-report' })).toBe(true);
  });
});
