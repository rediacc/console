/**
 * Scheduled backups to a hosted-service (chunk-store) destination.
 *
 * THE DEFECT THESE CATCH, which shipped and was silent: `buildBackupCommands`
 * looked every destination up in a per-destination argument map and did `continue` when it
 * found nothing. A hosted-service destination has no remote by
 * construction, so it was SKIPPED, the operator declared a chunk-store
 * destination, deployed the schedule, and got a timer that backed up nothing.
 * No error, no unit, no warning: the failure was invisible until someone went
 * looking for backups that did not exist.
 *
 * The remote-sync emission was REMOVED on 2026-08-15, so the chunk store is
 * now the only destination kind this generator can render. That makes the
 * silent-skip failure mode reachable from the other side, a config still
 * naming a `storage` destination, so the refusal tests below pin that such a
 * destination throws rather than producing a unit with no ExecStart at all.
 */

import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_DATASTORE_PATH,
} from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../../types/index.js';
import {
  buildAdhocSystemdRun,
  buildBackupCommands,
  generateServiceUnit,
} from '../backup/backup-schedule-unit-generator.js';

const RENET = '/usr/bin/renet';
const DATASTORE = WK_DATASTORE_PATH;

const hosted = (name = 'chunks'): BackupStrategyDestination => ({
  name,
  kind: 'hosted-service',
});

const storage = (name = 'offsite'): BackupStrategyDestination =>
  ({
    name,
    kind: 'storage',
    storage: 'onedrive',
  }) as unknown as BackupStrategyDestination;

/**
 * A destination as it appears in the operator's real config: no `kind` at all.
 * The schema defaults it to `storage` on parse, but the generator must not rely
 * on having been handed a parsed value, so this one is deliberately built
 * outside the type.
 */
const kindless = (name = 'legacy'): BackupStrategyDestination => {
  const raw: Record<string, unknown> = { name, storage: 'microsoft' };
  return raw as BackupStrategyDestination;
};

const strategy = (over: Partial<BackupStrategyConfig> = {}): BackupStrategyConfig => {
  const base: BackupStrategyConfig = { destinations: [], schedule: '0 * * * *' };
  return { ...base, ...over };
};

describe('scheduled backups to the chunk store', () => {
  it('emits a snapshot command instead of silently skipping the destination', () => {
    const { commands } = buildBackupCommands(strategy(), [hosted()], DATASTORE, RENET);
    expect(commands).toHaveLength(1);
    expect(commands[0]).toBe(`${RENET} backup snapshot --datastore ${DATASTORE} --parallelism 2`);
  });

  it('carries NO credentials into the unit or its EnvironmentFile', () => {
    // The point of the destination kind: the machine authenticates with its signed licence blob and the server hands back a short-lived grant.
    const { commands, envVars } = buildBackupCommands(strategy(), [hosted()], DATASTORE, RENET);
    expect(envVars).toEqual({});
    expect(commands[0]).not.toMatch(/--setenv|--storage-param/);
  });

  it('refuses to render an include or exclude list that was not resolved to GUIDs', () => {
    // renet takes GUIDs only. A strategy that names repositories goes through strategyUnitSpecs (backup-schedule-targets.ts); rendering it without that resolution would put names on argv, which renet refuses at run time inside the timer.
    for (const over of [{ include: ['mail'] }, { exclude: ['scratch'] }]) {
      expect(() => buildBackupCommands(strategy(over), [hosted()], DATASTORE, RENET)).toThrow(
        /resolve them to GUIDs/
      );
    }
  });

  it('emits --repo <guid> for an include scope and --exclude-repo <guid> otherwise', () => {
    const g1 = '11111111-1111-4111-8111-111111111111';
    const g2 = '22222222-2222-4222-8222-222222222222';
    const inc = buildBackupCommands(strategy(), [hosted()], DATASTORE, RENET, {
      include: [g1, g2],
      exclude: [],
    });
    expect(inc.commands[0]).toBe(
      `${RENET} backup snapshot --datastore ${DATASTORE} --repo ${g1} --repo ${g2} --parallelism 2`
    );
    const exc = buildBackupCommands(strategy(), [hosted()], DATASTORE, RENET, {
      exclude: [g1],
    });
    expect(exc.commands[0]).toBe(
      `${RENET} backup snapshot --datastore ${DATASTORE} --exclude-repo ${g1} --parallelism 2`
    );
  });

  it('keeps the strategy bandwidth limit on argv, converted to bytes/second', () => {
    // The schema declares bandwidthLimit as a unit-suffixed string ('6M'); the unit carries bytes/second so it never depends on renet re-parsing a suffix. M is DECIMAL: 6M = 6,000,000 B/s.
    const { commands } = buildBackupCommands(
      strategy({ bandwidthLimit: '6M' }),
      [hosted()],
      DATASTORE,
      RENET
    );
    expect(commands[0]).toContain('--bwlimit 6000000');
    expect(commands[0]).not.toContain('--bwlimit 6M');
  });

  it('carries the hostinger cap (100Mbps) and the modest parallelism on every strategy run', () => {
    // Operator order 2026-10-29: 100 Mbit/s, never unlimited, modest concurrency.
    const { commands } = buildBackupCommands(
      strategy({ bandwidthLimit: '100Mbps' }),
      [hosted()],
      DATASTORE,
      RENET
    );
    expect(commands[0]).toContain('--bwlimit 12500000');
    expect(commands[0]).toContain('--parallelism 2');
  });

  it("applies a destination's own cap, the tightest one winning (it was silently ignored)", () => {
    // `backup strategy set s --destination d --bwlimit 6M` stores the cap on the destination; the generator read only the strategy-level field, so no unit ever applied it.
    const { commands } = buildBackupCommands(
      strategy({ bandwidthLimit: '100Mbps' }),
      [hosted('a'), { ...hosted('b'), bandwidthLimit: '6M' }],
      DATASTORE,
      RENET
    );
    expect(commands[0]).toContain('--bwlimit 6000000');
    expect(commands[0]).not.toContain('--bwlimit 12500000');
  });

  it('runs the scheduled unit and the ad-hoc strategy run at low CPU and I/O priority', () => {
    const { serviceContent } = generateServiceUnit(
      's',
      strategy({ bandwidthLimit: '100Mbps' }),
      [hosted()],
      DATASTORE,
      RENET
    );
    expect(serviceContent).toContain('\nNice=10\n');
    expect(serviceContent).toContain('\nIOSchedulingClass=best-effort\n');
    expect(serviceContent).toContain('\nIOSchedulingPriority=7\n');
    expect(serviceContent).toContain('--bwlimit 12500000 --parallelism 2');

    const { commands } = buildBackupCommands(
      strategy({ bandwidthLimit: '100Mbps' }),
      [hosted()],
      DATASTORE,
      RENET
    );
    const adhoc = buildAdhocSystemdRun('rediacc-backup-s-adhoc', commands);
    expect(adhoc).toMatch(/^sudo systemd-run --unit=rediacc-backup-s-adhoc --remain-after-exit /);
    expect(adhoc).toContain(
      '-p Nice=10 -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7'
    );
    expect(adhoc).toContain('--bwlimit 12500000 --parallelism 2');
  });

  it('emits --read-bwlimit in bytes/second in the unit and the ad-hoc run only when the strategy sets it', () => {
    const s = strategy({ readBandwidthLimit: '50M' });
    const { serviceContent } = generateServiceUnit('s', s, [hosted()], DATASTORE, RENET);
    expect(serviceContent).toContain('--parallelism 2 --read-bwlimit 50000000');
    const { commands } = buildBackupCommands(s, [hosted()], DATASTORE, RENET);
    expect(buildAdhocSystemdRun('rediacc-backup-s-adhoc', commands)).toContain(
      '--read-bwlimit 50000000'
    );
  });

  it('keeps a read cap of 0 as --read-bwlimit 0 (unlimited), never dropping it to the verb default', () => {
    const { commands } = buildBackupCommands(
      strategy({ readBandwidthLimit: '0' }),
      [hosted()],
      DATASTORE,
      RENET
    );
    expect(commands[0]).toContain('--read-bwlimit 0');
  });

  it('emits no --read-bwlimit without one, and never emits --hash-parallelism', () => {
    for (const s of [strategy(), strategy({ readBandwidthLimit: '50M', bandwidthLimit: '6M' })]) {
      const { commands } = buildBackupCommands(s, [hosted()], DATASTORE, RENET);
      expect(commands[0]).not.toContain('--hash-parallelism');
      if (!s.readBandwidthLimit) expect(commands[0]).not.toContain('--read-bwlimit');
    }
  });

  it('REFUSES an unparseable read cap rather than emitting an unlimited read', () => {
    expect(() =>
      buildBackupCommands(strategy({ readBandwidthLimit: 'fast' }), [hosted()], DATASTORE, RENET)
    ).toThrow(/Read bandwidth limit "fast"/);
  });

  it('passes a plain byte count straight through', () => {
    const { commands } = buildBackupCommands(
      strategy({ bandwidthLimit: '1048576' }),
      [hosted()],
      DATASTORE,
      RENET
    );
    expect(commands[0]).toContain('--bwlimit 1048576');
  });

  it('omits --bwlimit entirely when the strategy sets no limit', () => {
    const { commands } = buildBackupCommands(strategy(), [hosted()], DATASTORE, RENET);
    expect(commands[0]).not.toContain('--bwlimit');
  });

  it('REFUSES a bandwidth limit it cannot convert rather than dropping the cap', () => {
    // Dropping it would silently lift a cap the operator set deliberately, an unmetered backup saturating the uplink, with nothing in the logs.
    expect(() =>
      buildBackupCommands(strategy({ bandwidthLimit: 'fast' }), [hosted()], DATASTORE, RENET)
    ).toThrow(/Bandwidth limit "fast" cannot be converted/);
  });

  it('takes ONE snapshot per run whatever the number of destinations (G3)', () => {
    // A command per destination uploaded the same cells twice and committed two manifests for one point in time. The renet command carries nothing from the destination, so a second one could only ever repeat the first.
    const { commands } = buildBackupCommands(
      strategy(),
      [hosted('chunks-a'), hosted('chunks-b')],
      DATASTORE,
      RENET
    );
    expect(commands).toHaveLength(1);
  });

  it('refuses destinations on two different endpoints, which one snapshot cannot serve', () => {
    const a: BackupStrategyDestination = { ...hosted('a'), endpoint: WK_ACCOUNT_DEFAULT_ORIGIN };
    const b: BackupStrategyDestination = { ...hosted('b'), endpoint: 'https://s3.example.com' };
    expect(() => buildBackupCommands(strategy(), [a, b], DATASTORE, RENET)).toThrow(
      /2 different endpoints/
    );
  });
});

describe('the refusal that replaced the retired path', () => {
  // The silent-emit case is the exact defect the hosted-service branch was added to fix. Removing it re-opened it from the other direction: a strategy that still names a `storage` destination would otherwise render a unit with no ExecStart at all, a timer that backs up nothing, quietly.
  it('THROWS on a `storage` destination rather than emitting nothing', () => {
    const call = () => buildBackupCommands(strategy(), [storage('offsite')], DATASTORE, RENET);
    expect(call).toThrow(/Backup destination "offsite"/);
    expect(call).toThrow(/kind "storage"/);
    expect(call).toThrow(/Only `hosted-service` destinations can be scheduled/);
    expect(call).toThrow(/Refusing to generate a unit that would back up nothing\./);
  });

  it('THROWS on a destination with no `kind` at all, naming it as storage', () => {
    // How the operator's real config looks: `kind` was added later and defaults to `storage` on parse, so an unparsed value arrives here as undefined.
    const call = () =>
      buildBackupCommands(strategy(), [kindless('onedrive-hourly')], DATASTORE, RENET);
    expect(call).toThrow(/Backup destination "onedrive-hourly"/);
    expect(call).toThrow(/kind "storage"/);
    expect(call).toThrow(/Refusing to generate a unit that would back up nothing\./);
  });

  it('refuses the whole strategy, not just the retired half, when kinds are mixed', () => {
    // Partial emission would be the worst outcome: a unit that looks deployed and silently drops one of the two declared destinations.
    expect(() =>
      buildBackupCommands(strategy(), [storage('offsite'), hosted()], DATASTORE, RENET)
    ).toThrow(/Backup destination "offsite"/);
  });

  it('names the FIRST offending destination when several are unusable', () => {
    expect(() =>
      buildBackupCommands(strategy(), [storage('dest1'), storage('dest2')], DATASTORE, RENET)
    ).toThrow(/Backup destination "dest1"/);
  });
});

describe('the CPU ceiling reaches the scheduled unit and the ad-hoc run', () => {
  const unit = (cpuLimit: number | undefined, cpuCount: number | undefined) =>
    generateServiceUnit(
      's',
      strategy({ cpuLimit }),
      [hosted()],
      DATASTORE,
      RENET,
      undefined,
      cpuCount
    ).serviceContent;

  it('writes CPUQuota = percent x the machine core count, default 50 percent', () => {
    expect(unit(undefined, 8)).toContain('\nCPUQuota=400%\n');
    expect(unit(25, 8)).toContain('\nCPUQuota=200%\n');
    expect(unit(50, 2)).toContain('\nCPUQuota=100%\n');
  });

  it('tells the snapshot record what bound it', () => {
    const { commands } = buildBackupCommands(
      strategy({ cpuLimit: 25 }),
      [hosted()],
      DATASTORE,
      RENET,
      undefined,
      8
    );
    expect(commands[0]).toContain('--cpu-limit 25 --cpu-quota 200%');
  });

  it('writes no quota for 100 (no ceiling), and none without a resolved core count', () => {
    expect(unit(100, 8)).not.toContain('CPUQuota');
    expect(unit(undefined, undefined)).not.toContain('CPUQuota');
    const { commands } = buildBackupCommands(strategy({}), [hosted()], DATASTORE, RENET);
    expect(commands[0]).not.toContain('--cpu-limit');
  });

  it('refuses an out-of-range ceiling instead of rendering a different quota', () => {
    expect(() => unit(0, 8)).toThrow();
    expect(() => unit(101, 8)).toThrow();
  });

  it('puts the quota on the ad-hoc systemd-run, resolved by the machine shell', () => {
    const adhoc = buildAdhocSystemdRun('u', ['renet backup snapshot']);
    expect(adhoc).toContain('-p CPUQuota=$(( $(nproc) * 50 ))%');
    expect(buildAdhocSystemdRun('u', ['x'], 20)).toContain('-p CPUQuota=$(( $(nproc) * 20 ))%');
    expect(buildAdhocSystemdRun('u', ['x'], 100)).not.toContain('CPUQuota');
    expect(() => buildAdhocSystemdRun('u', ['x'], 0)).toThrow();
  });
});

describe('the machine core count behind the quota', () => {
  const sftpAnswering = (stdout: string, code = 0) =>
    ({
      execStreaming: (
        command: string,
        h: { onStdout: (d: string) => void; onStderr: (d: string) => void }
      ) => {
        expect(command).toBe('nproc');
        h.onStdout(stdout);
        return Promise.resolve(code);
      },
    }) as never;

  it('reads nproc on the machine', async () => {
    const { resolveMachineCpuCount } = await import('../backup/backup-schedule-reconcile.js');
    expect(await resolveMachineCpuCount(sftpAnswering('8\n'))).toBe(8);
  });

  it.each([
    ['', 0],
    ['many', 0],
    ['0', 0],
    ['8', 127],
  ])('refuses to guess from %j (exit %i)', async (out, code) => {
    const { resolveMachineCpuCount } = await import('../backup/backup-schedule-reconcile.js');
    await expect(resolveMachineCpuCount(sftpAnswering(out, code))).rejects.toThrow(/CPU count/);
  });
});
