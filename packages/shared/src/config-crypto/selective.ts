/**
 * Selective Encryption
 *
 * Separates config into plaintext envelope (version, id) and encrypted
 * sensitive data (machines, ssh, repositories, storages).
 */

import { SENSITIVE_FIELDS } from './constants.js';
import { hmacCompute, hmacVerify } from './hmac.js';
import { configDecrypt, configEncrypt } from './layers.js';
import type {
  ConfigEnvelope,
  ConfigSensitiveData,
  EncryptedConfigPayload,
  FullConfig,
} from './types.js';

/**
 * Encrypt a full config into an envelope + encrypted blob.
 *
 * Plaintext envelope fields: id, version, teamId, orgId, lastModified, sdkEpoch
 * Encrypted fields: machines, repositories, storages, ssh
 *
 * @param config - Full config object
 * @param sdkDerived - Time-windowed SDK key
 * @param cek - Client Encryption Key
 * @param sdkEpoch - Current SDK epoch number
 * @returns Envelope (plaintext) + encrypted blob + HMAC
 */
export async function selectiveEncrypt(
  config: FullConfig,
  sdkDerived: CryptoKey,
  cek: CryptoKey,
  sdkEpoch: number
): Promise<EncryptedConfigPayload> {
  // Extract envelope (plaintext)
  const envelope: ConfigEnvelope = {
    id: config.id,
    version: config.version,
    sdkEpoch,
  };
  if (config.teamId) envelope.teamId = config.teamId;
  if (config.orgId) envelope.orgId = config.orgId;
  if (config.lastModified) envelope.lastModified = config.lastModified;

  // Extract sensitive data
  const sensitive: ConfigSensitiveData = {};
  for (const field of SENSITIVE_FIELDS) {
    if (config[field] !== undefined) {
      sensitive[field] = config[field];
    }
  }

  // Encrypt sensitive data (Layer 1: SDK, Layer 2: CEK)
  const sensitiveJson = JSON.stringify(sensitive);
  const encryptedBlob = await configEncrypt(sensitiveJson, sdkDerived, cek);

  // Compute HMAC over encrypted blob
  const hmac = await hmacCompute(encryptedBlob, cek);

  return { envelope, encryptedBlob, hmac };
}

/**
 * Decrypt an encrypted config payload back into a full config.
 *
 * @param payload - Envelope + encrypted blob + HMAC
 * @param cek - Client Encryption Key
 * @param sdkDerived - Time-windowed SDK key
 * @returns Full config object
 * @throws If HMAC verification fails (tamper detection)
 */
export async function selectiveDecrypt(
  payload: EncryptedConfigPayload,
  cek: CryptoKey,
  sdkDerived: CryptoKey
): Promise<FullConfig> {
  // Verify HMAC first (tamper detection)
  const hmacValid = await hmacVerify(payload.encryptedBlob, cek, payload.hmac);
  if (!hmacValid) {
    throw new Error(
      'Config integrity check failed. The encrypted data may have been corrupted or tampered with.'
    );
  }

  // Decrypt sensitive data (Layer 2: CEK, Layer 1: SDK)
  const sensitiveJson = await configDecrypt(payload.encryptedBlob, cek, sdkDerived);
  const sensitive = JSON.parse(sensitiveJson) as ConfigSensitiveData;

  // Merge envelope + sensitive data
  return {
    ...payload.envelope,
    ...sensitive,
  };
}
