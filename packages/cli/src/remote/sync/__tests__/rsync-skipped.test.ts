import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  createSkipLineScan,
  displayName,
  formatSkippedWarning,
  parseSkippedEntries,
  SKIP_SCAN_MAX_LINE,
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

  it('escapes bidi overrides and line separators, and doubles a literal backslash (review 589a76af)', () => {
    expect(displayName('a\u202eb')).toBe('a\\u202eb');
    expect(displayName('a\u2028b\u2069')).toBe('a\\u2028b\\u2069');
    expect(displayName('a\u200fb\u061c')).toBe('a\\u200fb\\u061c');
    // The text \x1b typed in a name is not the escaped ESC byte.
    expect(displayName('a\\x1b')).toBe('a\\\\x1b');
    expect(displayName('a\u001b')).not.toBe(displayName('a\\x1b'));
  });

  it('is applied to the names the warning shows', () => {
    expect(summarizeSkipped(['x\u001by']).shown).toEqual(['x\\x1by']);
  });
});

describe('createSkipLineScan', () => {
  it('keeps the skip lines, including one split across chunks, and drops the rest', () => {
    const scan = createSkipLineScan();
    scan.push('   1,024 100%  1.0MB/s 0:00:00 (xfr#1, to-chk=2/3)\nskipping non-regular');
    scan.push(' file "link-a"\r   2,048 100%  1.0MB/s\nskipping non-regular file "b"');
    expect(parseSkippedEntries(scan.text())).toEqual(['link-a', 'b']);
    expect(scan.text()).not.toContain('xfr#');
  });

  it('holds nothing for a stream with no skip line, however long', () => {
    const scan = createSkipLineScan();
    for (let i = 0; i < 1000; i++) scan.push(`${i} 100% progress\n`);
    expect(scan.text()).toBe('');
  });

  it('drops an overlong line that never ends, and reads the skip line after it', () => {
    const scan = createSkipLineScan();
    for (let i = 0; i < 20; i++) scan.push('x'.repeat(SKIP_SCAN_MAX_LINE / 2));
    scan.push('tail of the overlong line\nskipping non-regular file "after"\n');
    expect(parseSkippedEntries(scan.text())).toEqual(['after']);
    expect(scan.text()).not.toContain('xxxx');
  });
});

describe('parseSkippedEntries against a real rsync', () => {
  const rsyncAvailable = spawnSync('rsync', ['--version']).status === 0;

  it.skipIf(!rsyncAvailable)('names a config/ subdir that is a symlink, read from stdout', () => {
    const root = mkdtempSync(join(tmpdir(), 'rsync-skip-'));
    try {
      mkdirSync(join(root, 'real'));
      writeFileSync(join(root, 'real', 'app.conf'), 'x');
      mkdirSync(join(root, 'src'));
      writeFileSync(join(root, 'src', 'a.txt'), 'a');
      symlinkSync(join(root, 'real'), join(root, 'src', 'config'));
      mkdirSync(join(root, 'dst'));
      const run = spawnSync(
        'rsync',
        ['-a', '--no-links', '--no-D', `${join(root, 'src')}/`, `${join(root, 'dst')}/`],
        { encoding: 'utf8' }
      );
      expect(run.status).toBe(0);
      // Which stream carries the message is rsync's choice; the scan reads both.
      expect(parseSkippedEntries(`${run.stdout}\n${run.stderr}`)).toEqual(['config']);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
