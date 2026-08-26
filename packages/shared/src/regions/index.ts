/**
 * @rediacc/shared/regions
 *
 * Region discovery and verification for multi-region data residency.
 * Provides baked-in fallback regions and Ed25519 signature verification
 * for dynamically fetched region manifests.
 */

import { importPublicKey, verifySignature } from '../subscription/crypto.js';
import { SIGNING_KEYS } from '../subscription/signing-keys.js';
import type { SignedSubscriptionBlob } from '../subscription/types.js';

// Baked-in fallback regions: a copy of the root regions.json.
//
// NOT "kept in sync by the build process", which is what this comment used to
// say -- no such process exists, and the two files were identical only because
// somebody last copied one onto the other by hand. They are now held together by
// a gate (.ci/scripts/quality/check-regions-sync.sh), which fails CI if they
// diverge; keep them in step with `cp regions.json packages/shared/src/regions/data.json`.
//
// And "fallback" overstates the runtime path: region-discovery.ts fetches
// `${SITE_URL}/regions.json`, which returns 404, so this file is not the backup
// list -- it is the ONLY list users get.
import regionsData from './data.json' with { type: 'json' };

export interface RegionInfo {
  id: string;
  label: string;
  domain: string;
  edgeDomain: string;
  default: boolean;
}

export const BAKED_IN_REGIONS: RegionInfo[] = regionsData.regions.map(
  (r: { id: string; label: string; domain: string; edgeDomain: string; default: boolean }) => ({
    id: r.id,
    label: r.label,
    domain: r.domain,
    edgeDomain: r.edgeDomain,
    default: r.default,
  })
);

export const DEFAULT_REGION: RegionInfo =
  BAKED_IN_REGIONS.find((r) => r.default) ?? BAKED_IN_REGIONS[0];

/**
 * Verify a signed regions manifest and return the regions if valid.
 * Returns null if the signature is invalid or the payload can't be parsed.
 */
export async function verifySignedRegions(
  blob: SignedSubscriptionBlob
): Promise<RegionInfo[] | null> {
  // Register known signing keys (idempotent)
  for (const key of SIGNING_KEYS) {
    await importPublicKey(key.keyId, key.publicKeySpki);
  }

  const valid = await verifySignature(blob);
  if (!valid) return null;

  try {
    const regions = JSON.parse(blob.payload) as RegionInfo[];
    if (!Array.isArray(regions) || regions.length === 0) return null;
    return regions;
  } catch {
    return null;
  }
}
