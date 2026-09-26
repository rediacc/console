import { describe, expect, it } from 'vitest';
import {
  classifyKeyChange,
  fingerprint,
  keyBlobAlgorithm,
  parseKnownHosts,
  shortFingerprint,
} from '../host-keys.js';

// Real hostinger host keys observed during the incident that motivated this module: the pin that had gone stale, and the key the host was actually offering. Using real blobs keeps the fingerprint assertions honest.
const OLD_ED25519 = 'AAAAC3NzaC1lZDI1NTE5AAAAICrdYxwn02/Fqco8Pn6DTkW6dG2yogjIOe4K1bxuw06f';
const NEW_ED25519 = 'AAAAC3NzaC1lZDI1NTE5AAAAIDo5MxnUtG9Ie+slGgDyHWlx7r6VWsV0yF9K5vVzZG6/';
const RSA = 'AAAAB3NzaC1yc2EAAAADAQABAAABgQCkAMTTKw+6MbBy9EdCNhXac6xKxzqeErEQrwPvSfTmN5dpxyqp';

const host = '72.61.137.225';
const line = (key: string, type = 'ssh-ed25519') => `${host} ${type} ${key}`;

describe('parseKnownHosts', () => {
  it('returns the algorithm alongside the key', () => {
    expect(parseKnownHosts(line(OLD_ED25519))).toEqual([{ type: 'ssh-ed25519', key: OLD_ED25519 }]);
  });

  it('parses multiple entries across lines', () => {
    const parsed = parseKnownHosts(`${line(OLD_ED25519)}\n${line(RSA, 'ssh-rsa')}`);
    expect(parsed.map((e) => e.type)).toEqual(['ssh-ed25519', 'ssh-rsa']);
  });

  it('skips blank lines, comments and malformed entries', () => {
    const parsed = parseKnownHosts(
      ['', '   ', '# a comment', 'host-only', `${host} ssh-ed25519`, line(OLD_ED25519)].join('\n')
    );
    expect(parsed).toHaveLength(1);
  });

  it('tolerates a trailing comment field', () => {
    expect(parseKnownHosts(`${line(OLD_ED25519)} some-comment`)).toHaveLength(1);
  });
});

describe('fingerprint', () => {
  it('produces OpenSSH-style SHA256 with padding stripped', () => {
    const fp = fingerprint(OLD_ED25519);
    expect(fp.startsWith('SHA256:')).toBe(true);
    expect(fp.endsWith('=')).toBe(false);
  });

  it('distinguishes two different keys', () => {
    expect(fingerprint(OLD_ED25519)).not.toBe(fingerprint(NEW_ED25519));
  });

  it('is stable for the same key', () => {
    expect(fingerprint(OLD_ED25519)).toBe(fingerprint(OLD_ED25519));
  });

  it('abbreviates for table output while keeping the prefix', () => {
    const short = shortFingerprint(OLD_ED25519);
    expect(short.startsWith('SHA256:')).toBe(true);
    expect(short).toContain('…');
    expect(short.length).toBeLessThan(fingerprint(OLD_ED25519).length);
  });
});

describe('keyBlobAlgorithm', () => {
  it('reads the algorithm out of an ed25519 blob', () => {
    expect(keyBlobAlgorithm(OLD_ED25519)).toBe('ssh-ed25519');
  });

  it('reads the algorithm out of an rsa blob', () => {
    expect(keyBlobAlgorithm(RSA)).toBe('ssh-rsa');
  });

  it('returns empty for a blob that is too short to hold a length prefix', () => {
    expect(keyBlobAlgorithm(Buffer.from([1, 2]).toString('base64'))).toBe('');
  });

  it('returns empty rather than over-reading on a bogus length prefix', () => {
    // Length prefix claims 1000 bytes but the buffer holds far fewer.
    const bogus = Buffer.alloc(8);
    bogus.writeUInt32BE(1000, 0);
    expect(keyBlobAlgorithm(bogus.toString('base64'))).toBe('');
  });

  it('returns empty for non-ascii garbage in the name field', () => {
    const buf = Buffer.alloc(8);
    buf.writeUInt32BE(4, 0);
    buf.write('\x00\x01\x02\x03', 4, 'binary');
    expect(keyBlobAlgorithm(buf.toString('base64'))).toBe('');
  });
});

describe('classifyKeyChange', () => {
  it('flags a changed key of the same algorithm as replaced', () => {
    const [change] = classifyKeyChange(line(OLD_ED25519), line(NEW_ED25519));
    expect(change).toMatchObject({
      type: 'ssh-ed25519',
      kind: 'replaced',
      oldKey: OLD_ED25519,
      newKey: NEW_ED25519,
    });
  });

  it('flags an identical re-scan as unchanged', () => {
    const [change] = classifyKeyChange(line(OLD_ED25519), line(OLD_ED25519));
    expect(change.kind).toBe('unchanged');
  });

  it('flags a first-ever pin as pinned, not replaced', () => {
    const [change] = classifyKeyChange('', line(NEW_ED25519));
    expect(change.kind).toBe('pinned');
    expect(change.oldKey).toBeUndefined();
  });

  it('compares per algorithm rather than across the whole file', () => {
    // ed25519 rotated, rsa untouched. Reporting "a key changed" without the algorithm would lose which one.
    const before = `${line(OLD_ED25519)}\n${line(RSA, 'ssh-rsa')}`;
    const after = `${line(NEW_ED25519)}\n${line(RSA, 'ssh-rsa')}`;
    const byType = Object.fromEntries(
      classifyKeyChange(before, after).map((c) => [c.type, c.kind])
    );
    expect(byType).toEqual({ 'ssh-ed25519': 'replaced', 'ssh-rsa': 'unchanged' });
  });

  it('treats a newly offered algorithm as pinned, not replaced', () => {
    const change = classifyKeyChange(
      line(OLD_ED25519),
      `${line(OLD_ED25519)}\n${line(RSA, 'ssh-rsa')}`
    );
    expect(change.find((c) => c.type === 'ssh-rsa')?.kind).toBe('pinned');
  });

  it('ignores an algorithm the host no longer offers', () => {
    // A server dropping a legacy algorithm is not the same security event as a key changing, so it must not appear as a change.
    const before = `${line(OLD_ED25519)}\n${line(RSA, 'ssh-rsa')}`;
    const changes = classifyKeyChange(before, line(OLD_ED25519));
    expect(changes.map((c) => c.type)).toEqual(['ssh-ed25519']);
  });
});
