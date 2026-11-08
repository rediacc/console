import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_BENCH_ORIGIN,
  WK_SITE_ORIGIN,
} from '@rediacc/shared/config/well-known.generated';
import { BAKED_IN_REGIONS } from '@rediacc/shared/regions';
import { describe, expect, it } from 'vitest';
import { buildPortalRedirectUrl, getHostKind, isMarketingHost } from '../marketing-host';

const BENCH_HOST = new URL(WK_BENCH_ORIGIN).host;
const EU_HOST = new URL(WK_ACCOUNT_DEFAULT_ORIGIN).host;
const SITE_HOST = new URL(WK_SITE_ORIGIN).host;

describe('getHostKind', () => {
  it.each([
    [SITE_HOST, 'marketing'],
    ['pr-477.rediacc.workers.dev', 'preview'],
    ['anything.rediacc.workers.dev', 'preview'],
    ['localhost', 'localhost'],
    [EU_HOST, 'portal'],
    ...BAKED_IN_REGIONS.map((r) => [r.domain, 'portal'] as const),
    [BENCH_HOST, 'portal'],
    ['intranet.customer.example', 'portal'],
  ] as const)('%s -> %s', (hostname, kind) => {
    expect(getHostKind(hostname)).toBe(kind);
  });
});

describe('isMarketingHost', () => {
  it('opens the picker on the one marketing site and localhost', () => {
    expect(isMarketingHost(SITE_HOST)).toBe(true);
    expect(isMarketingHost('localhost')).toBe(true);
  });

  it('PR previews serve their own portal and must NOT open the picker', () => {
    expect(isMarketingHost('pr-477.rediacc.workers.dev')).toBe(false);
  });

  it('portal and on-prem hosts navigate directly', () => {
    expect(isMarketingHost(EU_HOST)).toBe(false);
    expect(isMarketingHost(BENCH_HOST)).toBe(false);
    expect(isMarketingHost('intranet.customer.example')).toBe(false);
  });
});

describe('buildPortalRedirectUrl', () => {
  it('preserves the target path and its query (checkout deep link)', () => {
    const url = new URL(
      buildPortalRedirectUrl(
        EU_HOST,
        '/account/?checkout=PROFESSIONAL&period=monthly&returnUrl=https%3A%2F%2Fwww.rediacc.com%2Fen%2Fpricing'
      )
    );
    expect(url.origin).toBe(WK_ACCOUNT_DEFAULT_ORIGIN);
    expect(url.pathname).toBe('/account/');
    expect(url.searchParams.get('checkout')).toBe('PROFESSIONAL');
    expect(url.searchParams.get('period')).toBe('monthly');
    expect(url.searchParams.get('returnUrl')).toBe(`${WK_SITE_ORIGIN}/en/pricing`);
  });

  it('builds on the host it is given, with no channel split', () => {
    expect(buildPortalRedirectUrl(EU_HOST, '/account/')).toBe(
      `${WK_ACCOUNT_DEFAULT_ORIGIN}/account/`
    );
    expect(buildPortalRedirectUrl('acme.eu.rediacc.cloud', '/account/')).toBe(
      'https://acme.eu.rediacc.cloud/account/'
    );
  });

  it('merges captured utm_* params', () => {
    const url = new URL(
      buildPortalRedirectUrl(EU_HOST, '/account/', {
        utm_source: 'hn',
        utm_campaign: 'launch',
      })
    );
    expect(url.searchParams.get('utm_source')).toBe('hn');
    expect(url.searchParams.get('utm_campaign')).toBe('launch');
  });

  it('never overwrites params already on the target path', () => {
    const url = new URL(
      buildPortalRedirectUrl(EU_HOST, '/account/?utm_source=explicit', {
        utm_source: 'stored',
      })
    );
    expect(url.searchParams.get('utm_source')).toBe('explicit');
  });

  it('ignores non-utm and empty values from the tracker', () => {
    const url = new URL(
      buildPortalRedirectUrl(EU_HOST, '/account/', {
        utm_source: '',
        referrer: 'https://evil.example',
        session_id: 'abc',
      })
    );
    expect([...url.searchParams.keys()]).toEqual([]);
  });
});
