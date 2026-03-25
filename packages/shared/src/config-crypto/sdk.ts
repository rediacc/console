/**
 * SDK Time-Windowed Key Derivation
 *
 * The master SDK never leaves the server. Clients receive a time-windowed
 * derived key that's valid for one epoch (default: 5 minutes).
 *
 * sdk_derived = HKDF(sdkMaster, epoch_string)
 * epoch = floor(timestamp / windowSeconds)
 */

import { HKDF_INFO, SDK_WINDOW_SECONDS } from './constants.js';
import { hkdfDeriveKey } from './hkdf.js';
import { randomBytes } from './aes.js';

/**
 * Get the current SDK epoch number.
 *
 * @param windowSeconds - Time window in seconds (default: 300 = 5 minutes)
 * @param timestamp - Unix timestamp in seconds (default: now)
 * @returns Epoch number (integer)
 */
export function sdkGetEpoch(
  windowSeconds: number = SDK_WINDOW_SECONDS,
  timestamp?: number
): number {
  const ts = timestamp ?? Math.floor(Date.now() / 1000);
  return Math.floor(ts / windowSeconds);
}

/**
 * Derive a time-windowed SDK key from the master SDK.
 *
 * @param sdkMaster - The master SDK key (raw bytes, never leaves server)
 * @param epoch - The epoch number (from sdkGetEpoch)
 * @returns Derived AES-256-GCM key for this epoch
 */
export async function sdkDerive(sdkMaster: Uint8Array, epoch: number): Promise<CryptoKey> {
  // Use the epoch as salt (converted to bytes)
  const epochBytes = new TextEncoder().encode(String(epoch));
  return hkdfDeriveKey(sdkMaster, epochBytes, HKDF_INFO.SDK_DERIVE);
}

/**
 * Generate a random master SDK key (32 bytes).
 * Called once during config store setup. Stored encrypted on the server.
 */
export function generateSdkMaster(): Uint8Array {
  return randomBytes(32);
}
