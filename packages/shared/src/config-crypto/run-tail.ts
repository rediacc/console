/**
 * Sealed run tail (agent/plans/PLAN-console-run-index.md D3).
 *
 * The executor seals the last RUN_TAIL_MAX_BYTES of a run's stdout and stderr under an HKDF subkey
 * of the session CEK, so the account server stores the tail without ever reading command output.
 * The browser opens it only while the config is unlocked. The AAD binds the ciphertext to its run:
 * a tail copied onto another run row fails to open.
 *
 * Web Crypto only, so it runs in Node, Workers and browsers.
 */

import { aesDecryptFromString, aesEncryptToString } from './aes.js';
import { hkdfDeriveKey } from './hkdf.js';

/** HKDF info string of the run-tail subkey. */
export const RUN_TAIL_INFO = 'rediacc/run-tail/v1';
/** Largest tail kept, in UTF-8 bytes. */
export const RUN_TAIL_MAX_BYTES = 8 * 1024;

const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });

function tailKey(cek: Uint8Array): Promise<CryptoKey> {
  return hkdfDeriveKey(cek, new Uint8Array(0), RUN_TAIL_INFO);
}

function tailAad(orgId: string, runId: string): Uint8Array {
  // JSON keeps the pair unambiguous when an id contains the separator.
  return encoder.encode(JSON.stringify([orgId, runId]));
}

/**
 * Keep the last RUN_TAIL_MAX_BYTES of `bytes`, moving the cut forward past UTF-8 continuation bytes
 * so the kept tail starts on a character boundary.
 */
function cutFromFront(bytes: Uint8Array): Uint8Array {
  if (bytes.length <= RUN_TAIL_MAX_BYTES) return bytes;
  let start = bytes.length - RUN_TAIL_MAX_BYTES;
  while (start < bytes.length && (bytes[start] & 0xc0) === 0x80) start++;
  return bytes.subarray(start);
}

/** Seal a run's output tail: base64(iv + ciphertext). A text over 8 KiB is cut from the front first. */
export async function sealRunTail(
  cek: Uint8Array,
  orgId: string,
  runId: string,
  text: string
): Promise<string> {
  const plaintext = cutFromFront(encoder.encode(text));
  return aesEncryptToString(await tailKey(cek), plaintext, tailAad(orgId, runId));
}

/** Open a sealed tail. Throws when the CEK, the org or the run id differ from the sealing call's. */
export async function openRunTail(
  cek: Uint8Array,
  orgId: string,
  runId: string,
  sealed: string
): Promise<string> {
  const plaintext = await aesDecryptFromString(await tailKey(cek), sealed, tailAad(orgId, runId));
  return decoder.decode(plaintext);
}
