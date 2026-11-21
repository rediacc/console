/**
 * X4 (PLAN-health-checks-local, D-remedy): `rdc repo repair` runs an undeclared (operator-only) repair() only after
 * its prompt is answered, an auto-with-backup one only after a snapshot, and exits from the level health() ends at.
 * `rdc machine repair` never allows operator-only repair() functions at all.
 */

import { withFix } from '@rediacc/shared/services/machine/findings';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warn: vi.fn(), print: vi.fn() },
}));
vi.mock('../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../i18n/index.js', () => ({ t: (k: string) => k }));

const { runRepoRepair, repoRepairExitCode } = await import('../repo-repair.js');
const { runMachineRepair } = await import('../machine/repair.js');

type Report = Parameters<typeof repoRepairExitCode>[0];
type Deps = Parameters<typeof runRepoRepair>[2];

const level = (l: 'ok' | 'warning' | 'error' | 'none') => ({
  state: 'healthy',
  level: l,
  files: [],
});

/** The report a one-file fake renet answers: planned or skipped in a dry run, ok or skipped in a real one. */
function fakeReport(
  cls: string,
  allowed: boolean,
  dryRun: boolean,
  fixedTo: 'ok' | 'warning'
): Report {
  const ran = allowed && !dryRun;
  const runResult = ran ? 'ok' : 'skipped';
  const file = {
    file: 'Rediaccfile',
    class: cls,
    declared: cls !== 'operator-only',
    window_only: false,
    health_level: 'warning' as const,
    result: dryRun && allowed ? 'planned' : runResult,
    exit: 0,
  };
  return {
    before: level('warning'),
    files: [file],
    ...(ran ? { after: level(fixedTo) } : {}),
    ran: ran ? 1 : 0,
    failed: 0,
  };
}

/**
 * A fake renet: one Rediaccfile with the given class whose health() is a warning; repair() clears it to `fixedTo`
 * when its class is allowed. Every call's allowed classes are recorded.
 */
function fakeRenet(
  cls: string,
  opts: { fixedTo?: 'ok' | 'warning'; snapshotOk?: boolean; confirm?: boolean } = {}
) {
  const calls: { allow: string[]; dryRun: boolean }[] = [];
  let snapshots = 0;
  let prompts = 0;
  const deps: Deps = {
    repair: (allow, _inWindow, dryRun) => {
      calls.push({ allow, dryRun });
      return Promise.resolve(fakeReport(cls, allow.includes(cls), dryRun, opts.fixedTo ?? 'ok'));
    },
    snapshot: () => {
      snapshots++;
      return Promise.resolve({ ok: opts.snapshotOk !== false });
    },
    confirm: () => {
      prompts++;
      return Promise.resolve(opts.confirm === true);
    },
  };
  return { deps, calls, snapshots: () => snapshots, prompts: () => prompts };
}

describe('rdc repo repair (X4 control)', () => {
  it('runs an undeclared repair() only after its prompt is answered', async () => {
    const declined = fakeRenet('operator-only', { confirm: false });
    const no = await runRepoRepair({}, false, declined.deps);
    expect(declined.prompts()).toBe(1);
    expect(declined.calls.at(-1)?.allow).toEqual(['auto-safe']);
    expect(no.withheld).toEqual(['not-confirmed']);
    expect(no.exitCode).toBe(1);

    const accepted = fakeRenet('operator-only', { confirm: true });
    const yes = await runRepoRepair({}, false, accepted.deps);
    expect(accepted.calls.at(-1)?.allow).toEqual(['auto-safe', 'operator-only']);
    expect(yes.exitCode).toBe(0);

    const flagged = fakeRenet('operator-only');
    await runRepoRepair({ yes: true }, false, flagged.deps);
    expect(flagged.prompts()).toBe(0);
    expect(flagged.calls.at(-1)?.allow).toContain('operator-only');
  });

  it('runs auto-with-backup only with --with-backup and a snapshot that succeeded', async () => {
    const without = fakeRenet('auto-with-backup');
    expect((await runRepoRepair({}, false, without.deps)).withheld).toEqual(['needs-backup']);
    expect(without.snapshots()).toBe(0);

    const failing = fakeRenet('auto-with-backup', { snapshotOk: false });
    const cancelled = await runRepoRepair({ withBackup: true }, false, failing.deps);
    expect(cancelled.withheld).toEqual(['snapshot-failed']);
    expect(failing.calls.at(-1)?.allow).toEqual(['auto-safe']);

    const ok = fakeRenet('auto-with-backup');
    const ran = await runRepoRepair({ withBackup: true }, false, ok.deps);
    expect(ok.snapshots()).toBe(1);
    expect(ran.allowClasses).toEqual(['auto-safe', 'auto-with-backup']);
    expect(ran.exitCode).toBe(0);
  });

  it('exits 1 when the repair leaves health() at a warning, 2 when a repair() failed', async () => {
    const stillWarning = fakeRenet('auto-safe', { fixedTo: 'warning' });
    expect((await runRepoRepair({}, false, stillWarning.deps)).exitCode).toBe(1);
    expect(
      repoRepairExitCode({
        before: level('warning'),
        files: [],
        after: level('ok'),
        ran: 1,
        failed: 1,
      })
    ).toBe(2);
    expect(repoRepairExitCode({ before: level('none'), files: [], ran: 0, failed: 0 })).toBe(0);
  });

  it('plans without running anything under --dry-run', async () => {
    const r = fakeRenet('auto-safe');
    const out = await runRepoRepair({ dryRun: true }, false, r.deps);
    expect(r.calls).toHaveLength(1);
    expect(r.calls[0].dryRun).toBe(true);
    expect(out.report.ran).toBe(0);
  });

  it('reports nothing withheld under --dry-run: no prompt would be shown', async () => {
    const r = fakeRenet('operator-only');
    const out = await runRepoRepair({ dryRun: true }, false, r.deps);
    expect(out.withheld).toEqual([]);
    expect(r.prompts()).toBe(0);
  });
});

describe('rdc machine repair never allows an undeclared repair()', () => {
  it('passes only auto-safe (and auto-with-backup after a snapshot) to a repo repair', async () => {
    const allows: string[][] = [];
    const f = {
      ...withFix({ code: 'repo.health.warning', severity: 'warning', subject: 'shop', detail: '' }),
      target: { repository: 'g1' },
    };
    let present = [f];
    const deps = {
      readHealth: () =>
        Promise.resolve({
          healthy: false,
          exitCode: 1,
          message: '',
          details: {} as never,
          issues: [],
          findings: present,
        }),
      runFix: (_f: unknown, ctx: { allowClasses: string[] }) => {
        allows.push(ctx.allowClasses);
        present = [];
        return Promise.resolve({ ok: true });
      },
      snapshot: () => Promise.resolve({ ok: true }),
      journal: () => Promise.resolve(),
      now: () => new Date('2026-11-06T12:00:00Z'),
    };
    await runMachineRepair('m1', undefined, {}, deps);
    present = [f];
    await runMachineRepair('m1', undefined, { withBackup: true, windowOverride: true }, deps);
    expect(allows).toEqual([['auto-safe'], ['auto-safe', 'auto-with-backup']]);
    for (const a of allows) expect(a).not.toContain('operator-only');
  });
});
