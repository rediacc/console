import { describe, expect, it } from 'vitest';
import type { Region } from '../../config/regions';
import {
  buildPortalRedirectUrl,
  getHostKind,
  getPortalDomain,
  isMarketingHost,
} from '../marketing-host';

const eu: Region = {
  id: 'eu',
  label: 'Europe',
  domain: 'eu.rediacc.com',
  edgeDomain: 'edge-eu.rediacc.com',
  default: true,
};

describe('getHostKind', () => {
  it.each([
    ['www.rediacc.com', 'marketing-stable'],
    ['edge.rediacc.com', 'marketing-edge'],
    ['pr-477.rediacc.workers.dev', 'preview'],
    ['anything.rediacc.workers.dev', 'preview'],
    ['localhost', 'localhost'],
    ['eu.rediacc.com', 'portal'],
    ['us.rediacc.com', 'portal'],
    ['asia.rediacc.com', 'portal'],
    ['edge-eu.rediacc.com', 'portal'],
    ['bench.rediacc.com', 'portal'],
    ['intranet.customer.example', 'portal'],
  ] as const)('%s -> %s', (hostname, kind) => {
    expect(getHostKind(hostname)).toBe(kind);
  });
});

describe('isMarketingHost', () => {
  it('opens the picker on the two marketing sites and localhost', () => {
    expect(isMarketingHost('www.rediacc.com')).toBe(true);
    expect(isMarketingHost('edge.rediacc.com')).toBe(true);
    expect(isMarketingHost('localhost')).toBe(true);
  });

  it('PR previews serve their own portal and must NOT open the picker', () => {
    expect(isMarketingHost('pr-477.rediacc.workers.dev')).toBe(false);
  });

  it('portal and on-prem hosts navigate directly', () => {
    expect(isMarketingHost('eu.rediacc.com')).toBe(false);
    expect(isMarketingHost('edge-eu.rediacc.com')).toBe(false);
    expect(isMarketingHost('bench.rediacc.com')).toBe(false);
    expect(isMarketingHost('intranet.customer.example')).toBe(false);
  });
});

describe('getPortalDomain (channel is host-determined)', () => {
  it('www hands off to the stable portal', () => {
    expect(getPortalDomain('www.rediacc.com', eu)).toBe('eu.rediacc.com');
  });

  it('edge marketing hands off to the edge portal', () => {
    expect(getPortalDomain('edge.rediacc.com', eu)).toBe('edge-eu.rediacc.com');
  });

  it('localhost dev hands off to the edge portal (dev-safe default)', () => {
    expect(getPortalDomain('localhost', eu)).toBe('edge-eu.rediacc.com');
  });
});

describe('buildPortalRedirectUrl', () => {
  it('preserves the target path and its query (checkout deep link)', () => {
    const url = new URL(
      buildPortalRedirectUrl(
        'www.rediacc.com',
        eu,
        '/account/?checkout=PROFESSIONAL&period=monthly&returnUrl=https%3A%2F%2Fwww.rediacc.com%2Fen%2Fpricing'
      )
    );
    expect(url.origin).toBe('https://eu.rediacc.com');
    expect(url.pathname).toBe('/account/');
    expect(url.searchParams.get('checkout')).toBe('PROFESSIONAL');
    expect(url.searchParams.get('period')).toBe('monthly');
    expect(url.searchParams.get('returnUrl')).toBe('https://www.rediacc.com/en/pricing');
  });

  it('regression: stable choice must not leak to the edge domain (old fast path hardcoded edgeDomain)', () => {
    expect(buildPortalRedirectUrl('www.rediacc.com', eu, '/account/')).toBe(
      'https://eu.rediacc.com/account/'
    );
  });

  it('merges captured utm_* params', () => {
    const url = new URL(
      buildPortalRedirectUrl('www.rediacc.com', eu, '/account/', {
        utm_source: 'hn',
        utm_campaign: 'launch',
      })
    );
    expect(url.searchParams.get('utm_source')).toBe('hn');
    expect(url.searchParams.get('utm_campaign')).toBe('launch');
  });

  it('never overwrites params already on the target path', () => {
    const url = new URL(
      buildPortalRedirectUrl('www.rediacc.com', eu, '/account/?utm_source=explicit', {
        utm_source: 'stored',
      })
    );
    expect(url.searchParams.get('utm_source')).toBe('explicit');
  });

  it('ignores non-utm and empty values from the tracker', () => {
    const url = new URL(
      buildPortalRedirectUrl('www.rediacc.com', eu, '/account/', {
        utm_source: '',
        referrer: 'https://evil.example',
        session_id: 'abc',
      })
    );
    expect([...url.searchParams.keys()]).toEqual([]);
  });

  it('uses the edge domain when built from the edge marketing host', () => {
    expect(buildPortalRedirectUrl('edge.rediacc.com', eu, '/account/')).toBe(
      'https://edge-eu.rediacc.com/account/'
    );
  });
});
