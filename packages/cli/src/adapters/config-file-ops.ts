/**
 * Helpers of ConfigFileStorage that read no instance state: the reserved-file
 * test, the request-scoped write path, and the at-rest seal inspections.
 */

import { CONTEXT_DEFAULTS } from '@rediacc/shared/config/defaults';
import {
  hasRemoteConfig,
  type RdcConfig,
  usesKeyring,
  usesMasterPassword,
} from '@rediacc/shared/config-schema';
import { t } from '../i18n/index.js';
import {
  CONFIG_WRITE_UNAVAILABLE,
  ConfigWriteUnavailableError,
  configWriteFailureCode,
  currentCommandName,
} from '../services/core/config-write-errors.js';
import { currentRequestConfig, type RequestConfigScope } from '../services/core/request-context.js';
import { parseJsonText } from '../utils/json-text.js';
import { loadKey, mintKey, newSealKdf, SealKeyLostError } from './config-seal-key.js';

/** Files in config dir that are not config files */
const EXCLUDED_FILES = new Set(['update-state.json', 'server.json', 'api-token.json']);

/**
 * True for JSON files in the config dir that are NOT rdc configs: the updater
 * state, and subscription device tokens (api-token-<config>.json, written by
 * services/subscription-auth.ts).
 *
 * `server.json` and the bare `api-token.json` are legacy artifacts from the
 * pre-universe layout; they are never configs. The CLI no longer reads or
 * writes them, but a stray file with either name would otherwise be parsed as
 * a config named `server`/`api-token`, so they stay on the exclusion list.
 */
export function isReservedFile(fileName: string): boolean {
  return EXCLUDED_FILES.has(fileName) || fileName.startsWith('api-token-');
}

/**
 * Refuse a file-level operation (create, delete, restore) inside a request that
 * runs against a request-scoped config: there is no file behind it to act on.
 */
export function refuseInRequestScope(what: string, name: string): void {
  if (currentRequestConfig()) {
    throw new Error(
      `Cannot ${what} config "${name}" here: this command runs against the config granted for its session, not a config file.`
    );
  }
}

/**
 * How a request-scoped write lands: `stored` changes the stored document (a spec
 * or state write), `cache` only this request's copy (updateCache).
 */
export type ScopedWriteKind = 'spec' | 'state' | 'cache';

/**
 * Apply a write to a request-scoped config (request-context.ts RequestConfigScope).
 *
 * With a writeback, a spec or state write is pushed to the config store, the
 * updater applied to the store's newest copy (and again after a version
 * conflict), and the scope re-seated on what the store now holds. Without one,
 * a spec write is refused before the updater runs, ending the command before
 * its host job starts, and a state write applies in memory for the request. A
 * cache write always stays in memory. A failed or refused write records its code
 * on the scope for the served result.
 */
export async function writeScoped(
  scope: RequestConfigScope,
  updater: (config: RdcConfig) => RdcConfig,
  kind: ScopedWriteKind
): Promise<RdcConfig> {
  if (kind !== 'cache' && scope.writeback) {
    try {
      scope.config = await scope.writeback.write(updater);
    } catch (error) {
      scope.writeFailure = configWriteFailureCode(error);
      throw error;
    }
  } else if (kind === 'spec') {
    scope.writeFailure = CONFIG_WRITE_UNAVAILABLE;
    throw new ConfigWriteUnavailableError(currentCommandName());
  } else {
    scope.config = updater(scope.config);
  }
  // The memoized resource view was built from the previous config.
  scope.resourceState = undefined;
  scope.readCopy = structuredClone(scope.config);
  return scope.config;
}

/** True when any blob of the config is legacy (no `v`): opening or re-sealing it needs the password. */
export function hasLegacyBlobs(config: RdcConfig): boolean {
  return Object.values(config.encryption?.encryptedFields ?? {}).some((blob) => blob.v !== 2);
}

/** True when the config still carries blobs this cycle never opened (an at-rest copy, not a decrypted one). */
export function hasUnopenedBlobs(config: RdcConfig): boolean {
  return Object.keys(config.encryption?.encryptedFields ?? {}).length > 0;
}

/**
 * What a reader of a stale copy would need to open it: the mode, the keyring key and the password
 * salt. When it changes between the previous file and the new one, the `.bak` copy is overwritten
 * too, so no plaintext, old-key or old-password copy stays one rename away (D5).
 */
export function sealIdentity(encryption: RdcConfig['encryption']): string {
  return [
    encryption?.mode ?? CONTEXT_DEFAULTS.CONFIG_KIND,
    encryption?.keyringId ?? '',
    encryption?.kdf?.salt ?? '',
  ].join('|');
}

/** The `encryption` record of a config file's text, when it parses; never throws. */
export function encryptionOfText(text: string): RdcConfig['encryption'] {
  try {
    return (parseJsonText(text) as RdcConfig | null)?.encryption;
  } catch {
    return undefined;
  }
}

/** Config names the file-store refusal (D6) was printed for in this process: one line per config. */
const fileStoreRefusalShown = new Set<string>();

/** Forget which configs printed the file-store refusal (tests). */
export function resetFileStoreRefusalNotice(): void {
  fileStoreRefusalShown.clear();
}

/**
 * Print the D6 refusal once per config per process: the file store keeps keys in a plain file, so
 * a seal under it would protect nothing.
 */
function noteFileStoreRefusal(name: string): void {
  if (fileStoreRefusalShown.has(name)) return;
  fileStoreRefusalShown.add(name);
  process.stderr.write(`${t('commands.config.seal.fileStoreRefused', { name })}\n`);
}

/**
 * The keyring key a seal upgrade uses: the previous file's own key when that file was already
 * keyring-sealed and its key still loads (a writer saving a stale plaintext copy must not orphan
 * it), else a freshly minted one, returned as `minted` so a failed write can delete it.
 */
async function upgradeKey(
  config: RdcConfig,
  previous: RdcConfig['encryption']
): Promise<{ keyringId: string; minted?: string }> {
  if (previous?.keyringId && usesKeyring(previous.mode)) {
    try {
      await loadKey(config.id, previous.keyringId);
      return { keyringId: previous.keyringId };
    } catch (error) {
      if (!(error instanceof SealKeyLostError)) throw error;
    }
  }
  const keyringId = await mintKey();
  return { keyringId, minted: keyringId };
}

/**
 * Seal on next write (D5). A remote-enabled config in `plaintext` or `master-password` mode, not
 * opted out, moves to `keyring` (`keyring+master-password` when a password is part of it). A config
 * still holding blobs this cycle never opened waits for the next decrypted write, since a blob
 * cannot be carried across a key change. Under `REDIACC_SECRET_STORE=file` the write keeps its
 * mode and the refusal is printed (D6). Local-only configs are never upgraded.
 */
export async function sealUpgrade(
  config: RdcConfig,
  name: string,
  previous: RdcConfig['encryption']
): Promise<{ config: RdcConfig; minted?: string }> {
  const encryption = config.encryption;
  const mode = encryption?.mode ?? CONTEXT_DEFAULTS.CONFIG_KIND;
  if (!hasRemoteConfig(config) || encryption?.sealOptOut) return { config };
  if (mode !== 'plaintext' && mode !== 'master-password') return { config };
  if (hasUnopenedBlobs(config)) return { config };
  if (process.env.REDIACC_SECRET_STORE === 'file') {
    noteFileStoreRefusal(name);
    return { config };
  }
  const stacked = mode === 'master-password' || Boolean(config.credentials?.masterPasswordVerifier);
  const { keyringId, minted } = await upgradeKey(config, previous);
  return {
    config: {
      ...config,
      encryption: {
        ...encryption,
        mode: stacked ? 'keyring+master-password' : 'keyring',
        keyringId,
      },
    },
    minted,
  };
}

/**
 * Give a password-sealed config a v2 verifier (D8): a legacy verifier is rewritten once the
 * password it verified is known, and a config with none (a password only ever given through
 * REDIACC_MASTER_PASSWORD) gets one from the password its fields are sealed under, so a wrong
 * password fails as an auth error instead of reading as a lost keyring key. The 600k kdf is
 * created when the config has none yet; the same write re-seals the fields under it.
 */
export async function upgradeVerifier(
  config: RdcConfig,
  requirePassword: (config: RdcConfig) => Promise<string>
): Promise<RdcConfig> {
  const encryption = config.encryption;
  const verifier = config.credentials?.masterPasswordVerifier;
  if (!encryption || !usesMasterPassword(encryption.mode)) return config;
  const mp = await import('../services/core/master-password.js');
  if (verifier && !mp.isLegacyVerifier(verifier)) return config;
  const password = await requirePassword(config);
  if (verifier && !mp.isVerifiedMasterPassword(config.id, verifier)) return config;
  const kdf = encryption.kdf ?? newSealKdf();
  const next = await mp.makeVerifier(config.id, kdf, password);
  mp.rememberMasterPassword(config.id, next, password);
  return {
    ...config,
    credentials: { ...config.credentials, masterPasswordVerifier: next },
    encryption: { ...encryption, kdf },
  };
}
