import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  getSubscriptionServerUrl,
  getSubscriptionTokenFile,
  getSubscriptionTokenState,
  isDevelopmentSubscriptionMode,
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
    });

    expect(getSubscriptionTokenState()).toEqual({
      kind: 'ready',
      serverUrl: 'http://localhost:4800',
      token: {
        token: 'rdt_valid',
        serverUrl: 'http://localhost:4800',
        subscriptionId: 'sub_123',
      },
    });

    rmSync(tempDir, { recursive: true, force: true });
  });

  it('normalizes trailing slashes consistently', () => {
    expect(normalizeServerUrl('http://localhost:4800///')).toBe('http://localhost:4800');
  });
});
