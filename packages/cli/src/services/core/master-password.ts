/**
 * The master password of a config (PLAN-config-sealed-local.md D2, D8).
 *
 * - The password resolves from this process's cache, then `REDIACC_MASTER_PASSWORD`, then a TTY
 *   prompt, and is checked against the config's `credentials.masterPasswordVerifier` before any
 *   field is unsealed with it: a wrong password must fail here as an auth error, never reach a v2
 *   blob, where a GCM failure under a keyring key reads as key loss.
 * - Verifier v2 is `v2:` + AES-256-GCM(K_pw, "rdc-mp-verifier-v2"), where K_pw is the PBKDF2 key of
 *   the config's `encryption.kdf` (600k, derived once per process by config-seal-key.ts).
 * - A legacy verifier (the password encrypted under itself, per-blob PBKDF2 at 100k) still verifies;
 *   the storage layer rewrites it as v2 at the next write (adapters/config-file-storage.ts).
 *
 * The cache is keyed by config id AND verifier, so two configs with different passwords in one
 * process never share an entry, and a write that installs a new verifier is encrypted under the
 * password remembered for it (`rememberMasterPassword`), not under the one the old verifier took.
 */

import { importAesKey } from '@rediacc/shared/config-crypto';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import {
  derivePasswordKey,
  newSealKdf,
  openString,
  type SealKdf,
  sealString,
} from '../../adapters/config-seal-key.js';
import { nodeCryptoProvider } from '../../adapters/crypto.js';
import { t } from '../../i18n/index.js';
import { EXIT_CODES } from '../../types/index.js';
import { AuthError } from '../../utils/errors.js';
import { askPassword } from '../../utils/prompt.js';

const VERIFIER_V2_PREFIX = 'v2:';
const VERIFIER_PLAINTEXT = 'rdc-mp-verifier-v2';

interface ResolvedPassword {
  password: string;
  /** The password opened the verifier (false only for an environment value accepted unchecked). */
  verified: boolean;
  /** Installed by `rememberMasterPassword` for a new verifier: it wins over the environment variable. */
  remembered: boolean;
}

/** `<config.id>|<verifier or ''>` -> the password this process resolved for it. */
const passwordCache = new Map<string, ResolvedPassword>();

function cacheSlot(configId: string, verifier: string | null | undefined): string {
  return `${configId}|${verifier ?? ''}`;
}

/** Forget every remembered password (tests). */
export function clearMasterPasswordCache(): void {
  passwordCache.clear();
}

/**
 * Remember `password` as the one that opens `verifier` of `configId`, for a write that installs a new
 * verifier and must seal under the new password (the master-password verbs, D8).
 */
export function rememberMasterPassword(configId: string, verifier: string, password: string): void {
  passwordCache.set(cacheSlot(configId, verifier), {
    password,
    verified: true,
    remembered: true,
  });
}

/** True for a verifier written before v2 (the password encrypted under itself). */
export function isLegacyVerifier(verifier: string): boolean {
  return !verifier.startsWith(VERIFIER_V2_PREFIX);
}

async function verifierKey(configId: string, kdf: SealKdf, password: string): Promise<CryptoKey> {
  return importAesKey(new Uint8Array(await derivePasswordKey(configId, kdf, password)));
}

/** A v2 verifier of `password` under `kdf`. */
export async function makeVerifier(
  configId: string,
  kdf: SealKdf,
  password: string
): Promise<string> {
  const key = await verifierKey(configId, kdf, password);
  return `${VERIFIER_V2_PREFIX}${await sealString(key, VERIFIER_PLAINTEXT, VERIFIER_PLAINTEXT)}`;
}

/** A fresh kdf and the v2 verifier of `password` under it (a set or change of the password, D8). */
export async function newPasswordRecord(
  configId: string,
  password: string
): Promise<{ kdf: SealKdf; verifier: string }> {
  const kdf = newSealKdf();
  return { kdf, verifier: await makeVerifier(configId, kdf, password) };
}

/**
 * True when `password` opens `verifier`. A v2 verifier needs the config's kdf; a legacy one is the
 * password encrypted under itself.
 */
export async function checkVerifier(
  configId: string,
  verifier: string,
  kdf: SealKdf | undefined,
  password: string
): Promise<boolean> {
  try {
    if (isLegacyVerifier(verifier)) {
      return (await nodeCryptoProvider.decrypt(verifier, password)) === password;
    }
    if (!kdf) return false;
    const key = await verifierKey(configId, kdf, password);
    const opened = await openString(
      key,
      verifier.slice(VERIFIER_V2_PREFIX.length),
      VERIFIER_PLAINTEXT
    );
    return opened === VERIFIER_PLAINTEXT;
  } catch {
    return false;
  }
}

async function promptForPassword(): Promise<string> {
  if (!process.stdin.isTTY) {
    throw new AuthError(
      'Master password required but running in non-interactive mode. Set REDIACC_MASTER_PASSWORD environment variable.',
      EXIT_CODES.AUTH_REQUIRED
    );
  }
  return await askPassword(t('prompts.masterPassword'));
}

/**
 * `REDIACC_MASTER_PASSWORD`, else a prompt, with no verifier check: for the v2-to-v3 schema
 * migration, whose blob decrypt rejects a wrong password itself.
 */
export function resolveUncheckedMasterPassword(): Promise<string> {
  const envPassword = process.env.REDIACC_MASTER_PASSWORD;
  return envPassword ? Promise.resolve(envPassword) : promptForPassword();
}

/**
 * Check `password` against `verifier`. REDIACC_MASTER_PASSWORD against a legacy verifier it does not
 * open is accepted unchecked, as before v2 (a legacy blob rejects a wrong password itself), and is
 * never recorded as verified, so it never becomes a v2 verifier. Anything else that fails throws.
 */
async function resolveAgainst(
  config: RdcConfig,
  verifier: string,
  password: string,
  fromEnv: boolean
): Promise<ResolvedPassword> {
  if (await checkVerifier(config.id, verifier, config.encryption?.kdf, password)) {
    return { password, verified: true, remembered: false };
  }
  if (fromEnv && isLegacyVerifier(verifier)) {
    return { password, verified: false, remembered: false };
  }
  throw new AuthError('Invalid master password', EXIT_CODES.AUTH_REQUIRED);
}

/**
 * The master password of `config`, checked against its verifier. Order: a password remembered for a
 * new verifier, then `REDIACC_MASTER_PASSWORD` (it takes over from an earlier value in the same
 * process), then this process's cache, then a prompt. Without a verifier only the environment
 * variable is accepted, unchecked (a config whose password was never recorded).
 */
export async function requireMasterPassword(config: RdcConfig): Promise<string> {
  const verifier = config.credentials?.masterPasswordVerifier;
  const slot = cacheSlot(config.id, verifier);
  const cached = passwordCache.get(slot);
  if (cached?.remembered) return cached.password;

  const envPassword = process.env.REDIACC_MASTER_PASSWORD;
  if (envPassword) {
    if (cached?.password === envPassword) return envPassword;
    const resolved = verifier
      ? await resolveAgainst(config, verifier, envPassword, true)
      : { password: envPassword, verified: false, remembered: false };
    passwordCache.set(slot, resolved);
    return envPassword;
  }
  if (cached) return cached.password;
  if (!verifier) {
    throw new AuthError('No master password configured for this config.', EXIT_CODES.AUTH_REQUIRED);
  }
  const resolved = await resolveAgainst(config, verifier, await promptForPassword(), false);
  passwordCache.set(slot, resolved);
  return resolved.password;
}

/**
 * True when the password this process resolved for `verifier` of `configId` actually opened it. A
 * legacy verifier is rewritten as v2 only then, so an unchecked environment password never becomes
 * the recorded one.
 */
export function isVerifiedMasterPassword(configId: string, verifier: string): boolean {
  return passwordCache.get(cacheSlot(configId, verifier))?.verified === true;
}
