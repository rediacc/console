/**
 * Ed25519 Signing Public Keys
 *
 * Static Ed25519 public keys for verifying signed payloads (regions, subscriptions).
 * The CLI uses these to verify that data came from the legitimate account server.
 *
 * Key rotation:
 * 1. Generate new key pair, deploy server with both old + new private keys
 * 2. Add new public key as first entry here, ship CLI update
 * 3. After deprecation period, remove old private key from server
 */

export interface SigningKey {
  /** Key identifier (referenced in signed blob's publicKeyId field) */
  keyId: string;
  /** Base64-encoded SPKI Ed25519 public key */
  publicKeySpki: string;
}

/**
 * Known Ed25519 signing public keys, newest first.
 * During key rotation, both old and new keys coexist here.
 */
export const SIGNING_KEYS: readonly SigningKey[] = [
  {
    keyId: 'v1',
    publicKeySpki: 'MCowBQYDK2VwAyEAWCQ8T/VaGggrRQZgNXBa5GkmidtctWtQtWYn8J37YRc=',
  },
] as const;

/** Current (newest) signing key. */
export const CURRENT_SIGNING_KEY: SigningKey = SIGNING_KEYS[0];
