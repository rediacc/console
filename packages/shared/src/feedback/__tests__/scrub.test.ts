import { describe, expect, it } from 'vitest';
import { scrubText } from '../scrub.js';

const JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEF123_-xyz';

describe('scrubText', () => {
  const cases: [string, string, string][] = [
    ['rdt token', 'auth rdt_AbCdEf123456 failed', 'rdt_AbCdEf123456'],
    ['sk token', 'key sk-abcdef1234567890 bad', 'sk-abcdef1234567890'],
    ['jwt', `got ${JWT} back`, JWT],
    ['bearer', 'Authorization: Bearer abc.def-123456', 'abc.def-123456'],
    ['long base64 run', `blob ${'A1b2'.repeat(10)} end`, 'A1b2'.repeat(10)],
    ['password pair', 'password=hunter2 next', 'hunter2'],
    ['token pair', 'api_token: s3cr3tvalue', 's3cr3tvalue'],
    ['quoted secret pair', 'secret="top secret"', 'top secret'],
    ['pem', '-----BEGIN PRIVATE KEY-----\nMIIabc\n-----END PRIVATE KEY-----', 'MIIabc'],
    ['url', 'GET https://internal.example.com/path?q=1 failed', 'internal.example.com'],
    ['email', 'sent to jane.doe@example.org today', 'jane.doe'],
    ['ipv4', 'connect 192.168.10.7 refused', '192.168.10.7'],
    ['ipv6 full', 'connect 2001:0db8:85a3:0000:0000:8a2e:0370:7334 refused', '2001:0db8'],
    ['ipv6 compressed', 'connect fe80::1ff:fe23:4567:890a refused', 'fe80'],
    ['hostname', 'ssh failed for box.rediacc.io now', 'box.rediacc.io'],
    ['local hostname', 'resolve nas.local failed', 'nas.local'],
    ['linux home', 'open /home/alice/.config/x', 'alice'],
    ['mac home', 'open /Users/bob/.config/x', 'bob'],
    ['windows home', 'open C:\\Users\\carol\\x', 'carol'],
  ];
  for (const [name, input, secret] of cases) {
    it(`redacts ${name}`, () => {
      const out = scrubText(input);
      expect(out).not.toContain(secret);
      expect(out).not.toBe(input);
    });
  }

  it('redacts the effective home directory', () => {
    const out = scrubText('cannot read /srv/dave-home/file', { homeDir: '/srv/dave-home' });
    expect(out).not.toContain('dave-home');
    expect(out).toContain('<home>');
  });

  const controls = [
    'repository not found',
    'exit code 1 after 3 retries',
    'version 1.2.3 is current',
    'name=value pair stays',
    'time 12:30 elapsed',
    'file index.ts failed',
    'use --force to continue',
    'a-short-word and ratio 3/4',
  ];
  for (const text of controls) {
    it(`leaves clean text unchanged: ${text}`, () => {
      expect(scrubText(text)).toBe(text);
    });
  }

  it('keeps non-sensitive key pairs while redacting sensitive ones', () => {
    expect(scrubText('mode=fast password=x1')).toBe('mode=fast password=<redacted>');
  });
});
