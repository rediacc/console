/**
 * Per-config content keys (envelope v4, agent/programs/remote-mcp/02-decisions.md D56).
 *
 * Each config gets its own random AES-256 content key. The config blob is sealed under that key
 * instead of the org CEK, and the content key travels in the envelope wrapped under the CEK:
 *
 *   wrappedConfigKey = AES-GCM(CEK, raw content key,
 *     AAD = 'rediacc-config-key-v1' NUL canonical({ storeId, configId, teamId | null, configKeyVersion, cekGeneration }))
 *
 * A member with a key slot unwraps the CEK and then any content key it may read; an agent grant is
 * handed one config's content key and nothing else (PLAN-rmcp-agent-grants.md Design 1), so a leaked
 * grant exposes one config. The wrap AAD pins the wrap to its config, team, key version and CEK
 * generation: a wrap moved to another config or team, relabelled with another key version, or
 * swapped in from another config does not open.
 *
 * The field-commitment key and the pointer-blinding key of a v4 envelope derive from the content
 * key (selective.ts), so a holder of one config's content key can read and write that config and no
 * other.
 */

import {
  aesDecryptFromString,
  aesEncryptToString,
  exportAesKey,
  generateAesKey,
  importAesKey,
} from './aes.js';
import { canonicalize } from './canonical.js';
import { ConfigIntegrityError } from './errors.js';

const WRAP_AAD_DOMAIN = new TextEncoder().encode('rediacc-config-key-v1\0');

/** What a wrapped content key is bound to. */
export interface ConfigKeyBinding {
  storeId: string;
  configId: string;
  /** The config's team, or null/absent for the org-level config. */
  teamId?: string | null;
  /** The content key's version: 1 for a config's first key, +1 on each content-key rotation. */
  configKeyVersion: number;
  /** The store's CEK generation the wrap is made under. */
  cekGeneration: number;
}

/** A config's content key with the version and CEK generation its wrap is bound to. */
export interface ConfigContentKey {
  key: CryptoKey;
  version: number;
  cekGeneration: number;
}

function assertNonNegativeInteger(name: string, value: number, min: number): void {
  if (!Number.isInteger(value) || value < min) {
    throw new Error(`${name} must be an integer >= ${min} (got ${value})`);
  }
}

/** Generate a fresh 256-bit content key (extractable, so it can be wrapped). */
export function generateConfigKey(): Promise<CryptoKey> {
  return generateAesKey();
}

/** The additional authenticated data of a content-key wrap (see the header). */
export function configKeyWrapAad(binding: ConfigKeyBinding): Uint8Array {
  assertNonNegativeInteger('configKeyVersion', binding.configKeyVersion, 1);
  assertNonNegativeInteger('cekGeneration', binding.cekGeneration, 0);
  const body = canonicalize({
    storeId: binding.storeId,
    configId: binding.configId,
    teamId: binding.teamId ?? null,
    configKeyVersion: binding.configKeyVersion,
    cekGeneration: binding.cekGeneration,
  });
  const out = new Uint8Array(WRAP_AAD_DOMAIN.length + body.length);
  out.set(WRAP_AAD_DOMAIN, 0);
  out.set(body, WRAP_AAD_DOMAIN.length);
  return out;
}

/** Wrap a content key under the CEK for `binding`. Returns base64(iv + ciphertext). */
export async function wrapConfigKey(
  configKey: CryptoKey,
  cek: CryptoKey,
  binding: ConfigKeyBinding
): Promise<string> {
  return aesEncryptToString(cek, await exportAesKey(configKey), configKeyWrapAad(binding));
}

/**
 * Unwrap a content key with the CEK. `binding` comes from the reader's own pointer plus the key
 * version and CEK generation the envelope names, which the tag then authenticates.
 *
 * @throws ConfigIntegrityError when the wrap does not open under `cek` and `binding`.
 */
export async function unwrapConfigKey(
  wrappedConfigKey: string,
  cek: CryptoKey,
  binding: ConfigKeyBinding
): Promise<CryptoKey> {
  const aad = configKeyWrapAad(binding);
  let raw: Uint8Array;
  try {
    raw = await aesDecryptFromString(cek, wrappedConfigKey, aad);
  } catch {
    throw new ConfigIntegrityError(
      'Config key integrity check failed: the wrapped content key was not sealed for this config, key version and CEK.'
    );
  }
  return importAesKey(raw);
}
