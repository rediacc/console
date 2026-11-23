/**
 * Per-config content keys (envelope v4, D56): known answers from fixed keys, round trips, and the
 * negative cases that make a leaked content key or a moved wrap useless outside its own config.
 */

import { describe, expect, it } from 'vitest';
import {
  blindPointer,
  type ConfigContentKey,
  ConfigIntegrityError,
  type ConfigKeyBinding,
  configDecrypt,
  configKeyWrapAad,
  derivePointerBlindingKey,
  envelopeAadV4,
  exportAesKey,
  generateAesKey,
  generateCek,
  generateConfigKey,
  importAesKey,
  selectiveDecrypt,
  selectiveDecryptWithConfigKey,
  selectiveEncrypt,
  toBase64,
  unwrapConfigKey,
  unwrapEnvelopeConfigKey,
  wrapConfigKey,
} from '../index.js';
import type { EncryptedConfigPayload, FullConfig } from '../types.js';
import { sealEnvelopeV3 } from './fixtures/envelope-v3.js';

const bytesToHex = (data: Uint8Array): string =>
  Array.from(data, (b) => b.toString(16).padStart(2, '0')).join('');
const seq = (start: number, length: number): Uint8Array =>
  new Uint8Array(Array.from({ length }, (_, i) => (start + i) & 0xff));

const STORE = 'store-v4';
const CONFIG_A = '550e8400-e29b-41d4-a716-44665544000a';
const CONFIG_B = '550e8400-e29b-41d4-a716-44665544000b';

const wrapBinding: ConfigKeyBinding = {
  storeId: STORE,
  configId: CONFIG_A,
  teamId: 'team-1',
  configKeyVersion: 1,
  cekGeneration: 2,
};

const fullConfig = (id: string, teamId?: string): FullConfig => ({
  envelopeVersion: 4,
  id,
  version: 7,
  sdkEpoch: 5913166,
  ...(teamId ? { teamId } : {}),
  commitments: { alg: 'HMAC-SHA256', fckSalt: '', fields: {} },
  machines: { server1: { ip: '10.0.0.1', port: 22 } },
  credentials: { token: 'secret' },
});

const bindingOf = (payload: EncryptedConfigPayload, storeId = STORE) => ({
  storeId,
  configId: payload.envelope.id,
  teamId: payload.envelope.teamId ?? null,
});

async function sealV4(id = CONFIG_A, teamId?: string, cek?: CryptoKey) {
  const sdkKey = await generateAesKey();
  const theCek = cek ?? (await generateCek());
  const configKey: ConfigContentKey = {
    key: await generateConfigKey(),
    version: 1,
    cekGeneration: 2,
  };
  const payload = await selectiveEncrypt(fullConfig(id, teamId), sdkKey, theCek, {
    storeId: STORE,
    sdkEpoch: 5913166,
    commitEntries: [{ pointer: '/credentials/token', value: 'secret' }],
    configKey,
  });
  return { sdkKey, cek: theCek, configKey, payload };
}

describe('content key wrap: known answers from fixed keys', () => {
  const CEK_RAW = seq(0x40, 32);
  const CONFIG_KEY_RAW = seq(0xc0, 32);
  // Sealed once from CEK_RAW and CONFIG_KEY_RAW under wrapBinding. Do NOT regenerate to make a red
  // test green: a red test here means every stored v4 wrap stops opening.
  const FROZEN_WRAP =
    'AGOYL8dSqZ174E9OGCZpTJjb8Lj89FrwKXG+GXFjNGEWWKwGsfPN3b8AxHmQ0eUq3kYuBZeVs8hgviqZ';

  it('pins the wrap AAD bytes', () => {
    const aad = configKeyWrapAad(wrapBinding);
    expect(new TextDecoder().decode(aad.slice(0, 22))).toBe('rediacc-config-key-v1\0');
    expect(toBase64(aad)).toBe(
      'cmVkaWFjYy1jb25maWcta2V5LXYxAAUAAAAFAAAADWNla0dlbmVyYXRpb24CMgAAAAhjb25maWdJZAMAAAAkNTUwZTg0MDAtZTI5Yi00MWQ0LWE3MTYtNDQ2NjU1NDQwMDBhAAAAEGNvbmZpZ0tleVZlcnNpb24CMQAAAAdzdG9yZUlkAwAAAAhzdG9yZS12NAAAAAZ0ZWFtSWQDAAAABnRlYW0tMQ=='
    );
  });

  it('unwraps the frozen wrap to the pinned content key', async () => {
    const cek = await importAesKey(CEK_RAW);
    const key = await unwrapConfigKey(FROZEN_WRAP, cek, wrapBinding);
    expect(bytesToHex(await exportAesKey(key))).toBe(bytesToHex(CONFIG_KEY_RAW));
  });

  it('pins the v4 blob AAD bytes', async () => {
    const aad = await envelopeAadV4(
      { storeId: STORE, configId: CONFIG_A, teamId: 'team-1' },
      {
        version: 7,
        sdkEpoch: 5913166,
        configKeyVersion: 1,
        commitments: { alg: 'HMAC-SHA256', fckSalt: 'AAAAAAAAAAAAAAAAAAAAAA==', fields: {} },
      }
    );
    expect(new TextDecoder().decode(aad.slice(0, 22))).toBe('rediacc-config-aad-v4\0');
    expect(toBase64(aad)).toMatchInlineSnapshot(
      `"cmVkaWFjYy1jb25maWctYWFkLXY0AAUAAAAIAAAAC2NvbW1pdG1lbnRzAwAAACw4VGZ5ejd5ZlVjRDUvTmhuVENuT2tGUEs1VUpKelVYamd4emRDTzN5VSt3PQAAAAhjb25maWdJZAMAAAAkNTUwZTg0MDAtZTI5Yi00MWQ0LWE3MTYtNDQ2NjU1NDQwMDBhAAAAEGNvbmZpZ0tleVZlcnNpb24CMQAAAAhzZGtFcG9jaAI1OTEzMTY2AAAAB3N0b3JlSWQDAAAACHN0b3JlLXY0AAAABnRlYW1JZAMAAAAGdGVhbS0xAAAAAXYCNAAAAAd2ZXJzaW9uAjc="`
    );
  });
});

describe('content key wrap: round trip and moved wraps', () => {
  it('round-trips a fresh content key', async () => {
    const cek = await generateCek();
    const key = await generateConfigKey();
    const wrapped = await wrapConfigKey(key, cek, wrapBinding);
    const back = await unwrapConfigKey(wrapped, cek, wrapBinding);
    expect(toBase64(await exportAesKey(back))).toBe(toBase64(await exportAesKey(key)));
  });

  it.each([
    ['another configId', { configId: CONFIG_B }],
    ['another teamId', { teamId: 'team-2' }],
    ['the org-level config (null team)', { teamId: null }],
    ['another configKeyVersion', { configKeyVersion: 2 }],
    ['another cekGeneration', { cekGeneration: 3 }],
    ['another store', { storeId: 'store-other' }],
  ])('refuses a wrap moved to %s', async (_label, moved) => {
    const cek = await generateCek();
    const wrapped = await wrapConfigKey(await generateConfigKey(), cek, wrapBinding);
    await expect(
      unwrapConfigKey(wrapped, cek, { ...wrapBinding, ...moved })
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('refuses a wrap under another CEK', async () => {
    const wrapped = await wrapConfigKey(
      await generateConfigKey(),
      await generateCek(),
      wrapBinding
    );
    await expect(unwrapConfigKey(wrapped, await generateCek(), wrapBinding)).rejects.toBeInstanceOf(
      ConfigIntegrityError
    );
  });

  it('refuses a key version below 1 and a negative generation', () => {
    expect(() => configKeyWrapAad({ ...wrapBinding, configKeyVersion: 0 })).toThrow(/>= 1/);
    expect(() => configKeyWrapAad({ ...wrapBinding, cekGeneration: -1 })).toThrow(/>= 0/);
  });
});

describe('envelope v4', () => {
  it('seals a v4 envelope carrying the wrap, the key version and the generation', async () => {
    const { payload } = await sealV4();
    expect(payload.envelope.envelopeVersion).toBe(4);
    expect(payload.envelope.configKeyVersion).toBe(1);
    expect(payload.envelope.cekGeneration).toBe(2);
    expect(typeof payload.envelope.wrappedConfigKey).toBe('string');
  });

  it('round-trips through the CEK (a member)', async () => {
    const { sdkKey, cek, payload } = await sealV4(CONFIG_A, 'team-1');
    const out = await selectiveDecrypt(payload, cek, sdkKey, bindingOf(payload));
    expect(out.machines).toEqual({ server1: { ip: '10.0.0.1', port: 22 } });
    expect(out.credentials).toEqual({ token: 'secret' });
    expect(out.envelopeVersion).toBe(4);
  });

  it('round-trips through the content key alone (an agent grant)', async () => {
    const { sdkKey, configKey, payload } = await sealV4();
    const out = await selectiveDecryptWithConfigKey(
      payload,
      configKey.key,
      sdkKey,
      bindingOf(payload)
    );
    expect(out.credentials).toEqual({ token: 'secret' });
  });

  it('keeps the envelope fields out of the blob', async () => {
    const { sdkKey, configKey, payload } = await sealV4();
    const aad = await envelopeAadV4(bindingOf(payload), {
      ...payload.envelope,
      configKeyVersion: 1,
    });
    const json = JSON.parse(await configDecrypt(payload.encryptedBlob, configKey.key, sdkKey, aad));
    expect(Object.keys(json).sort((a, b) => a.localeCompare(b))).toEqual([
      'credentials',
      'machines',
    ]);
  });

  it('refuses a blob decrypted with the CEK instead of its content key', async () => {
    const { sdkKey, cek, payload } = await sealV4();
    await expect(
      selectiveDecryptWithConfigKey(payload, cek, sdkKey, bindingOf(payload))
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it("refuses a wrap swapped between two configs of one store (config B's envelope carrying A's wrap)", async () => {
    const cek = await generateCek();
    const a = await sealV4(CONFIG_A, undefined, cek);
    const b = await sealV4(CONFIG_B, undefined, cek);
    const swapped: EncryptedConfigPayload = {
      ...b.payload,
      envelope: { ...b.payload.envelope, wrappedConfigKey: a.payload.envelope.wrappedConfigKey },
    };
    await expect(
      selectiveDecrypt(swapped, cek, b.sdkKey, bindingOf(swapped))
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it("refuses one config's content key on another config's blob (the leaked-grant case)", async () => {
    const cek = await generateCek();
    const a = await sealV4(CONFIG_A, undefined, cek);
    const b = await sealV4(CONFIG_B, undefined, cek);
    await expect(
      selectiveDecryptWithConfigKey(b.payload, a.configKey.key, b.sdkKey, bindingOf(b.payload))
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('refuses an envelope relabelled with another configKeyVersion', async () => {
    const { sdkKey, cek, payload } = await sealV4();
    const relabelled: EncryptedConfigPayload = {
      ...payload,
      envelope: { ...payload.envelope, configKeyVersion: 2 },
    };
    await expect(
      selectiveDecrypt(relabelled, cek, sdkKey, bindingOf(relabelled))
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('binds the blob itself to configKeyVersion (the content-key path, where no wrap is checked)', async () => {
    const { sdkKey, configKey, payload } = await sealV4();
    const relabelled: EncryptedConfigPayload = {
      ...payload,
      envelope: { ...payload.envelope, configKeyVersion: 2 },
    };
    await expect(
      selectiveDecryptWithConfigKey(relabelled, configKey.key, sdkKey, bindingOf(relabelled))
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('refuses a v4 blob served for another team or store', async () => {
    const { sdkKey, cek, payload } = await sealV4(CONFIG_A, 'team-1');
    await expect(
      selectiveDecrypt(payload, cek, sdkKey, { ...bindingOf(payload), teamId: 'team-2' })
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
    await expect(
      selectiveDecrypt(payload, cek, sdkKey, bindingOf(payload, 'store-other'))
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('refuses a v4 envelope missing its wrap fields', async () => {
    const { sdkKey, cek, payload } = await sealV4();
    const { wrappedConfigKey: _dropped, ...rest } = payload.envelope;
    await expect(
      selectiveDecrypt({ ...payload, envelope: rest }, cek, sdkKey, bindingOf(payload))
    ).rejects.toThrow(/must carry wrappedConfigKey/);
  });

  it('refuses a content key on a v3 envelope', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();
    const v3 = await sealEnvelopeV3(fullConfig(CONFIG_A), sdkKey, cek, {
      storeId: STORE,
      sdkEpoch: 5913166,
      commitEntries: [],
    });
    expect(v3.envelope.envelopeVersion).toBe(3);
    await expect(
      selectiveDecryptWithConfigKey(v3, await generateConfigKey(), sdkKey, bindingOf(v3))
    ).rejects.toThrow(/opens only envelope v4/);
  });

  it('unwrapEnvelopeConfigKey returns the sealing content key', async () => {
    const { cek, configKey, payload } = await sealV4();
    const key = await unwrapEnvelopeConfigKey(payload.envelope, cek, bindingOf(payload));
    expect(toBase64(await exportAesKey(key))).toBe(toBase64(await exportAesKey(configKey.key)));
  });
});

describe('envelope v4: commitments under the content key and the upgrade push', () => {
  it('blinds commitment keys under the content key, not the CEK', async () => {
    const { cek, configKey, payload } = await sealV4();
    const [key] = Object.keys(payload.envelope.commitments.fields);
    const underContent = await blindPointer(
      await derivePointerBlindingKey(configKey.key, CONFIG_A),
      '/credentials/token'
    );
    const underCek = await blindPointer(
      await derivePointerBlindingKey(cek, CONFIG_A),
      '/credentials/token'
    );
    expect(key).toBe(underContent);
    expect(key).not.toBe(underCek);
  });

  it('a v3 store pushed as v4 maps each stored (CEK-blinded) key to its v4 key, and tombstones under the stored keys', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();
    const configKey: ConfigContentKey = {
      key: await generateConfigKey(),
      version: 1,
      cekGeneration: 0,
    };
    const payload = await selectiveEncrypt(fullConfig(CONFIG_A), sdkKey, cek, {
      storeId: STORE,
      sdkEpoch: 5913166,
      commitEntries: [{ pointer: '/credentials/token', value: 'secret' }],
      configKey,
      prior: {
        envelopeVersion: 3,
        fckSalt: 'AAAAAAAAAAAAAAAAAAAAAA==',
        removed: [{ pointer: '/credentials/old', value: 'gone' }],
      },
    });
    const cekBlind = await derivePointerBlindingKey(cek, CONFIG_A);
    const contentBlind = await derivePointerBlindingKey(configKey.key, CONFIG_A);
    expect(payload.envelope.commitments.migrated).toEqual({
      [await blindPointer(cekBlind, '/credentials/token')]: await blindPointer(
        contentBlind,
        '/credentials/token'
      ),
    });
    expect(Object.keys(payload.envelope.commitments.removed ?? {})).toEqual([
      await blindPointer(cekBlind, '/credentials/old'),
    ]);
  });

  it('control: a v4 store pushed with the same content key sends no key map', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();
    const configKey: ConfigContentKey = {
      key: await generateConfigKey(),
      version: 1,
      cekGeneration: 0,
    };
    const payload = await selectiveEncrypt(fullConfig(CONFIG_A), sdkKey, cek, {
      storeId: STORE,
      sdkEpoch: 5913166,
      commitEntries: [{ pointer: '/credentials/token', value: 'secret' }],
      configKey,
      prior: { envelopeVersion: 4, fckSalt: 'AAAAAAAAAAAAAAAAAAAAAA==', removed: [] },
    });
    expect(payload.envelope.commitments.migrated).toBeUndefined();
  });

  it('a content-key rotation maps the old key to the new one', async () => {
    const sdkKey = await generateAesKey();
    const cek = await generateCek();
    const oldKey = await generateConfigKey();
    const configKey: ConfigContentKey = {
      key: await generateConfigKey(),
      version: 2,
      cekGeneration: 0,
    };
    const payload = await selectiveEncrypt(fullConfig(CONFIG_A), sdkKey, cek, {
      storeId: STORE,
      sdkEpoch: 5913166,
      commitEntries: [{ pointer: '/credentials/token', value: 'secret' }],
      configKey,
      prior: {
        envelopeVersion: 4,
        fckSalt: 'AAAAAAAAAAAAAAAAAAAAAA==',
        removed: [],
        configKey: oldKey,
      },
    });
    expect(payload.envelope.commitments.migrated).toEqual({
      [await blindPointer(await derivePointerBlindingKey(oldKey, CONFIG_A), '/credentials/token')]:
        await blindPointer(
          await derivePointerBlindingKey(configKey.key, CONFIG_A),
          '/credentials/token'
        ),
    });
  });
});
