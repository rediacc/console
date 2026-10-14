import { describe, expect, it } from 'vitest';
import { newRsyncCountState, updateRsyncCount } from '../rsync-count.js';

// Captured from `rsync -a --verbose --inplace --no-whole-file --progress` over a tree of a.txt and sub/b.txt.
const REAL_OUTPUT =
  'sending incremental file list\n./\na.txt\n' +
  '\r              2 100%    0.00kB/s    0:00:00  \r              2 100%    0.00kB/s    0:00:00 (xfr#1, to-chk=2/4)\n' +
  'sub/\nsub/b.txt\n' +
  '\r              2 100%    1.95kB/s    0:00:00  \r              2 100%    1.95kB/s    0:00:00 (xfr#2, to-chk=0/4)\n';

describe('updateRsyncCount', () => {
  it('counts every file when one stdout chunk carries several xfr# lines', () => {
    const state = newRsyncCountState();
    expect(updateRsyncCount(state, REAL_OUTPUT)).toBe(2);
  });

  it('keeps the highest count across chunks', () => {
    const state = newRsyncCountState();
    updateRsyncCount(state, 'x (xfr#1, to-chk=2/4)\n');
    expect(updateRsyncCount(state, 'y (xfr#2, to-chk=0/4)\n')).toBe(2);
  });

  it('joins a token split across chunk boundaries', () => {
    const state = newRsyncCountState();
    updateRsyncCount(state, '(xfr#1, to-chk=11/13)\n(xf');
    expect(updateRsyncCount(state, 'r#12, to-chk=0/13)\n')).toBe(12);
  });

  it('accepts the rsync 3.0 xfer# spelling and ignores unrelated output', () => {
    const state = newRsyncCountState();
    expect(updateRsyncCount(state, 'sending incremental file list\n')).toBe(0);
    expect(updateRsyncCount(state, '(xfer#3, to-chk=0/4)')).toBe(3);
  });
});
