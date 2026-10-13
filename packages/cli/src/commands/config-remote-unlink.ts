/**
 * `rdc config remote disable --local`: unlink a config on THIS device without the server, and the
 * guidance that leads there.
 *
 * `disable` is server-only by ruling: it pulls the newest server copy first, so a disable from a
 * stale cache cannot lose another device's writes. That leaves no way out once the server path is
 * closed for good: the store no longer holds the config, or this account left the store. The
 * local-only unlink is the explicit, separate way out (operator ruling 2026-10-13).
 *
 * The contract:
 *
 * - It never contacts the server. Newer server data, if any exists, is not fetched; the question
 *   it asks says so. A run with no terminal is refused with the same statement unless `--yes`
 *   (or REDIACC_YES=1) answered it, and the success line repeats what was not done.
 * - It writes the copy this device already holds. The local file of a linked config is the cache
 *   of the last pull or push, with this device's own sections already overlaid by the one cache
 *   merge (`overlayDeviceLocal`), so the unlinked file is that file without its `remote` pointer:
 *   what the server-backed disable writes when the server holds the cached version.
 * - It refuses, with the file untouched, when there is nothing whole to keep: a pointer that was
 *   never cache-stamped (or whose copy was removed), or a cache encrypted with a master password
 *   that cannot be supplied. An empty or partial config is never written.
 * - On success this device's token file goes, and its slot secret when no other local config
 *   names it. The key slot and the config on the server are not touched.
 *
 * The server-backed commands name `--local` only from the states where the server path cannot
 * work (`closedServerPath`, `storeCopyGone`), never as a shortcut around an unreachable server.
 */

import { t } from '../i18n/index.js';
import { ConfigServerError } from '../services/config/config-server-client.js';
import { RemoteTokenRefreshError } from '../services/config/device-token-refresh.js';
import { outputService } from '../services/core/output.js';
import type { RdcConfig, RemoteConfig } from '../types/index.js';
import { hasRemoteConfig } from '../types/index.js';
import { ValidationError } from '../utils/errors.js';
import { askConfirm } from '../utils/prompt.js';
import { storageKeyInUseElsewhere } from './config-remote-enable.js';

/**
 * The store answered that it holds no such config. The adapter maps the team's own 404
 * (`team_not_found`) to RemoteTeamNotFoundError before this is reached, so a bare 404 is the config's.
 */
export function isStoreCopyGone(error: unknown): boolean {
  return error instanceof ConfigServerError && error.status === 404;
}

/** The refusal for a linked config whose store copy is gone: it names the local-only unlink. */
export function storeCopyGone(configName: string, remote: RemoteConfig): ValidationError {
  return new ValidationError(
    t('commands.config.remote.storeCopyGone', {
      name: configName,
      configId: remote.configId,
      storeId: remote.storeId,
    })
  );
}

/** Renewal refusals that say this device's account is no longer in the store. */
const ACCOUNT_LEFT_STORE: ReadonlySet<string> = new Set(['not_store_member', 'store_mismatch']);

/**
 * The refusal `disable` raises when its pull failed for a reason that retrying does not cure: the
 * store copy is gone, or the server refuses this account. Undefined for every other failure, which
 * is raised as it came. A team refusal (`team_forbidden`) is not one of them: the read path removes
 * the offline copy for it (ruling E4), so there is no cached copy the unlink could keep.
 */
export function closedServerPath(
  error: unknown,
  configName: string,
  remote: RemoteConfig
): ValidationError | undefined {
  if (isStoreCopyGone(error)) return storeCopyGone(configName, remote);
  const refused =
    (error instanceof ConfigServerError && error.status === 403) ||
    (error instanceof RemoteTokenRefreshError && ACCOUNT_LEFT_STORE.has(error.code));
  if (!refused) return undefined;
  return new ValidationError(
    t('commands.config.remote.disable.accessLost', { name: configName, error: error.message })
  );
}

/**
 * Remove this device's slot secret for the unlinked config, unless another local config names it
 * (F17). A device whose secure storage cannot be used still unlinks: that state is one of the
 * reasons to be here, so it is reported and not raised.
 */
async function removeSlotSecret(storageKeyId: string, configName: string): Promise<void> {
  const { getSecureStorage, SecureStorageUnavailableError } = await import(
    '../utils/secure-storage.js'
  );
  if (await storageKeyInUseElsewhere(storageKeyId, configName)) return;
  try {
    await getSecureStorage().delete(storageKeyId);
  } catch (error) {
    if (!(error instanceof SecureStorageUnavailableError)) throw error;
    outputService.warn(
      t('commands.config.remote.disable.localSecretLeft', { error: error.message })
    );
  }
}

/** `config remote disable --local`. See the module doc for the contract. */
export async function disableLocal(configName: string, opts: { yes?: boolean }): Promise<void> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const linked = await configFileStorage.load(configName);
  if (!hasRemoteConfig(linked)) {
    throw new ValidationError(t('commands.config.remote.disable.notEnabled'));
  }
  const remote = linked.remote;

  // A pointer with no cache stamp holds no copy of the config: never pulled here, or removed when the account lost its team.
  if (remote.cachedVersion === undefined) {
    throw new ValidationError(
      t('commands.config.remote.disable.localNoCache', { name: configName })
    );
  }
  const version = String(remote.cachedVersion);

  // The cache is opened before the question is asked, so a copy that cannot be read is refused with nothing changed and nothing confirmed.
  try {
    await configFileStorage.loadDecrypted(configName);
  } catch (error) {
    throw new ValidationError(
      t('commands.config.remote.disable.localUnreadable', {
        name: configName,
        version,
        error: error instanceof Error ? error.message : String(error),
      })
    );
  }

  // askConfirm ends the process on a stdin that is no terminal, with a line that does not say what was being confirmed. The refusal here says it (REDIACC_YES=1 still confirms, as it does for every prompt).
  if (opts.yes !== true && process.stdin.isTTY !== true && process.env.REDIACC_YES !== '1') {
    throw new ValidationError(
      t('commands.config.remote.disable.localNeedsYes', { name: configName, version })
    );
  }

  const confirmed =
    opts.yes === true ||
    (await askConfirm(
      t('commands.config.remote.disable.localConfirm', {
        name: configName,
        server: remote.apiUrl,
        version,
        cachedAt: remote.cachedAt ?? '-',
      }),
      false
    ));
  if (!confirmed) {
    outputService.info(t('prompts.cancelled'));
    return;
  }

  await configFileStorage.update(configName, (cache) => {
    if (!hasRemoteConfig(cache)) {
      throw new ValidationError(t('commands.config.remote.disable.notEnabled'));
    }
    const unlinked: RdcConfig = { ...cache };
    delete unlinked.remote;
    return unlinked;
  });

  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  await remoteTokenStorage.delete(configName);
  await removeSlotSecret(remote.storageKeyId, configName);

  outputService.success(
    t('commands.config.remote.disable.localSuccess', { name: configName, version })
  );
}
