import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import {
  buildBackupCommands,
  generateServiceUnit,
} from '../../services/backup/backup-schedule-unit-generator.js';
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
    const u = buildStrategyUpdate({ exclude: 'demo-stackoverflow' });
    expect(u.exclude).toEqual(['demo-stackoverflow']);
    expect(u.include).toBeUndefined();
  });

  it('sets include and clears exclude', () => {
    const u = buildStrategyUpdate({ include: 'mail,gitlab' });
    expect(u.include).toEqual(['mail', 'gitlab']);
    expect(u.exclude).toBeUndefined();
  });

  it('clears the filter when exclude is empty / none (both undefined)', () => {
    const cleared = buildStrategyUpdate({ exclude: '' });
    expect(cleared.exclude).toBeUndefined();
    expect(cleared.include).toBeUndefined();

    const none = buildStrategyUpdate({ exclude: 'none' });
    expect(none.exclude).toBeUndefined();
    expect(none.include).toBeUndefined();
  });

  it('accepts both modes now that the scheduled verb can express cold', () => {
    // The inverse of what this asserted until 2026-08-15. `--mode cold` was refused here because scheduling it would have promised a container
    // quiesce that `backup snapshot` could not perform; the verb grew --cold,
    // so the refusal went with it. The schema's enum is exactly hot|cold, so there is no third value left for a guard to catch, one that survived would be a check that can never fire.
    expect(buildStrategyUpdate({ mode: 'cold' }).mode).toBe('cold');
    expect(buildStrategyUpdate({ mode: 'hot' }).mode).toBe('hot');
  });

  it('leaves a stored mode alone when --mode is not passed', () => {
    // Editing the cron of an existing strategy must not rewrite its mode.
    expect(buildStrategyUpdate({ cron: '0 4 * * *' }).mode).toBeUndefined();
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
 * `backup strategy set` could only make a destination kind the unit generator
 * had stopped being able to render. Every documented route from "configure a
 * strategy" to "deploy a timer" therefore ended in an exception, and only a
 * hand-edited config JSON could produce a working strategy.
 *
 * The crossing test below is the point of this file: ONE object made by the
 * create path is handed to the REAL unit generator. Every defect in this stack
 * so far came from each side being checked against its own fake while the two
 * agreed on nothing, so a test that asserts the shape against a locally
 * written expectation would prove exactly nothing here.
 */
describe('creating a destination an operator can actually schedule', () => {
  it('makes a chunk-store destination', () => {
    const dest = buildDestination({ destinationName: 'chunks' });
    expect(dest.kind).toBe('hosted-service');
    expect(dest.name).toBe('chunks');
    expect(dest).not.toHaveProperty('storage');
  });

  it('and the unit generator emits a real snapshot command for that object', () => {
    // The crossing: create path -> generator, no fake in between. Before the fix this could not even be written, because the create path threw.
    const dest = buildDestination({ destinationName: 'chunks' });
    const { commands, envVars } = buildBackupCommands(
      { schedule: '0 * * * *', destinations: [dest] },
      [dest],
      WK_DATASTORE_PATH,
      '/usr/bin/renet'
    );
    expect(commands).toEqual([`/usr/bin/renet backup snapshot --datastore ${WK_DATASTORE_PATH}`]);
    // No credential reaches the unit: the machine authenticates with its licence blob and the server hands back a short-lived grant.
    expect(envVars).toEqual({});
  });

  it('and a whole systemd unit comes out of it, ExecStart and all', () => {
    // One step further than the command list: what `rdc backup schedule` will actually write to the machine, built from the object the create path produced. This is the end-to-end claim the defect made impossible.
    const dest = buildDestination({ destinationName: 'chunks' });
    const { serviceContent } = generateServiceUnit(
      'hourly-chunks',
      { schedule: '0 * * * *', destinations: [dest] },
      [dest],
      WK_DATASTORE_PATH,
      '/usr/bin/renet'
    );
    expect(serviceContent).toContain(
      `ExecStart=/usr/bin/renet backup snapshot --datastore ${WK_DATASTORE_PATH}`
    );
    expect(serviceContent).not.toContain('EnvironmentFile=');
  });

  it('applies the bandwidth limit flag', () => {
    const dest = buildDestination({ destinationName: 'chunks', bwlimit: '6M' });
    expect(dest.kind).toBe('hosted-service');
    expect(dest).toMatchObject({ bandwidthLimit: '6M' });
  });

  it('omits keys the flags did not set, so the stored value survives the merge', () => {
    // addBackupDestination merges with `{...existing, ...dest}`, and zod KEEPS
    // an optional key passed as an explicit undefined. Before this, setting a bandwidth limit silently re-ENABLED a destination the operator had disabled, and any set without --bwlimit dropped the cap.
    const dest = buildDestination({ destinationName: 'chunks', bwlimit: '6M' });
    expect(Object.hasOwn(dest, 'enabled')).toBe(false);
    const merged = { ...{ name: 'chunks', kind: 'hosted-service', enabled: false }, ...dest };
    expect(merged.enabled).toBe(false);
  });
});
