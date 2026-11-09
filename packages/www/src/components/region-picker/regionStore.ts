import { REGIONS, type Region } from '../../config/regions';

export const REGION_META: Partial<
  Record<string, { flagSrc: string; flagAlt: string; location: string }>
> = {
  eu: {
    flagSrc: '/assets/images/flags/eu.svg',
    flagAlt: 'EU flag',
    location: 'Frankfurt, Germany',
  },
  us: { flagSrc: '/assets/images/flags/us.svg', flagAlt: 'US flag', location: 'Virginia, USA' },
  asia: {
    flagSrc: '/assets/images/flags/jp.svg',
    flagAlt: 'Japan flag',
    location: 'Tokyo, Japan',
  },
};

export const REGION_STORAGE_KEY = 'rediacc_region';

export function getStoredRegion(): Region | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(REGION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.region === 'string') {
      return REGIONS.find((r) => r.id === parsed.region) ?? null;
    }
  } catch {
    /* corrupted data */
  }
  return null;
}
