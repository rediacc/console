import { afterEach, describe, expect, it, vi } from 'vitest';
import { type SecureStorage, SecureStorageUnavailableError } from '../../utils/secure-storage.js';

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrentName: () => 'rediacc',
    getCurrent: async () => null,
    getResourceState: async () => ({ getMachines: () => ({}) }),
  },
}));

import { checkConfiguration } from '../doctor.js';
import { checkSecretStore } from '../doctor-secret-store.js';

function memoryStorage(type: string, lossy = false): SecureStorage {
  const map = new Map<string, string>();
  return {
    type,
    get: (k) => Promise.resolve(map.get(k) ?? null),
    set: (k, v) => {
      if (!lossy) map.set(k, v);
      return Promise.resolve();
    },
    delete: (k) => {
      map.delete(k);
      return Promise.resolve();
    },
  };
}

describe('doctor secret-store check', () => {
  const saved = process.env.REDIACC_SECRET_STORE;
  afterEach(() => {
    if (saved === undefined) delete process.env.REDIACC_SECRET_STORE;
    else process.env.REDIACC_SECRET_STORE = saved;
  });

  it('passes with the backend type when the round trip works', async () => {
    delete process.env.REDIACC_SECRET_STORE;
    const result = await checkSecretStore({ getStorage: () => memoryStorage('keyctl') });
    expect(result).toEqual({ name: 'Secret store', value: 'keyctl', status: 'ok' });
  });

  it('names REDIACC_SECRET_STORE when it chose the backend', async () => {
    process.env.REDIACC_SECRET_STORE = 'file';
    const result = await checkSecretStore({ getStorage: () => memoryStorage('file') });
    expect(result.status).toBe('ok');
    expect(result.value).toBe('file (REDIACC_SECRET_STORE=file)');
  });

  it('fails when the selection throws, carrying its message and a hint', async () => {
    const result = await checkSecretStore({
      getStorage: () => {
        throw new Error('keyctl is not installed');
      },
    });
    expect(result).toMatchObject({ status: 'fail', value: 'keyctl is not installed' });
    expect(result.hint).toContain('REDIACC_SECRET_STORE=file');
  });

  it('fails when a stored secret does not read back', async () => {
    const result = await checkSecretStore({ getStorage: () => memoryStorage('keyctl', true) });
    expect(result.status).toBe('fail');
    expect(result.value).toContain('did not read back');
  });

  it('warns, naming the key, when the probe secret cannot be removed', async () => {
    const stuck: SecureStorage = {
      ...memoryStorage('keyctl'),
      delete: () => Promise.reject(new Error('keyctl unlink refused')),
    };
    const result = await checkSecretStore({ getStorage: () => stuck });
    expect(result.status).toBe('warn');
    expect(result.value).toMatch(/rdc:doctor:.*could not be removed \(keyctl unlink refused\)/);
  });

  it('is a row of the configuration section', async () => {
    delete process.env.REDIACC_SECRET_STORE;
    const section = await checkConfiguration({ getStorage: () => memoryStorage('keyctl') });
    expect(section.checks.at(-1)).toEqual({ name: 'Secret store', value: 'keyctl', status: 'ok' });
    const failing = await checkConfiguration({ getStorage: () => memoryStorage('keyctl', true) });
    expect(failing.checks.at(-1)?.status).toBe('fail');
  });

  it('shows each platform its own hint, never the Linux keyctl one on Windows', async () => {
    const lossy = () => memoryStorage('dpapi', true);
    const win = await checkSecretStore({ getStorage: lossy, platform: 'win32' });
    expect(win.hint).toContain('powershell');
    expect(win.hint).not.toContain('keyctl');
    expect(win.hint).not.toContain('keyutils');
    const mac = await checkSecretStore({ getStorage: lossy, platform: 'darwin' });
    expect(mac.hint).toContain('Keychain');
    expect(mac.hint).not.toContain('keyctl');
    const linux = await checkSecretStore({ getStorage: lossy, platform: 'linux' });
    expect(linux.hint).toContain('keyctl link @u @s');
  });

  it('carries the own error text of the probe in the Windows hint', async () => {
    const result = await checkSecretStore({
      platform: 'win32',
      getStorage: () => {
        throw new SecureStorageUnavailableError(
          'could not be stored and read back',
          'Add-Type : access denied'
        );
      },
    });
    expect(result.status).toBe('fail');
    expect(result.hint).toContain('Add-Type : access denied');
    expect(result.hint).not.toContain('keyctl');
  });

  it('warns, naming the timeout, when the probe ran out of time', async () => {
    const result = await checkSecretStore({
      platform: 'win32',
      getStorage: () => {
        throw new SecureStorageUnavailableError(
          'powershell did not answer within 20 seconds',
          undefined,
          true
        );
      },
    });
    expect(result.status).toBe('warn');
    expect(result.value).toContain('within 20 seconds');
    expect(result.hint).toContain('timed out');
  });
});
