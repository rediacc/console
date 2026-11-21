/**
 * The licence detail of a machine status comes from the list-all job's `license_statuses` section. An absent
 * section or an entry that is not the shape the table reads is unknown, never an empty detail that renders every
 * backup as `ok`. `machine health` no longer registers the `-t/--team` option it stopped reading.
 */

import type { ListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import { Command } from 'commander';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../services/core/output.js', () => ({ outputService: { info: vi.fn() } }));
vi.mock('../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../i18n/index.js', () => ({ t: (k: string) => k }));

const { buildEnrichedJson, licenseDetailOf } = await import('../machine/status.js');
const { registerHealthCommand } = await import('../machine/health.js');

const GOOD = {
  repositoryGuid: 'g1',
  status: 'valid',
  datastoreId: 'ds-1',
  blockedBackup: { reason: 'expired' },
  lastRenewal: { outcome: 'refused', code: 'lapsed' },
};

const listing = (statuses: unknown): ListResult =>
  ({ license_statuses: statuses }) as unknown as ListResult;

describe('licenseDetailOf', () => {
  it('is unknown (undefined), not an empty map, when the listing has no licenses section', () => {
    expect(licenseDetailOf({} as ListResult)).toBeUndefined();
  });

  it.each([
    ['a non-object entry', ['x']],
    ['an entry without a guid', [{ status: 'valid' }]],
    ['a blockedBackup without a reason', [{ ...GOOD, blockedBackup: {} }]],
    ['a lastRenewal without an outcome', [{ ...GOOD, lastRenewal: { code: 'x' } }]],
    ['a non-string datastoreId', [{ ...GOOD, datastoreId: 7 }]],
    ['one bad entry among good ones', [GOOD, { repositoryGuid: 2 }]],
  ])('is unknown for %s', (_name, statuses) => {
    expect(licenseDetailOf(listing(statuses))).toBeUndefined();
  });

  it('control: a well-formed section is a map by guid, and an empty one is an empty map', () => {
    expect(licenseDetailOf(listing([GOOD]))?.get('g1')).toMatchObject({
      datastoreId: 'ds-1',
      blockedBackup: { reason: 'expired' },
    });
    expect(licenseDetailOf(listing([]))?.size).toBe(0);
  });
});

describe('buildEnrichedJson with no detail held', () => {
  const json = (detail: ReturnType<typeof licenseDetailOf>) =>
    buildEnrichedJson(
      listing([GOOD]),
      undefined,
      undefined,
      (g) => g,
      ((n: string) => ({ name: n, source: 'guid' })) as never,
      detail,
      'm1'
    ).license_statuses as Record<string, unknown>[];

  it('marks an entry whose detail is not held as unknown, never as not blocked', () => {
    // A filtered run that never read the licence detail passes an empty map.
    expect(json(new Map())[0].backups).toBe('unknown');
    expect(json(undefined)[0].backups).toBe('unknown');
  });

  it('control: an entry with its detail carries no unknown marker', () => {
    expect(json(licenseDetailOf(listing([GOOD])))[0].backups).toBeUndefined();
  });
});

describe('machine health options', () => {
  it('registers no -t/--team option, since the action never read it', () => {
    const machine = new Command('machine');
    registerHealthCommand(machine);
    const health = machine.commands.find((c) => c.name() === 'health');
    expect(health?.options.map((o) => o.long)).not.toContain('--team');
  });
});

describe('buildEnrichedJson license_statuses', () => {
  const json = (statuses: unknown) =>
    buildEnrichedJson(
      listing(statuses),
      undefined,
      undefined,
      (guid) => guid,
      (name) => ({ name, source: 'config' }) as never,
      licenseDetailOf(listing(statuses)),
      'm1'
    ).license_statuses as Record<string, unknown>[];

  it('marks every entry unknown when the detail is unreadable, so a blockedBackup check is not read as ok', () => {
    const entries = json([{ repositoryGuid: 'g1', status: 'valid' }, { repositoryGuid: 2 }]);
    expect(entries.map((e) => e.backups)).toEqual(['unknown', 'unknown']);
  });

  it('control: readable detail carries its own fields and no unknown marker', () => {
    const [entry] = json([GOOD]);
    expect(entry).toMatchObject({ datastoreId: 'ds-1', blockedBackup: { reason: 'expired' } });
    expect(entry).not.toHaveProperty('backups');
  });
});
