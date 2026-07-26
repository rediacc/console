import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { SUBSCRIPTION_DEFAULTS } from '@rediacc/shared/config';
import { getConfigDir } from '@rediacc/shared/paths';
import { getEffectiveConfigName } from '../config/config-name.js';
import { readAccountPointer } from './account-pointer.js';

const SUBSCRIPTION_TOKEN_ENV = 'REDIACC_TOKEN';

export interface StoredSubscriptionToken {
  token: string;
  serverUrl: string;
  subscriptionId?: string;
  orgId?: string;
  orgName?: string;
  teamId?: string;
  teamName?: string;
}

export function normalizeServerUrl(serverUrl: string): string {
  return serverUrl.replace(/\/+$/, '');
}

/**
 * Get the subscription token file path for a config.
 * Always per-config: `api-token-{name}.json` (default config included, so
 * `api-token-rediacc.json`). Defaults to the effective config name.
 */
export function getSubscriptionTokenFile(configName = getEffectiveConfigName()): string {
  return join(getConfigDir(), `api-token-${configName}.json`);
}

export function getSubscriptionServerUrl(preferredServerUrl?: string): string {
  // Precedence (highest first):
  //   1. preferredServerUrl        — runtime override (--server flag)
  //   2. REDIACC_ACCOUNT_SERVER    — env override
  //   3. config account.accountServer — the active config's server pointer
  //   4. SUBSCRIPTION_DEFAULTS.ACCOUNT_SERVER_URL — hardcoded default
  return normalizeServerUrl(
    preferredServerUrl ??
      process.env.REDIACC_ACCOUNT_SERVER ??
      readAccountPointer().accountServer ??
      SUBSCRIPTION_DEFAULTS.ACCOUNT_SERVER_URL
  );
}

function loadStoredSubscriptionToken(): StoredSubscriptionToken | null {
  const tokenFile = getSubscriptionTokenFile();
  if (!existsSync(tokenFile)) return null;

  try {
    const parsed = JSON.parse(readFileSync(tokenFile, 'utf-8')) as StoredSubscriptionToken;
    return {
      ...parsed,
      serverUrl: normalizeServerUrl(parsed.serverUrl),
    };
  } catch {
    return null;
  }
}

export function loadEnvSubscriptionToken(): StoredSubscriptionToken | null {
  const token = process.env[SUBSCRIPTION_TOKEN_ENV]?.trim();
  if (!token) return null;

  return {
    token,
    serverUrl: getSubscriptionServerUrl(),
  };
}

export function saveStoredSubscriptionToken(token: StoredSubscriptionToken): void {
  const tokenFile = getSubscriptionTokenFile();
  mkdirSync(dirname(tokenFile), { recursive: true, mode: 0o700 });
  writeFileSync(
    tokenFile,
    JSON.stringify(
      {
        ...token,
        serverUrl: normalizeServerUrl(token.serverUrl),
      },
      null,
      2
    ),
    { mode: 0o600 }
  );
}

export function deleteStoredSubscriptionToken(): void {
  const tokenFile = getSubscriptionTokenFile();
  try {
    unlinkSync(tokenFile);
  } catch {
    // File doesn't exist or can't be deleted — that's OK
  }
}

export function getSubscriptionScopeMismatch(
  token: Pick<StoredSubscriptionToken, 'teamName'>,
  configTeamName?: string
): string | null {
  const normalizedConfigTeam = configTeamName?.trim();
  const normalizedTokenTeam = token.teamName?.trim();

  if (!normalizedConfigTeam) {
    return null;
  }

  if (!normalizedTokenTeam) {
    return `Stored subscription token is missing team metadata for config team "${normalizedConfigTeam}". Run "rdc subscription login" again.`;
  }

  if (normalizedConfigTeam !== normalizedTokenTeam) {
    return `Stored subscription token is bound to team "${normalizedTokenTeam}", but the current config team is "${normalizedConfigTeam}". Run "rdc subscription login" again after selecting the correct team.`;
  }

  return null;
}

export type SubscriptionTokenState =
  | { kind: 'missing' }
  | { kind: 'ready'; token: StoredSubscriptionToken; serverUrl: string };

export function getSubscriptionTokenState(): SubscriptionTokenState {
  const token = loadEnvSubscriptionToken() ?? loadStoredSubscriptionToken();
  if (!token) return { kind: 'missing' };

  return {
    kind: 'ready',
    token,
    serverUrl: token.serverUrl,
  };
}
