import { describe, expect, it } from 'vitest';
import { getMachineHealth } from '../parsing-health.js';

/**
 * Build the minimum vaultStatus shape getMachineHealth parses. Only the fields
 * a given assertion cares about are set; the rest stay empty so one check's
 * fixture cannot accidentally trip another check's issue.
 */
function machineWith(overrides: {
  blockDevices?: unknown[];
  repositories?: unknown[];
  licenseStatuses?: unknown[];
}) {
  return {
    vaultStatus: JSON.stringify({
      // `system` is omitted rather than set to {}: getSystemInfo returns null
      // when absent, which is the shape the caller actually guards for. An empty
      // object is not a payload renet emits — SystemInfo always carries
      // memory/disk/datastore — so faking one only tests an impossible state.
      network: {},
      services: [],
      containers: [],
      system_containers: [],
      block_devices: overrides.blockDevices ?? [],
      repositories: overrides.repositories ?? [],
      license_statuses: overrides.licenseStatuses ?? [],
    }),
  } as unknown as Parameters<typeof getMachineHealth>[0];
}

const issuesOf = (m: Parameters<typeof getMachineHealth>[0]) => getMachineHealth(m).issues;

describe('SMART health classification', () => {
  // The regression: a QEMU/KVM guest reports smart_health "unknown" because a
  // virtual disk exposes no SMART data. Counting that as a failure raised the
  // file's highest-severity issue on every VM.
  it('does not report a failure for unknown SMART state', () => {
    const issues = issuesOf(
      machineWith({ blockDevices: [{ name: 'sda', smart_health: 'unknown' }] })
    );
    expect(issues.join(' ')).not.toContain('SMART');
  });

  it.each(['N/A', 'UNKNOWN', 'Unknown', '-', ''])(
    'treats %j as indeterminate, not failing',
    (state) => {
      const issues = issuesOf(
        machineWith({ blockDevices: [{ name: 'sda', smart_health: state }] })
      );
      expect(issues.join(' ')).not.toContain('SMART');
    }
  );

  it.each(['PASSED', 'OK'])('treats %j as healthy', (state) => {
    const issues = issuesOf(machineWith({ blockDevices: [{ name: 'sda', smart_health: state }] }));
    expect(issues.join(' ')).not.toContain('SMART');
  });

  // Control: a genuinely failing disk must still raise, or the fix above would
  // have silenced the check entirely rather than corrected it.
  it.each(['FAILED', 'FAILING!'])('still reports %j as a failure', (state) => {
    const issues = issuesOf(machineWith({ blockDevices: [{ name: 'sda', smart_health: state }] }));
    expect(issues.join(' ')).toContain('SMART failure');
  });

  it('sets a non-zero exit code for a real SMART failure', () => {
    const health = getMachineHealth(
      machineWith({ blockDevices: [{ name: 'sda', smart_health: 'FAILED' }] })
    );
    expect(health.exitCode).toBeGreaterThan(0);
    expect(health.healthy).toBe(false);
  });
});

describe('unmounted repository reporting', () => {
  // A repo with autostart off is parked on purpose; flagging it every run buries
  // the repos that actually fell over.
  it('ignores an unmounted repo that is not set to autostart', () => {
    const issues = issuesOf(
      machineWith({ repositories: [{ name: 'demo', mounted: false, autostart: false }] })
    );
    expect(issues.join(' ')).not.toContain('not mounted');
  });

  it('reports an unmounted repo that should have autostarted', () => {
    const issues = issuesOf(
      machineWith({ repositories: [{ name: 'mail', mounted: false, autostart: true }] })
    );
    expect(issues.join(' ')).toContain('1 repository(ies) not mounted');
  });

  it('counts only the autostart repos that are down', () => {
    const issues = issuesOf(
      machineWith({
        repositories: [
          { name: 'up', mounted: true, autostart: true },
          { name: 'parked', mounted: false, autostart: false },
          { name: 'down-a', mounted: false, autostart: true },
          { name: 'down-b', mounted: false, autostart: true },
        ],
      })
    );
    expect(issues.join(' ')).toContain('2 repository(ies) not mounted');
  });
});

describe('repo license reporting', () => {
  const lic = (status: string, n: number) => Array.from({ length: n }, () => ({ status }));

  // The gap: partial-missing was counted but never surfaced, so repos could drop
  // out of backups (the sync skips unlicensed repos) with no signal anywhere.
  it('reports partially missing licenses', () => {
    const issues = issuesOf(
      machineWith({ licenseStatuses: [...lic('missing', 3), ...lic('valid', 8)] })
    );
    expect(issues.join(' ')).toContain('3 repo license(s) missing');
  });

  it('still reports the all-missing case distinctly', () => {
    const issues = issuesOf(machineWith({ licenseStatuses: lic('missing', 4) }));
    expect(issues.join(' ')).toContain('All repo licenses are missing');
    expect(issues.join(' ')).not.toContain('4 repo license(s) missing');
  });

  it('says nothing when every license is valid', () => {
    const issues = issuesOf(machineWith({ licenseStatuses: lic('valid', 11) }));
    expect(issues.join(' ')).not.toContain('license');
  });

  it.each([
    ['expired', 'expired'],
    ['machine_mismatch', 'machine ID mismatch'],
    ['invalid_signature', 'invalid signatures'],
  ])('still reports %s licenses', (status, expected) => {
    const issues = issuesOf(
      machineWith({ licenseStatuses: [...lic(status, 2), ...lic('valid', 5)] })
    );
    expect(issues.join(' ')).toContain(expected);
  });
});

describe('license refresh window', () => {
  const daysFromNow = (n: number) => new Date(Date.now() + n * 86400_000).toISOString();
  const valid = (refreshRecommendedAt?: string) => ({
    status: 'valid',
    runtimeValid: true,
    ...(refreshRecommendedAt ? { refreshRecommendedAt } : {}),
  });

  // The warning that arrives in time to act on: once a licence actually expires
  // the backup has already started skipping that repo.
  it('warns when a still-valid license is past its refresh window', () => {
    const issues = issuesOf(machineWith({ licenseStatuses: [valid(daysFromNow(-2))] }));
    expect(issues.join(' ')).toContain('1 repo license(s) due for refresh');
  });

  it('stays quiet when the refresh window is still in the future', () => {
    const issues = issuesOf(machineWith({ licenseStatuses: [valid(daysFromNow(30))] }));
    expect(issues.join(' ')).not.toContain('due for refresh');
  });

  // An absent hint means the server published no window — not that the licence
  // is overdue. Treating missing as overdue would fire on every machine whose
  // licences predate the field.
  it('does not treat a missing refresh hint as overdue', () => {
    const issues = issuesOf(machineWith({ licenseStatuses: [valid()] }));
    expect(issues.join(' ')).not.toContain('due for refresh');
  });

  it('does not treat an unparseable refresh hint as overdue', () => {
    const issues = issuesOf(machineWith({ licenseStatuses: [valid('not-a-date')] }));
    expect(issues.join(' ')).not.toContain('due for refresh');
  });

  it('counts only the licenses actually past the window', () => {
    const issues = issuesOf(
      machineWith({
        licenseStatuses: [valid(daysFromNow(-1)), valid(daysFromNow(-5)), valid(daysFromNow(10))],
      })
    );
    expect(issues.join(' ')).toContain('2 repo license(s) due for refresh');
  });

  // Severity: due-for-refresh is advisory. An estate that is merely due must not
  // report as unhealthy, or the signal becomes indistinguishable from breakage.
  it('does not mark the machine unhealthy for a refresh-due license alone', () => {
    const health = getMachineHealth(machineWith({ licenseStatuses: [valid(daysFromNow(-2))] }));
    expect(health.exitCode).toBe(0);
    expect(health.healthy).toBe(true);
  });

  it('still reports expired separately from due-for-refresh', () => {
    const issues = issuesOf(
      machineWith({
        licenseStatuses: [valid(daysFromNow(-2)), { status: 'expired', runtimeValid: false }],
      })
    );
    const joined = issues.join(' ');
    expect(joined).toContain('due for refresh');
    expect(joined).toContain('expired');
  });
});

describe('backup coverage', () => {
  const cov = (repos: unknown[]) =>
    ({
      vaultStatus: JSON.stringify({
        network: {},
        services: [],
        containers: [],
        system_containers: [],
        block_devices: [],
        repositories: [],
        license_statuses: [],
        backup_coverage: { updated_at: '2026-07-18T00:00:00Z', repos },
      }),
    }) as unknown as Parameters<typeof getMachineHealth>[0];

  // The incident: repos at 10 and 11 days while the job reported success.
  it('reports a repo that has gone stale', () => {
    const issues = getMachineHealth(cov([{ guid: 'big-repo', age_days: 11 }])).issues;
    expect(issues.join(' ')).toContain('not backed up in over');
  });

  // Control: an on-schedule estate must stay silent, or the warning is noise.
  it('stays quiet for recently backed up repos', () => {
    const issues = getMachineHealth(
      cov([
        { guid: 'a', age_days: 1 },
        { guid: 'b', age_days: 6 },
      ])
    ).issues;
    expect(issues.join(' ')).not.toContain('not backed up');
  });

  it('counts only the stale repos', () => {
    const issues = getMachineHealth(
      cov([
        { guid: 'a', age_days: 1 },
        { guid: 'b', age_days: 11 },
        { guid: 'c', age_days: 20 },
      ])
    ).issues;
    expect(issues.join(' ')).toContain('2 repository(ies) not backed up');
  });

  // A never-backed-up repo that was actively skipped is an incident...
  it('reports a never-backed-up repo that was skipped', () => {
    const issues = getMachineHealth(
      cov([{ guid: 'a', age_days: -1, last_skipped_at: '2026-07-18T00:00:00Z' }])
    ).issues;
    expect(issues.join(' ')).toContain('never been backed up');
  });

  // ...but a brand new repo that simply has not had its first run is not.
  it('stays quiet for a new repo with no skip recorded', () => {
    const issues = getMachineHealth(cov([{ guid: 'a', age_days: -1 }])).issues;
    expect(issues.join(' ')).not.toContain('never been backed up');
  });

  // Absent coverage means no backup has ever run — that is not a claim of health,
  // but it must not fabricate an issue either.
  it('says nothing when no backup state exists', () => {
    const issues = issuesOf(machineWith({}));
    expect(issues.join(' ')).not.toContain('backed up');
  });
});
