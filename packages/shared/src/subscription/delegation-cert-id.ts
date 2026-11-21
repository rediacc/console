/**
 * Delegation cert identifier.
 *
 * A signed delegation cert carries no id of its own (DelegationCert in
 * types.ts), so the CLI and the on-premise account server name a cert by the
 * same derived value: the first 16 lowercase hex characters of SHA-256 over
 * the UTF-8 bytes of the base64 `payload` string. The payload is what the
 * upstream signature covers, so two certs share an id only when they share
 * every signed field.
 */

import type { SignedDelegationCert } from './types.js';

/** Length of a delegation cert id in hex characters. */
export const DELEGATION_CERT_ID_LENGTH = 16;

/** The id of a signed delegation cert; the module comment gives the definition. */
export async function delegationCertId(
  signed: Pick<SignedDelegationCert, 'payload'>
): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(signed.payload));
  const bytes = new Uint8Array(digest);
  let hex = '';
  for (let i = 0; i < DELEGATION_CERT_ID_LENGTH / 2; i++) {
    hex += bytes[i].toString(16).padStart(2, '0');
  }
  return hex;
}
