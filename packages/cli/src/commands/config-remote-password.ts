import type { SlotKdfParams } from '@rediacc/shared/config-crypto';
import { toBase64 } from '@rediacc/shared/config-crypto';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { outputService } from '../services/core/output.js';
import { ValidationError } from '../utils/errors.js';
import { askPassword } from '../utils/prompt.js';
import { finalizeEnable, type PendingRemoteConfig } from './config-remote-enable.js';

// ─── Headless Password Enroll ────────────────────────────────────────────

/** Shape of POST /configs/password-enroll (config:enroll api-token auth). */
interface PasswordEnrollResponse {
  method: 'password';
  kdfParams: SlotKdfParams;
  wrappedCek: string;
  token: string;
  storeId: string;
  /** null for a zero-config store — the CLI then mints an id and seeds it. */
  configId: string | null;
  /** The selected config's teamId; null for the default/org-level config. */
  teamId: string | null;
}

/**
 * Resolve the config master password for a headless password enrollment.
 * Order mirrors requireMasterPassword: REDIACC_CONFIG_PASSWORD env → interactive
 * prompt. There is nothing to verify it against locally — a wrong password fails
 * the probe pull below with a clear message.
 */
async function resolveConfigPassword(): Promise<string> {
  const envPassword = process.env.REDIACC_CONFIG_PASSWORD;
  if (envPassword) return envPassword;

  if (process.stdin.isTTY !== true) {
    throw new ValidationError(t('commands.config.remote.enable.passwordNonInteractive'));
  }
  return askPassword(t('commands.config.remote.enable.passwordPrompt'));
}

/**
 * Enroll this box against a PRE-PROVISIONED password slot, with no browser.
 *
 * The password slot itself is created ahead of time in the portal, where the
 * browser session holds the CEK. Here the headless box merely UNLOCKS it: its
 * own account token (scope config:enroll) fetches the slot's public kdfParams,
 * the opaque wrappedCek, a fresh config token, and the pointer coordinates; the
 * shared password (out of band) derives the slot secret locally; a probe pull
 * proves the unwrap actually opens the config before anything is written.
 */
export async function enablePassword(
  apiUrl: string,
  configName: string,
  opts: { force?: boolean } = {}
): Promise<void> {
  // 1. Ask the server to hand back the pre-provisioned password slot. userId is
  //    resolved server-side from the token creator, so the body is empty. An
  //    api token with the config:enroll scope authenticates the call.
  let enroll: PasswordEnrollResponse;
  try {
    enroll = await accountServerFetch<PasswordEnrollResponse>(
      '/account/api/v1/configs/password-enroll',
      {
        method: 'POST',
        serverUrl: apiUrl,
        token: process.env.REDIACC_TOKEN,
        body: {},
      }
    );
  } catch (error) {
    const status = (error as { status?: number }).status;
    if (status === 403) {
      throw new ValidationError(t('commands.config.remote.enable.passwordRequirePasskey'));
    }
    if (status === 404) {
      throw new ValidationError(t('commands.config.remote.enable.passwordNoSlot'));
    }
    throw error;
  }

  // 2. Derive the 32-byte slot secret from the shared password + public kdfParams.
  const password = await resolveConfigPassword();
  const { derivePasswordSlotSecret } = await import('@rediacc/shared/config-crypto');
  const slotSecret = await derivePasswordSlotSecret(password, enroll.kdfParams);

  // 3. Persist exactly like the browser handoff: slot secret in OS secure storage
  //    under a fresh local key id, token + wrappedCek in the token file, and a
  //    stripped pointer once the probe pull confirms the unwrap.
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const secureStorage = getSecureStorage();
  const storageKeyId = `rdc:pw:${crypto.randomUUID()}`;
  await secureStorage.set(storageKeyId, toBase64(slotSecret));

  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  await remoteTokenStorage.set(configName, { token: enroll.token, wrappedCek: enroll.wrappedCek });

  const remote: PendingRemoteConfig = {
    apiUrl,
    storeId: enroll.storeId,
    // null (zero-config store) collapses to undefined so finalizeEnable mints
    // a configId from the local config's id and seeds the store.
    configId: enroll.configId ?? undefined,
    storageKeyId,
    // null (default/org config) collapses to undefined — RemoteConfig.teamId is
    // an optional uuid, and a falsy teamId already means "no team filter" on pull.
    teamId: enroll.teamId ?? undefined,
  };

  // 4. Probe pull to fail fast. A wrong password surfaces as a CEK unwrap failure
  //    (RemoteStaleSlotError from the adapter). Clean up the stored artifacts so a
  //    retry starts from a clean slate, and report an actionable message.
  try {
    await finalizeEnable(remote, configName, opts);
  } catch (error) {
    await secureStorage.delete(storageKeyId).catch(() => {});
    await remoteTokenStorage.delete(configName).catch(() => {});

    const { RemoteStaleSlotError } = await import('../adapters/remote-config-adapter.js');
    if (error instanceof RemoteStaleSlotError) {
      throw new ValidationError(t('commands.config.remote.enable.passwordWrong'));
    }
    throw error;
  }

  outputService.success(t('commands.config.remote.enable.success', { name: configName, apiUrl }));
}
