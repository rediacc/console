/**
 * The policy record: the authorization policy of one config entry, sealed in its own record under
 * the store CEK instead of inside the config blob (agent/plans/PLAN-rmcp-policy-record.md Design 1).
 *
 * The record travels as `{version, cekGeneration, blob}` (Design 3), with no SDK epoch, so the blob
 * is one AES-256-GCM layer under the CEK; the server adds the org-passphrase layer at rest as it
 * does for configs. The AAD binds the blob to its record:
 *
 *   'rediacc-policy-aad-v1' NUL canonical({ v: 1, storeId, configId, teamId | null, version, cekGeneration })
 *
 * A reader rebuilds it from its OWN pointer plus the version and generation the record carries, so
 * a blob served for another store, config or team, under another version (a replay of an older
 * record under a newer number) or another CEK generation fails the GCM tag. The version is
 * therefore authentic, which is what makes a client-side high-water mark meaningful.
 *
 * Like the rest of config-crypto this module does not know the policy shape: it seals and opens a
 * JSON value, and the caller parses it with `PolicyDocumentSchema` (packages/shared/src/policy).
 */

import { aesDecryptFromString, aesEncryptToString } from './aes.js';
import { canonicalize } from './canonical.js';

const POLICY_AAD_DOMAIN = new TextEncoder().encode('rediacc-policy-aad-v1\0');

/** What a policy blob is sealed for. */
export interface PolicyRecordBinding {
  storeId: string;
  configId: string;
  /** The config's team, or null/absent for the org-level config. */
  teamId?: string | null;
  /** The record version the blob is written as (1 for the first save). */
  version: number;
  /** The store's CEK generation the blob is sealed under. */
  cekGeneration: number;
}

/** The record as the account server stores and serves it (Design 3). */
export interface PolicyRecord {
  version: number;
  cekGeneration: number;
  blob: string;
}

/**
 * The policy blob did not open under this CEK and binding: another store, config, team, version or
 * CEK generation, a different CEK, or a damaged blob.
 */
export class PolicyRecordIntegrityError extends Error {
  constructor(
    message = 'Policy record integrity check failed: the record was not sealed for this config, version and key.'
  ) {
    super(message);
    this.name = 'PolicyRecordIntegrityError';
  }
}

function assertBinding(binding: PolicyRecordBinding): void {
  if (!Number.isInteger(binding.version) || binding.version < 1) {
    throw new Error(`Policy record version must be a positive integer (got ${binding.version})`);
  }
  if (!Number.isInteger(binding.cekGeneration) || binding.cekGeneration < 0) {
    throw new Error(
      `Policy record cekGeneration must be a non-negative integer (got ${binding.cekGeneration})`
    );
  }
}

/** The additional authenticated data of a policy blob (see the header). */
export function policyRecordAad(binding: PolicyRecordBinding): Uint8Array {
  assertBinding(binding);
  const body = canonicalize({
    v: 1,
    storeId: binding.storeId,
    configId: binding.configId,
    teamId: binding.teamId ?? null,
    version: binding.version,
    cekGeneration: binding.cekGeneration,
  });
  const out = new Uint8Array(POLICY_AAD_DOMAIN.length + body.length);
  out.set(POLICY_AAD_DOMAIN, 0);
  out.set(body, POLICY_AAD_DOMAIN.length);
  return out;
}

/** Seal a policy document (any JSON value) for `binding`. Returns the record to PUT. */
export async function encryptPolicyRecord(
  document: unknown,
  cek: CryptoKey,
  binding: PolicyRecordBinding
): Promise<PolicyRecord> {
  const blob = await aesEncryptToString(
    cek,
    new TextEncoder().encode(JSON.stringify(document)),
    policyRecordAad(binding)
  );
  return { version: binding.version, cekGeneration: binding.cekGeneration, blob };
}

/**
 * Open a pulled policy record. The store, config and team come from the reader's own pointer; the
 * version and generation come from the record and are authenticated by the tag.
 *
 * @returns the parsed JSON value; the caller validates it with `PolicyDocumentSchema`.
 * @throws PolicyRecordIntegrityError when the blob does not open under `cek` and that binding.
 */
export async function decryptPolicyRecord(
  record: PolicyRecord,
  cek: CryptoKey,
  pointer: Pick<PolicyRecordBinding, 'storeId' | 'configId' | 'teamId'>
): Promise<unknown> {
  const aad = policyRecordAad({
    ...pointer,
    version: record.version,
    cekGeneration: record.cekGeneration,
  });
  let plaintext: Uint8Array;
  try {
    plaintext = await aesDecryptFromString(cek, record.blob, aad);
  } catch {
    throw new PolicyRecordIntegrityError();
  }
  return JSON.parse(new TextDecoder().decode(plaintext)) as unknown;
}
