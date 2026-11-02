/**
 * `rdc job wait`: resume from lastSeenLine, acknowledge, and exit with the job's
 * own exit code. The SSH tail is mocked; the store is real.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, type Mock, vi } from 'vitest';
import type { JobWaitDeps } from '../../services/jobs/job-wait.js';
import { TicketStore } from '../../services/jobs/ticket-store.js';
import { EXIT_CODES } from '../../types/index.js';

const out = vi.hoisted(() => ({
  print: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
}));
const holder = vi.hoisted(() => ({ store: undefined as unknown, deps: undefined as unknown }));

vi.mock('../../services/core/output.js', () => ({ outputService: out }));
vi.mock('../../services/executor/job-remote.js', () => ({
  renderJobEvent: vi.fn(),
  connectForJobs: vi.fn(),
  followJobLogs: vi.fn(),
  replayJobLogs: vi.fn(),
  readJobStatus: vi.fn(),
  listJobs: vi.fn(),
  cancelJob: vi.fn(),
  gcJobs: vi.fn(),
}));
vi.mock('../../services/jobs/remote-deps.js', () => ({
  openTicketStore: () => holder.store,
  sshWaitDeps: () => holder.deps,
}));

const { registerJobCommands } = await import('../job.js');
const { initI18n } = await import('../../i18n/index.js');

const JOB_ID = 'j1a2b-0123abcd';
let base: string;
let store: TicketStore;
let follow: Mock<JobWaitDeps['follow']>;
let readStatus: Mock<JobWaitDeps['readStatus']>;

type JobStatus = Awaited<ReturnType<JobWaitDeps['readStatus']>>;

function jobStatus(over: Partial<JobStatus>): JobStatus {
  return {
    job_id: JOB_ID,
    function: 'repository_up',
    state: 'succeeded',
    exit_code: 0,
    started_at: '2026-10-29T10:00:00Z',
    ...over,
  } as JobStatus;
}

async function run(...args: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerJobCommands(program);
  await program.parseAsync(['node', 'rdc', 'job', ...args]);
}

beforeEach(async () => {
  await initI18n('en');
  vi.clearAllMocks();
  process.exitCode = undefined;
  base = mkdtempSync(join(tmpdir(), 'rdc-job-wait-'));
  store = new TicketStore('rediacc', base);
  holder.store = store;
  follow = vi.fn<JobWaitDeps['follow']>().mockResolvedValue(false);
  readStatus = vi.fn<JobWaitDeps['readStatus']>().mockResolvedValue(jobStatus({}));
  holder.deps = {
    withConnection: <T>(_m: string, fn: (c: unknown) => Promise<T>) => fn({}),
    follow,
    readStatus,
  } satisfies JobWaitDeps;

  store.append('starting', 'req-1', {
    machine: 'box-7',
    verb: 'repo up',
    startedAt: new Date().toISOString(),
  });
  store.append('started', 'req-1', { jobId: JOB_ID, via: { kind: 'ssh' } });
  store.append('seen', 'req-1', { lastSeenLine: 42 });
});
afterEach(() => {
  process.exitCode = undefined;
  rmSync(base, { recursive: true, force: true });
});

describe('rdc job wait', () => {
  it('resumes the tail from the ticket lastSeenLine', async () => {
    await run('wait', JOB_ID);
    const cursor = follow.mock.calls[0][2];
    expect(cursor.sinceLine).toBe(42);
  });

  it('exits with the job exit code and acknowledges the ticket', async () => {
    readStatus.mockResolvedValue(jobStatus({ state: 'failed', exit_code: 9 }));
    await run('wait', JOB_ID);
    expect(process.exitCode).toBe(9);
    expect(store.pending()).toHaveLength(0);
    expect(store.tickets()[0]).toMatchObject({ state: 'failed', exitCode: 9, acknowledged: true });
  });

  it('names the failure reason of a job that did not succeed', async () => {
    readStatus.mockResolvedValue(
      jobStatus({ state: 'failed', exit_code: 9, error: 'disk full on /mnt' })
    );
    await run('wait', JOB_ID);
    expect(out.warn.mock.calls.map((c) => String(c[0])).join('\n')).toContain('disk full on /mnt');
  });

  it('exits 0 for a succeeded job', async () => {
    await run('wait', JOB_ID);
    expect(process.exitCode ?? 0).toBe(0);
    expect(out.success).toHaveBeenCalled();
  });

  it('records the cursor so a second wait resumes where this one stopped', async () => {
    follow.mockImplementation((_c: unknown, _j: string, cursor: { consume(b: Buffer): void }) => {
      cursor.consume(Buffer.from('a\nb\nc\n'));
      return Promise.resolve(true);
    });
    await run('wait', JOB_ID, '--timeout', '30s');
    expect(store.tickets()[0].lastSeenLine).toBe(45);
    expect(store.tickets()[0].acknowledged).toBe(false);
  });

  it('--timeout stops the wait with FOLLOW_LOST and leaves the ticket pending', async () => {
    follow.mockImplementation(
      (_c: unknown, _j: string, _cur: unknown, _on: unknown, signal: AbortSignal) =>
        new Promise<boolean>((resolve) => signal.addEventListener('abort', () => resolve(true)))
    );
    await run('wait', JOB_ID, '--timeout', '1s');
    expect(process.exitCode).toBe(EXIT_CODES.FOLLOW_LOST);
    expect(store.pending()).toHaveLength(1);
    expect(out.warn.mock.calls[0][0]).toContain(`rdc job wait ${JOB_ID}`);
  }, 10_000);

  it('does not tail a ticket already known finished, only acknowledges it', async () => {
    store.append('finished', 'req-1', { state: 'failed', exitCode: 4 });
    await run('wait', JOB_ID);
    expect(follow).not.toHaveBeenCalled();
    expect(process.exitCode).toBe(4);
    expect(store.pending()).toHaveLength(0);
  });

  it('refuses a malformed --timeout', async () => {
    const exit = vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never);
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    await run('wait', JOB_ID, '--timeout', 'soon');
    expect(follow).not.toHaveBeenCalled();
    expect(JSON.stringify(out.error.mock.calls)).toContain('--timeout');
    exit.mockRestore();
    err.mockRestore();
  });

  it('a proxy ticket is refused until J6 supplies followProxy', async () => {
    store.append('starting', 'req-2', { machine: 'm2' });
    store.append('started', 'req-2', { jobId: 'j9-aaaaaaaa', via: { kind: 'proxy' } });
    const exit = vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never);
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    await run('wait', 'j9-aaaaaaaa');
    expect(follow).not.toHaveBeenCalled();
    expect(JSON.stringify(out.error.mock.calls)).toContain('proxy');
    expect(store.find('j9-aaaaaaaa')?.acknowledged).toBe(false);
    exit.mockRestore();
    err.mockRestore();
  });
});
