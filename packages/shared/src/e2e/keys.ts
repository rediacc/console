/**
 * Server E2E Public Keys
 *
 * Static X25519 public keys for the account server.
 * The CLI uses these to encrypt requests — only the server with the
 * corresponding private key can decrypt.
 *
 * Key rotation:
 * 1. Generate new key pair on server, deploy with both old + new private keys
 * 2. Add new public key as first entry here, ship CLI update
 * 3. After deprecation period, remove old private key from server
 */

export interface ServerE2eKey {
  /** Key identifier (referenced in envelope's `kid` field) */
  keyId: string;
  /** Base64-encoded SPKI X25519 public key */
  publicKeySpki: string;
}

/**
 * Known server X25519 public keys, newest first.
 * During key rotation, both old and new keys coexist here.
 */
export const SERVER_E2E_KEYS: readonly ServerE2eKey[] = [
  {
    keyId: 'v1',
    publicKeySpki: 'MCowBQYDK2VuAyEALY64atDar/bIwKoYEJPoYphKKZ6KUIkPzIHdfH6nKg8=',
  },
] as const;

/** Current (newest) server key — CLI always uses this for encryption. */
export const CURRENT_SERVER_E2E_KEY: ServerE2eKey = SERVER_E2E_KEYS[0];
