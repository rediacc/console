/**
 * rsync reads `user@host:path` and splits at the first colon after the host, so an IPv6 machine
 * address has to be bracketed or the transfer goes to the wrong host and path.
 */

import { describe, expect, it } from 'vitest';
import { isRemotePath } from '../pathConverter.js';
import { rsyncUserHost } from '../rsync.js';

describe('rsyncUserHost', () => {
  it.each([
    ['203.0.113.7', 'root@203.0.113.7'],
    ['m.example.test', 'root@m.example.test'],
    ['2a02:4780:c:e9b5::1', 'root@[2a02:4780:c:e9b5::1]'],
    ['[2a02:4780:c:e9b5::1]', 'root@[2a02:4780:c:e9b5::1]'],
  ])('%s -> %s', (host, expected) => {
    expect(rsyncUserHost('root', host)).toBe(expected);
  });

  it('a bracketed IPv6 remote path still reads as remote', () => {
    expect(isRemotePath(`${rsyncUserHost('root', '2a02::1')}:/mnt/x`)).toBe(true);
  });
});
