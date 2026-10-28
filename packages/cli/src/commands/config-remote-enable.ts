/**
 * Enable/seed flow for `config remote enable` (split from config-remote.ts;
 * the one transport, the server relay, lives in config-remote-relay.ts).
 *
 * Validate the enrollment by pulling, seed a fresh store, and turn the local
 * file into a full-content cache (D1/D5):
 *
 * - 404 → a fresh store ONLY when the store lists no config this token can see:
 *   push the local config at version 0 (server inserts at v1), pull it back as
 *   round-trip proof, then write the cache. A 404 beside a non-empty list is an
 *   enroll that addressed nothing visible (bench 2026-10-28: a token whose
 *   enroll could not see the org-wide config seeded a second one beside it), so
 *   it attaches to the single visible config the handoff did not name, and
 *   refuses otherwise; a headless enable never seeds there. Only an operator's
 *   interactive "create new" pick seeds beside listed configs.
 * - pull succeeds but the store's synced content differs from non-empty local
 *   synced content → confirm before replacing it (`--force` skips; non-TTY
 *   aborts naming --force).
 * - any other error → abort with the local file untouched (the cache write is
 *   the LAST step).
 */

import { toFullConfig } from '@rediacc/shared/config-schema';
import type { RemoteConfigAdapter, RemoteConfigEntry } from '../adapters/remote-config-adapter.js';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import {
  getSubscriptionTokenState,
  normalizeServerUrl,
} from '../services/account/subscription-auth.js';
import { outputService } from '../services/core/output.js';
import type { RdcConfig, RemoteConfig } from '../types/index.js';
import { ValidationError } from '../utils/errors.js';
import { askChoice, askConfirm } from '../utils/prompt.js';
import type { DeviceCredentials } from './config-remote-handoff.js';

/** GET /configs/enable-requirements (api-token auth, subscription:read) for the token's own user. */
export interface EnableRequirements {
  email: string;
  totpEnabled: boolean;
  configServiceAvailable: boolean;
}

/**
 * This config's login token when it belongs to `apiUrl`. The relay binds the handoff to the token's user, so
 * without one there is nothing to bind to and enable refuses (operator ruling D1, 2026-09-25).
 */
export function requireLoginToken(apiUrl: string): string {
  const state = getSubscriptionTokenState();
  if (
    state.kind !== 'ready' ||
    normalizeServerUrl(state.serverUrl) !== normalizeServerUrl(apiUrl)
  ) {
    throw new ValidationError(
      t('commands.config.remote.enable.loginRequired', { apiUrl: normalizeServerUrl(apiUrl) })
    );
  }
  return state.token.token;
}

/**
 * The prerequisites the portal page enforces, read with the login token.
 * Null when the server cannot answer (an older server without the route, a revoked token): the CLI then only states the prerequisites.
 */
async function fetchEnableRequirements(
  apiUrl: string,
  token: string
): Promise<EnableRequirements | null> {
  try {
    return await accountServerFetch<EnableRequirements>(
      '/account/api/v1/configs/enable-requirements',
      { serverUrl: apiUrl, token }
    );
  } catch {
    return null;
  }
}

/** What the relay needs once the prerequisites pass: the login token, and the approving account when the server named it. */
export interface EnablePrerequisites {
  token: string;
  email?: string;
}

/**
 * Pre-flight for the relay enable: runs BEFORE any portal link is printed or opened.
 * No login token for `apiUrl` refuses with `loginRequired`. With one, the 2FA and server-availability
 * requirements are checked and a missing one refuses with the exact portal step; a server that cannot answer
 * gets the requirements stated instead. The page itself asks for the recently verified session.
 */
export async function checkEnablePrerequisites(apiUrl: string): Promise<EnablePrerequisites> {
  const token = requireLoginToken(apiUrl);
  const base = normalizeServerUrl(apiUrl);
  const settingsUrl = `${base}/account/settings`;
  const reqs = await fetchEnableRequirements(apiUrl, token);

  if (reqs) {
    const missing: string[] = [];
    if (!reqs.configServiceAvailable) {
      missing.push(t('commands.config.remote.enable.prereqUnavailable', { apiUrl: base }));
    }
    if (!reqs.totpEnabled) {
      missing.push(t('commands.config.remote.enable.prereqTotpMissing', { url: settingsUrl }));
    }
    if (missing.length > 0) {
      throw new ValidationError(
        [
          t('commands.config.remote.enable.prereqMissing', { email: reqs.email }),
          ...missing.map((line) => `  - ${line}`),
          t('commands.config.remote.enable.prereqRetry'),
        ].join('\n')
      );
    }
    outputService.info(t('commands.config.remote.enable.prereqChecked', { email: reqs.email }));
    outputService.info(`  - ${t('commands.config.remote.enable.prereqElevated')}`);
    outputService.info('');
    return { token, email: reqs.email };
  }

  outputService.info(t('commands.config.remote.enable.prereqHeader'));
  outputService.info(
    `  - ${t('commands.config.remote.enable.prereqSignedIn', { url: `${base}/account/login` })}`
  );
  outputService.info(`  - ${t('commands.config.remote.enable.prereqTotp', { url: settingsUrl })}`);
  outputService.info(`  - ${t('commands.config.remote.enable.prereqElevated')}`);
  outputService.info('');
  return { token };
}

/**
 * A remote pointer whose configId may still be unminted. Fresh-store handoffs
 * carry no configId; `finalizeEnable` mints one from the local config's id
 * before anything is written.
 */
export type PendingRemoteConfig = Omit<RemoteConfig, 'configId'> & { configId?: string };

export async function storeHandoffCredentials(
  payload: DeviceCredentials,
  configName: string
): Promise<PendingRemoteConfig> {
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const secureStorage = getSecureStorage();
  await secureStorage.set(payload.storageKeyId, payload.passkey_secret);

  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  await remoteTokenStorage.set(configName, {
    token: payload.token,
    wrappedCek: payload.wrappedCek,
  });

  return {
    apiUrl: payload.apiUrl,
    storeId: payload.storeId,
    // Absent for a fresh store; finalizeEnable mints it from the local
    // config's id (this function never loads the config file).
    configId: payload.configId,
    storageKeyId: payload.storageKeyId,
    teamId: payload.teamId,
  };
}

/**
 * True when a local config other than `configName` points at `storageKeyId`. The id names the
 * (store, user) enrollment, not one local config, so two local configs enrolled to the same store by
 * the same member share one slot secret (F17). A config file that cannot be read counts as a user:
 * a leftover keyring entry costs nothing, a deleted one locks that config out.
 */
export async function storageKeyInUseElsewhere(
  storageKeyId: string,
  configName: string
): Promise<boolean> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  for (const name of await configFileStorage.list()) {
    if (name === configName) continue;
    try {
      const other = await configFileStorage.load(name);
      if (other.remote?.storageKeyId === storageKeyId) return true;
    } catch {
      return true;
    }
  }
  return false;
}

/**
 * Best-effort removal of stored handoff credentials after a failed enable. The slot secret goes only
 * when this enable wrote it (it was absent before) and no other local config uses it (F17): a failed
 * enable of a second local config for the same store must not lock the first one out.
 */
async function cleanupHandoffCredentials(
  storageKeyId: string,
  configName: string,
  secretExisted: boolean
): Promise<void> {
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const inUse =
    secretExisted || (await storageKeyInUseElsewhere(storageKeyId, configName).catch(() => true));
  if (!inUse) {
    await getSecureStorage()
      .delete(storageKeyId)
      .catch(() => {});
  }
  await remoteTokenStorage.delete(configName).catch(() => {});
}

function countResources(config: RdcConfig): { machines: number; repos: number } {
  const r = config.resources;
  return {
    machines: Object.keys(r?.machines ?? {}).length,
    repos: Object.keys(r?.repositories ?? {}).length,
  };
}

/** Envelope fields toFullConfig adds; they say nothing about the content an enable would replace. */
const ENVELOPE_KEYS = new Set([
  'envelopeVersion',
  'id',
  'version',
  'sdkEpoch',
  'teamId',
  'commitments',
]);

/**
 * Runtime state is merged into the cache per repo (remote-cache.ts `mergeState`), never replaced
 * wholesale, so it is not content an enable could lose.
 */
const MERGED_SECTIONS = new Set(['state']);

/**
 * The synced half of a config: exactly what a push carries (toFullConfig), minus the envelope, with
 * empty sections dropped so an absent family and an empty one compare equal.
 */
function syncedContent(config: RdcConfig): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(toFullConfig(config, { version: 0, sdkEpoch: 0 }))) {
    if (ENVELOPE_KEYS.has(key) || MERGED_SECTIONS.has(key) || isEmpty(value)) continue;
    out[key] = value;
  }
  return out;
}

function isEmpty(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (Array.isArray(value)) return value.length === 0;
  return typeof value === 'object' && Object.keys(value).length === 0;
}

/** JSON with object keys sorted at every level, so key order never reads as a difference. */
function canonicalJson(value: unknown): string {
  return JSON.stringify(value, (_key, v: unknown) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b)))
      : v
  );
}

/**
 * Whether taking the store's copy would replace local content the user could lose (F17b): the whole
 * synced projection is compared, not only `resources`, so local ssh credentials, policy, infra, org
 * secrets and datastores are protected by the same prompt. `account` and `defaults` alone do not
 * count as local content (login writes `account` on its own, and a language or default size is a
 * preference, not data), but once there is content they take part in the comparison.
 */
const PREFERENCE_SECTIONS = new Set(['account', 'defaults']);

function localContentWouldBeReplaced(local: RdcConfig, pulled: RdcConfig): boolean {
  const mine = syncedContent(local);
  const hasContent = Object.keys(mine).some((key) => !PREFERENCE_SECTIONS.has(key));
  return hasContent && canonicalJson(mine) !== canonicalJson(syncedContent(pulled));
}

type Pulled = { config: RdcConfig; version: number };

/** The store's copy, or null for a 404 (which by itself proves nothing about the store being empty). */
async function pullOrNull(adapter: RemoteConfigAdapter): Promise<Pulled | null> {
  try {
    return await adapter.pull();
  } catch (error) {
    const { ConfigServerError } = await import('../services/config/config-server-client.js');
    if (error instanceof ConfigServerError && error.status === 404) return null;
    throw error;
  }
}

/** Seed a store proven empty from the local config, pulled back as round-trip proof before anything is written locally. */
async function seed(adapter: RemoteConfigAdapter, local: RdcConfig): Promise<Pulled> {
  // The push projection sends the document minus the device-local pointers (`remote` among them); `state` seeds the store with this device's network IDs.
  await adapter.push(local, 0); // server inserts at version 1
  const pulled = await adapter.pull();
  outputService.success(t('commands.config.remote.enable.seeded'));
  return pulled;
}

/**
 * Existing-store enroll would replace differing local content: confirm, or
 * abort naming --force. askConfirm exits the process on a non-TTY stdin, so
 * the TTY check happens here (REDIACC_YES=1 still auto-confirms).
 */
async function confirmOverwrite(
  configName: string,
  counts: { machines: number; repos: number },
  backupPath: string
): Promise<void> {
  const aborted = new ValidationError(
    t('commands.config.remote.enable.overwriteAborted', { config: configName })
  );
  if (process.stdin.isTTY !== true && process.env.REDIACC_YES !== '1') {
    throw aborted;
  }
  const confirmed = await askConfirm(
    t('commands.config.remote.enable.overwriteConfirm', {
      config: configName,
      machines: String(counts.machines),
      repos: String(counts.repos),
      backupPath,
    }),
    false
  );
  if (!confirmed) throw aborted;
}

const CREATE_NEW = '__new__';

/**
 * What enable addresses before its first pull: an existing entry (`attach`), a new entry the
 * operator chose beside the listed ones or on a store listed empty (`new`), or the handoff's
 * pointer as-is (`pointer`: no explicit --config-id and no interactive pick, whether or not the
 * handoff named an id), whose 404 is settled by the list later.
 */
type AttachChoice =
  | { kind: 'attach'; entry: RemoteConfigEntry }
  | { kind: 'new' }
  | { kind: 'pointer' };

/**
 * An explicit `--config-id` must name an entry the caller can see; with none given, an interactive
 * enable against a store that already holds configs asks. A list that cannot be read is refused
 * (never downgraded to minting a new entry) whenever the list is needed.
 */
async function chooseAttachTarget(
  adapter: RemoteConfigAdapter,
  remote: PendingRemoteConfig,
  explicitId: string | undefined
): Promise<AttachChoice> {
  const interactive =
    !remote.configId && process.stdin.isTTY === true && process.env.REDIACC_YES !== '1';
  if (!explicitId && !interactive) return { kind: 'pointer' };

  // An id named, or a prompt about to be shown, needs the list: guessing without it would mint a duplicate entry.
  const entries = await listEntries(adapter, explicitId === undefined);
  if (explicitId) return { kind: 'attach', entry: requireEntry(entries, explicitId) };
  if (!entries || entries.length === 0) return { kind: 'new' };
  const picked = await pickEntry(entries);
  return picked ? { kind: 'attach', entry: picked } : { kind: 'new' };
}

/**
 * The 404 of a pointer nobody chose: the list decides. Empty → seed (null). One visible config and
 * a handoff that named none → attach to it (the server's own password-enroll rule: exactly one
 * candidate is the target). Anything else is refused naming what is visible, never seeded beside.
 */
async function resolveUnaddressed(
  adapter: RemoteConfigAdapter,
  pointerId: string,
  handoffNamedConfig: boolean
): Promise<RemoteConfigEntry | null> {
  const entries = (await listEntries(adapter, true)) ?? [];
  if (entries.length === 0) return null;
  const [only] = entries;
  if (!handoffNamedConfig && entries.length === 1 && only) return only;
  throw new ValidationError(
    t('commands.config.remote.enable.configIdNotFound', {
      id: pointerId,
      available: entries.map((e) => e.configId).join(', '),
    })
  );
}

/**
 * The store's entries; a failed list is refused, never downgraded to creating a new entry. The
 * named error suggests `--config-id` only when none was given (`suggestId`); with an id named, the
 * list failure itself is the error, since that remedy was already tried.
 */
async function listEntries(
  adapter: RemoteConfigAdapter,
  suggestId: boolean
): Promise<RemoteConfigEntry[] | undefined> {
  try {
    return await adapter.listConfigs();
  } catch (error) {
    if (!suggestId) throw error;
    throw new ValidationError(
      t('commands.config.remote.enable.listFailedRefused', {
        error: error instanceof Error ? error.message : String(error),
      })
    );
  }
}

function requireEntry(entries: RemoteConfigEntry[] | undefined, id: string): RemoteConfigEntry {
  const found = entries?.find((e) => e.configId === id);
  if (!found) {
    throw new ValidationError(
      t('commands.config.remote.enable.configIdNotFound', {
        id,
        available: (entries ?? []).map((e) => e.configId).join(', ') || '-',
      })
    );
  }
  return found;
}

async function pickEntry(entries: RemoteConfigEntry[]): Promise<RemoteConfigEntry | undefined> {
  const picked = await askChoice<string>(t('commands.config.remote.enable.attachPrompt'), [
    ...entries.map((e) => ({
      name: t('commands.config.remote.enable.attachEntry', {
        id: e.configId,
        version: String(e.version),
        modified: e.lastModified,
      }),
      value: e.configId,
    })),
    { name: t('commands.config.remote.enable.attachNew'), value: CREATE_NEW },
  ]);
  return entries.find((e) => e.configId === picked);
}

/** Re-address a pointer at an existing store entry. */
function pointerFor(pointer: RemoteConfig, entry: RemoteConfigEntry): RemoteConfig {
  // The team is exactly the entry's: a stale team from the handoff would scope the pull to a team the entry is not in.
  const { teamId: _stale, ...withoutTeam } = pointer;
  return {
    ...withoutTeam,
    configId: entry.configId,
    ...(entry.teamId ? { teamId: entry.teamId } : {}),
  };
}

interface Addressed {
  pointer: RemoteConfig;
  /** The existing entry attached to, when one was. */
  target?: RemoteConfigEntry;
  pulled: Pulled;
  seeded: boolean;
}

/**
 * Decide which store entry this enable addresses and pull it, seeding only a store whose list is
 * empty (see the module doc).
 */
async function addressAndPull(
  remote: PendingRemoteConfig,
  local: RdcConfig,
  opts: { configId?: string },
  buildAdapter: (p: RemoteConfig) => RemoteConfigAdapter
): Promise<Addressed> {
  // Fresh-store handoffs carry no configId: mint one from the local config's own id (already a stable UUID); it is seeded on an empty store, or beside listed configs only when the operator picked "create new" interactively.
  const minted: RemoteConfig = { ...remote, configId: remote.configId ?? local.id };
  const mintedAdapter = buildAdapter(minted);
  const attach = async (entry: RemoteConfigEntry): Promise<Addressed> => {
    const pointer = pointerFor(minted, entry);
    return { pointer, target: entry, pulled: await buildAdapter(pointer).pull(), seeded: false };
  };

  // Attach to an existing entry of the store (an explicit --config-id, or the operator's pick) instead of creating a new one beside it.
  // An attach names an entry that exists; its 404 propagates, it is not a fresh store to seed.
  const choice = await chooseAttachTarget(mintedAdapter, remote, opts.configId);
  if (choice.kind === 'attach') return attach(choice.entry);

  const pulled = await pullOrNull(mintedAdapter);
  if (pulled) return { pointer: minted, pulled, seeded: false };

  // Only the headless pointer still needs the list; `new` was already chosen against it.
  if (choice.kind === 'pointer') {
    const existing = await resolveUnaddressed(
      mintedAdapter,
      minted.configId,
      remote.configId !== undefined
    );
    if (existing) return attach(existing);
  }
  return { pointer: minted, pulled: await seed(mintedAdapter, local), seeded: true };
}

/** See the module doc for the three-way contract this enforces. */
export async function finalizeEnable(
  remote: PendingRemoteConfig,
  configName: string,
  opts: { force?: boolean; configId?: string } = {}
): Promise<void> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const local = await configFileStorage.loadDecrypted(configName);

  const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const buildAdapter = (p: RemoteConfig) =>
    new RemoteConfigAdapter(p, configName, remoteTokenStorage, getSecureStorage());

  const { pointer, target, pulled, seeded } = await addressAndPull(
    remote,
    local,
    opts,
    buildAdapter
  );

  const counts = countResources(local);
  if (!seeded && !opts.force && localContentWouldBeReplaced(local, pulled.config)) {
    await confirmOverwrite(
      configName,
      counts,
      `${configFileStorage.getConfigPath(configName)}.bak`
    );
  }

  // The pointer file write IS the cache write: full server content, host-local sections (encryption mode included) preserved from the pre-enable config.
  const { mergeRemoteIntoCache } = await import('../services/config/remote-cache.js');
  const cached = mergeRemoteIntoCache({ ...local, remote: pointer }, pulled.config, pulled.version);
  // An attached config takes the store entry's identity: the local id and remote.configId name the same config.
  if (target) cached.id = target.configId;
  await configFileStorage.save(cached, configName);
}

/**
 * Store-and-finalize for a first enrollment, relay handoff or password slot alike. On any
 * finalize failure the stored credentials are removed so a retry starts clean. Exported for the
 * seed tests.
 */
export async function applyHandoff(
  payload: DeviceCredentials,
  configName: string,
  opts: { force?: boolean; configId?: string }
): Promise<void> {
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const secretExisted = (await getSecureStorage().get(payload.storageKeyId)) !== null;
  const remote = await storeHandoffCredentials(payload, configName);
  try {
    await finalizeEnable(remote, configName, opts);
  } catch (error) {
    await cleanupHandoffCredentials(payload.storageKeyId, configName, secretExisted);
    throw error;
  }
}
