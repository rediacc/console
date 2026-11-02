/**
 * Public half of the backup table-of-contents key, derived from the repository credential.
 *
 * Mirrors private/renet/pkg/chunkstore/toccrypt: HKDF-SHA256 over the credential's UTF-8 bytes with the lineage's
 * UTF-8 bytes as salt and info `rediacc-backup-toc-v1`, 32 bytes, used as an X25519 scalar (clamping is done by the
 * curve implementation). Only the public key leaves this module. No Unicode normalisation is applied, because the
 * Go side hashes the raw bytes and composed and decomposed forms must derive different keys.
 *
 * Imports node:crypto, so it is reachable only through the `@rediacc/shared/backup/*` subpath, never through the
 * package root that www and browser bundles load.
 */

import { createPrivateKey, createPublicKey, hkdfSync } from 'node:crypto';

const TOC_INFO = 'rediacc-backup-toc-v1';
const TOC_KEY_PREFIX = 'rediacc-toc-x25519 ';
// DER prefix of a PKCS#8 PrivateKeyInfo holding a raw 32-byte X25519 scalar.
const PKCS8_X25519_PREFIX = Buffer.from('302e020100300506032b656e04220420', 'hex');

export function deriveTocPublicKeyLine(credential: string, lineage: string): string {
  const scalar = Buffer.from(
    hkdfSync(
      'sha256',
      Buffer.from(credential, 'utf-8'),
      Buffer.from(lineage, 'utf-8'),
      TOC_INFO,
      32
    )
  );
  const priv = createPrivateKey({
    key: Buffer.concat([PKCS8_X25519_PREFIX, scalar]),
    format: 'der',
    type: 'pkcs8',
  });
  const spki = createPublicKey(priv).export({ format: 'der', type: 'spki' });
  const pub = spki.subarray(spki.length - 32);
  return `${TOC_KEY_PREFIX}${Buffer.from(pub).toString('base64')}\n`;
}
