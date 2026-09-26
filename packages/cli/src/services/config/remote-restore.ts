/**
 * Restore an earlier version of a remote config (PLAN-config-sync-hardening T16, operator ruling
 * D1 "plus versioning"): `rdc config remote versions` and `rdc config remote restore <version>`.
 *
 * A restore never moves the server backwards. The old version is read and decrypted
 * (`GET /configs/:id/versions/:v`), then pushed as a NEW version on top of the current one through
 * the ordinary compare-and-swap push. The current copy is the push's base, so every path the old
 * version lacks is deleted by tombstone, and every device's high-water mark stays valid. The push
 * names `restoredFromVersion`, which the server records as `config.version.restore`.
 */

import type {
  PullResult,
  RemoteConfigAdapter,
  RemoteVersionInfo,
} from '../../adapters/remote-config-adapter.js';
import { t } from '../../i18n/index.js';
import type { RdcConfig } from '../../types/index.js';
import { ValidationError } from '../../utils/errors.js';
import { pullOrPurge, writeRemoteCache } from './remote-cache.js';

/** The archived versions of the config, newest first. */
export function listRemoteVersions(adapter: RemoteConfigAdapter): Promise<RemoteVersionInfo[]> {
  return adapter.listVersions();
}

/** A `<version>` argument: a positive whole number, or a ValidationError naming what was typed. */
export function parseVersionArgument(raw: string): number {
  const version = /^[1-9]\d{0,9}$/.test(raw.trim()) ? Number(raw.trim()) : Number.NaN;
  if (!Number.isSafeInteger(version)) {
    throw new ValidationError(t('commands.config.remote.restore.invalidVersion', { version: raw }));
  }
  return version;
}

export interface RestoreResult {
  /** The version that was restored. */
  restoredFrom: number;
  /** The version that was current before the restore. */
  replaced: number;
  /** The new version, holding the restored content. */
  version: number;
}

/**
 * Publish `version`'s content as the newest version of the config. `confirm` is asked after both
 * copies are read and before anything is written; a false answer returns null and changes nothing.
 */
export async function restoreRemoteVersion(
  adapter: RemoteConfigAdapter,
  configName: string,
  version: number,
  confirm: (current: number) => Promise<boolean> = () => Promise.resolve(true)
): Promise<RestoreResult | null> {
  const current = await pullOrPurge(adapter, configName);
  if (current.version === version) {
    throw new ValidationError(
      t('commands.config.remote.restore.alreadyCurrent', {
        version: String(version),
        config: configName,
      })
    );
  }
  const old = await adapter.pullVersion(version);
  const content = keepAllocatorAhead(old, current);

  if (!(await confirm(current.version))) return null;

  const pushed = await adapter.push(content, current.version, {
    base: current.config,
    restoredFromVersion: version,
  });
  await writeRemoteCache(configName, content, pushed.version);
  return { restoredFrom: version, replaced: current.version, version: pushed.version };
}

/**
 * The old content, except that the network-ID allocator keeps the current counter when that is
 * higher: repositories created after the old version still hold the IDs handed out since, and a
 * counter moved back would hand them out again.
 */
function keepAllocatorAhead(old: PullResult, current: PullResult): RdcConfig {
  const content = structuredClone(old.config);
  const now = current.config.state?.networkIds?.next;
  const then = content.state?.networkIds?.next;
  if (now !== undefined && (then === undefined || now > then)) {
    content.state = { ...content.state, networkIds: { ...content.state?.networkIds, next: now } };
  }
  return content;
}
