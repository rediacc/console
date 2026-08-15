import { describe, expect, it } from 'vitest';

import {
  buildBackupCommands,
  generateServiceUnit,
} from '../../services/backup/backup-schedule-unit-generator.js';
import type { BackupStrategyDestination } from '../../types/index.js';
import { buildDestination, buildStrategyUpdate, parseRepoFilter } from '../backup-strategy.js';

describe('parseRepoFilter', () => {
  it('parses a comma-separated list, trimming and dropping empties', () => {
    expect(parseRepoFilter('a, b ,c')).toEqual(['a', 'b', 'c']);
    expect(parseRepoFilter('a,,b,')).toEqual(['a', 'b']);
  });

  it('treats empty / whitespace / "none" as CLEAR (undefined)', () => {
    expect(parseRepoFilter('')).toBeUndefined();
    expect(parseRepoFilter('   ')).toBeUndefined();
    expect(parseRepoFilter('none')).toBeUndefined();
    expect(parseRepoFilter('NONE')).toBeUndefined();
    // only separators -> nothing left -> clear
    expect(parseRepoFilter(',, ,')).toBeUndefined();
  });
});

describe('buildStrategyUpdate include/exclude', () => {
  it('sets exclude and clears include (mutually exclusive)', () => {
    const u = buildStrategyUpdate({ exclude: 'demo-stackoverflow' }, undefined);
    expect(u.exclude).toEqual(['demo-stackoverflow']);
    expect(u.include).toBeUndefined();
  });

  it('sets include and clears exclude', () => {
    const u = buildStrategyUpdate({ include: 'mail,gitlab' }, undefined);
    expect(u.include).toEqual(['mail', 'gitlab']);
    expect(u.exclude).toBeUndefined();
  });

  it('clears the filter when exclude is empty / none (both undefined)', () => {
    const cleared = buildStrategyUpdate({ exclude: '' }, undefined);
    expect(cleared.exclude).toBeUndefined();
    expect(cleared.include).toBeUndefined();

    const none = buildStrategyUpdate({ exclude: 'none' }, undefined);
    expect(none.exclude).toBeUndefined();
    expect(none.include).toBeUndefined();
  });

  it('accepts both modes now that the scheduled verb can express cold', () => {
    // The inverse of what this asserted until 2026-08-15. `--mode cold` was
    // refused here because scheduling it would have promised a container
    // quiesce that `backup snapshot` could not perform; the verb grew --cold,
    // so the refusal went with it. The schema's enum is exactly hot|cold, so
    // there is no third value left for a guard to catch — one that survived
    // would be a check that can never fire.
    expect(buildStrategyUpdate({ mode: 'cold' }, undefined).mode).toBe('cold');
    expect(buildStrategyUpdate({ mode: 'hot' }, undefined).mode).toBe('hot');
  });

  it('leaves a stored mode alone when --mode is not passed', () => {
    // Editing the cron of an existing strategy must not rewrite its mode.
    expect(buildStrategyUpdate({ cron: '0 4 * * *' }, undefined).mode).toBeUndefined();
  });

  it('passes through other fields and leaves filters untouched when not provided', () => {
    const u = buildStrategyUpdate({ cron: '0 * * * *', mode: 'hot', bwlimit: '6M' }, true);
    expect(u.schedule).toBe('0 * * * *');
    expect(u.mode).toBe('hot');
    expect(u.bandwidthLimit).toBe('6M');
    expect(u.enabled).toBe(true);
    expect('include' in u).toBe(false);
    expect('exclude' in u).toBe(false);
  });
});

/**
 * THE DEFECT THESE CLOSE: there was no supported way to schedule a backup.
 *
 * `backup strategy set` could only make `storage` (rclone) destinations — it
 * hard-required `--storage` — and on 2026-08-15 the unit generator stopped
 * being able to render that kind at all. Every documented route from
 * "configure a strategy" to "deploy a timer" therefore ended in an exception,
 * and only a hand-edited config JSON could produce a working strategy.
 *
 * The crossing test below is the point of this file: ONE object made by the
 * create path is handed to the REAL unit generator. Every defect in this stack
 * so far came from each side being checked against its own fake while the two
 * agreed on nothing, so a test that asserts the shape against a locally
 * written expectation would prove exactly nothing here.
 */
describe('creating a destination an operator can actually schedule', () => {
  it('defaults to a chunk-store destination when --storage is absent', () => {
    const dest = buildDestination({ destinationName: 'chunks' }, undefined);
    expect(dest.kind).toBe('hosted-service');
    expect(dest.name).toBe('chunks');
    expect(dest).not.toHaveProperty('storage');
  });

  it('and the unit generator emits a real snapshot command for that object', () => {
    // The crossing: create path -> generator, no fake in between. Before the
    // fix this could not even be written, because the create path threw.
    const dest = buildDestination({ destinationName: 'chunks' }, undefined);
    const { commands, envVars } = buildBackupCommands(
      { schedule: '0 * * * *', destinations: [dest] },
      [dest],
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(commands).toEqual(['/usr/bin/renet backup snapshot --datastore /mnt/rediacc']);
    // No credential reaches the unit: the machine authenticates with its
    // licence blob and the server hands back a short-lived grant.
    expect(envVars).toEqual({});
  });

  it('and a whole systemd unit comes out of it, ExecStart and all', () => {
    // One step further than the command list: what `rdc backup schedule` will
    // actually write to the machine, built from the object the create path
    // produced. This is the end-to-end claim the defect made impossible.
    const dest = buildDestination({ destinationName: 'chunks' }, undefined);
    const { serviceContent } = generateServiceUnit(
      'hourly-chunks',
      { schedule: '0 * * * *', destinations: [dest] },
      [dest],
      '/mnt/rediacc',
      '/usr/bin/renet'
    );
    expect(serviceContent).toContain(
      'ExecStart=/usr/bin/renet backup snapshot --datastore /mnt/rediacc'
    );
    expect(serviceContent).not.toContain('EnvironmentFile=');
  });

  it('still makes a storage destination when --storage is given', () => {
    // `--storage` keeps working for as long as storage destinations are legal
    // to hold on disk. It is now also the explicit opt-in to the legacy kind.
    const dest = buildDestination({ destinationName: 'offsite', storage: 'onedrive' }, undefined);
    expect(dest.kind).toBe('storage');
    expect(dest).toMatchObject({ storage: 'onedrive' });
  });

  it('does NOT convert an existing storage destination just because --storage was omitted', () => {
    // `set s --destination onedrive-hourly --disable` against the operator's
    // live rclone destination must edit it in place. Flipping its kind here
    // would orphan every backup already behind it.
    const existing: BackupStrategyDestination = {
      kind: 'storage',
      name: 'onedrive-hourly',
      storage: 'microsoft',
      folder: 'hot',
    };
    const dest = buildDestination({ destinationName: 'onedrive-hourly', enabled: false }, existing);
    expect(dest.kind).toBe('storage');
    expect(dest).toMatchObject({ storage: 'microsoft', folder: 'hot', enabled: false });
  });

  it('treats a destination with no `kind` at all as storage, not as a chunk store', () => {
    // How the operator's real config reads: `kind` was added later. Guessing
    // hosted-service for it would silently repoint an rclone destination.
    const raw: Record<string, unknown> = { name: 'onedrive-hourly', storage: 'microsoft' };
    const legacy = raw as BackupStrategyDestination;
    const dest = buildDestination({ destinationName: 'onedrive-hourly' }, legacy);
    expect(dest.kind).toBe('storage');
    expect(dest).toMatchObject({ storage: 'microsoft' });
  });

  it('keeps an existing chunk-store destination on its own kind', () => {
    const existing: BackupStrategyDestination = { kind: 'hosted-service', name: 'chunks' };
    const dest = buildDestination({ destinationName: 'chunks', bwlimit: '6M' }, existing);
    expect(dest.kind).toBe('hosted-service');
    expect(dest).toMatchObject({ bandwidthLimit: '6M' });
  });

  it('omits keys the flags did not set, so the stored value survives the merge', () => {
    // addBackupDestination merges with `{...existing, ...dest}`, and zod KEEPS
    // an optional key passed as an explicit undefined. Before this, setting a
    // bandwidth limit silently re-ENABLED a destination the operator had
    // disabled, and any set without --bwlimit dropped the cap.
    const dest = buildDestination({ destinationName: 'chunks', bwlimit: '6M' }, undefined);
    expect(Object.hasOwn(dest, 'enabled')).toBe(false);
    const merged = { ...{ name: 'chunks', kind: 'hosted-service', enabled: false }, ...dest };
    expect(merged.enabled).toBe(false);
  });

  it('REFUSES --folder on a chunk-store destination rather than dropping it', () => {
    // The server names every key in the chunk store, so a folder has nothing to
    // mean. Dropping it would put backups somewhere other than where the
    // operator said.
    expect(() => buildDestination({ destinationName: 'chunks', folder: 'hot' }, undefined)).toThrow(
      /--storage/
    );
  });

  it('accepts --folder together with --storage', () => {
    const dest = buildDestination(
      { destinationName: 'offsite', storage: 'onedrive', folder: 'cold' },
      undefined
    );
    expect(dest).toMatchObject({ kind: 'storage', folder: 'cold' });
  });
});
