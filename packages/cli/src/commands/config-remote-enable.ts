/**
 * Enable/seed flow for `config remote enable` (split from config-remote.ts,
 * which keeps the transports: callback server, device-code polling, rotate).
 *
 * Validate the enrollment by pulling, seed a fresh store, and turn the local
 * file into a full-content cache (D1/D5):
 *
 * - 404 (fresh store) → push the local config at version 0 (server inserts at
 *   v1), pull it back as round-trip proof, then write the cache.
 * - pull succeeds but the store's content differs from non-empty local
 *   resources → confirm before replacing local content (`--force` skips;
 *   non-TTY aborts naming --force).
 * - any other error → abort with the local file untouched (the cache write is
 *   the LAST step).
 */

import type { RemoteConfigAdapter } from '../adapters/remote-config-adapter.js';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import type { RdcConfig, RemoteConfig } from '../types/index.js';
import { ValidationError } from '../utils/errors.js';
import { askConfirm } from '../utils/prompt.js';
import type { HandoffPayload } from './config-remote-handoff.js';

/**
 * A remote pointer whose configId may still be unminted. Fresh-store handoffs
 * carry no configId; `finalizeEnable` mints one from the local config's id
 * before anything is written.
 */
export type PendingRemoteConfig = Omit<RemoteConfig, 'configId'> & { configId?: string };

export async function storeHandoffCredentials(
  payload: HandoffPayload,
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

/** Best-effort removal of stored handoff credentials after a failed enable. */
async function cleanupHandoffCredentials(storageKeyId: string, configName: string): Promise<void> {
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  await getSecureStorage()
    .delete(storageKeyId)
    .catch(() => {});
  await remoteTokenStorage.delete(configName).catch(() => {});
}

function countResources(config: RdcConfig): { machines: number; repos: number; total: number } {
  const r = config.resources;
  const machines = Object.keys(r?.machines ?? {}).length;
  const repos = Object.keys(r?.repositories ?? {}).length;
  const total =
    machines +
    repos +
    Object.keys(r?.storages ?? {}).length +
    (r?.deletedRepositories?.length ?? 0);
  return { machines, repos, total };
}

/** Order-sensitive but adequate: worst case is one extra confirmation prompt. */
function resourcesDiffer(local: RdcConfig, pulled: RdcConfig): boolean {
  return JSON.stringify(local.resources ?? {}) !== JSON.stringify(pulled.resources ?? {});
}

/**
 * Pull the store's copy; a 404 means a fresh store, which is seeded from the
 * local config and pulled back as round-trip proof before anything is written
 * locally.
 */
async function pullOrSeed(
  adapter: RemoteConfigAdapter,
  local: RdcConfig
): Promise<{ pulled: { config: RdcConfig; version: number }; seeded: boolean }> {
  try {
    return { pulled: await adapter.pull(), seeded: false };
  } catch (error) {
    const { ConfigServerError } = await import('../services/config/config-server-client.js');
    if (!(error instanceof ConfigServerError && error.status === 404)) throw error;

    const { stripStateForPush } = await import('../adapters/config-field-crypto.js');
    const seedDoc = stripStateForPush(local);
    // Belt and braces: the push projection drops `remote` anyway.
    delete seedDoc.remote;
    await adapter.push(seedDoc, 0); // server inserts at version 1
    const pulled = await adapter.pull();
    outputService.success(t('commands.config.remote.enable.seeded'));
    return { pulled, seeded: true };
  }
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

/** See the module doc for the three-way contract this enforces. */
export async function finalizeEnable(
  remote: PendingRemoteConfig,
  configName: string,
  opts: { force?: boolean } = {}
): Promise<void> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const local = await configFileStorage.loadDecrypted(configName);

  // Fresh-store handoffs carry no configId: mint one from the local config's
  // own id (already a stable UUID) and seed the store below.
  const pointer: RemoteConfig = { ...remote, configId: remote.configId ?? local.id };

  const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const adapter = new RemoteConfigAdapter(
    pointer,
    configName,
    remoteTokenStorage,
    getSecureStorage()
  );

  const { pulled, seeded } = await pullOrSeed(adapter, local);

  const counts = countResources(local);
  if (!seeded && counts.total > 0 && resourcesDiffer(local, pulled.config) && !opts.force) {
    await confirmOverwrite(
      configName,
      counts,
      `${configFileStorage.getConfigPath(configName)}.bak`
    );
  }

  // The pointer file write IS the cache write: full server content, host-local
  // sections (encryption mode included) preserved from the pre-enable config.
  const { mergeRemoteIntoCache } = await import('../services/config/remote-cache.js');
  const cached = mergeRemoteIntoCache({ ...local, remote: pointer }, pulled.config, pulled.version);
  await configFileStorage.save(cached, configName);
}

/**
 * Decrypt-store-finalize shared by the browser and headless flows. On any
 * finalize failure the stored credentials are removed so a retry starts clean
 * (mirrors the password path's cleanup). Exported for the seed tests.
 */
export async function applyHandoff(
  payload: HandoffPayload,
  configName: string,
  opts: { force?: boolean }
): Promise<void> {
  const remote = await storeHandoffCredentials(payload, configName);
  try {
    await finalizeEnable(remote, configName, opts);
  } catch (error) {
    await cleanupHandoffCredentials(payload.storageKeyId, configName);
    throw error;
  }
}
