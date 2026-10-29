/**
 * `rdc job list` without -m prints this config's tickets, and the optional -m on
 * status, logs and cancel takes the machine from the ticket.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TicketStore } from '../../services/jobs/ticket-store.js';

const remote = vi.hoisted(() => ({
  connectForJobs: vi.fn(),
  readJobStatus: vi.fn(),
  followJobLogs: vi.fn(),
  replayJobLogs: vi.fn(),
  listJobs: vi.fn(),
  cancelJob: vi.fn(),
  gcJobs: vi.fn(),
  renderJobEvent: vi.fn(),
}));
const out = vi.hoisted(() => ({
  print: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
}));
const holder = vi.hoisted(() => ({ store: undefined as unknown }));

vi.mock('../../services/executor/job-remote.js', () => remote);
vi.mock('../../services/core/output.js', () => ({ outputService: out }));
vi.mock('../../services/jobs/remote-deps.js', () => ({
  openTicketStore: () => holder.store,
  sshWaitDeps: () => ({}),
}));

const { registerJobCommands } = await import('../job.js');
const { initI18n } = await import('../../i18n/index.js');

const JOB_ID = 'j1a2b-0123abcd';
let base: string;
let store: TicketStore;

async function run(...args: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  program.option('-o, --output <format>', 'output format', 'table');
  registerJobCommands(program);
  await program.parseAsync(['node', 'rdc', 'job', ...args]);
}

beforeEach(async () => {
  await initI18n('en');
  vi.clearAllMocks();
  base = mkdtempSync(join(tmpdir(), 'rdc-job-tickets-'));
  store = new TicketStore('rediacc', base);
  holder.store = store;
  remote.connectForJobs.mockResolvedValue({
    lease: { sftp: {}, release: vi.fn() },
    remoteRenetPath: '/usr/bin/renet',
    machineName: 'm1',
  });
  remote.readJobStatus.mockResolvedValue({ job_id: JOB_ID, state: 'running', function: 'repo_up' });
  remote.listJobs.mockResolvedValue([]);
});
afterEach(() => {
  rmSync(base, { recursive: true, force: true });
});

function addTicket(): void {
  store.append('starting', 'req-1', {
    machine: 'box-7',
    verb: 'repo up',
    repo: 'web',
    startedAt: new Date().toISOString(),
  });
  store.append('started', 'req-1', { jobId: JOB_ID, via: { kind: 'ssh' } });
}

describe('rdc job list without -m', () => {
  it('prints this config tickets and makes no machine call', async () => {
    addTicket();
    await run('list');

    expect(remote.connectForJobs).not.toHaveBeenCalled();
    expect(out.print).toHaveBeenCalledTimes(1);
    const [rows] = out.print.mock.calls[0];
    expect(rows).toEqual([
      expect.objectContaining({
        id: JOB_ID,
        verb: 'repo up',
        repo: 'web',
        machine: 'box-7',
        state: 'running',
      }),
    ]);
  });

  it('says so when the config has no pending tickets', async () => {
    await run('list');
    expect(out.info).toHaveBeenCalledWith('No pending jobs for this config.');
    expect(out.print).not.toHaveBeenCalled();
  });

  it('hides acknowledged tickets', async () => {
    addTicket();
    store.append('acknowledged', 'req-1');
    await run('list');
    expect(out.print).not.toHaveBeenCalled();
  });

  it('with -m still lists the machine jobs as before', async () => {
    addTicket();
    await run('list', '-m', 'm1');
    expect(remote.listJobs).toHaveBeenCalled();
    expect(remote.connectForJobs).toHaveBeenCalledWith('m1', 'read-only');
  });
});

describe('the optional -m takes the machine from the ticket', () => {
  it('job status uses the ticket machine', async () => {
    addTicket();
    await run('status', JOB_ID);
    expect(remote.connectForJobs).toHaveBeenCalledWith('box-7', 'read-only');
  });

  it('an explicit -m wins over the ticket', async () => {
    addTicket();
    await run('status', JOB_ID, '-m', 'other');
    expect(remote.connectForJobs).toHaveBeenCalledWith('other', 'read-only');
  });

  it('job cancel uses the ticket machine', async () => {
    addTicket();
    remote.cancelJob.mockResolvedValue({ job_id: JOB_ID, state: 'cancelled' });
    await run('cancel', JOB_ID, '-y');
    expect(remote.connectForJobs).toHaveBeenCalledWith('box-7', 'provision');
  });

  it('with no ticket and no -m the command fails and names -m', async () => {
    const exit = vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never);
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    await run('status', JOB_ID);
    expect(remote.connectForJobs).not.toHaveBeenCalled();
    expect(JSON.stringify(out.error.mock.calls)).toContain('-m');
    exit.mockRestore();
    err.mockRestore();
  });
});
