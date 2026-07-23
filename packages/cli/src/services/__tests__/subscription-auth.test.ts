import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { setConfigNameOverride } from '../config/config-name.js';
import {
  getSubscriptionScopeMismatch,
  getSubscriptionServerUrl,
  getSubscriptionTokenFile,
  getSubscriptionTokenState,
  loadEnvSubscriptionToken,
  normalizeServerUrl,
  saveStoredSubscriptionToken,
} from '../account/subscription-auth.js';

const DEFAULT_SERVER = 'https://eu.rediacc.com';

/**
 * These tests drive the REAL account-pointer reader against a temp config dir
 * pointed at by XDG_CONFIG_HOME (getConfigDir() re-reads it on every call), so
 * the precedence and token-file resolution are exercised end-to-end, not mocked.
 */
describe('subscription-auth', () => {
  const envBackup = { ...process.env };
  let configHome: string;
  let configDir: string;

  beforeEach(() => {
    configHome = mkdtempSync(join(tmpdir(), 'sub-auth-'));
    configDir = join(configHome, 'rediacc');
    mkdirSync(configDir, { recursive: true });
    process.env.XDG_CONFIG_HOME = configHome;
    setConfigNameOverride(null);
  });

  afterEach(() => {
    process.env = { ...envBackup };
    setConfigNameOverride(null);
    rmSync(configHome, { recursive: true, force: true });
  });

  function writeConfig(name: string, account: Record<string, unknown>): void {
    writeFileSync(
      join(configDir, `${name}.json`),
      JSON.stringify({
        schemaVersion: 3,
        id: '00000000-0000-4000-8000-000000000000',
        version: 1,
        encryption: { mode: 'plaintext' },
        account,
      })
    );
  }

  describe('getSubscriptionServerUrl() precedence', () => {
    // | flag | REDIACC_ACCOUNT_SERVER | config account.accountServer | expect |
    it('flag wins over env and config', () => {
      process.env.REDIACC_ACCOUNT_SERVER = 'https://env.example.com';
      writeConfig('rediacc', { accountServer: 'https://config.example.com' });
      expect(getSubscriptionServerUrl('https://flag.example.com')).toBe('https://flag.example.com');
    });

    it('env wins over config when no flag', () => {
      delete process.env.REDIACC_ACCOUNT_SERVER;
      process.env.REDIACC_ACCOUNT_SERVER = 'https://env.example.com';
      writeConfig('rediacc', { accountServer: 'https://config.example.com' });
      expect(getSubscriptionServerUrl()).toBe('https://env.example.com');
    });

    it('config wins when no flag and no env', () => {
      delete process.env.REDIACC_ACCOUNT_SERVER;
      writeConfig('rediacc', { accountServer: 'https://config.example.com' });
      expect(getSubscriptionServerUrl()).toBe('https://config.example.com');
    });

    it('falls back to the SUBSCRIPTION_DEFAULTS default with no signal', () => {
      delete process.env.REDIACC_ACCOUNT_SERVER;
      // no config file written
      expect(getSubscriptionServerUrl()).toBe(DEFAULT_SERVER);
    });

    it('normalizes trailing slashes on the resolved value', () => {
      delete process.env.REDIACC_ACCOUNT_SERVER;
      writeConfig('rediacc', { accountServer: 'https://config.example.com///' });
      expect(getSubscriptionServerUrl()).toBe('https://config.example.com');
    });
  });

  describe('getSubscriptionTokenFile()', () => {
    it('returns api-token-rediacc.json for the default config', () => {
      delete process.env.REDIACC_CONFIG;
      expect(getSubscriptionTokenFile()).toBe(join(configDir, 'api-token-rediacc.json'));
    });

    it('returns api-token-<name>.json under REDIACC_CONFIG', () => {
      process.env.REDIACC_CONFIG = 'staging';
      expect(getSubscriptionTokenFile()).toBe(join(configDir, 'api-token-staging.json'));
    });

    it('honours an explicit configName argument', () => {
      expect(getSubscriptionTokenFile('bench')).toBe(join(configDir, 'api-token-bench.json'));
    });
  });

  describe('token state', () => {
    it('is missing when neither env token nor file exists', () => {
      delete process.env.REDIACC_TOKEN;
      expect(getSubscriptionTokenState()).toEqual({ kind: 'missing' });
    });

    it('loads a ready token from REDIACC_TOKEN', () => {
      process.env.REDIACC_TOKEN = 'rdt_env';
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

    it('prefers REDIACC_TOKEN over the stored token file', () => {
      process.env.REDIACC_TOKEN = 'rdt_env';
      process.env.REDIACC_ACCOUNT_SERVER = 'http://localhost:4800/account/';
      writeFileSync(
        join(configDir, 'api-token-rediacc.json'),
        JSON.stringify({ token: 'rdt_file', serverUrl: 'http://localhost:4830/account' })
      );

      expect(getSubscriptionTokenState()).toEqual({
        kind: 'ready',
        serverUrl: 'http://localhost:4800/account',
        token: {
          token: 'rdt_env',
          serverUrl: 'http://localhost:4800/account',
        },
      });
    });

    it('persists a normalized token and loads it as ready', () => {
      delete process.env.REDIACC_TOKEN;
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
    });
  });

  it('normalizes trailing slashes consistently', () => {
    expect(normalizeServerUrl('http://localhost:4800///')).toBe('http://localhost:4800');
  });

  describe('getSubscriptionScopeMismatch()', () => {
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
});
