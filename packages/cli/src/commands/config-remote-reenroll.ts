/**
 * Re-enrollment of THIS device for a config that is already linked (`config remote enable` on a
 * linked config).
 *
 * A linked config whose device credentials stopped working had no way back: every error of that
 * family names `rdc config remote enable`, which refused a linked config and named `disable`, and
 * `disable` is server-only, so it needs the very credentials that are gone. The slot secret is the
 * usual casualty: the Linux kernel keyring that holds it does not outlive a reboot.
 *
 * The contract:
 *
 * - `enrollmentUsable` decides between the two answers of `enable` on a linked config. A missing
 *   slot secret or token file is read locally with no request; otherwise one server-only pull
 *   decides. A pull that opens the config means the enrollment works and `enable` still refuses.
 *   Only a failure a new enrollment cures counts as lost; an unreachable server, a team this
 *   account is not in, a rollback, or a renewal refusal outside the closed cured set is raised as
 *   it came. A store that no longer holds the config is refused naming `disable --local`.
 * - `reenrollDevice` takes fresh device credentials for the SAME store and replaces only what is
 *   device-held: the slot secret, the config token, the wrapped CEK and the pointer's
 *   `storageKeyId` (and the team the server names for the same config). `storeId` and `configId`
 *   never change, and credentials for another store or another config are refused.
 * - It never pushes and never seeds. The local file of a linked config is a cache, so the pull is
 *   written through the one cache writer (`writeRemoteCache`), which keeps every host-local
 *   section, and a pull older than the cache is refused. `--force` has no part in it.
 * - Any failure puts the previous credentials back, so a failed attempt leaves the device exactly
 *   as it was.
 */

import type { RemoteConfigAdapter } from '../adapters/remote-config-adapter.js';
import {
  RemoteAuthError,
  RemoteConfigUndecryptableError,
  RemotePasskeySecretMissingError,
  RemoteRollbackError,
  RemoteStaleSlotError,
  RemoteTeamNotFoundError,
} from '../adapters/remote-config-errors.js';
import { t } from '../i18n/index.js';
import { normalizeServerUrl } from '../services/account/subscription-auth.js';
import { RemoteTokenRefreshError } from '../services/config/device-token-refresh.js';
import { outputService } from '../services/core/output.js';
import type { RemoteConfig } from '../types/index.js';
import { ValidationError } from '../utils/errors.js';
import { checkEnablePrerequisites, storageKeyInUseElsewhere } from './config-remote-enable.js';
import type { DeviceCredentials } from './config-remote-handoff.js';
import { runRelayHandoff } from './config-remote-relay.js';
import { isStoreCopyGone, storeCopyGone } from './config-remote-unlink.js';

/**
 * The renewal refusals a new enrollment cures: the key was rotated away from every slot of this
 * account, or the login is bound to another address and its own message names a new enrollment as
 * the other remedy. The set is closed on purpose. Every other code is raised as it came and starts
 * no enrollment: a rate limit, a rejected or scopeless login, an account outside the store, and
 * any code not listed here (a failed or malformed renewal says nothing about this device's
 * credentials, and replacing working ones over a passing fault is the worse mistake).
 */
const CURED_BY_ENROLLMENT: ReadonlySet<string> = new Set([
  'stale_cek_generation',
  'login_ip_mismatch',
]);

/**
 * Whether `error`, raised by a pull, is a failure of this device's own credentials: the kind a
 * fresh slot secret, config token and wrapped CEK replace.
 */
function isLostEnrollment(error: unknown): boolean {
  if (error instanceof RemoteTokenRefreshError) return CURED_BY_ENROLLMENT.has(error.code);
  return (
    error instanceof RemotePasskeySecretMissingError ||
    error instanceof RemoteStaleSlotError ||
    error instanceof RemoteAuthError ||
    error instanceof RemoteConfigUndecryptableError ||
    error instanceof RemoteTeamNotFoundError
  );
}

/**
 * True when this device can still open the linked config. See the module doc for how it decides;
 * an error that says nothing about the device's credentials is rethrown.
 */
export async function enrollmentUsable(remote: RemoteConfig, configName: string): Promise<boolean> {
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const secureStorage = getSecureStorage();

  if ((await secureStorage.get(remote.storageKeyId)) === null) return false;
  const tokenData = await remoteTokenStorage.get(configName);
  if (!tokenData?.token || !tokenData.wrappedCek) return false;

  const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
  const adapter = new RemoteConfigAdapter(remote, configName, remoteTokenStorage, secureStorage);
  try {
    await adapter.pull();
    return true;
  } catch (error) {
    if (isLostEnrollment(error)) return false;
    // The credentials work and the store no longer holds the config: no enrollment brings it back, so the way out is named.
    if (isStoreCopyGone(error)) throw storeCopyGone(configName, remote);
    throw error;
  }
}

/** Refuse credentials that are not for the store and config this local config is linked to. */
function assertSameTarget(
  credentials: DeviceCredentials,
  linked: RemoteConfig,
  configName: string
): void {
  if (credentials.storeId !== linked.storeId) {
    throw new ValidationError(
      t('commands.config.remote.enable.reenrollStoreMismatch', {
        name: configName,
        linkedStore: linked.storeId,
        offeredStore: credentials.storeId,
      })
    );
  }
  if (credentials.configId !== undefined && credentials.configId !== linked.configId) {
    throw new ValidationError(
      t('commands.config.remote.enable.reenrollConfigMismatch', {
        name: configName,
        linkedConfig: linked.configId,
        offeredConfig: credentials.configId,
      })
    );
  }
}

/**
 * Replace this device's credentials for the linked config with `credentials`, prove them with a
 * pull, and refresh the cache. Returns the server version now cached. See the module doc.
 */
async function reenrollDevice(
  credentials: DeviceCredentials,
  configName: string,
  linked: RemoteConfig
): Promise<number> {
  assertSameTarget(credentials, linked, configName);

  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const secureStorage = getSecureStorage();

  // The pointer keeps its store and config. The team follows the server only when the credentials name this same config; a handoff that names none says nothing about its team.
  const pointer: RemoteConfig = {
    ...linked,
    storageKeyId: credentials.storageKeyId,
    teamId: credentials.configId === undefined ? linked.teamId : credentials.teamId,
  };

  const previousToken = await remoteTokenStorage.get(configName);
  const previousSecret = await secureStorage.get(credentials.storageKeyId);
  const restore = async (): Promise<void> => {
    if (previousToken) await remoteTokenStorage.set(configName, previousToken);
    else await remoteTokenStorage.delete(configName);
    if (previousSecret !== null) {
      await secureStorage.set(credentials.storageKeyId, previousSecret);
    } else if (!(await storageKeyInUseElsewhere(credentials.storageKeyId, configName))) {
      await secureStorage.delete(credentials.storageKeyId);
    }
  };

  let version: number;
  try {
    await secureStorage.set(credentials.storageKeyId, credentials.passkey_secret);
    // `set` keeps the token file's sync record, so the versions this device already saw still guard the pull below.
    await remoteTokenStorage.set(configName, {
      token: credentials.token,
      wrappedCek: credentials.wrappedCek,
    });

    const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
    const adapter = new RemoteConfigAdapter(pointer, configName, remoteTokenStorage, secureStorage);
    const pulled = await pullLinked(adapter, configName, linked);

    // The sync record lives in the token file; when that file was lost with the secret, the cache stamp is what this device last saw.
    if (linked.cachedVersion !== undefined && pulled.version < linked.cachedVersion) {
      throw new RemoteRollbackError(
        t('commands.config.remote.rollback', {
          configId: linked.configId,
          version: String(pulled.version),
          highWater: String(linked.cachedVersion),
        })
      );
    }

    // The pointer and the content it opened land in one cache write, through the one cache merge.
    const { writeRemoteCache } = await import('../services/config/remote-cache.js');
    await writeRemoteCache(configName, pulled.config, pulled.version, pointer);
    version = pulled.version;
  } catch (error) {
    await restore().catch(() => {});
    throw error;
  }

  // The secret under the old key id is no longer named by this config; it goes unless another local config still uses it.
  if (
    linked.storageKeyId !== credentials.storageKeyId &&
    !(await storageKeyInUseElsewhere(linked.storageKeyId, configName).catch(() => true))
  ) {
    await secureStorage.delete(linked.storageKeyId).catch(() => {});
  }
  return version;
}

/** The server-only pull of a re-enrollment. A store that no longer holds the config is named, never seeded. */
async function pullLinked(adapter: RemoteConfigAdapter, configName: string, linked: RemoteConfig) {
  try {
    return await adapter.pull();
  } catch (error) {
    if (isStoreCopyGone(error)) throw storeCopyGone(configName, linked);
    throw error;
  }
}

/** The account server a re-enrollment talks to: the linked store's own. `--api-url` may only repeat it. */
function linkedApiUrl(linked: RemoteConfig, configName: string, requested?: string): string {
  if (
    requested !== undefined &&
    normalizeServerUrl(requested) !== normalizeServerUrl(linked.apiUrl)
  ) {
    throw new ValidationError(
      t('commands.config.remote.enable.reenrollServerMismatch', {
        name: configName,
        linkedUrl: linked.apiUrl,
        requestedUrl: requested,
      })
    );
  }
  return linked.apiUrl;
}

/**
 * `config remote enable` on a linked config whose enrollment is lost: obtain fresh credentials
 * the way a first enable does (the portal handoff, or the password slot with `--password`) and
 * apply them with `reenrollDevice`.
 */
export async function reenroll(
  configName: string,
  linked: RemoteConfig,
  options: { password?: boolean; apiUrl?: string; configId?: string }
): Promise<void> {
  const apiUrl = linkedApiUrl(linked, configName, options.apiUrl);
  // A re-enrollment is for the config this one is linked to; naming another is refused up front.
  if (options.configId !== undefined && options.configId !== linked.configId) {
    throw new ValidationError(
      t('commands.config.remote.enable.reenrollConfigIdMismatch', {
        name: configName,
        linkedConfig: linked.configId,
        requestedConfig: options.configId,
      })
    );
  }
  outputService.info(t('commands.config.remote.enable.reenrolling', { name: configName }));

  let version: number;
  if (options.password) {
    const { passwordCredentials, passwordFailure } = await import('./config-remote-password.js');
    const credentials = await passwordCredentials(apiUrl, options.configId);
    version = await reenrollDevice(credentials, configName, linked).catch(
      async (error: unknown) => {
        throw await passwordFailure(error);
      }
    );
  } else {
    const { token, email } = await checkEnablePrerequisites(apiUrl);
    const payload = await runRelayHandoff(apiUrl, token, email);
    version = await reenrollDevice(payload, configName, linked);
  }

  outputService.success(
    t('commands.config.remote.enable.reenrollSuccess', {
      name: configName,
      version: String(version),
    })
  );
}
