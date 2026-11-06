/**
 * Local edits of a remote config's cache file are never overwritten silently (#5013fce6).
 *
 * The local file of a remote-enabled config is a cache of server version `remote.cachedVersion`.
 * A pull used to replace it outright, so an edit made to the file by hand (three dead repo entries
 * removed from eu-remote.json, 2026-11-06) was undone by the next command with no word said.
 *
 * Every successful pull now passes through `reconcileLocalEdits` before the cache is rewritten:
 *
 * - The file equals what the cache of the pulled copy would hold: nothing local to lose.
 * - The server is still at the cached version: the file's difference IS a local edit made on top
 *   of the copy the server holds, so it is pushed as the next version (announced on stderr), with
 *   the server copy as the base so a removal carries its tombstone.
 * - The server has moved on: the cached version is read back from the server's history. The file
 *   equal to it means no local edit (the cache is only behind); otherwise both sides changed and
 *   the read is refused with an error naming both versions and the changed pointers. A cached
 *   version that cannot be read back is refused the same way, because a local edit cannot then be
 *   told apart from the server's change.
 *
 * The offline path is untouched: the file is what is served, local edits included.
 */

import type { PullResult, RemoteConfigAdapter } from '../../adapters/remote-config-adapter.js';
import {
  RemoteAuthError,
  RemoteUnreachableError,
  RemoteVersionConflictError,
  RemoteWriteFailedClosedError,
} from '../../adapters/remote-config-errors.js';
import { t } from '../../i18n/index.js';
import type { RdcConfig } from '../../types/index.js';
import { outputService } from '../core/output.js';
import { describeChange, isNoopPush } from './push-visibility.js';
import { mergeRemoteIntoCache } from './remote-cache.js';

/** The local file and the server both changed since the cached version; nothing was overwritten. */
export class RemoteLocalEditConflictError extends Error {
  constructor(
    public readonly configName: string,
    public readonly cachedVersion: number,
    public readonly serverVersion: number,
    public readonly changes: string,
    reason?: string
  ) {
    super(
      reason === undefined
        ? t('commands.config.remote.localEditsConflict', {
            config: configName,
            cached: String(cachedVersion),
            server: String(serverVersion),
            changes,
          })
        : t('commands.config.remote.localEditsUnverifiable', {
            config: configName,
            cached: String(cachedVersion),
            server: String(serverVersion),
            changes,
            reason,
          })
    );
    this.name = 'RemoteLocalEditConflictError';
  }
}

/** The local file's synced content differs from what the cache of `copy` at `version` holds. */
function differs(local: RdcConfig, copy: RdcConfig, version: number): RdcConfig | null {
  const expected = mergeRemoteIntoCache(local, copy, version);
  return isNoopPush(local, expected) ? null : expected;
}

/** Push the local edit made on top of server version `cached`, whose cache form is `base`. */
async function pushLocalEdit(
  adapter: RemoteConfigAdapter,
  configName: string,
  local: RdcConfig,
  base: RdcConfig,
  pulled: PullResult
): Promise<PullResult> {
  const cached = pulled.version;
  const changes = describeChange(local, base) || '-';
  let pushedVersion: number;
  try {
    ({ version: pushedVersion } = await adapter.push(local, cached, { base }));
  } catch (error) {
    if (error instanceof RemoteUnreachableError) {
      throw new RemoteWriteFailedClosedError(configName, error.apiUrl, error);
    }
    if (error instanceof RemoteVersionConflictError) {
      // Another device pushed between the pull and this push: both sides changed.
      throw new RemoteLocalEditConflictError(configName, cached, cached + 1, changes);
    }
    throw error;
  }
  outputService.warn(
    t('commands.config.remote.localEditsPushed', {
      config: configName,
      from: String(cached),
      to: String(pushedVersion),
      changes,
    })
  );
  return { config: local, version: pushedVersion, sdkEpoch: pulled.sdkEpoch };
}

/**
 * What the cache of `configName` must become after `pulled`: the pulled copy, or the local file's
 * edits pushed as a newer version. Throws RemoteLocalEditConflictError when both sides changed.
 * `local` is the decrypted local file.
 */
export async function reconcileLocalEdits(
  adapter: RemoteConfigAdapter,
  configName: string,
  local: RdcConfig,
  pulled: PullResult
): Promise<PullResult> {
  const cached = local.remote?.cachedVersion;
  // A bare pointer (never cached) holds nothing of the store's to lose; a pull older than the cache
  // is refused by the adapter's high-water check before it gets here.
  if (cached === undefined || pulled.version < cached) return pulled;

  const againstPulled = differs(local, pulled.config, pulled.version);
  if (!againstPulled) return pulled;
  if (pulled.version === cached) {
    return pushLocalEdit(adapter, configName, local, againstPulled, pulled);
  }
  await refuseIfEditedSince(adapter, configName, local, cached, pulled.version, againstPulled);
  return pulled;
}

/**
 * The server moved from `cached` to `serverVersion`: read `cached` back and refuse when the local
 * file differs from it too (both sides changed), or when it cannot be read (undecidable).
 */
async function refuseIfEditedSince(
  adapter: RemoteConfigAdapter,
  configName: string,
  local: RdcConfig,
  cached: number,
  serverVersion: number,
  againstPulled: RdcConfig
): Promise<void> {
  let atCached: PullResult;
  try {
    atCached = await adapter.pullVersion(cached);
  } catch (error) {
    if (error instanceof RemoteUnreachableError || error instanceof RemoteAuthError) throw error;
    throw new RemoteLocalEditConflictError(
      configName,
      cached,
      serverVersion,
      describeChange(local, againstPulled) || '-',
      error instanceof Error ? error.message : String(error)
    );
  }
  const againstCached = differs(local, atCached.config, cached);
  if (!againstCached) return;
  throw new RemoteLocalEditConflictError(
    configName,
    cached,
    serverVersion,
    describeChange(local, againstCached) || '-'
  );
}

/**
 * The pointers at which the local file differs from the cache of `pulled`, or null when it does
 * not: what `config remote refresh` is about to discard, named before it does.
 */
export function localEditsAgainst(local: RdcConfig, pulled: PullResult): string | null {
  if (local.remote?.cachedVersion === undefined) return null;
  const expected = differs(local, pulled.config, pulled.version);
  return expected ? describeChange(local, expected) || '-' : null;
}
