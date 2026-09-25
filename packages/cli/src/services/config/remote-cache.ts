/**
 * Offline read-cache for remote-enabled configs.
 *
 * The local config file of a remote-enabled config is a full-content,
 * read-only CACHE of the last successful pull/push, not a bare pointer.
 * Everything mirrors the server copy except the device-local pointers named by
 * DEVICE_LOCAL_POINTERS (packages/shared config-schema/sensitivity.ts), the one exclusion list of
 * config sync (T17). `state` syncs too, merged per repo (see `mergeState`). One helper owns that
 * merge so enable, read-refresh,
 * mutation-push, `remote refresh`, and the CEK-rotation verify all write the
 * same shape.
 *
 * Cache writes never bump the local `version` counter (they are observations,
 * not declared intent, same rationale as `updateState`). The server's
 * envelope version is authoritative and tracked in `remote.cachedVersion`.
 */

import { DEVICE_LOCAL_POINTERS, RdcConfigSchema } from '@rediacc/shared/config-schema';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import { t } from '../../i18n/index.js';
import type { RdcConfig, RemoteConfig } from '../../types/index.js';

/** Top-level keys the schema declares; anything else in a document is an unknown (newer-CLI) key. */
const KNOWN_TOP_LEVEL_KEYS: ReadonlySet<string> = new Set(Object.keys(RdcConfigSchema.shape));

function pointerSegments(pointer: string): string[] {
  return pointer.split('/').slice(1);
}

/** Set `doc[key]` to `value`, or remove the key when `value` is undefined. */
function setOrDelete(doc: Record<string, unknown>, key: string, value: unknown): void {
  if (value === undefined) delete doc[key];
  else doc[key] = value;
}

/** Overlay one device-local pointer (one or two segments) from `local` onto `out`, cloning any parent it edits. */
function overlayPointer(
  out: Record<string, unknown>,
  local: Record<string, unknown>,
  pointer: string
): void {
  const [root, ...rest] = pointerSegments(pointer);
  if (rest.length === 0) {
    setOrDelete(out, root, local[root]);
    return;
  }
  const child = rest[0];
  const localValue = (local[root] as Record<string, unknown> | undefined)?.[child];
  const parent = out[root] as Record<string, unknown> | undefined;
  if (localValue === undefined && !(parent && child in parent)) return;
  const edited = { ...(parent ?? {}) };
  setOrDelete(edited, child, localValue);
  out[root] = edited;
}

type RepoStates = NonNullable<NonNullable<RdcConfig['state']>['repos']>;

/** Per repo and tag: the pulled runtime wins where both copies have it, each side's own survives. */
function mergeRepoStates(
  pulled: RepoStates | undefined,
  local: RepoStates | undefined
): RepoStates {
  const merged: RepoStates = { ...(local ?? {}) };
  for (const [repo, tags] of Object.entries(pulled ?? {})) {
    merged[repo] = { ...(merged[repo] ?? {}), ...tags };
  }
  return merged;
}

/**
 * The `state` a pulled copy leaves in the cache.
 *
 * - The pulled copy carries no `state` at all: it was pushed before state synced (T17), so the local
 *   state is kept whole, and the next push publishes it. This one-time migration is what keeps an
 *   upgrade from erasing every repo's networkId.
 * - Otherwise the pulled state wins, except `repos`, merged per repo and tag: a repo only this device
 *   has runtime for keeps it, and the pulled runtime wins for a repo both have.
 */
function mergeState(
  pulled: RdcConfig['state'],
  local: RdcConfig['state']
): RdcConfig['state'] | undefined {
  if (pulled === undefined) return local;
  if (local?.repos === undefined) return pulled;
  return { ...pulled, repos: mergeRepoStates(pulled.repos, local.repos) };
}

/**
 * Overlay THIS device's pointers onto a pulled (or just-pushed) server copy. The one
 * implementation, driven by DEVICE_LOCAL_POINTERS: every writer of a pulled document (the cache
 * merge, the in-memory load, the push's cache write, the conflict rebase) goes through here.
 *
 * - Each device-local pointer takes the LOCAL value, absence included: the pulled value is never
 *   trusted there (a pull rebuilds `encryption` as plaintext and carries no `remote`).
 * - `state` syncs, merged by `mergeState` (a pulled copy without state never erases local state).
 * - Unknown top-level keys from `local` survive unless `pulled` carries the same key (F18, the
 *   `.loose()` contract in schemas.ts).
 * - Everything else, `account` and `defaults` included, follows the server with no local override
 *   (operator ruling D3, PLAN-config-sync-hardening F5).
 *
 * Pure: neither input is mutated.
 */
export function overlayDeviceLocal(pulled: RdcConfig, local: RdcConfig): RdcConfig {
  const out: Record<string, unknown> = { ...pulled };
  const localDoc = local as Record<string, unknown>;

  for (const [key, value] of Object.entries(localDoc)) {
    if (!KNOWN_TOP_LEVEL_KEYS.has(key) && !(key in out)) out[key] = value;
  }

  for (const pointer of DEVICE_LOCAL_POINTERS) overlayPointer(out, localDoc, pointer);
  setOrDelete(out, 'state', mergeState(pulled.state, local.state));
  return out as RdcConfig;
}

/**
 * Merge a pulled (or just-pushed) server copy into the local cache file shape: `overlayDeviceLocal`,
 * plus fresh cache metadata on the `remote` pointer. The local `version` counter is device-local; the
 * server's envelope version lives in `remote.cachedVersion`.
 */
export function mergeRemoteIntoCache(
  local: RdcConfig,
  pulled: RdcConfig,
  version: number
): RdcConfig {
  const merged = overlayDeviceLocal(pulled, local);
  if (merged.remote) {
    merged.remote = {
      ...merged.remote,
      cachedVersion: version,
      cachedAt: new Date().toISOString(),
    };
  }
  return merged;
}

/**
 * Refresh the on-disk cache of `configName` from a pulled server copy.
 * Loads the current file under lock (decrypted), merges, and saves through
 * the no-bump `updateCache` path (the storage layer re-encrypts per field).
 *
 * Returns the merged PLAINTEXT document, exactly what the cache now holds, so an in-memory
 * reader sees the same device-local pointers and merged `state` the file does.
 */
export async function writeRemoteCache(
  configName: string,
  pulled: RdcConfig,
  version: number
): Promise<RdcConfig> {
  let merged: RdcConfig | undefined;
  await configFileStorage.updateCache(configName, (local) => {
    merged = mergeRemoteIntoCache(local, pulled, version);
    return merged;
  });
  if (!merged) throw new Error(`Config "${configName}" cache write did not run its merge`);
  return merged;
}

/** A remote pointer that has been cache-stamped by a successful pull/push. */
export type CachedRemoteConfig = RemoteConfig & { cachedVersion: number };

/** Rough humanized age of an ISO timestamp, for the staleness warning. */
function formatAge(cachedAt: string | undefined): string {
  const then = cachedAt ? Date.parse(cachedAt) : Number.NaN;
  if (Number.isNaN(then)) return 'unknown time';
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

/**
 * Staleness warning for offline cache serves. Callers guarantee the pointer is
 * cache-stamped (loadRemote refuses to cache-serve a bare pointer), so the
 * version needs no fallback.
 */
export function formatStaleCacheWarning(remote: CachedRemoteConfig, configName: string): string {
  return t('commands.config.remote.offlineCacheWarning', {
    server: remote.apiUrl,
    config: configName,
    version: String(remote.cachedVersion),
    age: formatAge(remote.cachedAt),
  });
}
