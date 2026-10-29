/**
 * `machine status` renders the jobs section of `renet list all` (PLAN-detached-jobs J21): one row
 * per live or recently finished job with its id, verb, repo, start time, origin, state and the
 * exact attach command, and the JSON output carries the jobs with their repo names resolved.
 */

import type { JobInfo } from '@rediacc/shared/renet-contract/data/list-types.generated';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../services/core/output.js', () => ({ outputService: { info: vi.fn() } }));
vi.mock('../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../i18n/index.js', () => ({
  t: (k: string, p?: Record<string, unknown>) => (p ? `${k} ${JSON.stringify(p)}` : k),
}));

const { runningJobLines, enrichJobs, statusJsonDocument } = await import('../machine/status.js');

const GUID = 'a0000000-0000-4000-8000-000000000001';
const FOREIGN = 'b0000000-0000-4000-8000-000000000002';
const resolve = (guid: string) => (guid === GUID ? 'mail' : guid);

const live: JobInfo = {
  job_id: 'j-123',
  function: 'backup_snapshot',
  repo_guid: GUID,
  machine: 'hostinger',
  state: 'running',
  lock_class: 'repo-shared',
  started_at: '2026-10-29T10:00:00Z',
  attach: 'rdc job logs j-123 -m hostinger --follow',
  origin: { client: 'rdc', config_name: 'default', ssh_user: 'muhammed' },
};

function params(line: string): Record<string, string> {
  return JSON.parse(line.slice(line.indexOf('{'))) as Record<string, string>;
}

describe('machine status running jobs', () => {
  it('renders one row per job, carrying the attach command', () => {
    const lines = runningJobLines([live], resolve);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toBe('commands.machine.status.runningJobsSection');
    const row = params(lines[1]);
    expect(row).toEqual({
      id: 'j-123',
      verb: 'backup_snapshot',
      repo: 'mail',
      startedAt: '2026-10-29T10:00:00Z',
      origin: 'rdc default (muhammed)',
      state: 'running',
      attach: 'rdc job logs j-123 -m hostinger --follow',
    });
  });

  it('a job from another config shows its GUID and its origin', () => {
    const foreign: JobInfo = {
      ...live,
      job_id: 'j-9',
      repo_guid: FOREIGN,
      origin: { client: 'proxy', config_name: 'ops', actor: 'alice@example.com' },
    };
    const row = params(runningJobLines([foreign], resolve)[1]);
    expect(row.repo).toBe(FOREIGN);
    expect(row.origin).toBe('proxy ops (alice@example.com)');
  });

  it('a command-kind job without a repo or origin falls back to its command and a dash', () => {
    const cmd: JobInfo = {
      job_id: 'j-7',
      command: 'setup',
      state: 'succeeded',
      lock_class: 'machine-exclusive',
      started_at: '2026-10-29T09:00:00Z',
      attach: 'rdc job logs j-7 --follow',
    };
    const row = params(runningJobLines([cmd], resolve)[1]);
    expect(row.verb).toBe('setup');
    expect(row.repo).toBe('-');
    expect(row.origin).toBe('-');
  });

  it('JSON output carries the jobs with the repo name resolved', () => {
    const out = enrichJobs([live], resolve);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ job_id: 'j-123', repo_guid: GUID, repository: 'mail' });
  });

  it('the printed JSON document always carries a jobs key, empty when renet reports none', () => {
    const doc = statusJsonDocument({ machine: 'hostinger' }, undefined, resolve, null, []);
    expect(Object.keys(doc)).toEqual(['machine', 'jobs', 'stale_binary', 'backup_staleness']);
    expect(doc.jobs).toEqual([]);
    const withJob = statusJsonDocument({ machine: 'hostinger' }, [live], resolve, null, []);
    expect(withJob.jobs).toEqual([{ ...live, repository: 'mail' }]);
  });

  it('control: an empty or absent jobs section prints nothing extra', () => {
    expect(runningJobLines([], resolve)).toEqual([]);
    expect(runningJobLines(undefined, resolve)).toEqual([]);
    expect(enrichJobs(undefined, resolve)).toEqual([]);
  });
});
