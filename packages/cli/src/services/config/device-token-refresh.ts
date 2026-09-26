/**
 * Renew a device's config token with its login token (PLAN-config-sync-hardening T11, operator
 * ruling D4: auto-refresh through the login API token, 7-day config tokens).
 *
 * A config token chain dies when it idles past its lifetime, when its three uses are spent, or
 * when the device changes network (the chain binds to the address of its first use). The account
 * server mints a fresh, unbound one at `POST /configs/device-token/refresh` for the login token's
 * own user, provided that user is a member of the store with a key slot at the current CEK
 * generation. The response carries no key material: opening the config still takes this device's
 * slot secret.
 *
 * The call goes through `accountServerFetch`, so a login token bound to another address is moved
 * here by the TOTP rebind prompt of PLAN-token-ip-rebind (an interactive terminal only) and the
 * refresh is then sent once more. `remote-config-adapter.ts` is the only caller: it refreshes once
 * per operation, under the token lease, and retries the refused request once.
 */

import { TOKEN_IP_MISMATCH } from '@rediacc/shared/subscription/types';
import { t } from '../../i18n/index.js';
import type { RemoteConfig } from '../../types/index.js';
import { type AccountFetchError, accountServerFetch } from '../account/account-client.js';
import { getSubscriptionTokenState, normalizeServerUrl } from '../account/subscription-auth.js';

export const DEVICE_TOKEN_REFRESH_PATH = '/account/api/v1/configs/device-token/refresh';

/**
 * The config-token 401 codes a new token cures. `decryption_failed` is not one: the token was
 * found and valid, and its chain's key would not open what it guards, which a new token from the
 * same enrollment does not explain away.
 */
export const REFRESHABLE_AUTH_REASONS: ReadonlySet<string> = new Set([
  'token_expired',
  'token_exhausted',
  'ip_mismatch',
  'invalid_token',
]);

/** The login token stored for `apiUrl` (`rdc subscription login`, or REDIACC_TOKEN), if any. */
export function loginTokenFor(apiUrl: string): string | undefined {
  const state = getSubscriptionTokenState();
  if (state.kind !== 'ready') return undefined;
  if (normalizeServerUrl(state.serverUrl) !== normalizeServerUrl(apiUrl)) return undefined;
  return state.token.token;
}

/** The server refused the renewal, or its answer was unusable. `code` names why. */
export class RemoteTokenRefreshError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    options?: { cause?: unknown }
  ) {
    super(message, options);
    this.name = 'RemoteTokenRefreshError';
  }
}

/** Transport seams, threaded from the adapter's own (the round-trip harness); production passes none. */
export interface RefreshTransport {
  fetchImpl?: typeof fetch;
  serverKey?: { key: CryptoKey; keyId: string };
}

/**
 * Ask the account server for a fresh config token for `remote`'s store (and team), with the login
 * token. Returns the new token. A refusal is thrown as RemoteTokenRefreshError with the remedy in
 * its message, except the team refusals (403 `team_forbidden`, 404 `team_not_found`) and
 * network-class failures, which are rethrown as they came so the adapter maps them the way it maps
 * every config route's.
 */
export async function refreshDeviceToken(
  remote: RemoteConfig,
  loginToken: string,
  transport: RefreshTransport = {}
): Promise<string> {
  let response: { deviceToken?: unknown };
  try {
    response = await accountServerFetch<{ deviceToken?: unknown }>(DEVICE_TOKEN_REFRESH_PATH, {
      method: 'POST',
      body: { storeId: remote.storeId, teamId: remote.teamId ?? null },
      token: loginToken,
      serverUrl: remote.apiUrl,
      ...transport,
    });
  } catch (error) {
    throw refusalFor(error, remote);
  }
  if (typeof response.deviceToken !== 'string' || response.deviceToken.length === 0) {
    throw new RemoteTokenRefreshError(
      'malformed_response',
      t('commands.config.remote.tokenRefresh.refused', {
        error: 'the response carried no config token',
      })
    );
  }
  return response.deviceToken;
}

/** The error to raise for a failed refresh call; see refreshDeviceToken. */
function refusalFor(error: unknown, remote: RemoteConfig): unknown {
  const e = error as Partial<AccountFetchError> | null;
  if (typeof e?.status !== 'number') return error;
  const serverMessage = e.message ?? `HTTP ${e.status}`;
  const refused = (code: string, message: string) =>
    new RemoteTokenRefreshError(code, message, { cause: error });

  if (e.status === 401) {
    return refused('login_invalid', t('commands.config.remote.tokenRefresh.loginInvalid'));
  }
  if (e.status === 429) {
    return refused(
      'rate_limited',
      t('commands.config.remote.tokenRefresh.rateLimited', { error: serverMessage })
    );
  }
  if (e.status === 404 && e.code === 'team_not_found') return error;
  if (e.status !== 403) {
    return refused(
      'refresh_failed',
      t('commands.config.remote.tokenRefresh.refused', { error: serverMessage })
    );
  }
  switch (e.code) {
    case TOKEN_IP_MISMATCH:
      // The rebind already ran (or could not, off a terminal) and its message names how to move the login; the other remedy is a new enrollment.
      return refused(
        'login_ip_mismatch',
        t('commands.config.remote.tokenRefresh.loginIpMismatch', { error: serverMessage })
      );
    case 'team_forbidden':
      return error;
    case 'not_store_member':
      return refused(
        'not_store_member',
        t('commands.config.remote.tokenRefresh.notStoreMember', { storeId: remote.storeId })
      );
    case 'store_mismatch':
      return refused(
        'store_mismatch',
        t('commands.config.remote.tokenRefresh.storeMismatch', { storeId: remote.storeId })
      );
    case 'stale_cek_generation':
      return refused(
        'stale_cek_generation',
        t('commands.config.remote.tokenRefresh.staleGeneration')
      );
    case undefined:
      // A bare 403 from the api-token middleware: the login lacks `config:enroll` (a login made before the refresh route existed), or its team is gone.
      return refused('login_scope', t('commands.config.remote.tokenRefresh.loginScope'));
    default:
      return refused(
        e.code,
        t('commands.config.remote.tokenRefresh.refused', { error: serverMessage })
      );
  }
}
