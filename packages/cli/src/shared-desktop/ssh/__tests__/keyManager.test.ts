import { describe, expect, it } from 'vitest';
import { decodeSSHKey } from '../keyManager.js';

describe('decodeSSHKey normalization', () => {
  const VALID_BODY = [
    'b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAAB',
    'AAAAMwAAAAtzc2gtZWQyNTUxOQAAACA1iaXz/V8Lwx9aB+r//AAA',
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
  ].join('\n');

  const wrap = (sep: string, trailing = '\n'): string =>
    [`-----BEGIN OPENSSH PRIVATE KEY-----`, VALID_BODY, `-----END OPENSSH PRIVATE KEY-----`].join(
      sep
    ) + trailing;

  it('strips CRLF line endings to LF (the ssh-add libcrypto trigger)', () => {
    const crlfKey = wrap('\r\n', '\r\n');
    const out = decodeSSHKey(crlfKey);
    expect(out).not.toContain('\r');
    expect(out.endsWith('\n')).toBe(true);
  });

  it('appends a trailing newline when missing (ssh-add expects one)', () => {
    const noTrailing = wrap('\n', '');
    const out = decodeSSHKey(noTrailing);
    expect(out.endsWith('\n')).toBe(true);
    expect(out.endsWith('\n\n')).toBe(false);
  });

  it('collapses multiple trailing newlines to exactly one', () => {
    const tooManyNewlines = wrap('\n', '\n\n\n');
    const out = decodeSSHKey(tooManyNewlines);
    expect(out.endsWith('\n')).toBe(true);
    expect(out.endsWith('\n\n')).toBe(false);
  });

  it('passes through an already-clean key unchanged in semantics', () => {
    const clean = wrap('\n', '\n');
    const out = decodeSSHKey(clean);
    expect(out).toBe(clean);
  });

  it('rejects empty input', () => {
    expect(() => decodeSSHKey('')).toThrow(/empty/i);
    expect(() => decodeSSHKey('   \n  ')).toThrow(/empty/i);
  });

  it('rejects non-PEM input', () => {
    expect(() => decodeSSHKey('not a key')).toThrow(/PEM format/i);
  });

  it('rejects PEM with unrecognized key type', () => {
    const fake = '-----BEGIN GARBAGE-----\nzzz\n-----END GARBAGE-----\n';
    expect(() => decodeSSHKey(fake)).toThrow(/key type not recognized/i);
  });
});
