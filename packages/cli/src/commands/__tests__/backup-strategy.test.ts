import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import {
  buildBackupCommands,
  generateServiceUnit,
} from '../../services/backup/backup-schedule-unit-generator.js';
import { strategyUnschedulableReason } from '../../services/backup/backup-strategy-validate.js';
import {
  applyBackupStrategyOptions,
  buildDestination,
  buildStrategyUpdate,
  parseRepoFilter,
  parseRetentionOption,
} from '../backup-strategy.js';

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
    // The inverse of what this asserted until 2026-08-15. `--mode cold` was refused here because scheduling it would have promised a container
    // quiesce that `backup snapshot` could not perform; the verb grew --cold,
    // so the refusal went with it. The schema's enum is exactly hot|cold, so there is no third value left for a guard to catch, one that survived would be a check that can never fire.
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
    expect(commands).toEqual([
      `/usr/bin/renet backup snapshot --datastore ${WK_DATASTORE_PATH} --parallelism 2`,
    ]);
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

describe('strategy retention (F4)', () => {
  it('--retention parses name=count pairs into the stored policy', () => {
    const u = buildStrategyUpdate({ retention: 'last=7,daily=7,weekly=4,monthly=6' }, undefined);
    expect(u.retention).toEqual({ keepLast: 7, keepDaily: 7, keepWeekly: 4, keepMonthly: 6 });
  });

  it('leaves retention out of the update when the flag is absent, so a set never wipes it', () => {
    expect('retention' in buildStrategyUpdate({ cron: '0 3 * * *' }, undefined)).toBe(false);
  });

  it('"none" clears the stored policy', () => {
    const u = buildStrategyUpdate({ retention: 'none' }, undefined);
    expect('retention' in u).toBe(true);
    expect(u.retention).toBeUndefined();
  });

  it.each(['last=x', 'last', 'weekly=1,weekly=2', 'fortnightly=2', 'last=-1', 'last=1.5'])(
    'refuses %s rather than guessing what to delete',
    (raw) => {
      expect(() => parseRetentionOption(raw)).toThrow(/--retention/);
    }
  );
});

describe('strategy read cap (--read-bwlimit)', () => {
  it('stores the value as readBandwidthLimit and leaves it alone when not passed', () => {
    expect(buildStrategyUpdate({ readBwlimit: '50M' }, undefined).readBandwidthLimit).toBe('50M');
    expect(() => buildStrategyUpdate({ readBwlimit: 'fast' }, undefined)).toThrow(
      /Read bandwidth limit "fast" cannot be converted/
    );
    expect(() => buildStrategyUpdate({ readBwlimit: ' ' }, undefined)).toThrow(
      /--read-bwlimit must be a rate/
    );
    expect(() => buildStrategyUpdate({ bwlimit: '100Mb' }, undefined)).toThrow(
      /Bandwidth limit "100Mb" cannot be converted/
    );
    expect(() => buildStrategyUpdate({ bwlimit: '' }, undefined)).toThrow(
      /--bwlimit must be a rate/
    );
    expect(buildStrategyUpdate({ readBwlimit: '0' }, undefined).readBandwidthLimit).toBe('0');
    expect('readBandwidthLimit' in buildStrategyUpdate({ cron: '0 * * * *' }, undefined)).toBe(
      false
    );
  });

  it('clears the cap on none', () => {
    const u = buildStrategyUpdate({ readBwlimit: 'none' }, undefined);
    expect('readBandwidthLimit' in u).toBe(true);
    expect(u.readBandwidthLimit).toBeUndefined();
  });

  it('is refused together with --destination, because the read is not tied to a destination', async () => {
    await expect(
      applyBackupStrategyOptions('s', { destination: 'd', readBwlimit: '50M' })
    ).rejects.toThrow(/applies to the whole strategy/);
  });

  it('makes a strategy with an unparseable read cap unschedulable, and accepts 0 and 50M', () => {
    const base = { destinations: [], schedule: '0 * * * *' };
    expect(strategyUnschedulableReason({ ...base, readBandwidthLimit: 'fast' })).toMatch(
      /Read bandwidth limit "fast"/
    );
    expect(strategyUnschedulableReason({ ...base, readBandwidthLimit: '100Mb' })).toBeDefined();
    expect(strategyUnschedulableReason({ ...base, readBandwidthLimit: '50M' })).toBeUndefined();
    expect(strategyUnschedulableReason({ ...base, readBandwidthLimit: '0' })).toBeUndefined();
  });
});
