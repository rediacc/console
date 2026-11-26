import { describe, expect, it } from 'vitest';
import { exportAesKey, generateAesKey, importAesKey, toBase64 } from '../aes.js';
import {
  decryptPolicyRecord,
  derivePolicyKey,
  encryptPolicyRecord,
  type PolicyRecordBinding,
  PolicyRecordIntegrityError,
  policyKeyInfo,
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

  it('reports a malformed served version as an integrity failure (review 6eea934f.1)', async () => {
    const cek = await generateAesKey();
    const record = await encryptPolicyRecord(policy, cek, binding);
    const served = { ...record, version: '3' as unknown as number };
    await expect(decryptPolicyRecord(served, cek, pointer)).rejects.toBeInstanceOf(
      PolicyRecordIntegrityError
    );
    const generation = { ...record, cekGeneration: -1 };
    await expect(decryptPolicyRecord(generation, cek, pointer)).rejects.toBeInstanceOf(
      PolicyRecordIntegrityError
    );
  });

  it('reports a CEK that cannot be exported as its own failure, not as a tampered record', async () => {
    const cek = await generateAesKey();
    const record = await encryptPolicyRecord(policy, cek, binding);
    const sealed = await crypto.subtle.importKey(
      'raw',
      (await exportAesKey(cek)) as Uint8Array<ArrayBuffer>,
      { name: 'AES-GCM', length: 256 },
      false,
      ['decrypt']
    );
    const failure = await decryptPolicyRecord(record, sealed, pointer).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(Error);
    expect(failure).not.toBeInstanceOf(PolicyRecordIntegrityError);
    // Control: the extractable twin of the same key opens the record.
    await expect(decryptPolicyRecord(record, cek, pointer)).resolves.toEqual(policy);
  });

  it('refuses a blob sealed under another CEK', async () => {
    const record = await encryptPolicyRecord(policy, await generateAesKey(), binding);
    await expect(
      decryptPolicyRecord(record, await generateAesKey(), pointer)
    ).rejects.toBeInstanceOf(PolicyRecordIntegrityError);
  });

  it('pins the AAD bytes (domain, NUL, canonical body)', () => {
    const aad = policyRecordAad(binding);
    const domain = new TextEncoder().encode('rediacc-policy-aad-v2\0');
    expect(aad.slice(0, domain.length)).toEqual(domain);
    // Known answer: any change to the AAD layout changes this and breaks every stored record.
    expect(toBase64(aad)).toMatchInlineSnapshot(
      `"cmVkaWFjYy1wb2xpY3ktYWFkLXYyAAUAAAAGAAAADWNla0dlbmVyYXRpb24CMgAAAAhjb25maWdJZAMAAAAIY29uZmlnLTEAAAAHc3RvcmVJZAMAAAAHc3RvcmUtMQAAAAZ0ZWFtSWQDAAAABnRlYW0tMQAAAAF2AjIAAAAHdmVyc2lvbgIz"`
    );
  });

  it('opens a frozen record (known answer from a fixed CEK)', async () => {
    const cek = await importAesKey(new Uint8Array(32).fill(7));
    const frozen = {
      version: 3,
      cekGeneration: 2,
      blob: 'gUjBer3WNzjhb3ggvKeP4Ut2zEvsr0XjWIduTadwceSqBRP3PzjpaAHVOFivsiKlurgnBUY8/K/tKM8TU/bOutyFNPp+e/z1cefmam0KdxY/B9yEHOg=',
    };
    await expect(decryptPolicyRecord(frozen, cek, pointer)).resolves.toEqual(policy);
  });

  it('refuses a v1 blob, sealed under the CEK itself with the v1 AAD (clean break)', async () => {
    const cek = await importAesKey(new Uint8Array(32).fill(7));
    // The frozen record of the v1 format (same CEK, binding and policy as the v2 known answer).
    const v1 = {
      version: 3,
      cekGeneration: 2,
      blob: 'KWc+2CSux59MSnKU1h6tALTCqAdWqgiSaElTrUQLO/em/3TsWEFQYKzjSVc8UDECUi5XLtLOAQI/1T5BHYYi88aPZAqKPjmHabeILgJgGr73XMO9W0U=',
    };
    await expect(decryptPolicyRecord(v1, cek, pointer)).rejects.toBeInstanceOf(
      PolicyRecordIntegrityError
    );
    await expect(
      decryptPolicyRecord(v1, await derivePolicyKey(cek, { ...pointer, cekGeneration: 2 }), pointer)
    ).rejects.toBeInstanceOf(PolicyRecordIntegrityError);
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

  describe('policy key', () => {
    it('pins the derived key (known answer, checked against an independent RFC 5869 HKDF)', async () => {
      const cek = await importAesKey(new Uint8Array(32).fill(7));
      const info = policyKeyInfo(binding);
      expect(new TextDecoder().decode(info.slice(0, 22))).toBe('rediacc-policy-key-v1\0');
      const derived = await derivePolicyKey(cek, binding);
      expect(derived.kind).toBe('policy-key');
      expect(toBase64(await exportAesKey(derived.key))).toBe(
        'W8B3Rq896+VCT9klMNcj9tlX+eCQkKW9nz56XuIDXW0='
      );
    });

    it('the CEK and the derived key open the same record', async () => {
      const cek = await generateAesKey();
      const record = await encryptPolicyRecord(policy, cek, binding);
      const derived = await derivePolicyKey(cek, { ...pointer, cekGeneration: 2 });
      await expect(decryptPolicyRecord(record, cek, pointer)).resolves.toEqual(policy);
      await expect(decryptPolicyRecord(record, derived, pointer)).resolves.toEqual(policy);
    });

    it('does not seal under the CEK itself: the raw CEK posing as a policy key fails', async () => {
      const cek = await generateAesKey();
      const record = await encryptPolicyRecord(policy, cek, binding);
      await expect(
        decryptPolicyRecord(record, { kind: 'policy-key', key: cek }, pointer)
      ).rejects.toBeInstanceOf(PolicyRecordIntegrityError);
    });

    it.each([
      ['another store', { storeId: 'store-2' }],
      ['another config', { configId: 'config-2' }],
      ['another team', { teamId: 'team-2' }],
      ['the org-level config', { teamId: null }],
      ['another CEK generation', { cekGeneration: 3 }],
    ])(
      'a key derived for %s does not open the record (control: its own key opens)',
      async (_l, change) => {
        const cek = await generateAesKey();
        const record = await encryptPolicyRecord(policy, cek, binding);
        const own = await derivePolicyKey(cek, { ...pointer, cekGeneration: 2 });
        await expect(decryptPolicyRecord(record, own, pointer)).resolves.toEqual(policy);
        const wrong = await derivePolicyKey(cek, { ...pointer, cekGeneration: 2, ...change });
        await expect(decryptPolicyRecord(record, wrong, pointer)).rejects.toBeInstanceOf(
          PolicyRecordIntegrityError
        );
      }
    );

    it('a pointer key read against another pointer fails even when that pointer has a record', async () => {
      const cek = await generateAesKey();
      const orgPointer = { storeId: 'store-1', configId: 'org-1', teamId: null };
      const orgRecord = await encryptPolicyRecord(policy, cek, {
        ...orgPointer,
        version: 1,
        cekGeneration: 2,
      });
      const teamKey = await derivePolicyKey(cek, { ...pointer, cekGeneration: 2 });
      await expect(decryptPolicyRecord(orgRecord, teamKey, orgPointer)).rejects.toBeInstanceOf(
        PolicyRecordIntegrityError
      );
      const orgKey = await derivePolicyKey(cek, { ...orgPointer, cekGeneration: 2 });
      await expect(decryptPolicyRecord(orgRecord, orgKey, orgPointer)).resolves.toEqual(policy);
    });
  });
});
