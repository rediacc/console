/**
 * X2 (PLAN-health-checks-local, D-remedy): `rdc machine repair` enforces the safety classes, the maintenance window
 * and the re-check, and settles its exit code from what is left. The machine side is injected (RepairDeps).
 */

import type { HealthFinding } from '@rediacc/shared/services/machine/findings';
import { withFix } from '@rediacc/shared/services/machine/findings';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warn: vi.fn(), print: vi.fn() },
}));
vi.mock('../../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../../i18n/index.js', () => ({ t: (k: string) => k }));

const {
  inMaintenanceWindow,
  parseMaintenanceWindow,
  repairExitCode,
  repoRepairOutcome,
  runMachineRepair,
  supervisorNetworkIds,
} = await import('../repair.js');

type Deps = Parameters<typeof runMachineRepair>[3];

const finding = (code: string, subject = 's1', severity: HealthFinding['severity'] = 'warning') =>
  withFix({ code, severity, subject, detail: `${code} on ${subject}` });

const verdict = (findings: HealthFinding[]) => ({
  healthy: findings.length === 0,
  exitCode: Math.max(0, ...findings.map((f) => (f.severity === 'error' ? 2 : 1))),
  message: '',
  details: {} as never,
  issues: findings.map((f) => f.detail),
  findings,
});

/**
 * A fake machine: `fixes` maps a fix action to the finding codes it clears. readHealth answers what is still there;
 * every call is recorded.
 */
function fakeMachine(
  initial: HealthFinding[],
  opts: {
    clears?: Record<string, string[]>;
    fail?: string[];
    snapshotOk?: boolean;
    now?: string;
  } = {}
) {
  let present = [...initial];
  const ran: { action: string; subject: string; allow: string[]; inWindow: boolean }[] = [];
  const journal: string[] = [];
  const snapshots: string[] = [];
  const deps: Deps = {
    readHealth: () => Promise.resolve(verdict(present)),
    runFix: (f, ctx) => {
      const action = f.fix?.action ?? '';
      ran.push({ action, subject: f.subject, allow: ctx.allowClasses, inWindow: ctx.inWindow });
      if (opts.fail?.includes(action)) return Promise.resolve({ ok: false, detail: 'boom' });
      const cleared = opts.clears?.[action] ?? [f.code];
      present = present.filter((p) => !(cleared.includes(p.code) && p.subject === f.subject));
      return Promise.resolve({ ok: true });
    },
    snapshot: (f) => {
      snapshots.push(f.subject);
      return Promise.resolve(
        opts.snapshotOk === false ? { ok: false, detail: 'no store' } : { ok: true }
      );
    },
    journal: (_m, a) => {
      journal.push(`${a.code}:${a.result}`);
      return Promise.resolve();
    },
    now: () => new Date(opts.now ?? '2026-11-06T12:00:00Z'),
  };
  return { deps, ran, journal, snapshots };
}

describe('maintenance window', () => {
  it('parses HH:MM-HH:MM and refuses anything else', () => {
    expect(parseMaintenanceWindow('00:00-03:00')).toEqual({ start: 0, end: 180 });
    expect(parseMaintenanceWindow('3-4')).toBeNull();
    expect(parseMaintenanceWindow('01:00-01:00')).toBeNull();
  });

  it('answers inside and outside, across midnight, and never without a window', () => {
    const at = (iso: string) => new Date(`2026-11-06T${iso}:00Z`);
    expect(inMaintenanceWindow('00:00-03:00', at('01:30'))).toBe(true);
    expect(inMaintenanceWindow('00:00-03:00', at('03:00'))).toBe(false);
    expect(inMaintenanceWindow('23:00-01:00', at('23:30'))).toBe(true);
    expect(inMaintenanceWindow('23:00-01:00', at('00:30'))).toBe(true);
    expect(inMaintenanceWindow('23:00-01:00', at('12:00'))).toBe(false);
    expect(inMaintenanceWindow(undefined, at('01:00'))).toBe(false);
  });
});

describe('runMachineRepair (X2 control)', () => {
  it('runs an auto-safe fix, re-checks, and a second run reports zero actions', async () => {
    const m = fakeMachine([finding('datastore.usage.high', 'datastore')]);
    const first = await runMachineRepair('m1', undefined, {}, m.deps);
    expect(first.actions.map((a) => [a.code, a.result, a.after])).toEqual([
      ['datastore.usage.high', 'ok', 'gone'],
    ]);
    expect(first.exitCode).toBe(0);
    expect(m.journal).toEqual(['datastore.usage.high:ok']);
    const second = await runMachineRepair('m1', undefined, {}, m.deps);
    expect(second.actions).toEqual([]);
    expect(m.ran).toHaveLength(1);
  });

  it('prints an operator-only finding with its command and never runs it', async () => {
    const m = fakeMachine([finding('backup.coverage.absent', 'mail')]);
    const out = await runMachineRepair('m1', undefined, {}, m.deps);
    expect(m.ran).toEqual([]);
    expect(out.actions[0]).toMatchObject({
      result: 'operator',
      command: 'rdc backup strategy bind <strategy> -m m1',
    });
    expect(out.exitCode).toBe(1);
  });

  it('does not run an auto-with-backup fix without --with-backup, and cancels it when the snapshot fails', async () => {
    const f = {
      ...finding('repo.health.error', 'shop', 'error'),
      fix: {
        action: 'repo-repair' as const,
        class: 'auto-with-backup' as const,
        window_only: false,
      },
      target: { repository: 'g1' },
    };
    const without = fakeMachine([f]);
    const skipped = await runMachineRepair('m1', undefined, {}, without.deps);
    expect(skipped.actions[0].result).toBe('skipped');
    expect(without.ran).toEqual([]);

    const failingSnapshot = fakeMachine([f], { snapshotOk: false });
    const cancelled = await runMachineRepair(
      'm1',
      undefined,
      { withBackup: true },
      failingSnapshot.deps
    );
    expect(cancelled.actions[0].result).toBe('cancelled');
    expect(failingSnapshot.snapshots).toEqual(['shop']);
    expect(failingSnapshot.ran).toEqual([]);
    expect(cancelled.exitCode).toBe(2);

    const withSnapshot = fakeMachine([f]);
    const ran = await runMachineRepair('m1', undefined, { withBackup: true }, withSnapshot.deps);
    expect(ran.actions[0].result).toBe('ok');
    expect(withSnapshot.ran[0].allow).toEqual(['auto-safe', 'auto-with-backup']);
  });

  it('lets a repo repair run only auto-safe repair() functions unless a snapshot succeeded', async () => {
    const f = finding('repo.health.warning', 'shop');
    const m = fakeMachine([f], { snapshotOk: false });
    await runMachineRepair('m1', undefined, { withBackup: true }, m.deps);
    expect(m.ran[0]).toMatchObject({ action: 'repo-repair', allow: ['auto-safe'] });
  });

  it('refuses a window-only fix outside the window, and on a machine with no window', async () => {
    const f = finding('renet.binary.replaced', 'rediacc-docker-5');
    const outside = fakeMachine([f], { now: '2026-11-06T12:00:00Z' });
    const refused = await runMachineRepair('m1', '00:00-03:00', {}, outside.deps);
    expect(refused.actions[0]).toMatchObject({
      result: 'refused',
      reason: 'commands.machine.repair.reasonOutsideWindow',
    });
    expect(outside.ran).toEqual([]);

    const noWindow = fakeMachine([f], { now: '2026-11-06T01:00:00Z' });
    const never = await runMachineRepair('m1', undefined, {}, noWindow.deps);
    expect(never.actions[0]).toMatchObject({
      result: 'refused',
      reason: 'commands.machine.repair.reasonNoWindow',
    });
    expect(noWindow.ran).toEqual([]);

    const inside = fakeMachine([f], { now: '2026-11-06T01:00:00Z' });
    const ran = await runMachineRepair('m1', '00:00-03:00', {}, inside.deps);
    expect(ran.actions[0].result).toBe('ok');
    expect(inside.ran[0].inWindow).toBe(true);

    const override = fakeMachine([f]);
    expect(
      (await runMachineRepair('m1', undefined, { windowOverride: true }, override.deps)).actions[0]
        .result
    ).toBe('ok');
  });

  it('gives exit 2 when a fix fails, and names it', async () => {
    const m = fakeMachine([finding('cert.expiry.near', 'a.example.com')], {
      fail: ['restart-traefik'],
    });
    const out = await runMachineRepair('m1', undefined, {}, m.deps);
    expect(out.actions[0]).toMatchObject({ result: 'failed', detail: 'boom', after: 'present' });
    expect(out.exitCode).toBe(2);
    expect(m.journal).toEqual(['cert.expiry.near:failed']);
  });

  it('re-checks before each fix: a finding the previous fix cleared runs nothing', async () => {
    // The repo's trim also clears the datastore finding (same subject in the fake), so the second fix finds it gone.
    const m = fakeMachine(
      [finding('repo.disk.high', 'demo'), finding('datastore.usage.high', 'demo')],
      {
        clears: { 'trim-prune': ['repo.disk.high', 'datastore.usage.high'] },
      }
    );
    const out = await runMachineRepair('m1', undefined, {}, m.deps);
    expect(out.actions.map((a) => a.result)).toEqual(['ok', 'gone']);
    expect(m.ran).toHaveLength(1);
    const gone = fakeMachine([finding('cert.expiry.near', 'a'), finding('cert.expiry.near', 'b')]);
    const restarted = await runMachineRepair('m1', undefined, {}, gone.deps);
    // One Traefik restart covers every certificate.
    expect(restarted.actions.map((a) => a.result)).toEqual(['ok', 'covered']);
    expect(gone.ran).toHaveLength(1);
  });

  it('plans without running under --dry-run, and limits the run to --code', async () => {
    const findings = [
      finding('datastore.usage.high', 'datastore'),
      finding('acme.challenge.cname-shared', 'www.example.com'),
    ];
    const dry = fakeMachine(findings);
    const planned = await runMachineRepair('m1', undefined, { dryRun: true }, dry.deps);
    expect(planned.actions.map((a) => a.result)).toEqual(['planned', 'planned']);
    expect(dry.ran).toEqual([]);
    expect(planned.exitCode).toBe(1);
    const one = fakeMachine(findings);
    const scoped = await runMachineRepair(
      'm1',
      undefined,
      { code: ['acme.challenge.cname-shared'] },
      one.deps
    );
    expect(scoped.actions.map((a) => a.code)).toEqual(['acme.challenge.cname-shared']);
    expect(one.ran.map((r) => r.action)).toEqual(['acme-anchor']);
  });
});

describe('repair helpers', () => {
  it('settles the exit code from what is left', () => {
    expect(repairExitCode([], [])).toBe(0);
    expect(repairExitCode([], [finding('memory.usage.high')])).toBe(1);
    expect(repairExitCode([], [finding('license.refresh-due', 'licenses', 'info')])).toBe(1);
    expect(repairExitCode([], [finding('storage.smart.failing', 'storage', 'critical')])).toBe(2);
  });

  it('reads the supervisor network ids and the renet repair report', () => {
    expect(supervisorNetworkIds('rediacc-docker-5, rediacc-router, rediacc-docker-12')).toEqual([
      5, 12,
    ]);
    expect(
      repoRepairOutcome('{"ran":1,"failed":1,"files":[{"file":"Rediaccfile","result":"failed"}]}')
    ).toEqual({
      ok: false,
      detail: 'Rediaccfile: failed',
    });
    expect(
      repoRepairOutcome(
        '{"ran":0,"failed":0,"files":[{"file":"Rediaccfile","result":"skipped","reason":"class operator-only is not allowed"}]}'
      )
    ).toEqual({
      ok: true,
      detail: 'Rediaccfile: skipped (class operator-only is not allowed)',
    });
  });
});
