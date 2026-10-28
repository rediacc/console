import { describe, expect, it } from 'vitest';
import {
  executorName,
  placementOf,
  UNREACHABLE_THRESHOLD,
  UNREACHABLE_WINDOW_MS,
  unreachableRecent,
} from '../placement';

describe('executorName', () => {
  it('suffixes every placement, 0 included', () => {
    expect(executorName('org-a', 0)).toBe('org-a:p0');
    expect(executorName('org-a', 3)).toBe('org-a:p3');
  });

  it('names two placements of one org differently', () => {
    expect(executorName('org-a', 0)).not.toBe(executorName('org-a', 1));
  });
});

describe('placementOf', () => {
  it.each([0, 1, 41])('accepts %s', (value) => {
    expect(placementOf(value)).toBe(value);
  });

  it.each([
    ['negative', -1],
    ['fractional', 1.5],
    ['string', '1'],
    ['undefined', undefined],
    ['null', null],
    ['NaN', Number.NaN],
    ['infinity', Number.POSITIVE_INFINITY],
    ['unsafe integer', 2 ** 53],
  ])('refuses %s', (_label, value) => {
    expect(placementOf(value)).toBeUndefined();
  });
});

describe('unreachableRecent', () => {
  const now = 1_000_000_000;

  it('holds the plan constants', () => {
    expect(UNREACHABLE_THRESHOLD).toBe(3);
    expect(UNREACHABLE_WINDOW_MS).toBe(600_000);
  });

  it('is recent inside the window and not at its edge', () => {
    expect(unreachableRecent(now, now)).toBe(true);
    expect(unreachableRecent(now - UNREACHABLE_WINDOW_MS + 1, now)).toBe(true);
    expect(unreachableRecent(now - UNREACHABLE_WINDOW_MS, now)).toBe(false);
  });

  it('is not recent when missing, in the future or not finite', () => {
    expect(unreachableRecent(undefined, now)).toBe(false);
    expect(unreachableRecent(now + 1, now)).toBe(false);
    expect(unreachableRecent(Number.NaN, now)).toBe(false);
  });
});
