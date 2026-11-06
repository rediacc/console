import { describe, expect, it } from 'vitest';
import {
  FINDING_TABLE,
  type HealthFinding,
  isKnownFindingCode,
  operatorCommand,
  severityExitCode,
  withFix,
} from '../findings.js';
import { getMachineHealth } from '../parsing-health.js';

type Machine = Parameters<typeof getMachineHealth>[0];

function machine(listing: Record<string, unknown>): Machine {
  return {
    machineName: 'm1',
    vaultStatus: JSON.stringify({
      network: {},
      services: { services: [] },
      containers: { containers: [] },
      system_containers: [],
      block_devices: [],
      repositories: [],
      license_statuses: [],
      ...listing,
    }),
  } as unknown as Machine;
}

const lic = (status: string, n: number, extra: Record<string, unknown> = {}) =>
  Array.from({ length: n }, () => ({ status, runtimeValid: status === 'valid', ...extra }));

/** Fixtures that between them trigger every issue producer in parsing-health.ts. */
const FIXTURES: Record<string, Machine> = {
  everything: machine({
    system: {
      memory: { use_percent: '92%' },
      disk: { use_percent: '90%' },
      datastore: { use_percent: '86%' },
      uptime: '1d',
    },
    containers: {
      containers: [
        {
          name: 'web',
          repository: 'g1',
          state: 'running',
          status: 'Up 2 hours (unhealthy)',
          health: { status: 'unhealthy', failing_streak: 6 },
        },
        {
          name: 'job',
          repository: 'g1',
          state: 'restarting',
          status: 'Restarting (1) 5 seconds ago',
        },
      ],
    },
    services: {
      services: [
        {
          name: 'rediacc-docker-5',
          service_name: 'rediacc-docker-5.service',
          active_state: 'failed',
          sub_state: 'failed',
          restart_count: 0,
          repository: 'g1',
        },
        {
          name: 'flappy',
          service_name: 'flappy.service',
          active_state: 'active',
          sub_state: 'auto-restart',
          restart_count: 7,
          repository: '',
        },
      ],
    },
    block_devices: [{ name: 'sda', smart_health: 'FAILED', temperature: 70 }],
    repositories: [
      { name: 'g1', repo_name: 'mail', mounted: false, autostart: true, network_id: 5 },
      {
        name: 'g2',
        repo_name: 'demo',
        mounted: true,
        autostart: true,
        network_id: 6,
        disk_space: { use_percent: '99%' },
      },
    ],
    backup_coverage: {
      repos: [{ age_days: 12 }, { age_days: -1, last_skipped_at: '2026-11-01T00:00:00Z' }],
    },
    license_statuses: [
      ...lic('valid', 1, { refreshRecommendedAt: '2020-01-01T00:00:00Z' }),
      ...lic('expired', 1),
      ...lic('machine_mismatch', 1),
      ...lic('invalid_signature', 1),
      ...lic('missing', 1),
    ],
  }),
  allLicensesMissing: machine({ license_statuses: lic('missing', 2) }),
  mildStreak: machine({
    containers: {
      containers: [
        {
          name: 'api',
          repository: 'g3',
          state: 'running',
          status: 'Up',
          health: { status: 'starting', failing_streak: 3 },
        },
      ],
    },
  }),
  noStatus: { machineName: 'm1', vaultStatus: '' } as unknown as Machine,
};

/** Each issue text a producer writes, and the code its finding must carry. A new producer with no row fails below. */
const PRODUCERS: [RegExp, string][] = [
  [/^No vault status data$/, 'machine.status.unavailable'],
  [/^Memory usage (high|critical)/, 'memory.usage.high'],
  [/^Disk usage (high|critical)/, 'disk.usage.high'],
  [/^Datastore usage (high|critical)/, 'datastore.usage.high'],
  [/^Repository \S+ disk usage (high|critical)/, 'repo.disk.high'],
  [/unhealthy container\(s\)$/, 'container.unhealthy'],
  [/container\(s\) in restart loop$/, 'container.restart-loop'],
  [/^Container health check failing streak/, 'container.health-streak'],
  [/failed service\(s\)$/, 'service.failed'],
  [/service\(s\) in restart loop$/, 'service.restart-loop'],
  [/SMART failure$/, 'storage.smart.failing'],
  [/^Storage temperature high/, 'storage.temperature.high'],
  [/repository\(ies\) not mounted$/, 'repo.unmounted'],
  [/not backed up in over/, 'backup.stale'],
  [/have never been backed up$/, 'backup.never'],
  [/due for refresh$/, 'license.refresh-due'],
  [/license\(s\) expired$/, 'license.expired'],
  [/machine ID mismatch$/, 'license.machine-mismatch'],
  [/invalid signatures$/, 'license.invalid-signature'],
  [/license\(s\) missing$|^All repo licenses are missing$/, 'license.missing'],
];

describe('findings table (X1)', () => {
  it('gives every issue a coded finding whose code is in the table', () => {
    const raised = new Set<string>();
    for (const [name, m] of Object.entries(FIXTURES)) {
      const health = getMachineHealth(m);
      for (const f of health.findings) {
        expect(isKnownFindingCode(f.code), `${name}: ${f.code} is not in FINDING_TABLE`).toBe(true);
        expect(f.subject, `${name}: ${f.code} has no subject`).not.toBe('');
        raised.add(f.code);
      }
      for (const text of health.issues) {
        const row = PRODUCERS.find(([re]) => re.test(text));
        expect(row, `${name}: issue "${text}" has no producer row, so no code`).toBeDefined();
        const code = (row as [RegExp, string])[1];
        expect(
          health.findings.some((f) => f.code === code),
          `${name}: issue "${text}" raised no ${code} finding`
        ).toBe(true);
      }
    }
    expect([...raised].sort()).toEqual([...new Set(PRODUCERS.map(([, c]) => c))].sort());
  });

  it('keeps the issue strings exactly as before', () => {
    const health = getMachineHealth(FIXTURES.everything);
    expect(health.issues).toContain('1 repository(ies) not backed up in over 10 days');
    expect(health.issues).toContain('1 container(s) in restart loop');
    expect(health.issues).toContain('Datastore usage high: 86%');
  });

  it('never raises the exit code above what the issues alone raised', () => {
    for (const m of Object.values(FIXTURES)) {
      const health = getMachineHealth(m);
      const worst = Math.max(0, ...health.findings.map((f) => severityExitCode(f.severity)));
      expect(worst).toBe(health.exitCode);
    }
  });

  it('names each container and repository with what its fix acts on', () => {
    const findings = getMachineHealth(FIXTURES.everything).findings;
    const loop = findings.find((f) => f.code === 'container.restart-loop') as HealthFinding;
    expect(loop).toMatchObject({
      subject: 'job',
      severity: 'critical',
      target: { container: 'job', repository: 'g1' },
    });
    expect(loop.fix).toEqual({
      action: 'restart-container',
      class: 'auto-safe',
      window_only: false,
    });
    const disk = findings.find((f) => f.code === 'repo.disk.high') as HealthFinding;
    expect(disk).toMatchObject({
      subject: 'demo',
      severity: 'error',
      target: { repository: 'g2', networkId: 6 },
    });
    expect(disk.fix?.action).toBe('trim-prune');
  });

  it('carries the rows of the hostinger table with their classes', () => {
    const fixOf = (code: string) =>
      withFix({ code, severity: 'warning', subject: 's', detail: '' }).fix;
    expect(fixOf('datastore.usage.high')).toEqual({
      action: 'trim-prune',
      class: 'auto-safe',
      window_only: false,
    });
    expect(fixOf('repo.disk.high')?.class).toBe('auto-safe');
    expect(fixOf('renet.binary.replaced')).toEqual({
      action: 'restart-repo-supervisors',
      class: 'auto-safe',
      window_only: true,
    });
    expect(fixOf('cert.expiry.near')).toEqual({
      action: 'restart-traefik',
      class: 'auto-safe',
      window_only: false,
    });
    expect(fixOf('acme.challenge.cname-shared')).toEqual({
      action: 'acme-anchor',
      class: 'auto-safe',
      window_only: false,
    });
    expect(fixOf('container.restart-loop')?.class).toBe('auto-safe');
    expect(fixOf('backup.coverage.absent')?.class).toBe('operator-only');
    expect(fixOf('ops.targets.drift')?.class).toBe('operator-only');
    expect(fixOf('storage.smart.failing')).toBeUndefined();
  });

  it('gives every operator-only fix an exact command', () => {
    for (const [code, row] of Object.entries(FINDING_TABLE)) {
      const fix = (row as { fix?: { class: string } }).fix;
      if (fix?.class !== 'operator-only') continue;
      const cmd = operatorCommand(
        withFix({ code, severity: 'warning', subject: 'r1', detail: '' }),
        'm1'
      );
      expect(cmd, code).toMatch(/^(rdc |PYTHONPATH=)/);
    }
  });
});
