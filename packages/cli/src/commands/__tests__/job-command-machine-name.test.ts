/**
 * The job verbs hand the machine name to the remote helpers, so a renet failure names the machine
 * (and the `rdc machine setup` hint can say which one) instead of a bare "the machine".
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

vi.mock('../../services/executor/job-remote.js', () => remote);
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: vi.fn(), info: vi.fn(), warn: vi.fn(), success: vi.fn() },
}));

const { registerJobCommands } = await import('../job.js');

const JOB_ID = '0123456789abcdef0123456789abcdef';
const SUCCEEDED = { job_id: JOB_ID, state: 'succeeded', function: 'repo_up' };

async function run(...args: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  program.option('-o, --output <format>', 'output format', 'table');
  registerJobCommands(program);
  await program.parseAsync(['node', 'rdc', 'job', ...args]);
}

describe('rdc job passes the machine name to the remote helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    remote.connectForJobs.mockResolvedValue({
      lease: { sftp: {}, release: vi.fn() },
      remoteRenetPath: '/usr/bin/renet',
      machineName: 'm1',
    });
    remote.readJobStatus.mockResolvedValue(SUCCEEDED);
    remote.followJobLogs.mockResolvedValue(false);
  });

  it('job status', async () => {
    await run('status', JOB_ID, '-m', 'm1');
    expect(remote.readJobStatus).toHaveBeenCalledWith({}, '/usr/bin/renet', JOB_ID, 'm1');
  });

  it('job logs --follow, both the tail and the closing status read', async () => {
    await run('logs', JOB_ID, '-m', 'm1', '--follow');
    expect(remote.followJobLogs.mock.calls[0]?.[5]).toBe('m1');
    expect(remote.readJobStatus).toHaveBeenCalledWith({}, '/usr/bin/renet', JOB_ID, 'm1');
  });

  it('job cancel reads the current state with the machine name', async () => {
    await run('cancel', JOB_ID, '-m', 'm1', '--yes');
    expect(remote.readJobStatus).toHaveBeenCalledWith({}, '/usr/bin/renet', JOB_ID, 'm1');
  });
});
