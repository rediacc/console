import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SecureStorage } from '../../utils/secure-storage.js';

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrentName: () => 'rediacc',
    getCurrent: async () => null,
    getResourceState: async () => ({ getMachines: () => ({}) }),
  },
}));

import { checkConfiguration, checkSecretStore } from '../doctor.js';

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
});
