import { describe, expect, it } from 'vitest';
import { generateAesKey, importAesKey, toBase64 } from '../aes.js';
import {
  decryptPolicyRecord,
  encryptPolicyRecord,
  type PolicyRecordBinding,
  PolicyRecordIntegrityError,
  policyRecordAad,
} from '../policy-record.js';

const binding: PolicyRecordBinding = {
  storeId: 'store-1',
  configId: 'config-1',
  teamId: 'team-1',
  version: 3,
  cekGeneration: 2,
};
const pointer = { storeId: 'store-1', configId: 'config-1', teamId: 'team-1' };
const policy = { version: 1, defaults: { commands: { allow: ['repo *'] } } };

describe('policy record', () => {
  it('round-trips under its own binding', async () => {
    const cek = await generateAesKey();
    const record = await encryptPolicyRecord(policy, cek, binding);
    expect(record.version).toBe(3);
    expect(record.cekGeneration).toBe(2);
    await expect(decryptPolicyRecord(record, cek, pointer)).resolves.toEqual(policy);
  });

  it('opens an org-level record with a null or absent team alike', async () => {
    const cek = await generateAesKey();
    const record = await encryptPolicyRecord(policy, cek, { ...binding, teamId: null });
    await expect(
      decryptPolicyRecord(record, cek, { storeId: 'store-1', configId: 'config-1' })
    ).resolves.toEqual(policy);
  });

  it.each([
    ['another store', { ...pointer, storeId: 'store-2' }],
    ['another config', { ...pointer, configId: 'config-2' }],
    ['another team', { ...pointer, teamId: 'team-2' }],
    ['the org-level config', { ...pointer, teamId: null }],
  ])('refuses a blob served for %s', async (_label, readerPointer) => {
    const cek = await generateAesKey();
    const record = await encryptPolicyRecord(policy, cek, binding);
    await expect(decryptPolicyRecord(record, cek, readerPointer)).rejects.toBeInstanceOf(
      PolicyRecordIntegrityError
    );
  });

  it('refuses a replayed older blob served under a newer version', async () => {
    const cek = await generateAesKey();
    const record = await encryptPolicyRecord(policy, cek, binding);
    await expect(
      decryptPolicyRecord({ ...record, version: 4 }, cek, pointer)
    ).rejects.toBeInstanceOf(PolicyRecordIntegrityError);
  });

  it('refuses a blob relabelled with another CEK generation', async () => {
    const cek = await generateAesKey();
    const record = await encryptPolicyRecord(policy, cek, binding);
    await expect(
      decryptPolicyRecord({ ...record, cekGeneration: 3 }, cek, pointer)
    ).rejects.toBeInstanceOf(PolicyRecordIntegrityError);
  });

  it('refuses a blob sealed under another CEK', async () => {
    const record = await encryptPolicyRecord(policy, await generateAesKey(), binding);
    await expect(
      decryptPolicyRecord(record, await generateAesKey(), pointer)
    ).rejects.toBeInstanceOf(PolicyRecordIntegrityError);
  });

  it('pins the AAD bytes (domain, NUL, canonical body)', () => {
    const aad = policyRecordAad(binding);
    const domain = new TextEncoder().encode('rediacc-policy-aad-v1\0');
    expect(aad.slice(0, domain.length)).toEqual(domain);
    // Known answer: any change to the AAD layout changes this and breaks every stored record.
    expect(toBase64(aad)).toMatchInlineSnapshot(
      `"cmVkaWFjYy1wb2xpY3ktYWFkLXYxAAUAAAAGAAAADWNla0dlbmVyYXRpb24CMgAAAAhjb25maWdJZAMAAAAIY29uZmlnLTEAAAAHc3RvcmVJZAMAAAAHc3RvcmUtMQAAAAZ0ZWFtSWQDAAAABnRlYW0tMQAAAAF2AjEAAAAHdmVyc2lvbgIz"`
    );
  });

  it('opens a frozen record (known answer from a fixed CEK)', async () => {
    const cek = await importAesKey(new Uint8Array(32).fill(7));
    const frozen = {
      version: 3,
      cekGeneration: 2,
      blob: 'KWc+2CSux59MSnKU1h6tALTCqAdWqgiSaElTrUQLO/em/3TsWEFQYKzjSVc8UDECUi5XLtLOAQI/1T5BHYYi88aPZAqKPjmHabeILgJgGr73XMO9W0U=',
    };
    await expect(decryptPolicyRecord(frozen, cek, pointer)).resolves.toEqual(policy);
  });

  it('refuses a version below 1 and a negative generation before sealing', async () => {
    const cek = await generateAesKey();
    await expect(encryptPolicyRecord(policy, cek, { ...binding, version: 0 })).rejects.toThrow(
      /positive integer/
    );
    await expect(
      encryptPolicyRecord(policy, cek, { ...binding, cekGeneration: -1 })
    ).rejects.toThrow(/non-negative integer/);
  });
});
