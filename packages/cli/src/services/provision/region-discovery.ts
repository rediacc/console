/**
 * Region Discovery
 *
 * Returns the regions this CLI was built with.
 *
 * IT USED TO CLAIM MORE THAN IT DID. This module fetched a signed manifest from
 * `${SITE_URL}/regions.json`, verified an Ed25519 signature, and "fell back" to
 * the baked-in list. That endpoint returns 404 (measured 2026-08-26) and always
 * has: nothing publishes it, and `scripts/sign-regions.ts` -- the tool that
 * would have produced the signed blob -- had no caller anywhere in the repo.
 *
 * So every call took the fallback, on a five-second-timeout HTTP round trip
 * whose failure was swallowed silently. The docstring said "falls back on
 * failure" while failure was the only path, which is the kind of comment that
 * makes a reader trust a capability that does not exist.
 *
 * Removed rather than finished, deliberately (operator decision 2026-08-26).
 * Publishing a signed manifest is a deploy-surface change and a signing-key
 * question; until someone wants that, the honest shape is a function that
 * returns the built-in list and says so. Adding a region means a CLI release --
 * which is exactly what it meant before, just without the pretence.
 *
 * `verifySignedRegions` is kept in @rediacc/shared: it is the piece worth
 * reviving if runtime discovery is ever built, and it costs nothing unused.
 */

import { BAKED_IN_REGIONS, type RegionInfo } from '@rediacc/shared/regions';

/**
 * The regions this build knows about.
 *
 * Async purely to preserve the call signature: every caller already awaits it,
 * and changing that would ripple through subscription.ts and region-prompt.ts
 * for no behavioural gain.
 */
export async function discoverRegions(): Promise<RegionInfo[]> {
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
    if (
      tz.startsWith('Asia/') ||
      tz.startsWith('Pacific/') ||
      tz.startsWith('Australia/') ||
      tz.startsWith('Indian/')
    ) {
      return regions.find((r) => r.id === 'asia') ?? regions[0];
    }
  } catch {
    // Fallback to default
  }
  return regions.find((r) => r.default) ?? regions[0];
}
