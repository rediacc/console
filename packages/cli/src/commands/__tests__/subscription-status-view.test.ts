/** The order of the "elsewhere" summary line of `subscription status --all`: deleted first, then most urgent. */

import { describe, expect, it, vi } from 'vitest';
import type { LicenceRow } from '../../services/account/license-retire.js';
import { elsewhereItems } from '../subscription-status-view.js';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string | undefined, params?: { count?: number; state?: string }) =>
    `${key?.split('.').at(-1)}:${params?.count}:${params?.state}`,
}));

function row(presence: LicenceRow['presence'], freshness: string): LicenceRow {
  return {
    guid: 'g',
    name: null,
    machine: null,
    kind: null,
    freshness: freshness as LicenceRow['freshness'],
    refreshRecommendedAt: null,
    hardExpiresAt: null,
    presence,
    fix: null,
  };
}

describe('elsewhereItems ordering', () => {
  it('lists deleted before absent, then hard expired before refresh recommended before valid', () => {
    const items = elsewhereItems([
      row('absent', 'valid'),
      row('absent', 'hard_expired'),
      row('deleted', 'valid'),
      row('absent', 'refresh_recommended'),
    ]);
    expect(items.map((i) => i.split(':')[0])).toEqual([
      'elsewhereDeleted',
      'elsewhereAbsent',
      'elsewhereAbsent',
      'elsewhereAbsent',
    ]);
    expect(items.slice(1).map((i) => i.split(':')[2])).toEqual([
      'hardExpired',
      'refreshRecommended',
      'valid',
    ]);
  });

  it('ranks a freshness the server sends that matches no key after every known one, in a stable order', () => {
    const rows = [row('absent', 'surprise'), row('absent', 'valid'), row('absent', 'hard_expired')];
    const forward = elsewhereItems(rows);
    expect(forward.map((i) => i.split(':')[2])).toEqual(['hardExpired', 'valid', 'undefined']);
    expect(elsewhereItems([...rows].reverse())).toEqual(forward);
  });
});
