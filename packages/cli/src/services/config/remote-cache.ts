/**
 * Offline read-cache for remote-enabled configs.
 *
 * The local config file of a remote-enabled config is a full-content,
 * read-only CACHE of the last successful pull/push — not a bare pointer.
 * Content sections mirror the server copy; host-local sections (`remote`,
 * `state`, `encryption`, plus local `account`/`defaults` overrides) stay
 * host-local. One helper owns that merge so enable, read-refresh,
 * mutation-push, `remote refresh`, and the CEK-rotation verify all write the
 * same shape.
 *
 * Cache writes never bump the local `version` counter (they are observations,
 * not declared intent — same rationale as `updateState`). The server's
 * envelope version is authoritative and tracked in `remote.cachedVersion`.
 */

import { configFileStorage } from '../../adapters/config-file-storage.js';
import { t } from '../../i18n/index.js';
import type { RdcConfig, RemoteConfig } from '../../types/index.js';

/**
 * Merge a pulled (or just-pushed) server copy into the local cache file shape.
 * Pulled content sections win; `remote` (stamped with fresh cache metadata),
 * `state`, `encryption`, and the local `account`/`defaults` overrides are
 * re-applied from `local` — the same precedence `loadRemote` uses in memory.
 */
export function mergeRemoteIntoCache(
  local: RdcConfig,
  pulled: RdcConfig,
  version: number
): RdcConfig {
  const merged: RdcConfig = {
    ...pulled,
    // The local file keeps its own optimistic counter; the server's envelope
    // version lives in remote.cachedVersion, not here.
    version: local.version,
    remote: local.remote
      ? { ...local.remote, cachedVersion: version, cachedAt: new Date().toISOString() }
      : undefined,
    state: local.state,
    encryption: local.encryption,
  };
  if (local.account) merged.account = { ...(pulled.account ?? {}), ...local.account };
  if (local.defaults) merged.defaults = { ...(pulled.defaults ?? {}), ...local.defaults };
  return merged;
}

/**
 * Refresh the on-disk cache of `configName` from a pulled server copy.
 * Loads the current file under lock (decrypted), merges, and saves through
 * the no-bump `updateCache` path (the storage layer re-encrypts per field).
 */
export async function writeRemoteCache(
  configName: string,
  pulled: RdcConfig,
  version: number
): Promise<void> {
  await configFileStorage.updateCache(configName, (local) =>
    mergeRemoteIntoCache(local, pulled, version)
  );
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
