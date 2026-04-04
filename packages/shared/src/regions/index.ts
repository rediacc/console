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

// Baked-in fallback regions (imported from regions.json at build time).
// These are always available, even offline or when the marketing site is down.
import regionsData from '../../../../regions.json';

export interface RegionInfo {
  id: string;
  label: string;
  domain: string;
  default: boolean;
}

export const BAKED_IN_REGIONS: RegionInfo[] = regionsData.regions.map(
  (r: { id: string; label: string; domain: string; default: boolean }) => ({
    id: r.id,
    label: r.label,
    domain: r.domain,
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
