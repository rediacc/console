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

  it('ranks freshness values that match no key after every known one, by name, whatever the input order', () => {
    const rows = [
      row('absent', 'surprise'),
      row('absent', 'valid'),
      row('absent', 'other'),
      row('absent', 'hard_expired'),
    ];
    const forward = elsewhereItems(rows);
    expect(forward.map((i) => i.split(':')[2])).toEqual([
      'hardExpired',
      'valid',
      'other',
      'surprise',
    ]);
    // Review 6af0546d.1: the server's row order must not reorder the line; 5b4dbcde.2: every rotation and the reverse.
    expect(elsewhereItems([...rows].reverse())).toEqual(forward);
    for (let k = 1; k < rows.length; k++) {
      expect(elsewhereItems([...rows.slice(k), ...rows.slice(0, k)])).toEqual(forward);
    }
  });

  it('orders equal-rank unknown values by code unit when the host localeCompare calls distinct strings equal', () => {
    // Review aa64a33e.1: with localeCompare returning 0, the order must not fall back to the input order.
    const spy = vi.spyOn(String.prototype, 'localeCompare').mockReturnValue(0);
    try {
      const rows = [row('absent', 'b-state'), row('absent', 'a-state'), row('absent', 'c-state')];
      const names = (input: LicenceRow[]): string[] =>
        elsewhereItems(input).map((i) => i.split(':')[2]);
      expect(names(rows)).toEqual(['a-state', 'b-state', 'c-state']);
      expect(names([...rows].reverse())).toEqual(['a-state', 'b-state', 'c-state']);
    } finally {
      spy.mockRestore();
    }
  });

  it.each(['toString', 'constructor', '__proto__'])(
    'ranks the inherited name %s as unknown, not as a function',
    (name) => {
      const items = elsewhereItems([row('absent', name), row('absent', 'valid')]);
      expect(items.map((i) => i.split(':')[2])).toEqual(['valid', name]);
    }
  );
});
