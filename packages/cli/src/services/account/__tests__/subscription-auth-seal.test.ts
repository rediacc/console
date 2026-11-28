/**
 * The api-token file of a keyring-sealed config (PLAN-config-sealed-local.md D9): `serverUrl` in
 * plaintext and readable with no keyring call, the token sealed under the config's seal key and
 * unsealed synchronously, a local-only config's file left in plaintext, and a lost key read as no
 * token. Secure storage is an in-memory stand-in that counts its reads; every token is a throwaway.
 */
import { randomBytes } from 'node:crypto';
import { copyFileSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const stand = vi.hoisted(() => ({
  values: new Map<string, string>(),
  reads: 0,
  configDir: '',
}));

vi.mock('@rediacc/shared/paths', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@rediacc/shared/paths')>();
  return { ...actual, getConfigDir: () => stand.configDir };
});

vi.mock('../../../utils/secure-storage.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../utils/secure-storage.js')>();
  const storage = {
    type: 'mem',
    get: (key: string) => {
      stand.reads += 1;
      return Promise.resolve(stand.values.get(key) ?? null);
    },
    getSync: (key: string) => {
      stand.reads += 1;
      return stand.values.get(key) ?? null;
    },
    set: (key: string, value: string) => {
      stand.values.set(key, value);
      return Promise.resolve();
    },
    delete: (key: string) => {
      stand.values.delete(key);
      return Promise.resolve();
    },
  };
  return { ...actual, getSecureStorage: () => storage };
});

const auth = await import('../subscription-auth.js');
const { clearSealKeyCache, SealKeyLostError } = await import(
  '../../../adapters/config-seal-key.js'
);

const KEYRING_ID = 'rdc:seal:0b6f7a52-3c1d-4e8f-9a0b-1c2d3e4f5a6b';
const CONFIG_ID = '11111111-2222-4333-8444-555555555555';
const TOKEN = 'throwaway-api-token-9f3c';
const SERVER = 'https://account.example.invalid';

function writeConfig(name: string, encryption: Record<string, unknown>): void {
  writeFileSync(
    join(stand.configDir, `${name}.json`),
    JSON.stringify({ id: CONFIG_ID, version: 1, encryption })
  );
}

const tokenFile = (name = 'eu') => join(stand.configDir, `api-token-${name}.json`);

beforeAll(() => {
  stand.configDir = mkdtempSync(join(tmpdir(), 'rdc-api-token-seal-'));
});
afterAll(() => {
  rmSync(stand.configDir, { recursive: true, force: true });
  vi.unstubAllEnvs();
});
beforeEach(() => {
  rmSync(stand.configDir, { recursive: true, force: true });
  stand.configDir = mkdtempSync(join(tmpdir(), 'rdc-api-token-seal-'));
  vi.stubEnv('REDIACC_CONFIG', 'eu');
  vi.stubEnv('REDIACC_TOKEN', '');
  vi.stubEnv('REDIACC_ACCOUNT_SERVER', '');
  stand.values.clear();
  stand.values.set(KEYRING_ID, randomBytes(32).toString('base64'));
  stand.reads = 0;
  clearSealKeyCache();
});

function saveSealed(): void {
  writeConfig('eu', { mode: 'keyring', keyringId: KEYRING_ID });
  auth.saveStoredSubscriptionToken({ token: TOKEN, serverUrl: `${SERVER}/`, teamName: 'ops' });
  clearSealKeyCache();
  stand.reads = 0;
}

describe('a keyring-sealed config', () => {
  it('stores serverUrl in plaintext and the token sealed, with the keyringId beside it', () => {
    saveSealed();
    const text = readFileSync(tokenFile(), 'utf8');
    expect(text).not.toContain(TOKEN);
    const file = JSON.parse(text);
    expect(file.serverUrl).toBe(SERVER);
    expect(file.keyringId).toBe(KEYRING_ID);
    expect(file.sealed.v).toBe(1);
    expect(file.token).toBeUndefined();
  });

  it('unseals the token synchronously, with one keyring read', () => {
    saveSealed();
    const state = auth.getSubscriptionTokenState();
    expect(state).toEqual({
      kind: 'ready',
      token: { token: TOKEN, serverUrl: SERVER, teamName: 'ops' },
      serverUrl: SERVER,
    });
    auth.getSubscriptionTokenState();
    expect(stand.reads).toBe(1);
  });

  it('answers the serverUrl readers with no keyring call', () => {
    saveSealed();
    expect(auth.getConfiguredServerUrl()).toBe(SERVER);
    expect(auth.getNamedTokenServerUrl()).toBe(SERVER);
    expect(stand.reads).toBe(0);
  });

  it('reads a lost seal key as no token', () => {
    saveSealed();
    stand.values.delete(KEYRING_ID);
    expect(auth.getSubscriptionTokenState()).toEqual({ kind: 'missing' });
    expect(auth.getConfiguredServerUrl()).toBe(SERVER);
  });

  it('refuses to save under a lost seal key rather than write the token in plaintext', () => {
    writeConfig('eu', { mode: 'keyring', keyringId: KEYRING_ID });
    stand.values.delete(KEYRING_ID);
    expect(() => auth.saveStoredSubscriptionToken({ token: TOKEN, serverUrl: SERVER })).toThrow(
      SealKeyLostError
    );
  });

  it('a sealed file copied to another config does not open there', () => {
    saveSealed();
    writeConfig('us', { mode: 'keyring', keyringId: KEYRING_ID });
    copyFileSync(tokenFile('eu'), tokenFile('us'));
    vi.stubEnv('REDIACC_CONFIG', 'us');
    expect(auth.getSubscriptionTokenState()).toEqual({ kind: 'missing' });
  });
});

describe('a config that is not keyring-sealed', () => {
  it('a local-only config keeps its api token in plaintext, with no keyring call', () => {
    writeConfig('eu', { mode: 'plaintext' });
    auth.saveStoredSubscriptionToken({ token: TOKEN, serverUrl: SERVER });
    const file = JSON.parse(readFileSync(tokenFile(), 'utf8'));
    expect(file.token).toBe(TOKEN);
    expect(file.sealed).toBeUndefined();
    expect(auth.getSubscriptionTokenState()).toMatchObject({ kind: 'ready' });
    expect(stand.reads).toBe(0);
  });

  it('a master-password-only config keeps it in plaintext too', () => {
    writeConfig('eu', { mode: 'master-password' });
    auth.saveStoredSubscriptionToken({ token: TOKEN, serverUrl: SERVER });
    expect(JSON.parse(readFileSync(tokenFile(), 'utf8')).token).toBe(TOKEN);
    expect(stand.reads).toBe(0);
  });
});
