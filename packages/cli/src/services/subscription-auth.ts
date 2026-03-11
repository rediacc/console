import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { SUBSCRIPTION_DEFAULTS } from '@rediacc/shared/config';
import { getConfigDir } from '@rediacc/shared/paths';

const TOKEN_FILE_ENV = 'REDIACC_SUBSCRIPTION_TOKEN_FILE';
const DEV_ENV = 'development';

export interface StoredSubscriptionToken {
  token: string;
  serverUrl: string;
  subscriptionId?: string;
}

export function normalizeServerUrl(serverUrl: string): string {
  return serverUrl.replace(/\/+$/, '');
}

export function isDevelopmentSubscriptionMode(): boolean {
  return process.env.REDIACC_ENVIRONMENT === DEV_ENV && !!process.env[TOKEN_FILE_ENV];
}

export function getSubscriptionTokenFile(): string {
  return process.env[TOKEN_FILE_ENV] ?? join(getConfigDir(), 'api-token.json');
}

export function getSubscriptionServerUrl(preferredServerUrl?: string): string {
  if (isDevelopmentSubscriptionMode()) {
    const serverUrl = process.env.REDIACC_ACCOUNT_SERVER;
    if (!serverUrl) {
      throw new Error('Development mode requires REDIACC_ACCOUNT_SERVER to be set');
    }
    return normalizeServerUrl(serverUrl);
  }

  return normalizeServerUrl(
    preferredServerUrl ??
      process.env.REDIACC_ACCOUNT_SERVER ??
      SUBSCRIPTION_DEFAULTS.ACCOUNT_SERVER_URL
  );
}

export function loadStoredSubscriptionToken(): StoredSubscriptionToken | null {
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

export type SubscriptionTokenState =
  | { kind: 'missing' }
  | { kind: 'server_mismatch'; expectedServerUrl: string; actualServerUrl: string }
  | { kind: 'ready'; token: StoredSubscriptionToken; serverUrl: string };

export function getSubscriptionTokenState(): SubscriptionTokenState {
  const token = loadStoredSubscriptionToken();
  if (!token) return { kind: 'missing' };

  if (isDevelopmentSubscriptionMode()) {
    const expectedServerUrl = getSubscriptionServerUrl();
    if (token.serverUrl !== expectedServerUrl) {
      return {
        kind: 'server_mismatch',
        expectedServerUrl,
        actualServerUrl: token.serverUrl,
      };
    }

    return {
      kind: 'ready',
      token,
      serverUrl: expectedServerUrl,
    };
  }

  return {
    kind: 'ready',
    token,
    serverUrl: token.serverUrl,
  };
}
