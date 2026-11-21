/**
 * Delegation certificates: the signed cert JSON `{payload, signature, publicKeyId}`, whose `payload`
 * is itself base64 JSON. The box holds it as `data/web/delegation-cert.json`; the account server's
 * `POST /delegation/issue` answers carry its base64.
 */

import type { DelegationCert, SignedDelegationCert } from '@rediacc/shared/subscription';

export class CertError extends Error {}

function fromBase64(text: string): string {
  return Buffer.from(text, 'base64').toString('utf-8');
}

function isSigned(value: unknown): value is SignedDelegationCert {
  const v = value as Partial<SignedDelegationCert> | null;
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof v.payload === 'string' &&
    typeof v.signature === 'string' &&
    typeof v.publicKeyId === 'string'
  );
}

/** A signed cert from what a file or an answer holds: the cert JSON, an answer carrying `cert`, or the base64 of either. */
export function parseSignedCert(text: string): SignedDelegationCert {
  const trimmed = text.trim();
  const candidates = [trimmed];
  if (!trimmed.startsWith('{')) candidates.push(fromBase64(trimmed));
  for (const candidate of candidates) {
    let doc: unknown;
    try {
      doc = JSON.parse(candidate);
    } catch {
      continue;
    }
    const inner = (doc as { cert?: unknown } | null)?.cert;
    if (isSigned(doc)) return doc;
    if (isSigned(inner)) return inner;
  }
  throw new CertError('not a signed delegation certificate');
}

export function certToBase64(cert: SignedDelegationCert): string {
  const json = JSON.stringify({
    payload: cert.payload,
    signature: cert.signature,
    publicKeyId: cert.publicKeyId,
  });
  return Buffer.from(json, 'utf-8').toString('base64');
}

/** The decoded payload of a signed cert, or a `CertError` naming what was unreadable. */
export function decodeCert(cert: SignedDelegationCert): DelegationCert {
  try {
    const payload = JSON.parse(fromBase64(cert.payload)) as DelegationCert;
    if (!payload.subscriptionId || !payload.delegatedPublicKey) {
      throw new CertError('the certificate payload names no subscription or key');
    }
    return payload;
  } catch (error) {
    if (error instanceof CertError) throw error;
    throw new CertError('the certificate payload is not readable JSON');
  }
}

/** Refuse a cert issued for another key than the one the box generated. */
export function assertCertKey(cert: DelegationCert, boxPublicKey: string): void {
  if (cert.delegatedPublicKey !== boxPublicKey) {
    throw new CertError('key-mismatch');
  }
}
