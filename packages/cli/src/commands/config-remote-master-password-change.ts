/**
 * `rdc config remote master-password change`: replace this member's master password (the `password` key slot)
 * without the portal.
 *
 * The CEK never leaves this process. It comes from THIS device's own enrollment (slot secret in secure
 * storage, wrapped CEK beside the config token), proven current by a pull before anything is written.
 * The new slot is built exactly as the portal's buildPasswordSlot builds it (fresh PBKDF2 params, the
 * shared wrapCekForSlot pipeline), so `config remote enable --master-password` unlocks it. The write is
 * PUT /configs/slots/password, which needs a cookie session that is 2FA-enabled and ELEVATED: a
 * password login does not elevate, POST /auth/reauth/totp does, and a TOTP step is spent once per user,
 * so the step-up code must come from a later step than the sign-in code.
 */
import type { SlotKdfParams } from '@rediacc/shared/config-crypto';
import { t } from '../i18n/index.js';
import {
  LOGIN_EMAIL_ENV,
  LOGIN_PASSWORD_ENV,
  LOGIN_TOTP_ENV,
  openSession,
  type PasswordLoginInput,
  sessionRequest,
} from '../services/account/subscription-password-auth.js';
import { outputService } from '../services/core/output.js';
import { hasRemoteConfig } from '../types/index.js';
import { ValidationError } from '../utils/errors.js';
import { askInput, askPassword } from '../utils/prompt.js';
import { withSpinner } from '../utils/spinner.js';

/** The new master password, when not piped on stdin. Never argv. */
const NEW_STORE_MASTER_PASSWORD_ENV = 'REDIACC_NEW_STORE_MASTER_PASSWORD';
/** A TOTP code from a later 30-second step than REDIACC_LOGIN_TOTP, spent on the re-authentication. */
const LOGIN_TOTP_NEXT_ENV = 'REDIACC_LOGIN_TOTP_NEXT';
/** The portal's floor (ConfigKeySlots addPasswordSlot). */
export const MIN_MASTER_PASSWORD_LENGTH = 8;

const TOTP_PATTERN = /^\d{6}$/;
const EMAIL_PATTERN = /^\S+@\S+$/;

function interactive(): boolean {
  return process.stdin.isTTY === true;
}

function checkLength(password: string): string {
  if (password.length < MIN_MASTER_PASSWORD_LENGTH) {
    throw new ValidationError(
      t('commands.config.remote.masterPassword.change.newPasswordTooShort', {
        min: MIN_MASTER_PASSWORD_LENGTH,
      })
    );
  }
  return password;
}

/** The new master password: stdin under --new-master-password-stdin, else the env, else a confirmed TTY prompt. */
export async function resolveNewMasterPassword(fromStdin: boolean): Promise<string> {
  if (fromStdin) {
    const { readStdinValue } = await import('../utils/stdin.js');
    const value = await readStdinValue();
    if (!value) {
      throw new ValidationError(
        t('commands.config.remote.masterPassword.change.newPasswordStdinEmpty')
      );
    }
    return checkLength(value);
  }
  const fromEnv = process.env[NEW_STORE_MASTER_PASSWORD_ENV];
  if (fromEnv) return checkLength(fromEnv);
  if (!interactive()) {
    throw new ValidationError(
      t('commands.config.remote.masterPassword.change.newPasswordMissing', {
        env: NEW_STORE_MASTER_PASSWORD_ENV,
      })
    );
  }
  const first = checkLength(
    await askPassword(t('commands.config.remote.masterPassword.change.newPasswordPrompt'))
  );
  const second = await askPassword(
    t('commands.config.remote.masterPassword.change.newPasswordConfirm')
  );
  if (first !== second) {
    throw new ValidationError(
      t('commands.config.remote.masterPassword.change.newPasswordMismatch')
    );
  }
  return first;
}

/** Account sign-in input: env first, a TTY prompt otherwise; a missing field is named, never guessed. */
async function resolveLoginInput(): Promise<PasswordLoginInput> {
  const missing = (field: string) =>
    new ValidationError(t('commands.subscription.login.passwordMissing', { field }));

  let email = process.env[LOGIN_EMAIL_ENV]?.trim();
  if (!email) {
    if (!interactive()) throw missing(LOGIN_EMAIL_ENV);
    email = await askInput(
      t('commands.config.remote.masterPassword.change.emailPrompt'),
      EMAIL_PATTERN
    );
  }
  let password = process.env[LOGIN_PASSWORD_ENV];
  if (!password) {
    if (!interactive()) throw missing(LOGIN_PASSWORD_ENV);
    password = await askPassword(
      t('commands.config.remote.masterPassword.change.loginPasswordPrompt')
    );
  }
  let totp = process.env[LOGIN_TOTP_ENV]?.trim();
  if (!totp && interactive()) {
    totp = await askInput(
      t('commands.config.remote.masterPassword.change.totpPrompt'),
      TOTP_PATTERN
    );
  }
  return { email, password, ...(totp ? { totp } : {}) };
}

/** The step-up code: REDIACC_LOGIN_TOTP_NEXT, else a TTY prompt, else a named refusal. */
async function resolveStepUpCode(loginTotp: string | undefined): Promise<string> {
  let code = process.env[LOGIN_TOTP_NEXT_ENV]?.trim();
  if (!code) {
    if (!interactive()) {
      throw new ValidationError(
        t('commands.config.remote.masterPassword.change.stepUpRequired', {
          field: LOGIN_TOTP_NEXT_ENV,
          loginField: LOGIN_TOTP_ENV,
        })
      );
    }
    code = await askInput(
      t('commands.config.remote.masterPassword.change.stepUpPrompt'),
      TOTP_PATTERN
    );
  }
  // The server spends a TOTP step once per user; the sign-in already spent this one.
  if (loginTotp && code === loginTotp) {
    throw new ValidationError(
      t('commands.config.remote.masterPassword.change.stepUpSameCode', {
        field: LOGIN_TOTP_NEXT_ENV,
        loginField: LOGIN_TOTP_ENV,
      })
    );
  }
  return code;
}

interface ErrorBody {
  error?: string;
  code?: string;
}

/** Elevate the cookie session (skipped while the account is already elevated). */
async function elevateSession(
  serverUrl: string,
  cookie: string,
  loginTotp: string | undefined
): Promise<void> {
  const status = await sessionRequest<{ elevated?: boolean }>(
    serverUrl,
    'GET',
    '/auth/reauth/status',
    undefined,
    cookie
  );
  if (status.status < 400 && status.body.elevated === true) return;

  const code = await resolveStepUpCode(loginTotp);
  const reply = await sessionRequest<ErrorBody>(
    serverUrl,
    'POST',
    '/auth/reauth/totp',
    { code },
    cookie
  );
  if (reply.status >= 400) {
    throw new ValidationError(
      t('commands.config.remote.masterPassword.change.stepUpRefused', {
        status: reply.status,
        error: reply.body.error ?? `HTTP ${reply.status}`,
        field: LOGIN_TOTP_NEXT_ENV,
      })
    );
  }
}

/** The new password slot, built as the portal's buildPasswordSlot builds it. */
export async function buildPasswordSlot(
  cek: CryptoKey,
  password: string,
  serverSecret: Uint8Array
): Promise<{ kdfParams: SlotKdfParams; wrappedCek: string }> {
  const { derivePasswordSlotSecret, newPasswordSlotParams, wrapCekForSlot } = await import(
    '@rediacc/shared/config-crypto'
  );
  const kdfParams = newPasswordSlotParams();
  const slotSecret = await derivePasswordSlotSecret(password, kdfParams);
  return { kdfParams, wrappedCek: await wrapCekForSlot(cek, slotSecret, serverSecret) };
}

/**
 * True when `slot`, unwrapped with `password` and the server secret, yields this device's CEK.
 * Only the unwrap itself may answer false (a wrong key fails its AES-GCM authentication); a
 * derive or key-import error is a defect, not a mismatch, and propagates.
 */
export async function slotOpensCek(
  slot: { kdfParams: SlotKdfParams; wrappedCek: string },
  password: string,
  material: { cek: CryptoKey; serverSecret: Uint8Array }
): Promise<boolean> {
  const { cekUnwrap, derivePasswordSlotSecret, deriveWrappingKey } = await import(
    '@rediacc/shared/config-crypto'
  );
  const secret = await derivePasswordSlotSecret(password, slot.kdfParams);
  const wrappingKey = await deriveWrappingKey(secret, material.serverSecret);
  let unwrapped: CryptoKey;
  try {
    unwrapped = await cekUnwrap(slot.wrappedCek, wrappingKey);
  } catch {
    return false;
  }
  return sameKey(unwrapped, material.cek);
}

/** True when two AES keys hold the same raw bytes. */
async function sameKey(a: CryptoKey, b: CryptoKey): Promise<boolean> {
  const { exportAesKey } = await import('@rediacc/shared/config-crypto');
  const [ra, rb] = await Promise.all([exportAesKey(a), exportAesKey(b)]);
  return ra.length === rb.length && ra.every((byte, i) => byte === rb[i]);
}

/**
 * Prove the server's password slot opens with the NEW password, through the material
 * `enable --master-password` reads (masterPasswordCredentials), and that it yields this store's CEK.
 * Nothing is stored and no slot is written.
 */
export async function verifyNewMasterPassword(
  apiUrl: string,
  remote: { storeId: string; configId: string; teamId?: string },
  password: string,
  expected: { cek: CryptoKey; serverSecret: Uint8Array }
): Promise<void> {
  const fail = (error: string) =>
    new ValidationError(t('commands.config.remote.masterPassword.change.verifyFailed', { error }));
  const { masterPasswordCredentials } = await import('./config-remote-master-password.js');
  const { fromBase64, unwrapCekForSlot } = await import('@rediacc/shared/config-crypto');

  let credentials: Awaited<ReturnType<typeof masterPasswordCredentials>>;
  try {
    // The enroll route narrows a team-scoped token to configs of that team, so a config with no team is unreachable by configId from such a token (404). The store is what the verify compares, so the config is only named when it belongs to a team.
    credentials = await masterPasswordCredentials(
      apiUrl,
      remote.teamId ? remote.configId : undefined,
      password
    );
  } catch (error) {
    throw fail(error instanceof Error ? error.message : String(error));
  }
  if (credentials.storeId !== remote.storeId) {
    throw fail(t('commands.config.remote.masterPassword.change.verifyOtherStore'));
  }
  let unlocked: CryptoKey;
  try {
    unlocked = await unwrapCekForSlot(
      credentials.wrappedCek,
      fromBase64(credentials.passkey_secret),
      expected.serverSecret
    );
  } catch {
    throw fail(t('commands.config.remote.masterPassword.change.verifyNoUnlock'));
  }
  if (!(await sameKey(unlocked, expected.cek))) {
    throw fail(t('commands.config.remote.masterPassword.change.verifyOtherKey'));
  }
}

/** Run the change for `configName`; the new password is resolved by the caller (stdin is read first). */
export async function changeMasterPassword(configName: string, newPassword: string): Promise<void> {
  const { configFileStorage } = await import('../adapters/config-file-storage.js');
  const config = await configFileStorage.load(configName);
  if (!hasRemoteConfig(config)) {
    throw new ValidationError(t('commands.config.remote.refresh.notEnabled'));
  }
  const remote = config.remote;
  const apiUrl = remote.apiUrl;
  const login = await resolveLoginInput();

  // 1. The CEK from this device's enrollment, proven current by a pull: a CEK rotated away would
  //    otherwise be wrapped into the new slot and break the password for every future enrollment.
  const { RemoteConfigAdapter } = await import('../adapters/remote-config-adapter.js');
  const { remoteTokenStorage } = await import('../adapters/remote-token-storage.js');
  const { getSecureStorage } = await import('../utils/secure-storage.js');
  const adapter = new RemoteConfigAdapter(
    remote,
    configName,
    remoteTokenStorage,
    getSecureStorage()
  );
  const material = await withSpinner(
    t('commands.config.remote.masterPassword.change.unlocking'),
    async () => {
      await adapter.pull();
      return adapter.unlockKeyMaterial();
    },
    t('commands.config.remote.masterPassword.change.unlocked')
  );

  // 2. Cookie session, elevated.
  const cookie = await withSpinner(
    t('commands.subscription.login.passwordSigningIn'),
    () => openSession(apiUrl, login),
    t('commands.subscription.login.passwordSignedIn')
  );
  await elevateSession(apiUrl, cookie, login.totp);

  // 3. The new slot replaces this member's password slot (putSlot upserts on store+user+method).
  const slot = await buildPasswordSlot(material.cek, newPassword, material.serverSecret);
  // The old slot is replaced by the PUT, so the new one must open this CEK before it is sent.
  if (!(await slotOpensCek(slot, newPassword, material))) {
    throw new ValidationError(t('commands.config.remote.masterPassword.change.verifyOtherKey'));
  }
  const put = await withSpinner(
    t('commands.config.remote.masterPassword.change.writing'),
    () =>
      sessionRequest<ErrorBody>(
        apiUrl,
        'PUT',
        '/configs/slots/password',
        { storeId: remote.storeId, kdfParams: slot.kdfParams, wrappedCek: slot.wrappedCek },
        cookie
      ),
    t('commands.config.remote.masterPassword.change.written')
  );
  if (put.status >= 400) {
    throw new ValidationError(
      t('commands.config.remote.masterPassword.change.slotRefused', {
        status: put.status,
        error: put.body.error ?? `HTTP ${put.status}`,
      })
    );
  }

  // 4. Read it back the way a headless enrollment does.
  await withSpinner(
    t('commands.config.remote.masterPassword.change.verifying'),
    () => verifyNewMasterPassword(apiUrl, remote, newPassword, material),
    t('commands.config.remote.masterPassword.change.verified')
  );

  outputService.success(
    t('commands.config.remote.masterPassword.change.success', { name: configName })
  );
}
