/**
 * Format skew between rdc releases: rdc 1.3.12 predates envelope v3 and reads every pull as v2, and
 * a pre-v4 rdc reads every pull as v3. These pin both directions of the gap: an envelope this reader
 * is too old for names the gap, and a blob relabelled to an older version (what an older rdc does)
 * fails closed with the integrity error.
 */

import { describe, expect, it } from 'vitest';
import {
  ConfigEnvelopeTooNewError,
  ConfigIntegrityError,
  generateAesKey,
  generateCek,
  generateConfigKey,
  selectiveDecrypt,
  selectiveEncrypt,
} from '../index.js';
import type { EncryptedConfigPayload, FullConfig } from '../types.js';
import { sealEnvelopeV3 } from './fixtures/envelope-v3.js';

const STORE = 'store-skew';

const config: FullConfig = {
  envelopeVersion: 4,
  id: '550e8400-e29b-41d4-a716-446655440001',
  version: 7,
  sdkEpoch: 5913166,
  commitments: { alg: 'HMAC-SHA256', fckSalt: '', fields: {} },
  machines: { server1: { ip: '10.0.0.1', port: 22 } },
};

function bindingOf(payload: EncryptedConfigPayload) {
  return { storeId: STORE, configId: payload.envelope.id, teamId: payload.envelope.teamId ?? null };
}

async function sealed() {
  const sdkKey = await generateAesKey();
  const cek = await generateCek();
  const payload = await selectiveEncrypt(config, sdkKey, cek, {
    storeId: STORE,
    sdkEpoch: config.sdkEpoch,
    commitEntries: [],
    configKey: { key: await generateConfigKey(), version: 1, cekGeneration: 1 },
  });
  return { sdkKey, cek, payload };
}

async function sealedV3() {
  const sdkKey = await generateAesKey();
  const cek = await generateCek();
  const payload = await sealEnvelopeV3(config, sdkKey, cek, {
    storeId: STORE,
    sdkEpoch: config.sdkEpoch,
    commitEntries: [],
  });
  return { sdkKey, cek, payload };
}

describe('envelope skew', () => {
  it('reads its own v4 blob (positive control)', async () => {
    const { sdkKey, cek, payload } = await sealed();
    expect(payload.envelope.envelopeVersion).toBe(4);
    const out = await selectiveDecrypt(payload, cek, sdkKey, bindingOf(payload));
    expect(out.machines).toEqual(config.machines);
  });

  it('reads a stored v3 blob (positive control)', async () => {
    const { sdkKey, cek, payload } = await sealedV3();
    const out = await selectiveDecrypt(payload, cek, sdkKey, bindingOf(payload));
    expect(out.machines).toEqual(config.machines);
  });

  it('a v4 blob relabelled v3, as a pre-v4 rdc reads it, fails the integrity check', async () => {
    const { sdkKey, cek, payload } = await sealed();
    const asOldCli = {
      ...payload,
      envelope: { ...payload.envelope, envelopeVersion: 3 as const },
    };
    await expect(
      selectiveDecrypt(asOldCli, cek, sdkKey, bindingOf(asOldCli))
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('a v3 blob relabelled v2, as rdc 1.3.12 reads it, fails the integrity check', async () => {
    const { sdkKey, cek, payload } = await sealedV3();
    const asOldCli = {
      ...payload,
      envelope: { ...payload.envelope, envelopeVersion: 2 as const },
    };
    await expect(
      selectiveDecrypt(asOldCli, cek, sdkKey, bindingOf(asOldCli))
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('a v5 envelope names the gap, not the slot key', async () => {
    const { sdkKey, cek, payload } = await sealed();
    const v5 = {
      ...payload,
      envelope: { ...payload.envelope, envelopeVersion: 5 as unknown as 4 },
    };
    const err = await selectiveDecrypt(v5, cek, sdkKey, bindingOf(v5)).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ConfigEnvelopeTooNewError);
    expect(err).not.toBeInstanceOf(ConfigIntegrityError);
    expect((err as Error).message).toBe(
      'Written by a newer rdc (envelope v5); this build reads v2 to v4. Upgrade rdc.'
    );
  });

  it('a v3 blob relabelled v4 fails closed with the integrity error', async () => {
    const { sdkKey, cek, payload } = await sealedV3();
    const relabelled = {
      ...payload,
      envelope: { ...payload.envelope, envelopeVersion: 4 as const },
    };
    await expect(
      selectiveDecrypt(relabelled, cek, sdkKey, bindingOf(relabelled))
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('an envelope older than v2 keeps the generic unsupported-version error', async () => {
    const { sdkKey, cek, payload } = await sealed();
    const v1 = {
      ...payload,
      envelope: { ...payload.envelope, envelopeVersion: 1 as unknown as 4 },
    };
    const err = await selectiveDecrypt(v1, cek, sdkKey, bindingOf(v1)).catch((e: unknown) => e);
    expect(err).not.toBeInstanceOf(ConfigEnvelopeTooNewError);
    expect((err as Error).message).toContain('Unsupported envelope version');
  });
});
