/**
 * Scheduled backups to a hosted-service (chunk-store) destination.
 *
 * THE DEFECT THESE CATCH, which shipped and was silent: `buildBackupCommands`
 * looked every destination up in `rcloneArgsByDest` and did `continue` when it
 * found nothing. A hosted-service destination has no rclone remote by
 * construction, so it was SKIPPED — the operator declared a chunk-store
 * destination, deployed the schedule, and got a timer that backed up nothing.
 * No error, no unit, no warning: the failure was invisible until someone went
 * looking for backups that did not exist.
 *
 * The rclone/OneDrive emission was REMOVED on 2026-08-15, so the chunk store is
 * now the only destination kind this generator can render. That makes the
 * silent-skip failure mode reachable from the other side — a config still
 * naming a `storage` destination — so the refusal tests below pin that such a
 * destination throws rather than producing a unit with no ExecStart at all.
 */

import { describe, expect, it } from 'vitest';
import { buildBackupCommands } from '../backup/backup-schedule-unit-generator.js';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../../types/index.js';

const RENET = '/usr/bin/renet';
const DATASTORE = '/mnt/rediacc';

const hosted = (name = 'chunks'): BackupStrategyDestination => ({
  name,
  kind: 'hosted-service',
});

const storage = (name = 'offsite'): BackupStrategyDestination => ({
  name,
  kind: 'storage',
  storage: 'onedrive',
});

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
    expect(commands[0]).toBe(`${RENET} backup snapshot --datastore ${DATASTORE}`);
  });

  it('carries NO credentials into the unit or its EnvironmentFile', () => {
    // The point of the destination kind: the machine authenticates with its
    // signed licence blob and the server hands back a short-lived grant.
    const { commands, envVars } = buildBackupCommands(strategy(), [hosted()], DATASTORE, RENET);
    expect(envVars).toEqual({});
    expect(commands[0]).not.toMatch(/--rclone-param|--setenv|RCLONE_/);
  });

  it('scopes to the strategy include list, one --repo per entry', () => {
    const { commands } = buildBackupCommands(
      strategy({ include: ['mail', 'gitlab'] }),
      [hosted()],
      DATASTORE,
      RENET
    );
    expect(commands[0]).toContain('--repo mail');
    expect(commands[0]).toContain('--repo gitlab');
  });

  it('REFUSES an exclude list rather than backing up what was excluded', () => {
    // `backup snapshot` has no exclude flag. Dropping the list would back up
    // repositories the operator asked to leave out — the same silent
    // wrong-scope failure this whole file exists to close.
    expect(() =>
      buildBackupCommands(strategy({ exclude: ['scratch'] }), [hosted()], DATASTORE, RENET)
    ).toThrow(/exclude/i);
  });

  it('keeps the strategy bandwidth limit on argv, converted to bytes/second', () => {
    // The schema declares bandwidthLimit as an rclone-style string ('6M') but
    // `backup snapshot --bwlimit` is an Int64 in bytes/second, so passing the
    // string through would fail at cobra's flag parse — inside the timer, at
    // run time, long after the deploy reported success.
    const { commands } = buildBackupCommands(
      strategy({ bandwidthLimit: '6M' }),
      [hosted()],
      DATASTORE,
      RENET
    );
    expect(commands[0]).toContain('--bwlimit 6291456');
    expect(commands[0]).not.toContain('--bwlimit 6M');
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
    // Dropping it would silently lift a cap the operator set deliberately —
    // an unmetered backup saturating the uplink, with nothing in the logs.
    expect(() =>
      buildBackupCommands(strategy({ bandwidthLimit: 'fast' }), [hosted()], DATASTORE, RENET)
    ).toThrow(/bandwidthLimit "fast" is not a size/);
  });

  it('each hosted destination produces its own command', () => {
    // Without this, the single-destination tests above would be satisfied by a
    // build that emits exactly one command no matter how many destinations the
    // strategy declares. The two commands are byte-identical because the
    // chunk-store command is a function of the strategy and datastore alone —
    // nothing in the destination (name, endpoint) reaches argv today.
    const { commands } = buildBackupCommands(
      strategy(),
      [hosted('chunks-a'), hosted('chunks-b')],
      DATASTORE,
      RENET
    );
    expect(commands).toHaveLength(2);
    expect(commands[0]).toBe(commands[1]);
  });
});

describe('the refusal that replaced the rclone path', () => {
  // The silent-emit case is the exact defect the hosted-service branch was
  // added to fix. Removing rclone re-opened it from the other direction: a
  // strategy that still names a `storage` destination would otherwise render a
  // unit with no ExecStart at all — a timer that backs up nothing, quietly.
  it('THROWS on a `storage` destination rather than emitting nothing', () => {
    const call = () => buildBackupCommands(strategy(), [storage('offsite')], DATASTORE, RENET);
    expect(call).toThrow(/Backup destination "offsite"/);
    expect(call).toThrow(/kind "storage"/);
    expect(call).toThrow(/rclone\/OneDrive path was removed on 2026-08-15/);
    expect(call).toThrow(/Refusing to generate a unit that would back up nothing\./);
  });

  it('THROWS on a destination with no `kind` at all, naming it as storage', () => {
    // How the operator's real config looks: `kind` was added later and defaults
    // to `storage` on parse, so an unparsed value arrives here as undefined.
    const call = () =>
      buildBackupCommands(strategy(), [kindless('onedrive-hourly')], DATASTORE, RENET);
    expect(call).toThrow(/Backup destination "onedrive-hourly"/);
    expect(call).toThrow(/kind "storage"/);
    expect(call).toThrow(/Refusing to generate a unit that would back up nothing\./);
  });

  it('refuses the whole strategy, not just the rclone half, when kinds are mixed', () => {
    // Partial emission would be the worst outcome: a unit that looks deployed
    // and silently drops one of the two declared destinations.
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
