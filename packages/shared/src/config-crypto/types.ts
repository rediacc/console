/**
 * Config Storage Encryption Types
 */

/** Plaintext envelope — server can read these fields without decryption */
export interface ConfigEnvelope {
  id: string;
  version: number;
  teamId?: string;
  orgId?: string;
  lastModified?: string;
  sdkEpoch: number;
}

/** The sensitive config data that gets encrypted */
export interface ConfigSensitiveData {
  machines?: Record<string, unknown>;
  repositories?: Record<string, unknown>;
  storages?: Record<string, unknown>;
  ssh?: Record<string, unknown>;
}

/** Result of selective encryption: plaintext envelope + encrypted blob */
export interface EncryptedConfigPayload {
  envelope: ConfigEnvelope;
  encryptedBlob: string; // base64(clientEnc_CEK(serverKeyEnc_SDK(sensitiveData)))
  hmac: string; // HMAC-SHA256 over encryptedBlob, keyed with CEK
}

/** Full config (envelope + sensitive data merged) */
export type FullConfig = ConfigEnvelope & ConfigSensitiveData;

/** Result of AES-256-GCM encryption: IV + ciphertext (includes auth tag) */
export interface AesEncryptResult {
  iv: Uint8Array;
  ct: Uint8Array;
}

/** Serialized encrypted data: base64(iv + ct) */
export type EncryptedString = string;

/** CEK handoff blob for X25519-based member key distribution */
export interface CekHandoffBlob {
  v: number; // protocol version
  eph: string; // base64 ephemeral X25519 public key
  salt: string; // base64 HKDF salt
  iv: string; // base64 AES-GCM IV
  ct: string; // base64 AES-GCM ciphertext (encrypted CEK)
}
