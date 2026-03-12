import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  getSubscriptionScopeMismatch,
  getSubscriptionServerUrl,
  getSubscriptionTokenFile,
  getSubscriptionTokenState,
  isDevelopmentSubscriptionMode,
  loadEnvSubscriptionToken,
  normalizeServerUrl,
  saveStoredSubscriptionToken,
} from '../subscription-auth.js';

describe('subscription-auth', () => {
  const envBackup = { ...process.env };

  afterEach(() => {
    process.env = { ...envBackup };
  });

  it('uses the global config dir by default', async () => {
    const { getConfigDir } = await import('@rediacc/shared/paths');
    delete process.env.REDIACC_SUBSCRIPTION_TOKEN_FILE;
    delete process.env.REDIACC_ENVIRONMENT;

    expect(getSubscriptionTokenFile()).toBe(join(getConfigDir(), 'api-token.json'));
    expect(isDevelopmentSubscriptionMode()).toBe(false);
  });

  it('uses the worktree-local token file in development mode', () => {
    process.env.REDIACC_ENVIRONMENT = 'development';
    process.env.REDIACC_SUBSCRIPTION_TOKEN_FILE = '/tmp/worktree-a/dev-token.json';

    expect(isDevelopmentSubscriptionMode()).toBe(true);
    expect(getSubscriptionTokenFile()).toBe('/tmp/worktree-a/dev-token.json');
  });

  it('uses REDIACC_ACCOUNT_SERVER as the authoritative dev server', () => {
    process.env.REDIACC_ENVIRONMENT = 'development';
    process.env.REDIACC_SUBSCRIPTION_TOKEN_FILE = '/tmp/worktree-a/dev-token.json';
    process.env.REDIACC_ACCOUNT_SERVER = 'http://localhost:4800/';

    expect(getSubscriptionServerUrl('http://localhost:9999')).toBe('http://localhost:4800');
  });

  it('reports a server mismatch for stale dev tokens', () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'subscription-auth-'));
    const tokenFile = join(tempDir, 'api-token.json');

    process.env.REDIACC_ENVIRONMENT = 'development';
    process.env.REDIACC_SUBSCRIPTION_TOKEN_FILE = tokenFile;
    process.env.REDIACC_ACCOUNT_SERVER = 'http://localhost:4800';

    writeFileSync(
      tokenFile,
      JSON.stringify({
        token: 'rdt_stale',
        serverUrl: 'http://localhost:4830/',
      })
    );

    expect(getSubscriptionTokenState()).toEqual({
      kind: 'server_mismatch',
      expectedServerUrl: 'http://localhost:4800',
      actualServerUrl: 'http://localhost:4830',
    });

    rmSync(tempDir, { recursive: true, force: true });
  });

  it('loads a ready token from REDIACC_SUBSCRIPTION_TOKEN', () => {
    process.env.REDIACC_SUBSCRIPTION_TOKEN = 'rdt_env';
    process.env.REDIACC_ACCOUNT_SERVER = 'http://localhost:4800/account/';

    expect(loadEnvSubscriptionToken()).toEqual({
      token: 'rdt_env',
      serverUrl: 'http://localhost:4800/account',
    });

    expect(getSubscriptionTokenState()).toEqual({
      kind: 'ready',
      serverUrl: 'http://localhost:4800/account',
      token: {
        token: 'rdt_env',
        serverUrl: 'http://localhost:4800/account',
      },
    });
  });

  it('prefers REDIACC_SUBSCRIPTION_TOKEN over the stored token file', () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'subscription-auth-'));
    const tokenFile = join(tempDir, 'api-token.json');

    process.env.REDIACC_SUBSCRIPTION_TOKEN = 'rdt_env';
    process.env.REDIACC_ACCOUNT_SERVER = 'http://localhost:4800/account/';
    process.env.REDIACC_SUBSCRIPTION_TOKEN_FILE = tokenFile;

    writeFileSync(
      tokenFile,
      JSON.stringify({
        token: 'rdt_file',
        serverUrl: 'http://localhost:4830/account',
      })
    );

    expect(getSubscriptionTokenState()).toEqual({
      kind: 'ready',
      serverUrl: 'http://localhost:4800/account',
      token: {
        token: 'rdt_env',
        serverUrl: 'http://localhost:4800/account',
      },
    });

    rmSync(tempDir, { recursive: true, force: true });
  });

  it('persists normalized dev tokens and loads them as ready', () => {
    const tempDir = mkdtempSync(join(tmpdir(), 'subscription-auth-'));
    const tokenFile = join(tempDir, 'nested', 'api-token.json');

    process.env.REDIACC_ENVIRONMENT = 'development';
    process.env.REDIACC_SUBSCRIPTION_TOKEN_FILE = tokenFile;
    process.env.REDIACC_ACCOUNT_SERVER = 'http://localhost:4800/';

    mkdirSync(join(tempDir, 'nested'), { recursive: true });
    saveStoredSubscriptionToken({
      token: 'rdt_valid',
      serverUrl: 'http://localhost:4800/',
      subscriptionId: 'sub_123',
      orgId: 'org_123',
      orgName: 'Acme',
      teamId: 'team_123',
      teamName: 'Platform',
    });

    expect(getSubscriptionTokenState()).toEqual({
      kind: 'ready',
      serverUrl: 'http://localhost:4800',
      token: {
        token: 'rdt_valid',
        serverUrl: 'http://localhost:4800',
        subscriptionId: 'sub_123',
        orgId: 'org_123',
        orgName: 'Acme',
        teamId: 'team_123',
        teamName: 'Platform',
      },
    });

    rmSync(tempDir, { recursive: true, force: true });
  });

  it('normalizes trailing slashes consistently', () => {
    expect(normalizeServerUrl('http://localhost:4800///')).toBe('http://localhost:4800');
  });

  it('reports a hard mismatch when the config team differs from the token team', () => {
    expect(
      getSubscriptionScopeMismatch(
        {
          token: 'rdt_valid',
          serverUrl: 'http://localhost:4800',
          teamId: 'team_123',
          teamName: 'Platform',
        },
        'Infra'
      )
    ).toContain('Platform');
  });

  it('requires re-login when config team exists but token team metadata is missing', () => {
    expect(
      getSubscriptionScopeMismatch(
        {
          token: 'rdt_valid',
          serverUrl: 'http://localhost:4800',
        },
        'Platform'
      )
    ).toContain('Run "rdc subscription login" again');
  });
});
