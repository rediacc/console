import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { SUBSCRIPTION_DEFAULTS } from '@rediacc/shared/config';
import { getConfigDir } from '@rediacc/shared/paths';

const TOKEN_FILE_ENV = 'REDIACC_SUBSCRIPTION_TOKEN_FILE';
const SUBSCRIPTION_TOKEN_ENV = 'REDIACC_SUBSCRIPTION_TOKEN';
const DEV_ENV = 'development';
const SERVER_CONFIG_FILE = 'server.json';

export interface ServerConfig {
  accountServer: string;
  e2ePublicKey?: string;
}

export function getServerConfigFile(): string {
  return join(getConfigDir(), SERVER_CONFIG_FILE);
}

export function loadServerConfig(): ServerConfig | null {
  const configFile = getServerConfigFile();
  if (!existsSync(configFile)) return null;

  try {
    return JSON.parse(readFileSync(configFile, 'utf-8')) as ServerConfig;
  } catch {
    return null;
  }
}

export function saveServerConfig(config: ServerConfig): void {
  const configFile = getServerConfigFile();
  mkdirSync(dirname(configFile), { recursive: true, mode: 0o700 });
  writeFileSync(configFile, `${JSON.stringify(config, null, 2)}\n`, { mode: 0o600 });
}

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
      loadServerConfig()?.accountServer ??
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
  | { kind: 'server_mismatch'; expectedServerUrl: string; actualServerUrl: string }
  | { kind: 'ready'; token: StoredSubscriptionToken; serverUrl: string };

export function getSubscriptionTokenState(): SubscriptionTokenState {
  const token = loadEnvSubscriptionToken() ?? loadStoredSubscriptionToken();
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
