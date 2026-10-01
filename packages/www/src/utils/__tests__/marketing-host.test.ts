import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_BENCH_ORIGIN,
  WK_EDGE_ORIGIN,
  WK_SITE_ORIGIN,
} from '@rediacc/shared/config/well-known.generated';
import { BAKED_IN_REGIONS, type RegionInfo } from '@rediacc/shared/regions';
import { describe, expect, it } from 'vitest';
import type { Region } from '../../config/regions';
import {
  buildPortalRedirectUrl,
  getHostKind,
  getPortalDomain,
  isMarketingHost,
} from '../marketing-host';

const BENCH_HOST = new URL(WK_BENCH_ORIGIN).host;
const EDGE_HOST = new URL(WK_EDGE_ORIGIN).host;
const EU_HOST = new URL(WK_ACCOUNT_DEFAULT_ORIGIN).host;
const SITE_HOST = new URL(WK_SITE_ORIGIN).host;
const regionOf = (id: string): RegionInfo => {
  const r = BAKED_IN_REGIONS.find((x) => x.id === id);
  if (!r) throw new Error(`no baked-in region ${id}`);
  return r;
};

const eu: Region = {
  id: 'eu',
  label: 'Europe',
  domain: EU_HOST,
  edgeDomain: regionOf('eu').edgeDomain,
  default: true,
};

describe('getHostKind', () => {
  it.each([
    [SITE_HOST, 'marketing-stable'],
    [EDGE_HOST, 'marketing-edge'],
    ['pr-477.rediacc.workers.dev', 'preview'],
    ['anything.rediacc.workers.dev', 'preview'],
    ['localhost', 'localhost'],
    [EU_HOST, 'portal'],
    [regionOf('us').domain, 'portal'],
    [regionOf('asia').domain, 'portal'],
    [regionOf('eu').edgeDomain, 'portal'],
    [BENCH_HOST, 'portal'],
    ['intranet.customer.example', 'portal'],
  ] as const)('%s -> %s', (hostname, kind) => {
    expect(getHostKind(hostname)).toBe(kind);
  });
});

describe('isMarketingHost', () => {
  it('opens the picker on the two marketing sites and localhost', () => {
    expect(isMarketingHost(SITE_HOST)).toBe(true);
    expect(isMarketingHost(EDGE_HOST)).toBe(true);
    expect(isMarketingHost('localhost')).toBe(true);
  });

  it('PR previews serve their own portal and must NOT open the picker', () => {
    expect(isMarketingHost('pr-477.rediacc.workers.dev')).toBe(false);
  });

  it('portal and on-prem hosts navigate directly', () => {
    expect(isMarketingHost(EU_HOST)).toBe(false);
    expect(isMarketingHost(regionOf('eu').edgeDomain)).toBe(false);
    expect(isMarketingHost(BENCH_HOST)).toBe(false);
    expect(isMarketingHost('intranet.customer.example')).toBe(false);
  });
});

describe('getPortalDomain (channel is host-determined)', () => {
  it('www hands off to the stable portal', () => {
    expect(getPortalDomain(SITE_HOST, eu)).toBe(EU_HOST);
  });

  it('edge marketing hands off to the edge portal', () => {
    expect(getPortalDomain(EDGE_HOST, eu)).toBe(regionOf('eu').edgeDomain);
  });

  it('localhost dev hands off to the edge portal (dev-safe default)', () => {
    expect(getPortalDomain('localhost', eu)).toBe(regionOf('eu').edgeDomain);
  });
});

describe('buildPortalRedirectUrl', () => {
  it('preserves the target path and its query (checkout deep link)', () => {
    const url = new URL(
      buildPortalRedirectUrl(
        SITE_HOST,
        eu,
        '/account/?checkout=PROFESSIONAL&period=monthly&returnUrl=https%3A%2F%2Fwww.rediacc.com%2Fen%2Fpricing'
      )
    );
    expect(url.origin).toBe(WK_ACCOUNT_DEFAULT_ORIGIN);
    expect(url.pathname).toBe('/account/');
    expect(url.searchParams.get('checkout')).toBe('PROFESSIONAL');
    expect(url.searchParams.get('period')).toBe('monthly');
    expect(url.searchParams.get('returnUrl')).toBe(`${WK_SITE_ORIGIN}/en/pricing`);
  });

  it('regression: stable choice must not leak to the edge domain (old fast path hardcoded edgeDomain)', () => {
    expect(buildPortalRedirectUrl(SITE_HOST, eu, '/account/')).toBe(
      `${WK_ACCOUNT_DEFAULT_ORIGIN}/account/`
    );
  });

  it('merges captured utm_* params', () => {
    const url = new URL(
      buildPortalRedirectUrl(SITE_HOST, eu, '/account/', {
        utm_source: 'hn',
        utm_campaign: 'launch',
      })
    );
    expect(url.searchParams.get('utm_source')).toBe('hn');
    expect(url.searchParams.get('utm_campaign')).toBe('launch');
  });

  it('never overwrites params already on the target path', () => {
    const url = new URL(
      buildPortalRedirectUrl(SITE_HOST, eu, '/account/?utm_source=explicit', {
        utm_source: 'stored',
      })
    );
    expect(url.searchParams.get('utm_source')).toBe('explicit');
  });

  it('ignores non-utm and empty values from the tracker', () => {
    const url = new URL(
      buildPortalRedirectUrl(SITE_HOST, eu, '/account/', {
        utm_source: '',
        referrer: 'https://evil.example',
        session_id: 'abc',
      })
    );
    expect([...url.searchParams.keys()]).toEqual([]);
  });

  it('uses the edge domain when built from the edge marketing host', () => {
    expect(buildPortalRedirectUrl(EDGE_HOST, eu, '/account/')).toBe(
      `https://${regionOf('eu').edgeDomain}/account/`
    );
  });
});
