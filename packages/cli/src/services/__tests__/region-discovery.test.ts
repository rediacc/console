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

import { discoverRegions, detectLikelyRegion } from '../region-discovery.js';

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
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('should return fetched regions when signature is valid', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ payload: '...', signature: '...', publicKeyId: 'v1' }),
    });
    mockVerifySignedRegions.mockResolvedValue(FETCHED_REGIONS);

    const result = await discoverRegions();

    expect(result).toEqual(FETCHED_REGIONS);
    expect(mockVerifySignedRegions).toHaveBeenCalledOnce();
  });

  it('should return baked-in regions on network error', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    const result = await discoverRegions();

    expect(result).toHaveLength(2);
    expect(result[0].id).toBe('eu');
    expect(mockVerifySignedRegions).not.toHaveBeenCalled();
  });

  it('should return baked-in regions on non-200 response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });

    const result = await discoverRegions();

    expect(result).toHaveLength(2);
    expect(mockVerifySignedRegions).not.toHaveBeenCalled();
  });

  it('should return baked-in regions when signature verification fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ payload: '...', signature: 'bad', publicKeyId: 'v1' }),
    });
    mockVerifySignedRegions.mockResolvedValue(null);

    const result = await discoverRegions();

    expect(result).toHaveLength(2);
    expect(result[0].id).toBe('eu');
  });

  it('should return baked-in regions when response JSON parsing fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.reject(new SyntaxError('Unexpected token')),
    });

    const result = await discoverRegions();

    expect(result).toHaveLength(2);
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
