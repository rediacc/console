/**
 * The one write path for the synced part of a config (PLAN-config-sync-hardening T18).
 *
 * A remote-enabled config's local file is a CACHE of the server copy: the next pull overwrites
 * every synced section with what the server holds. An edit that only reached the file was
 * therefore reverted silently on the next command. Every writer of a synced section goes through
 * `updateSyncedConfig`, which pushes the edit (with the version-conflict replay of
 * `RemoteResourceState.updateDocument`) when the config is remote and edits the file otherwise.
 *
 * Only the device-local pointers (DEVICE_LOCAL_POINTERS in packages/shared config-schema) stay on
 * this host; a write aimed at one of them goes to the file even for a remote config.
 * `__tests__/synced-write-guard.test.ts` fails when a new direct file writer appears.
 */

import { DEVICE_LOCAL_POINTERS } from '@rediacc/shared/config-schema';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import type { RdcConfig } from '../../types/index.js';
import { hasRemoteConfig } from '../../types/index.js';
import { currentRequestConfig } from '../core/request-context.js';

type ConfigEdit = (cfg: RdcConfig) => RdcConfig;

/** True when `configName` exists on disk and carries a `remote` pointer. */
export async function isRemoteConfigFile(configName: string): Promise<boolean> {
  // A request-scoped dispatch edits the session's config in memory, never a remote store.
  if (currentRequestConfig()) return false;
  if (!(await configFileStorage.exists(configName))) return false;
  return hasRemoteConfig(await configFileStorage.load(configName));
}

/** True when `pointer` is (or sits under) a pointer that never leaves this host. */
export function isDeviceLocalPointer(pointer: string): boolean {
  return DEVICE_LOCAL_POINTERS.some((p) => pointer === p || pointer.startsWith(`${p}/`));
}

/**
 * Apply `edit` to config `configName`. For a remote config the edit is pushed, and on a version
 * conflict applied again to the fresh server copy, so `edit` must derive its result from the
 * document it is given (never from a copy read earlier). Any other config is edited on disk.
 */
export async function updateSyncedConfig(configName: string, edit: ConfigEdit): Promise<void> {
  if (await isRemoteConfigFile(configName)) {
    await pushEdit(configName, edit);
    return;
  }
  await configFileStorage.update(configName, edit);
}

/**
 * `updateSyncedConfig` for a write aimed at one JSON pointer: a device-local pointer is edited in
 * the file, anything else is synced.
 */
export async function updateConfigAtPointer(
  configName: string,
  pointer: string,
  edit: ConfigEdit
): Promise<void> {
  if (isDeviceLocalPointer(pointer)) {
    await configFileStorage.update(configName, edit);
    return;
  }
  await updateSyncedConfig(configName, edit);
}

async function pushEdit(configName: string, edit: ConfigEdit): Promise<void> {
  // Imported lazily: config-resources imports the cluster and datastore writers that import this module.
  const { configService } = await import('./config-resources.js');
  if (configName !== configService.getEffectiveConfigName()) {
    throw new Error(
      `Config "${configName}" is remote-enabled but is not the active config; select it with --config to edit it`
    );
  }
  const state = await configService.getResourceState();
  const { RemoteResourceState } = await import('./resource-state.js');
  if (!(state instanceof RemoteResourceState)) {
    await configFileStorage.update(configName, edit);
    return;
  }
  await state.updateDocument(edit);
  // The memoized snapshot and resource view predate the push; the next read pulls again.
  configService.resetResourceView();
}
