import type { SlotKdfParams } from '@rediacc/shared/config-crypto';
import { toBase64 } from '@rediacc/shared/config-crypto';
import { TOKEN_IP_MISMATCH } from '@rediacc/shared/subscription/types';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { outputService } from '../services/core/output.js';
import { ValidationError } from '../utils/errors.js';
import { askPassword } from '../utils/prompt.js';
import { applyHandoff } from './config-remote-enable.js';
import type { DeviceCredentials } from './config-remote-handoff.js';

// ─── Headless Password Enroll ────────────────────────────────────────────

/** Shape of POST /configs/password-enroll (config:enroll api-token auth). */
interface PasswordEnrollResponse {
  method: 'password';
  kdfParams: SlotKdfParams;
  wrappedCek: string;
  token: string;
  storeId: string;
  /** null for a zero-config store, the CLI then mints an id and seeds it. */
  configId: string | null;
  /** The selected config's teamId; null for the default/org-level config. */
  teamId: string | null;
}

/**
 * Turn a 403 from `POST /configs/password-enroll` into an actionable message.
 *
 * Several unrelated causes share that status, and only one of them is the
 * passkey policy that this code used to blame for all of them. The IP-binding
 * refusal carries `code: TOKEN_IP_MISMATCH` and is handled centrally in
 * `accountServerFetch`, which has already produced its localized message by
 * the time it reaches here. The rest are still bare `HTTPException`s, so the
 * envelope is `{"error":"<message>"}` with NO machine-readable `code` (see
 * private/account/src/middleware/error-handler.ts and
 * src/middleware/api-token.ts) and matching the server's text is the only
 * discriminator for them; `code` is preferred whenever the server sends one.
 *
 * Anything unrecognised repeats the server's own words rather than guessing.
 */
function describeEnrollForbidden(error: unknown): string {
  const { code, message } = error as { code?: string; message?: string };
  const serverMessage = message ?? '';

  if (code === TOKEN_IP_MISMATCH) return serverMessage;
  if (code === 'REQUIRE_PASSKEY' || serverMessage.includes('requires a passkey')) {
    return t('commands.config.remote.enable.passwordRequirePasskey');
  }
  if (serverMessage.includes('Missing required scope')) {
    return t('commands.config.remote.enable.passwordMissingScope');
  }
  if (serverMessage.includes('team is no longer available')) {
    return t('commands.config.remote.enable.passwordTeamGone');
  }
  if (serverMessage.includes('no associated user') || serverMessage.includes('no organization')) {
    return t('commands.config.remote.enable.passwordTokenNotEnrollable');
  }
  return t('commands.config.remote.enable.passwordForbidden', { error: serverMessage });
}

/**
 * Resolve the config master password for a headless password enrollment.
 * Order mirrors requireMasterPassword: REDIACC_CONFIG_PASSWORD env → interactive
 * prompt. There is nothing to verify it against locally, a wrong password fails
 * the probe pull below with a clear message.
 */
function resolveConfigPassword(): Promise<string> {
  const envPassword = process.env.REDIACC_CONFIG_PASSWORD;
  if (envPassword) return Promise.resolve(envPassword);

  if (process.stdin.isTTY !== true) {
    throw new ValidationError(t('commands.config.remote.enable.passwordNonInteractive'));
  }
  return askPassword(t('commands.config.remote.enable.passwordPrompt'));
}

/**
 * The device credentials of a PRE-PROVISIONED password slot, with no browser.
 *
 * The password slot itself is created ahead of time in the portal, where the
 * browser session holds the CEK. Here the headless box merely UNLOCKS it: its
 * own account token (scope config:enroll) fetches the slot's public kdfParams,
 * the opaque wrappedCek, a fresh config token, and the pointer coordinates; the
 * shared password (out of band) derives the slot secret locally. Nothing is
 * stored here: a first enable (`enablePassword`) and a re-enrollment
 * (config-remote-reenroll.ts) both store the result and prove it with a pull.
 */
export async function passwordCredentials(
  apiUrl: string,
  configId?: string
): Promise<DeviceCredentials> {
  // 1. Ask the server to hand back the pre-provisioned password slot. userId is resolved server-side from the token creator; the body carries only the chosen configId (`--config-id`), which scopes the match when the token reads several configs. An api token with the config:enroll scope authenticates the call.
  let enroll: PasswordEnrollResponse;
  try {
    enroll = await accountServerFetch<PasswordEnrollResponse>(
      '/account/api/v1/configs/password-enroll',
      {
        method: 'POST',
        serverUrl: apiUrl,
        token: process.env.REDIACC_TOKEN,
        body: configId ? { configId } : {},
      }
    );
  } catch (error) {
    const status = (error as { status?: number }).status;
    if (status === 403) {
      throw new ValidationError(describeEnrollForbidden(error));
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

  // 3. The same shape the browser handoff carries: the slot secret under a fresh local key id, the token, the wrapped CEK and the pointer coordinates.
  return {
    passkey_secret: toBase64(slotSecret),
    token: enroll.token,
    storageKeyId: `rdc:pw:${crypto.randomUUID()}`,
    wrappedCek: enroll.wrappedCek,
    storeId: enroll.storeId,
    apiUrl,
    // null (zero-config store) collapses to undefined so finalizeEnable mints a configId from the local config's id and seeds the store.
    ...(enroll.configId ? { configId: enroll.configId } : {}),
    // null (default/org config) collapses to undefined, RemoteConfig.teamId is an optional uuid, and a falsy teamId already means "no team filter" on pull.
    ...(enroll.teamId ? { teamId: enroll.teamId } : {}),
  };
}

/** A wrong password surfaces as a CEK unwrap failure (RemoteStaleSlotError from the adapter): name it. */
export async function passwordFailure(error: unknown): Promise<unknown> {
  const { RemoteStaleSlotError } = await import('../adapters/remote-config-adapter.js');
  return error instanceof RemoteStaleSlotError
    ? new ValidationError(t('commands.config.remote.enable.passwordWrong'))
    : error;
}

/**
 * Enroll this box against the password slot: store the credentials exactly like the browser
 * handoff and let the probe pull fail fast (`applyHandoff` removes what it stored on any failure,
 * so a retry starts from a clean slate).
 */
export async function enablePassword(
  apiUrl: string,
  configName: string,
  opts: { force?: boolean; configId?: string } = {}
): Promise<void> {
  const credentials = await passwordCredentials(apiUrl, opts.configId);
  try {
    await applyHandoff(credentials, configName, opts);
  } catch (error) {
    throw await passwordFailure(error);
  }

  outputService.success(t('commands.config.remote.enable.success', { name: configName, apiUrl }));
}
