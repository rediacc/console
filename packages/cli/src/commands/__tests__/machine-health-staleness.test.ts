/**
 * machine status and health report renet processes on a replaced binary (C4) and repos whose last
 * backup is older than twice their schedule interval (G7); health exits at least 1 on either.
 */

import { describe, expect, it, vi } from 'vitest';

vi.mock('../../services/core/output.js', () => ({ outputService: { info: vi.fn() } }));
vi.mock('../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../i18n/index.js', () => ({ t: (k: string) => k }));

const { applyStaleness } = await import('../machine/health.js');
const { staleBackupRows, staleBinaryRows } = await import('../machine/status.js');

const healthy = {
  healthy: true,
  exitCode: 0,
  message: 'All systems healthy',
  details: {} as never,
  issues: [],
};

const hub = {
  pid: 101,
  unit: 'rediacc-hub.service',
  exe: '/usr/lib/rediacc/renet/0.9.1/renet (deleted)',
};
const stale = {
  guid: 'a0000000-0000-4000-8000-000000000001',
  lastSuccessAt: '2026-10-20T03:00:00Z',
  ageDays: 5.4,
  intervalDays: 1,
};

describe('health folds in staleness', () => {
  it('a stale renet process makes health exit 1 and names the unit', () => {
    const h = applyStaleness(healthy, { staleBinary: [hub], staleBackups: [] });
    expect(h.exitCode).toBe(1);
    expect(h.healthy).toBe(false);
    expect(h.message).toBe('System has warnings');
    expect(h.issues[0]).toMatch(/rediacc-hub\.service \(pid 101\)/);
  });

  it('a repo two schedule intervals behind makes health exit 1', () => {
    const h = applyStaleness(healthy, { staleBinary: [], staleBackups: [stale] });
    expect(h.exitCode).toBe(1);
    expect(h.issues[0]).toMatch(/more than twice their schedule interval/);
  });

  it('never lowers a worse verdict, and leaves a clean machine clean (control)', () => {
    const worse = applyStaleness(
      { ...healthy, healthy: false, exitCode: 2, message: 'System has errors' },
      { staleBinary: [hub], staleBackups: [stale] }
    );
    expect(worse.exitCode).toBe(2);
    expect(worse.message).toBe('System has errors');
    expect(applyStaleness(healthy, { staleBinary: [], staleBackups: [] })).toEqual(healthy);
  });

  it('an unreadable probe (null) is not reported as stale', () => {
    expect(applyStaleness(healthy, { staleBinary: null, staleBackups: [] }).exitCode).toBe(0);
  });
});

describe('machine status staleness tables', () => {
  it('lists pid, unit and exe target per stale process', () => {
    expect(staleBinaryRows([hub])).toEqual([
      {
        pid: 101,
        unit: 'rediacc-hub.service',
        exe: '/usr/lib/rediacc/renet/0.9.1/renet (deleted)',
      },
    ]);
  });

  it('lists each stale repo by name with its age and schedule', () => {
    expect(staleBackupRows([stale], () => 'mail')).toEqual([
      {
        repository: 'mail',
        lastBackup: '2026-10-20T03:00:00Z',
        ageDays: 5.4,
        scheduleEveryDays: 1,
      },
    ]);
  });
});
