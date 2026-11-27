import { createCipheriv, createDecipheriv, hkdfSync, randomBytes } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { SUBSCRIPTION_DEFAULTS } from '@rediacc/shared/config';
import { type EncryptionMode, usesKeyring } from '@rediacc/shared/config-schema';
import { getConfigDir } from '@rediacc/shared/paths';
import { loadKeySync } from '../../adapters/config-seal-key.js';
import { parseJsonText } from '../../utils/json-text.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { readAccountPointer } from './account-pointer.js';

const SUBSCRIPTION_TOKEN_ENV = 'REDIACC_TOKEN';

export interface StoredSubscriptionToken {
  token: string;
  serverUrl: string;
  subscriptionId?: string;
  orgId?: string;
  orgName?: string;
  teamId?: string;
  teamName?: string;
}

export function normalizeServerUrl(serverUrl: string): string {
  return serverUrl.replace(/\/+$/, '');
}

/**
 * Get the subscription token file path for a config.
 * Per-config: `api-token-{name}.json` (default config included, so
 * `api-token-rediacc.json`). Defaults to the effective config name. While the
 * config is on a preview, the preview's own `api-token-{name}.preview-{preview}.json`,
 * so the real token is neither read nor overwritten (PLAN-preview-signer.md D8).
 */
export function getSubscriptionTokenFile(
  configName = getEffectiveConfigName(),
  configDir = getConfigDir()
): string {
  return (
    readAccountPointer(configName, configDir).tokenFile ??
    join(configDir, `api-token-${configName}.json`)
  );
}

/** A server URL that names something: an empty or blank value (`REDIACC_ACCOUNT_SERVER=`) counts as unset. */
function named(serverUrl: string | undefined): string | undefined {
  return serverUrl?.trim() ? serverUrl.trim() : undefined;
}

export function getSubscriptionServerUrl(preferredServerUrl?: string): string {
  // Precedence (highest first): 1. preferredServerUrl, runtime override (--server flag) 2. REDIACC_ACCOUNT_SERVER, env override 3. config account.accountServer, the active config's server pointer 4. SUBSCRIPTION_DEFAULTS.ACCOUNT_SERVER_URL, hardcoded default
  return normalizeServerUrl(
    named(preferredServerUrl) ??
      getConfigNamedServerUrl() ??
      SUBSCRIPTION_DEFAULTS.ACCOUNT_SERVER_URL
  );
}

/**
 * The server the config universe itself names: REDIACC_ACCOUNT_SERVER, else the active config's
 * `account.accountServer`. No stored token and no default; an empty value counts as unset.
 */
function getConfigNamedServerUrl(): string | undefined {
  const server =
    named(process.env.REDIACC_ACCOUNT_SERVER) ?? named(readAccountPointer().accountServer);
  return server ? normalizeServerUrl(server) : undefined;
}

/**
 * The api-token file as stored. A sealed config's file (PLAN-config-sealed-local.md D9) keeps
 * `serverUrl` and the token's metadata in plaintext, and the token itself as `sealed` under the
 * config's seal key (`keyringId`, the config's `encryption.keyringId` when the file was written).
 */
interface StoredTokenFile extends Omit<StoredSubscriptionToken, 'token'> {
  token?: string;
  keyringId?: string;
  sealed?: { v: 1; data: string };
}

const API_TOKEN_SEAL_INFO = 'rdc-api-token-v1|';
const GCM_IV_BYTES = 12;
const GCM_TAG_BYTES = 16;

/** What the api-token seal needs of a config in a keyring mode: its id and its `keyringId`. */
interface ConfigSeal {
  configId: string;
  keyringId: string;
}

/**
 * The seal of config `configName` as its file records it, read synchronously and without the
 * keyring: the `id` and `encryption.keyringId` of a config in a keyring mode, else null (a plaintext
 * or master-password-only config, a local-only config, or a file that cannot be read).
 */
function readConfigSeal(configName: string, configDir: string): ConfigSeal | null {
  try {
    const raw = readFileSync(join(configDir, `${configName}.json`), 'utf8');
    const parsed = parseJsonText(raw) as {
      id?: unknown;
      encryption?: { mode?: EncryptionMode; keyringId?: unknown };
    };
    const keyringId = parsed.encryption?.keyringId;
    if (!usesKeyring(parsed.encryption?.mode) || typeof keyringId !== 'string') return null;
    return { configId: typeof parsed.id === 'string' ? parsed.id : '', keyringId };
  } catch {
    return null;
  }
}

/** The AES-256-GCM key of config `configName`'s api token: HKDF-SHA256 over its seal key. */
function apiTokenKey(seal: ConfigSeal, configName: string): Buffer {
  const ring = loadKeySync(seal.configId, seal.keyringId);
  return Buffer.from(
    hkdfSync('sha256', ring, Buffer.alloc(0), `${API_TOKEN_SEAL_INFO}${configName}`, 32)
  );
}

function apiTokenAad(configName: string, keyringId: string): Buffer {
  return Buffer.from(`${API_TOKEN_SEAL_INFO}${configName}|${keyringId}`, 'utf8');
}

/** base64(iv + ciphertext + tag), the layout of the shared aesEncryptToString. */
function sealApiToken(token: string, seal: ConfigSeal, configName: string): string {
  const iv = randomBytes(GCM_IV_BYTES);
  const cipher = createCipheriv('aes-256-gcm', apiTokenKey(seal, configName), iv);
  cipher.setAAD(apiTokenAad(configName, seal.keyringId));
  const ct = Buffer.concat([cipher.update(token, 'utf8'), cipher.final()]);
  return Buffer.concat([iv, ct, cipher.getAuthTag()]).toString('base64');
}

/** The inverse of `sealApiToken`; throws SealKeyLostError when the key is gone, and an auth error when it is not the key. */
function openApiToken(data: string, seal: ConfigSeal, configName: string): string {
  const combined = Buffer.from(data, 'base64');
  const iv = combined.subarray(0, GCM_IV_BYTES);
  const tag = combined.subarray(combined.length - GCM_TAG_BYTES);
  const ct = combined.subarray(GCM_IV_BYTES, combined.length - GCM_TAG_BYTES);
  const decipher = createDecipheriv('aes-256-gcm', apiTokenKey(seal, configName), iv);
  decipher.setAAD(apiTokenAad(configName, seal.keyringId));
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ct), decipher.final()]).toString('utf8');
}

/** The api-token file of the active config as stored: nothing is unsealed, so the keyring is never read. */
function loadStoredTokenFile(): StoredTokenFile | null {
  const tokenFile = getSubscriptionTokenFile();
  if (!existsSync(tokenFile)) return null;

  try {
    const parsed = parseJsonText(readFileSync(tokenFile, 'utf-8')) as StoredTokenFile;
    return {
      ...parsed,
      serverUrl: normalizeServerUrl(parsed.serverUrl),
    };
  } catch {
    return null;
  }
}

/**
 * The stored token of the active config, unsealed. A sealed token whose seal key is gone
 * (SealKeyLostError), or that the key does not open, reads as no token: the remedy is
 * `rdc subscription login` either way, and the config's key-loss recovery names it
 * (services/config/seal-recovery.ts).
 */
function loadStoredSubscriptionToken(): StoredSubscriptionToken | null {
  const file = loadStoredTokenFile();
  if (!file) return null;
  const { keyringId, sealed, token, ...rest } = file;
  if (!sealed) return typeof token === 'string' ? { ...rest, token } : null;
  if (typeof keyringId !== 'string') return null;
  const configName = getEffectiveConfigName();
  const configId = readConfigSeal(configName, getConfigDir())?.configId ?? '';
  try {
    return { ...rest, token: openApiToken(sealed.data, { configId, keyringId }, configName) };
  } catch {
    return null;
  }
}

/**
 * The account server this config universe names, with no default: REDIACC_ACCOUNT_SERVER, the
 * active config's `account.accountServer`, or the server its stored token was issued by. Unlike
 * getSubscriptionServerUrl it never falls back to the production default, so a caller that must not
 * contact production on a config that names no server yet (the startup telemetry fetch, while
 * `config init --server <dev>` is still writing the config) can tell "none" apart.
 */
export function getConfiguredServerUrl(): string | undefined {
  return getConfigNamedServerUrl() ?? named(loadStoredTokenFile()?.serverUrl);
}

/**
 * The server the active token belongs to, as something named it: for a REDIACC_TOKEN env token the
 * server REDIACC_ACCOUNT_SERVER or the config's `account.accountServer` names (never the stored
 * token's server, which issued a different token), else the server the stored token was issued by. Never the production default, unlike the `serverUrl` of getSubscriptionTokenState,
 * which for an env token falls back to it. Background traffic (the audit flush) uses this, so a
 * token on a config that names no server sends nothing rather than reaching production.
 */
export function getNamedTokenServerUrl(): string | undefined {
  if (process.env[SUBSCRIPTION_TOKEN_ENV]?.trim()) return getConfigNamedServerUrl();
  return named(loadStoredTokenFile()?.serverUrl);
}

export function loadEnvSubscriptionToken(): StoredSubscriptionToken | null {
  const token = process.env[SUBSCRIPTION_TOKEN_ENV]?.trim();
  if (!token) return null;

  return {
    token,
    serverUrl: getSubscriptionServerUrl(),
  };
}

/**
 * Write the active config's api-token file. A config in a keyring mode stores the token sealed under
 * its seal key, with the `keyringId` beside it; any other config stores it in plaintext. A seal key
 * that secure storage no longer holds refuses the write (SealKeyLostError) rather than storing the
 * token in plaintext.
 */
export function saveStoredSubscriptionToken(token: StoredSubscriptionToken): void {
  const tokenFile = getSubscriptionTokenFile();
  const configName = getEffectiveConfigName();
  const seal = readConfigSeal(configName, getConfigDir());
  const { token: secret, ...metadata } = token;
  const serverUrl = normalizeServerUrl(token.serverUrl);
  const stored: StoredTokenFile = seal
    ? {
        ...metadata,
        serverUrl,
        keyringId: seal.keyringId,
        sealed: { v: 1, data: sealApiToken(secret, seal, configName) },
      }
    : { ...token, serverUrl };
  mkdirSync(dirname(tokenFile), { recursive: true, mode: 0o700 });
  writeFileSync(tokenFile, JSON.stringify(stored, null, 2), { mode: 0o600 });
}

export function deleteStoredSubscriptionToken(): void {
  const tokenFile = getSubscriptionTokenFile();
  try {
    unlinkSync(tokenFile);
  } catch {
    // File doesn't exist or can't be deleted, that's OK
  }
}

export function getSubscriptionScopeMismatch(
  token: Pick<StoredSubscriptionToken, 'teamName'>,
  configTeamName?: string
): string | null {
  const normalizedConfigTeam = configTeamName?.trim();
  const normalizedTokenTeam = token.teamName?.trim();

  if (!normalizedConfigTeam) {
    return null;
  }

  if (!normalizedTokenTeam) {
    return `Stored subscription token is missing team metadata for config team "${normalizedConfigTeam}". Run "rdc subscription login" again.`;
  }

  if (normalizedConfigTeam !== normalizedTokenTeam) {
    return `Stored subscription token is bound to team "${normalizedTokenTeam}", but the current config team is "${normalizedConfigTeam}". Run "rdc subscription login" again after selecting the correct team.`;
  }

  return null;
}

export type SubscriptionTokenState =
  | { kind: 'missing' }
  | { kind: 'ready'; token: StoredSubscriptionToken; serverUrl: string };

export function getSubscriptionTokenState(): SubscriptionTokenState {
  const token = loadEnvSubscriptionToken() ?? loadStoredSubscriptionToken();
  if (!token) return { kind: 'missing' };

  return {
    kind: 'ready',
    token,
    serverUrl: token.serverUrl,
  };
}
