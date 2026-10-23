/**
 * `rdc subscription proxy-token`: trade this device's login token for a short-lived proxy:exec token.
 *
 * The login grant carries no proxy:exec (operator ruling 2026-10-23, the login stays least-privilege),
 * so `rdc --proxy` takes a token minted by POST /proxy/cli-token:
 * `REDIACC_TOKEN=$(rdc subscription proxy-token) rdc --proxy <url> ...`. Stdout carries the minted
 * token and nothing else, so the command substitution captures exactly the token; `--json` adds its
 * expiry. The token never reaches argv: the login token travels in the encrypted tunnel's header.
 */

import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import {
  getSubscriptionScopeMismatch,
  getSubscriptionTokenState,
} from '../services/account/subscription-auth.js';
import { configService } from '../services/config/config-resources.js';
import { writeStdout } from '../services/core/request-context.js';
import { ValidationError } from '../utils/errors.js';

/** The account route that mints a proxy token from a CLI login token. */
export const PROXY_CLI_TOKEN_PATH = '/account/api/v1/proxy/cli-token';

interface ProxyTokenResponse {
  token: string;
  expiresAt: string;
  scopes: string[];
}

export async function executeProxyToken(options: { json?: boolean }): Promise<void> {
  const state = getSubscriptionTokenState();
  if (state.kind !== 'ready') {
    throw new ValidationError(t('errors.subscription.notLoggedIn'));
  }
  // The minted token takes the login token's team, so a login for another team would proxy
  // commands under the wrong team.
  const mismatch = getSubscriptionScopeMismatch(state.token, await configService.getTeam());
  if (mismatch) {
    throw new ValidationError(mismatch);
  }

  const minted = await accountServerFetch<ProxyTokenResponse>(PROXY_CLI_TOKEN_PATH, {
    method: 'POST',
    body: {},
    token: state.token.token,
    serverUrl: state.serverUrl,
  });
  if (typeof minted.token !== 'string' || minted.token.length === 0) {
    throw new Error(t('commands.subscription.proxyToken.noToken'));
  }

  writeStdout(
    options.json
      ? `${JSON.stringify({ token: minted.token, expiresAt: minted.expiresAt })}\n`
      : `${minted.token}\n`
  );
}
