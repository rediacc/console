/**
 * Region Discovery
 *
 * Fetches the signed regions manifest from the marketing site, verifies the
 * Ed25519 signature, and falls back to baked-in regions on failure.
 */

import {
  BAKED_IN_REGIONS,
  verifySignedRegions,
  type RegionInfo,
} from '@rediacc/shared/regions';
import { PROTOCOL_DEFAULTS } from '@rediacc/shared/config/defaults';

const REGIONS_URL = `${PROTOCOL_DEFAULTS.SITE_URL}/regions.json`;
const FETCH_TIMEOUT_MS = 5000;

/**
 * Discover available regions.
 * Tries to fetch the signed manifest from the marketing site.
 * Falls back to baked-in regions on any failure (network, timeout, invalid signature).
 */
export async function discoverRegions(): Promise<RegionInfo[]> {
  try {
    const resp = await fetch(REGIONS_URL, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!resp.ok) return BAKED_IN_REGIONS;

    const blob = await resp.json() as { payload: string; signature: string; publicKeyId: string };
    const regions = await verifySignedRegions(blob);
    if (regions && regions.length > 0) return regions;
  } catch {
    // Network error, timeout, or invalid JSON -- fall back silently
  }
  return BAKED_IN_REGIONS;
}

/**
 * Detect the likely region from the browser/system timezone.
 */
export function detectLikelyRegion(regions: RegionInfo[]): RegionInfo {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz.startsWith('Europe/') || tz.startsWith('Africa/')) {
      return regions.find((r) => r.id === 'eu') ?? regions[0];
    }
    if (tz.startsWith('America/')) {
      return regions.find((r) => r.id === 'us') ?? regions[0];
    }
  } catch {
    // Fallback to default
  }
  return regions.find((r) => r.default) ?? regions[0];
}
