import { describe, expect, it } from 'vitest';
import { WK_OPENAI_API_BASE } from '../../config/well-known.generated.js';
import { validateBaseUrl } from '../base-url.js';

const refused = (url: string): string | null => {
  const r = validateBaseUrl(url);
  return r.ok ? null : r.reason;
};

describe('validateBaseUrl', () => {
  it.each([
    'https://api.anthropic.com/v1',
    'https://gateway.ai.cloudflare.com/v1/acc/gw/compat',
    'https://litellm.example.org:8443/v1',
    'https://8.8.8.8/v1',
    'https://172.15.0.1/v1',
    'https://172.32.0.1/v1',
    'https://192.169.1.1/v1',
    'https://[2606:4700::1111]/v1',
    'https://api.example.com./v1',
  ])('accepts the public endpoint %s', (url) => {
    expect(validateBaseUrl(url).ok).toBe(true);
  });

  it('returns the parsed URL on success', () => {
    const r = validateBaseUrl(WK_OPENAI_API_BASE);
    expect(r.ok && r.url.hostname).toBe('api.openai.com');
  });

  it.each([
    WK_OPENAI_API_BASE.replace('https://', 'http://'),
    'ftp://example.com',
    'wss://example.com/x',
  ])('refuses a scheme other than https: %s', (url) => {
    expect(refused(url)).toBe('not-https');
  });

  it.each(['', 'not a url', 'https://', '//example.com'])(
    'refuses an unparseable value %j',
    (url) => {
      expect(refused(url)).toBe('unparseable');
    }
  );

  it('refuses embedded credentials', () => {
    expect(refused(WK_OPENAI_API_BASE.replace('https://', 'https://user:pw@'))).toBe('credentials');
    expect(refused(WK_OPENAI_API_BASE.replace('https://', 'https://user@'))).toBe('credentials');
  });

  it.each([
    'https://account.internal/v1',
    'https://ai.internal/v1',
    'https://ACCOUNT.INTERNAL/v1',
    'https://account.internal./v1',
    'https://anything.internal/v1',
    'https://localhost/v1',
    'https://LocalHost:8443/v1',
    'https://api.localhost/v1',
  ])('refuses the internal host %s', (url) => {
    expect(refused(url)).toBe('internal-host');
  });

  it.each([
    ['https://127.0.0.1/v1', 'loopback'],
    ['https://127.255.255.254/v1', 'loopback'],
    ['https://[::1]/v1', 'loopback'],
    ['https://2130706433/v1', 'loopback'],
    ['https://0x7f.1/v1', 'loopback'],
    ['https://[::ffff:127.0.0.1]/v1', 'loopback'],
    ['https://0.0.0.0/v1', 'unspecified'],
    ['https://[::]/v1', 'unspecified'],
    ['https://169.254.169.254/latest', 'link-local'],
    ['https://[fe80::1]/v1', 'link-local'],
    ['https://[febf::1]/v1', 'link-local'],
    ['https://10.0.0.5/v1', 'private-address'],
    ['https://172.16.0.1/v1', 'private-address'],
    ['https://172.31.255.255/v1', 'private-address'],
    ['https://192.168.1.1/v1', 'private-address'],
    ['https://[fc00::1]/v1', 'private-address'],
    ['https://[fd12:3456::1]/v1', 'private-address'],
    ['https://[::ffff:10.1.2.3]/v1', 'private-address'],
    ['https://[::ffff:a9fe:a9fe]/v1', 'link-local'],
  ])('refuses the address literal %s as %s', (url, reason) => {
    expect(refused(url)).toBe(reason);
  });

  it('carries a message for each refusal', () => {
    const r = validateBaseUrl('https://10.0.0.5/v1');
    expect(r.ok).toBe(false);
    expect(!r.ok && r.message).toContain('private');
  });

  it('control: a name that merely contains a refused word is accepted', () => {
    expect(validateBaseUrl('https://internal-tools.example.com/v1').ok).toBe(true);
    expect(validateBaseUrl('https://localhost.example.com/v1').ok).toBe(true);
    expect(validateBaseUrl('https://my-account-internal.example.com/v1').ok).toBe(true);
  });
});
