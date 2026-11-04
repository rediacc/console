import type { ListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import { describe, expect, it } from 'vitest';
import { staleBinariesOf } from '../status.js';

const listing = (stale?: ListResult['stale_processes']) =>
  ({ stale_processes: stale }) as ListResult;

describe('staleBinariesOf', () => {
  it('maps the processes of a readable section, sorted as renet sent them', () => {
    expect(
      staleBinariesOf(
        listing({
          status: 'ok',
          processes: [
            { pid: 7, unit: 'rediacc-router.service', exe: '/x/renet (deleted)' },
            { pid: 9, unit: '', exe: '/y/renet' },
          ],
        })
      )
    ).toEqual([
      { pid: 7, unit: 'rediacc-router.service', exe: '/x/renet (deleted)' },
      { pid: 9, unit: '-', exe: '/y/renet' },
    ]);
  });

  it('reports none stale as an empty list, not as unknown', () => {
    expect(staleBinariesOf(listing({ status: 'ok', processes: [] }))).toEqual([]);
  });

  it('is unknown when /proc was unreadable or the section is absent', () => {
    expect(
      staleBinariesOf(
        listing({ status: 'unknown', processes: null as unknown as [], error: 'denied' })
      )
    ).toBeNull();
    expect(staleBinariesOf(listing())).toBeNull();
  });
});
