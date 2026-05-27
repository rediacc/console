import { describe, expect, it } from 'vitest';

import { buildStrategyUpdate, parseRepoFilter } from '../config-backup-strategy.js';

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
