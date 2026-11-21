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
 * Only a hand edit counts: `state` is runtime the cache merge resolves per repo, so a difference
 * there is settled by the merge, never pushed (S3 in private/account config-sync/state-sync.test.ts).
 * The CLI-maintained `resources` families (CLI_MAINTAINED_RESOURCES: archive records) are not hand
 * edits either: each is written by its own CLI command through a versioned push, so a read never
 * pushes a difference there and the pulled copy's value wins.
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

/**
 * What a hand edit of `local` means against `expected` (the cache of a pulled copy): the file with
 * every family the cache merge resolves taken from `expected`. `state` is runtime the merge settles
 * per repo (the pulled copy wins where both have a repo), so a state difference is never an edit to
 * push; the device-local pointers already take the local value in `expected`.
 */
function asHandEdit(local: RdcConfig, expected: RdcConfig): RdcConfig {
  const edited: RdcConfig = { ...local };
  if (expected.state === undefined) delete edited.state;
  else edited.state = expected.state;
  return withCliMaintainedFrom(edited, expected);
}

/**
 * The `resources` families only CLI commands write (repo delete/archive and config prune), each
 * through the normal versioned push: a person does not hand-edit them, so a local difference there
 * is never an edit for a read to push (#46e74ab0).
 */
const CLI_MAINTAINED_RESOURCES = ['deletedRepositories'] as const;

/** `edited` with every CLI-maintained `resources` family taken from `expected`. */
function withCliMaintainedFrom(edited: RdcConfig, expected: RdcConfig): RdcConfig {
  if (edited.resources === undefined && expected.resources === undefined) return edited;
  const resources: NonNullable<RdcConfig['resources']> = { ...edited.resources };
  for (const key of CLI_MAINTAINED_RESOURCES) {
    const value = expected.resources?.[key];
    if (value === undefined) delete resources[key];
    else resources[key] = value;
  }
  if (Object.keys(resources).length === 0 && expected.resources === undefined) {
    delete edited.resources;
  } else {
    edited.resources = resources;
  }
  return edited;
}

interface LocalEdit {
  /** The cache form of the pulled copy: the push base. */
  expected: RdcConfig;
  /** The local file as a hand edit: what gets pushed. */
  edited: RdcConfig;
}

/** The local file's hand edit against the cache of `copy` at `version`, or null when it holds none. */
function differs(local: RdcConfig, copy: RdcConfig, version: number): LocalEdit | null {
  const expected = mergeRemoteIntoCache(local, copy, version);
  const edited = asHandEdit(local, expected);
  return isNoopPush(edited, expected) ? null : { expected, edited };
}

/** Push the local edit made on top of server version `cached`, whose cache form is `base`. */
async function pushLocalEdit(
  adapter: RemoteConfigAdapter,
  configName: string,
  { expected: base, edited: local }: LocalEdit,
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
    return pushLocalEdit(adapter, configName, againstPulled, pulled);
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
  againstPulled: LocalEdit
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
      describeChange(againstPulled.edited, againstPulled.expected) || '-',
      error instanceof Error ? error.message : String(error)
    );
  }
  const againstCached = differs(local, atCached.config, cached);
  if (!againstCached) return;
  throw new RemoteLocalEditConflictError(
    configName,
    cached,
    serverVersion,
    describeChange(againstCached.edited, againstCached.expected) || '-'
  );
}

/**
 * The pointers at which the local file differs from the cache of `pulled`, or null when it does
 * not: what `config remote refresh` is about to discard, named before it does.
 */
export function localEditsAgainst(local: RdcConfig, pulled: PullResult): string | null {
  if (local.remote?.cachedVersion === undefined) return null;
  const edit = differs(local, pulled.config, pulled.version);
  return edit ? describeChange(edit.edited, edit.expected) || '-' : null;
}
