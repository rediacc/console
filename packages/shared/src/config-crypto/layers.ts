/**
 * Triple-Layer Encryption/Decryption
 *
 * Layer 1 (Inner — SDK):  AES-GCM(sdk_derived, plaintext)
 * Layer 2 (Middle — CEK): AES-GCM(cek, layer1_output)
 * Layer 3 (Outer — Org):  AES-GCM(orgKey, layer2_output) — server-side only
 *
 * At rest: orgEnc(clientEnc_CEK(serverKeyEnc_SDK(plaintext)))
 */

import { aesDecryptFromString, aesEncryptToString, importAesKey } from './aes.js';
import { ConfigIntegrityError } from './errors.js';

const encoder = new TextEncoder();
const decoder = new TextDecoder();

/**
 * Client-side encryption: Layer 1 (SDK) + Layer 2 (CEK).
 *
 * @param plaintext - JSON string of sensitive config data
 * @param sdkDerived - Time-windowed SDK key from server
 * @param cek - Client Encryption Key
 * @param aad - Envelope v3 binding (selective.ts `envelopeAad`), authenticated by both layers
 * @returns Base64-encoded doubly-encrypted blob
 */
export async function configEncrypt(
  plaintext: string,
  sdkDerived: CryptoKey,
  cek: CryptoKey,
  aad?: Uint8Array
): Promise<string> {
  // Layer 1: Encrypt with SDK (inner layer)
  const sdkEncrypted = await aesEncryptToString(sdkDerived, encoder.encode(plaintext), aad);

  // Layer 2: Encrypt with CEK (middle layer)
  return aesEncryptToString(cek, encoder.encode(sdkEncrypted), aad);
}

/**
 * Client-side decryption: Layer 2 (CEK) + Layer 1 (SDK).
 *
 * @param clientEncrypted - Base64-encoded doubly-encrypted blob
 * @param cek - Client Encryption Key
 * @param sdkDerived - Time-windowed SDK key from server
 * @param aad - The binding the blob was sealed with (none for an envelope v2 blob)
 * @returns Decrypted JSON string
 * @throws ConfigIntegrityError when the CEK layer does not open: another CEK, or (with `aad`) a blob
 *   sealed for another config, version, team or commitment set. A failure of the SDK layer below
 *   it passes through as the raw WebCrypto error.
 */
export async function configDecrypt(
  clientEncrypted: string,
  cek: CryptoKey,
  sdkDerived: CryptoKey,
  aad?: Uint8Array
): Promise<string> {
  // Layer 2: Decrypt CEK layer (middle)
  let sdkEncryptedBytes: Uint8Array;
  try {
    sdkEncryptedBytes = await aesDecryptFromString(cek, clientEncrypted, aad);
  } catch {
    throw new ConfigIntegrityError();
  }
  const sdkEncrypted = decoder.decode(sdkEncryptedBytes);

  // Layer 1: Decrypt SDK layer (inner)
  const plaintextBytes = await aesDecryptFromString(sdkDerived, sdkEncrypted, aad);
  return decoder.decode(plaintextBytes);
}

/**
 * Server-side encryption: Layer 3 (Org passphrase).
 *
 * @param data - Client-encrypted blob (already Layer 1+2 encrypted)
 * @param orgPassphrase - Organization passphrase (raw bytes or string)
 * @returns Base64-encoded triply-encrypted blob
 */
export async function orgEncrypt(data: string, orgPassphrase: Uint8Array): Promise<string> {
  const orgKey = await importAesKey(orgPassphrase);
  return aesEncryptToString(orgKey, encoder.encode(data));
}

/**
 * Server-side decryption: Layer 3 (Org passphrase).
 *
 * @param orgEncrypted - Base64-encoded triply-encrypted blob
 * @param orgPassphrase - Organization passphrase (raw bytes)
 * @returns Client-encrypted blob (still Layer 1+2 encrypted)
 */
export async function orgDecrypt(orgEncrypted: string, orgPassphrase: Uint8Array): Promise<string> {
  const orgKey = await importAesKey(orgPassphrase);
  const decrypted = await aesDecryptFromString(orgKey, orgEncrypted);
  return decoder.decode(decrypted);
}
