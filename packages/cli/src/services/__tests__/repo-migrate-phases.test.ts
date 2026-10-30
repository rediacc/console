/**
 * The per-phase details of `repo migrate` (PLAN-detached-jobs J4, operator ruling 2026-10-30: "keep the per-phase
 * details"). renet records each phase's bytes and duration and the downtime window in the job's `migrate_result`
 * line; the reportMigrateResult step prints them in the foreground and, through the log replay, from `rdc job wait`.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { extractMigrateResult, renderMigrateResult } from '../../commands/repo-migrate.js';
import { outputService } from '../core/output.js';
import type { JobStatus } from '../executor/job-client.js';
import type { RenetEvent } from '../executor/types.js';
import { type JobWaitDeps, waitForJob } from '../jobs/job-wait.js';
import type { ClaimExec } from '../jobs/run-job.js';
import { planStep, resolveStepHandler, toTicketSteps } from '../jobs/steps.js';
import { type Ticket, TicketStore } from '../jobs/ticket-store.js';

const RESULT_LINE = JSON.stringify({
  migrate_result: {
    phases: [
      { name: 'bulk', transferMode: 'full', transferredBytes: 1_073_741_824, transferMs: 41_000 },
      { name: 'cutover', transferMode: 'delta', transferredBytes: 52_428_800, transferMs: 6_200 },
    ],
    downtimeMs: 9_500,
  },
});

let info: ReturnType<typeof vi.spyOn>;

function printed(): string[] {
  return info.mock.calls.map((c: unknown[]) => String(c[0]));
}

beforeEach(async () => {
  const { initI18n } = await import('../../i18n/index.js');
  await initI18n('en');
  info = vi.spyOn(outputService, 'info').mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('migrate_result line', () => {
  it('is found between log lines and behind a relay prefix', () => {
    const output = `[repository_migrate] pushing\n[repository_migrate] ${RESULT_LINE}\ndone`;
    expect(extractMigrateResult(output)?.downtimeMs).toBe(9_500);
  });

  it('is absent from output that has none, or a malformed one', () => {
    expect(extractMigrateResult(undefined)).toBeUndefined();
    expect(extractMigrateResult('{"migrate_result": {"phases": 3}}\nplain')).toBeUndefined();
  });
});

describe('renderMigrateResult', () => {
  it('prints both transfers and the downtime with real numbers', () => {
    renderMigrateResult(RESULT_LINE);
    const lines = printed();
    expect(lines[0]).toBe('  Transferred 1.0 GB in 41.0s, source stayed online');
    expect(lines[1]).toContain('Phase 2: Cutover (brief downtime)...');
    expect(lines[2]).toBe('  Cutover (DOWNTIME): 50.0 MB in 6.2s');
    expect(lines[3]).toBe('  Downtime: 9.5s');
  });

  it('omits a transfer whose bytes renet could not measure, and prints nothing without a result', () => {
    renderMigrateResult(
      JSON.stringify({
        migrate_result: {
          phases: [
            { name: 'bulk', transferredBytes: -1, transferMs: 0 },
            { name: 'cutover', transferredBytes: -1, transferMs: 0 },
          ],
          downtimeMs: 2_000,
        },
      })
    );
    expect(printed().some((l) => l.includes('Transferred'))).toBe(false);
    expect(printed()).toContain('  Downtime: 2.0s');

    info.mockClear();
    renderMigrateResult('no result here');
    expect(info).not.toHaveBeenCalled();
  });
});

describe('rdc job wait reads the result later', () => {
  let base: string;
  beforeEach(() => {
    base = mkdtempSync(join(tmpdir(), 'rdc-migrate-phases-'));
  });
  afterEach(() => {
    rmSync(base, { recursive: true, force: true });
  });

  it('a ticket that finished while away replays the log and prints the phases once', async () => {
    const store = new TicketStore('rediacc', base);
    store.append('starting', 'r1', {
      machine: 'm1',
      verb: 'repo migrate',
      repo: 'web',
      startedAt: '2026-01-01T00:00:00Z',
      steps: toTicketSteps([planStep('reportMigrateResult')]),
    });
    store.append('started', 'r1', { jobId: 'j1a2b-0123abcd', via: { kind: 'ssh' } });
    store.append('finished', 'r1', { state: 'succeeded', exitCode: 0 });

    const claim: ClaimExec = async ({ steps }) =>
      steps.map((name) => ({ name, result: 'claimed' as const }));
    const replay = vi.fn((_c: unknown, _id: string, onEvent: (e: RenetEvent) => void) => {
      onEvent({ type: 'output', msg: 'pushing' } as RenetEvent);
      onEvent({ type: 'output', msg: RESULT_LINE } as RenetEvent);
      return Promise.resolve();
    });
    const deps: JobWaitDeps = {
      withConnection: (_m, fn) => fn({}),
      follow: async () => false,
      readStatus: async () => ({}) as JobStatus,
      replay,
      steps: {
        claim,
        resolve: resolveStepHandler,
        observer: { configName: 'rediacc' },
        warn: vi.fn(),
      },
    };

    const outcome = await waitForJob(store, store.find('j1a2b-0123abcd') as Ticket, deps, {
      onEvent: () => {},
    });

    expect(outcome.kind === 'finished' && outcome.steps.ran).toEqual(['reportMigrateResult']);
    expect(replay).toHaveBeenCalledTimes(1);
    expect(printed()).toContain('  Downtime: 9.5s');
    expect(printed()).toContain('  Cutover (DOWNTIME): 50.0 MB in 6.2s');
  });
});
