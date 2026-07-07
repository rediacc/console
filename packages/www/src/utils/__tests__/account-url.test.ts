import { describe, expect, it } from 'vitest';
import { getLocalAccountUrl } from '../account-url';

describe('getLocalAccountUrl', () => {
  it('marketing hosts get no local URL (picker handles the handoff)', () => {
    expect(getLocalAccountUrl('https://www.rediacc.com')).toBeUndefined();
    expect(getLocalAccountUrl('https://edge.rediacc.com')).toBeUndefined();
    expect(getLocalAccountUrl('https://localhost')).toBeUndefined();
  });

  it('PR previews link straight to their own portal', () => {
    expect(getLocalAccountUrl('https://pr-477.rediacc.workers.dev')).toBe('/account/');
  });

  it('portal hosts link straight to /account/', () => {
    expect(getLocalAccountUrl('https://eu.rediacc.com')).toBe('/account/');
    expect(getLocalAccountUrl('https://edge-eu.rediacc.com')).toBe('/account/');
    expect(getLocalAccountUrl('https://bench.rediacc.com')).toBe('/account/');
    expect(getLocalAccountUrl('https://onprem.internal.example')).toBe('/account/');
  });

  it('accepts a bare hostname as the origin argument', () => {
    expect(getLocalAccountUrl('eu.rediacc.com')).toBe('/account/');
    expect(getLocalAccountUrl('www.rediacc.com')).toBeUndefined();
  });
});
