import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { mockVerifySignedRegions } = vi.hoisted(() => ({
  mockVerifySignedRegions: vi.fn(),
}));

vi.mock('@rediacc/shared/regions', () => ({
  BAKED_IN_REGIONS: [
    {
      id: 'eu',
      label: 'Europe',
      domain: 'eu.rediacc.com',
      edgeDomain: 'edge-eu.rediacc.com',
      default: true,
    },
    {
      id: 'us',
      label: 'United States',
      domain: 'us.rediacc.com',
      edgeDomain: 'edge-us.rediacc.com',
      default: false,
    },
  ],
  DEFAULT_REGION: {
    id: 'eu',
    label: 'Europe',
    domain: 'eu.rediacc.com',
    edgeDomain: 'edge-eu.rediacc.com',
    default: true,
  },
  verifySignedRegions: mockVerifySignedRegions,
}));

import { detectLikelyRegion, discoverRegions } from '../provision/region-discovery.js';

const FETCHED_REGIONS = [
  {
    id: 'eu',
    label: 'Europe',
    domain: 'eu.rediacc.com',
    edgeDomain: 'edge-eu.rediacc.com',
    default: true,
  },
  {
    id: 'us',
    label: 'United States',
    domain: 'us.rediacc.com',
    edgeDomain: 'edge-us.rediacc.com',
    default: false,
  },
  {
    id: 'asia',
    label: 'Asia Pacific',
    domain: 'asia.rediacc.com',
    edgeDomain: 'edge-asia.rediacc.com',
    default: false,
  },
];

describe('discoverRegions', () => {
  // THESE CASES CHANGED SHAPE ON PURPOSE (2026-08-26).
  //
  // They used to pin a runtime-fetch path: fetch the signed manifest, verify it,
  // and "fall back" to the baked-in list on failure. Five of the six cases were
  // already asserting the fallback, because the fallback was the only path that
  // ever ran -- `${SITE_URL}/regions.json` returns 404 and nothing publishes it,
  // and `scripts/sign-regions.ts` had no caller. The one case that asserted the
  // happy path was the only one describing behaviour users never got.
  //
  // The fetch was removed rather than finished (operator decision), so what is
  // worth pinning now is the opposite claim: this function makes NO network call
  // at all. That is a stronger assertion than the old suite had -- nothing
  // previously would have caught a stray request on a 5s timeout.
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('returns the baked-in regions', async () => {
    const result = await discoverRegions();

    expect(result).toHaveLength(2);
    expect(result[0].id).toBe('eu');
    expect(result[1].id).toBe('us');
  });

  it('makes NO network request', async () => {
    // The point of the removal. A fetch here would mean the dead path came back,
    // costing every caller a timeout on a URL that 404s.
    const spy = vi.fn();
    globalThis.fetch = spy;

    await discoverRegions();

    expect(spy).not.toHaveBeenCalled();
  });

  it('does not attempt signature verification', async () => {
    // verifySignedRegions is still exported from @rediacc/shared, deliberately,
    // so it is available if runtime discovery is ever built. Nothing should be
    // calling it today.
    await discoverRegions();

    expect(mockVerifySignedRegions).not.toHaveBeenCalled();
  });

  it('is stable across calls', async () => {
    const a = await discoverRegions();
    const b = await discoverRegions();

    expect(a).toEqual(b);
  });
});

describe('detectLikelyRegion', () => {
  const TEST_REGIONS = [
    { id: 'eu', label: 'Europe', domain: 'eu.rediacc.com', default: true },
    { id: 'us', label: 'United States', domain: 'us.rediacc.com', default: false },
  ];

  it('should return a valid region from the input list', () => {
    const result = detectLikelyRegion(TEST_REGIONS);
    expect(TEST_REGIONS.some((r) => r.id === result.id)).toBe(true);
  });

  it('should return default region when only one region exists', () => {
    const single = [{ id: 'eu', label: 'Europe', domain: 'eu.rediacc.com', default: true }];
    const result = detectLikelyRegion(single);
    expect(result.id).toBe('eu');
  });
});
