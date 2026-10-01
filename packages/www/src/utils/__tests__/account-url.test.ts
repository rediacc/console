import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_BENCH_ORIGIN,
  WK_EDGE_ORIGIN,
  WK_SITE_ORIGIN,
} from '@rediacc/shared/config/well-known.generated';
import { BAKED_IN_REGIONS, type RegionInfo } from '@rediacc/shared/regions';
import { describe, expect, it } from 'vitest';
import { getLocalAccountUrl } from '../account-url';

const EU_HOST = new URL(WK_ACCOUNT_DEFAULT_ORIGIN).host;
const SITE_HOST = new URL(WK_SITE_ORIGIN).host;
const regionOf = (id: string): RegionInfo => {
  const r = BAKED_IN_REGIONS.find((x) => x.id === id);
  if (!r) throw new Error(`no baked-in region ${id}`);
  return r;
};

describe('getLocalAccountUrl', () => {
  it('marketing hosts get no local URL (picker handles the handoff)', () => {
    expect(getLocalAccountUrl(WK_SITE_ORIGIN)).toBeUndefined();
    expect(getLocalAccountUrl(WK_EDGE_ORIGIN)).toBeUndefined();
    expect(getLocalAccountUrl('https://localhost')).toBeUndefined();
  });

  it('PR previews link straight to their own portal', () => {
    expect(getLocalAccountUrl('https://pr-477.rediacc.workers.dev')).toBe('/account/');
  });

  it('portal hosts link straight to /account/', () => {
    expect(getLocalAccountUrl(WK_ACCOUNT_DEFAULT_ORIGIN)).toBe('/account/');
    expect(getLocalAccountUrl(`https://${regionOf('eu').edgeDomain}`)).toBe('/account/');
    expect(getLocalAccountUrl(WK_BENCH_ORIGIN)).toBe('/account/');
    expect(getLocalAccountUrl('https://onprem.internal.example')).toBe('/account/');
  });

  it('accepts a bare hostname as the origin argument', () => {
    expect(getLocalAccountUrl(EU_HOST)).toBe('/account/');
    expect(getLocalAccountUrl(SITE_HOST)).toBeUndefined();
  });
});
