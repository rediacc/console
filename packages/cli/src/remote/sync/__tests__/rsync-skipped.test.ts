import { describe, expect, it } from 'vitest';
import {
  displayName,
  formatSkippedWarning,
  parseSkippedEntries,
  SKIPPED_NAMES_SHOWN,
  summarizeSkipped,
} from '../rsync-skipped.js';

describe('parseSkippedEntries', () => {
  it('reads each skipped name from rsync stderr', () => {
    const stderr =
      'skipping non-regular file "link-a"\nrsync: something else\nskipping non-regular file "sub/link b"\n';
    expect(parseSkippedEntries(stderr)).toEqual(['link-a', 'sub/link b']);
  });

  it('returns nothing for clean stderr', () => {
    expect(parseSkippedEntries('')).toEqual([]);
    expect(parseSkippedEntries('rsync: warning: some unrelated line\n')).toEqual([]);
  });

  it('drops duplicates and tolerates CRLF', () => {
    expect(
      parseSkippedEntries('skipping non-regular file "x"\r\nskipping non-regular file "x"\r\n')
    ).toEqual(['x']);
  });
});

describe('summarizeSkipped', () => {
  it('bounds the shown names and counts the rest', () => {
    const names = Array.from({ length: SKIPPED_NAMES_SHOWN + 3 }, (_, i) => `l${i}`);
    const { shown, more } = summarizeSkipped(names);
    expect(shown).toHaveLength(SKIPPED_NAMES_SHOWN);
    expect(more).toBe(3);
  });

  it('shows everything when under the bound', () => {
    expect(summarizeSkipped(['a'])).toEqual({ shown: ['a'], more: 0 });
  });
});

describe('formatSkippedWarning', () => {
  const stub = (key: string, params: Record<string, unknown>) => `${key}:${JSON.stringify(params)}`;

  it('is silent when nothing was skipped', () => {
    expect(formatSkippedWarning([], stub)).toBeUndefined();
  });

  it('names every entry when few', () => {
    expect(formatSkippedWarning(['a', 'b'], stub)).toBe(
      'commands.sync.skippedNonRegular:{"count":2,"names":"a, b"}'
    );
  });

  it('bounds the list and adds the remainder count', () => {
    const names = Array.from({ length: SKIPPED_NAMES_SHOWN + 2 }, (_, i) => `l${i}`);
    const out = formatSkippedWarning(names, stub) ?? '';
    expect(out).toContain(`"count":${names.length}`);
    expect(out).toContain('commands.sync.skippedMore');
    expect(out).toContain('\\"count\\":2');
    expect(out).not.toContain(`l${SKIPPED_NAMES_SHOWN}`);
  });
});

describe('displayName', () => {
  it('escapes control characters a remote name could carry (review ef6dbb53.2)', () => {
    expect(displayName('ok-name')).toBe('ok-name');
    expect(displayName('evil\u001b[2Jname')).toBe('evil\\x1b[2Jname');
    expect(displayName('a\u0007b\u009bc\u007f')).toBe('a\\x07b\\x9bc\\x7f');
    expect(displayName('ünïcode')).toBe('ünïcode');
  });

  it('is applied to the names the warning shows', () => {
    expect(summarizeSkipped(['x\u001by']).shown).toEqual(['x\\x1by']);
  });
});
