import type { MachineSecretKdfParams } from '@rediacc/shared/config-crypto';
import { toBase64 } from '@rediacc/shared/config-crypto';
import { TOKEN_IP_MISMATCH } from '@rediacc/shared/subscription/types';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { outputService } from '../services/core/output.js';
import { ValidationError } from '../utils/errors.js';
import { askPassword } from '../utils/prompt.js';
import { applyHandoff } from './config-remote-enable.js';
import type { DeviceCredentials } from './config-remote-handoff.js';

// ─── Headless enrollment by a machine secret (D46) ──────────────────────────

/** The environment variable a headless box passes its machine secret in; never argv. */
export const MACHINE_SECRET_ENV = 'REDIACC_MACHINE_SECRET';

/** Shape of POST /configs/machine-enroll (config:enroll api-token auth). */
interface MachineEnrollResponse {
  machineSecretId: string;
  kdfParams: MachineSecretKdfParams;
  wrappedCek: string;
  cekGeneration: number;
  token: string;
  storeId: string;
  /** null when the secret's scope holds no config yet: the CLI then mints an id and seeds it. */
  configId: string | null;
  /** The selected config's teamId; null for the org-level config. */
  teamId: string | null;
}

/**
 * Turn a 403 from `POST /configs/machine-enroll` into an actionable message. The IP-binding refusal
 * carries `code: TOKEN_IP_MISMATCH` and arrives already localized from `accountServerFetch`; a team
 * refusal carries `code: team_forbidden`; the rest are bare messages (routes/configs.ts), matched by
 * text. Anything unrecognised repeats the server's own words.
 */
function describeForbidden(error: unknown): string {
  const { code, message } = error as { code?: string; message?: string };
  const serverMessage = message ?? '';
  if (code === TOKEN_IP_MISMATCH) return serverMessage;
  if (serverMessage.includes('was revoked')) {
    return t('commands.config.remote.enable.machineSecretRevoked');
  }
  if (code === 'team_forbidden') {
    return t('commands.config.remote.enable.machineSecretTeamForbidden', { error: serverMessage });
  }
  if (serverMessage.includes('Missing required scope')) {
    return t('commands.config.remote.enable.machineSecretMissingScope');
  }
  if (serverMessage.includes('no associated user') || serverMessage.includes('no organization')) {
    return t('commands.config.remote.enable.machineSecretTokenNotEnrollable');
  }
  return t('commands.config.remote.enable.machineSecretForbidden', { error: serverMessage });
}

/**
 * Resolve the machine secret: REDIACC_MACHINE_SECRET, else stdin when it is piped, else a hidden
 * prompt on a TTY. Never argv, so the secret stays out of the process list and shell history.
 * The value is validated (and normalized to its canonical `RM1-` form) before any server call.
 */
async function resolveMachineSecret(): Promise<string> {
  let raw = process.env[MACHINE_SECRET_ENV];
  if (!raw) {
    if (process.stdin.isTTY === true) {
      raw = await askPassword(t('commands.config.remote.enable.machineSecretPrompt'));
    } else {
      const { readStdinValue } = await import('../utils/stdin.js');
      raw = await readStdinValue();
    }
  }
  if (!raw?.trim()) {
    throw new ValidationError(
      t('commands.config.remote.enable.machineSecretEmpty', { env: MACHINE_SECRET_ENV })
    );
  }
  const { parseMachineSecret } = await import('@rediacc/shared/config-crypto');
  try {
    return parseMachineSecret(raw.trim());
  } catch (error) {
    throw new ValidationError(
      t('commands.config.remote.enable.machineSecretInvalid', {
        error: error instanceof Error ? error.message : String(error),
      })
    );
  }
}

/**
 * The device credentials of a machine secret, with no browser.
 *
 * A member minted the secret in the portal, where the browser session holds the CEK; the box got
 * its id on the command line and the secret out of band. Its own api token (scope config:enroll,
 * the same member's) fetches the secret's public kdfParams, the opaque wrappedCek, a config token
 * chained to the secret and the pointer coordinates; the secret derives the wrapping secret
 * locally. Nothing is stored here: a first enable (`enableMachineSecret`) and a re-enrollment
 * (config-remote-reenroll.ts) both store the result and prove it with a pull.
 */
export async function machineSecretCredentials(
  apiUrl: string,
  machineSecretId: string
): Promise<DeviceCredentials> {
  // Read and validate the secret first: a missing or malformed one leaves no server call behind.
  const machineSecret = await resolveMachineSecret();

  let enroll: MachineEnrollResponse;
  try {
    enroll = await accountServerFetch<MachineEnrollResponse>(
      '/account/api/v1/configs/machine-enroll',
      {
        method: 'POST',
        serverUrl: apiUrl,
        token: process.env.REDIACC_TOKEN,
        body: { machineSecretId },
      }
    );
  } catch (error) {
    const status = (error as { status?: number }).status;
    if (status === 403) throw new ValidationError(describeForbidden(error));
    if (status === 404) {
      throw new ValidationError(
        t('commands.config.remote.enable.machineSecretNotFound', {
          id: machineSecretId,
          error: (error as { message?: string }).message ?? '',
        })
      );
    }
    throw error;
  }

  const { deriveMachineSecretSlotSecret } = await import('@rediacc/shared/config-crypto');
  const slotSecret = await deriveMachineSecretSlotSecret(machineSecret, enroll.kdfParams);

  // The same shape the browser handoff carries: the derived secret under a fresh local key id, the token, the wrapped CEK and the pointer coordinates.
  return {
    passkey_secret: toBase64(slotSecret),
    token: enroll.token,
    storageKeyId: `rdc:ms:${crypto.randomUUID()}`,
    wrappedCek: enroll.wrappedCek,
    storeId: enroll.storeId,
    apiUrl,
    // null (empty scope) collapses to undefined so finalizeEnable mints a configId from the local config's id and seeds the store.
    ...(enroll.configId ? { configId: enroll.configId } : {}),
    // null (org-level config) collapses to undefined; RemoteConfig.teamId is an optional uuid.
    ...(enroll.teamId ? { teamId: enroll.teamId } : {}),
  };
}

/** A wrong machine secret surfaces as a CEK unwrap failure (RemoteStaleSlotError from the adapter): name it. */
export async function machineSecretFailure(error: unknown): Promise<unknown> {
  const { RemoteStaleSlotError } = await import('../adapters/remote-config-adapter.js');
  return error instanceof RemoteStaleSlotError
    ? new ValidationError(
        t('commands.config.remote.enable.machineSecretWrong', { env: MACHINE_SECRET_ENV })
      )
    : error;
}

/**
 * Enroll this box with a machine secret: store the credentials exactly like the browser handoff
 * and let the probe pull fail fast (`applyHandoff` removes what it stored on any failure, so a
 * retry starts from a clean slate).
 */
export async function enableMachineSecret(
  apiUrl: string,
  configName: string,
  machineSecretId: string,
  opts: { force?: boolean } = {}
): Promise<void> {
  const credentials = await machineSecretCredentials(apiUrl, machineSecretId);
  try {
    await applyHandoff(credentials, configName, opts);
  } catch (error) {
    throw await machineSecretFailure(error);
  }
  outputService.success(t('commands.config.remote.enable.success', { name: configName, apiUrl }));
}
