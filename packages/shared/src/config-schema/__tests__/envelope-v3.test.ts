/**
 * Envelope v3 (PLAN-config-sync-hardening T8/T9, operator rulings D1, D2, D6).
 *
 * - The blob is bound to (store, config, team, version, epoch, commitment state) by the AES-GCM AAD:
 *   a reader that asks for one config opens nothing else (F1).
 * - Commitment keys are blinded pointers: the envelope carries no document name (F14).
 * - A push that drops a committed path carries a tombstone equal to the STORED commitment (F2).
 * - A v2 envelope still opens for one release, under its blob HMAC (D2), and the push that upgrades
 *   it maps every v2 pointer to its v3 key.
 */

import { describe, expect, it } from 'vitest';
import {
  blindPointer,
  ConfigIntegrityError,
  computeCommitments,
  configEncrypt,
  deriveFieldCommitmentKey,
  derivePointerBlindingKey,
  type EncryptedConfigPayload,
  generateCek,
  generateFckSalt,
  generateSdkMaster,
  hmacCompute,
  sdkDerive,
} from '../../config-crypto/index.js';
import {
  buildCommitEntries,
  buildConfigPushPayload,
  decryptConfigPullPayload,
  removedCommitEntries,
  toFullConfig,
} from '../payload.js';
import type { RdcConfig } from '../schemas.js';

const STORE = 'store-a';
const CONFIG = '00000000-0000-0000-0000-00000000c0f1';

function doc(machines: Record<string, { ip: string; user: string }>): RdcConfig {
  return {
    schemaVersion: 3,
    id: CONFIG,
    version: 1,
    resources: { machines, repositories: {}, storages: {} },
    credentials: { ssh: { privateKey: 'PRIVATE-KEY-BYTES', publicKey: 'ssh-ed25519 AAA' } },
  } as RdcConfig;
}

const BOTH = {
  alpha: { ip: '10.0.0.1', user: 'root' },
  'secret-host': { ip: '10.0.0.2', user: 'ops' },
};

async function keys() {
  return { cek: await generateCek(), sdkDerived: await sdkDerive(generateSdkMaster(), 11) };
}

function push(
  config: RdcConfig,
  k: { cek: CryptoKey; sdkDerived: CryptoKey },
  extra: Partial<Parameters<typeof buildConfigPushPayload>[1]> = {}
) {
  return buildConfigPushPayload(config, {
    version: 2,
    sdkEpoch: 11,
    sdkDerived: k.sdkDerived,
    cek: k.cek,
    storeId: STORE,
    ...extra,
  });
}

function open(
  payload: EncryptedConfigPayload,
  k: { cek: CryptoKey; sdkDerived: CryptoKey },
  binding: { storeId?: string; configId?: string; teamId?: string | null } = {}
) {
  return decryptConfigPullPayload(payload, {
    ...k,
    binding: { storeId: STORE, configId: CONFIG, teamId: null, ...binding },
  });
}

/** An envelope v2 payload exactly as a pre-v3 client sealed it: plain pointers, blob HMAC, no AAD. */
async function legacyV2(config: RdcConfig, k: { cek: CryptoKey; sdkDerived: CryptoKey }) {
  const fckSalt = generateFckSalt();
  const fck = await deriveFieldCommitmentKey(k.cek, fckSalt);
  const commitments = await computeCommitments(fck, fckSalt, buildCommitEntries(config));
  const sensitive: Record<string, unknown> = {
    ...toFullConfig(config, { version: 1, sdkEpoch: 11 }),
  };
  for (const envelopeField of ['envelopeVersion', 'id', 'version', 'sdkEpoch', 'commitments']) {
    delete sensitive[envelopeField];
  }
  const encryptedBlob = await configEncrypt(JSON.stringify(sensitive), k.sdkDerived, k.cek);
  const payload: EncryptedConfigPayload = {
    envelope: { envelopeVersion: 2, id: CONFIG, version: 1, sdkEpoch: 11, commitments },
    encryptedBlob,
    hmac: await hmacCompute(encryptedBlob, k.cek),
  };
  return payload;
}

describe('envelope v3: the AAD binding (F1)', () => {
  it('opens for the binding it was sealed for', async () => {
    const k = await keys();
    const payload = await push(doc(BOTH), k);
    expect(payload.envelope.envelopeVersion).toBe(3);
    expect(payload.hmac).toBeUndefined();
    const opened = await open(payload, k);
    expect(opened.machines).toEqual(BOTH);
  });

  it.each([
    ['another config', { configId: 'ffffffff-0000-0000-0000-000000000000' }],
    ['another store', { storeId: 'store-b' }],
    ['another team', { teamId: 'team-x' }],
  ])('refuses to open as %s', async (_label, binding) => {
    const k = await keys();
    const payload = await push(doc(BOTH), k);
    await expect(open(payload, k, binding)).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it.each([
    [
      'version',
      (p: EncryptedConfigPayload) => ({ ...p.envelope, version: p.envelope.version + 5 }),
    ],
    [
      'sdkEpoch',
      (p: EncryptedConfigPayload) => ({ ...p.envelope, sdkEpoch: p.envelope.sdkEpoch + 1 }),
    ],
    [
      'commitment hmac',
      (p: EncryptedConfigPayload) => {
        const [key] = Object.keys(p.envelope.commitments.fields);
        return {
          ...p.envelope,
          commitments: {
            ...p.envelope.commitments,
            fields: {
              ...p.envelope.commitments.fields,
              [key]: { hmac: 'AAAA', kind: 'string' as const },
            },
          },
        };
      },
    ],
    [
      'salt',
      (p: EncryptedConfigPayload) => ({
        ...p.envelope,
        commitments: { ...p.envelope.commitments, fckSalt: generateFckSalt() },
      }),
    ],
  ])('refuses an envelope whose %s the server edited', async (_label, edit) => {
    const k = await keys();
    const payload = await push(doc(BOTH), k);
    const tampered = { ...payload, envelope: edit(payload) } as EncryptedConfigPayload;
    await expect(open(tampered, k)).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('a blob sealed under another CEK reads as an integrity failure', async () => {
    const k = await keys();
    const payload = await push(doc(BOTH), k);
    const other = { ...k, cek: await generateCek() };
    await expect(open(payload, other)).rejects.toBeInstanceOf(ConfigIntegrityError);
  });
});

describe('envelope v3: blinded pointers (F14, D6)', () => {
  it('carries no machine, repo or credential name', async () => {
    const k = await keys();
    const payload = await push(doc(BOTH), k);
    const json = JSON.stringify(payload.envelope);
    expect(json).not.toMatch(/secret-host|alpha|machines|credentials|privateKey|\/resources/);
  });

  it('one pointer keeps one key across pushes, and another config gets unrelated keys', async () => {
    const k = await keys();
    const first = await push(doc(BOTH), k);
    const second = await push(doc(BOTH), k, { version: 3 });
    expect(Object.keys(second.envelope.commitments.fields).sort()).toEqual(
      Object.keys(first.envelope.commitments.fields).sort()
    );
    const ownKey = await blindPointer(
      await derivePointerBlindingKey(k.cek, CONFIG),
      '/resources/machines/alpha/ip'
    );
    const otherKey = await blindPointer(
      await derivePointerBlindingKey(k.cek, 'another-config'),
      '/resources/machines/alpha/ip'
    );
    expect(first.envelope.commitments.fields).toHaveProperty([ownKey]);
    expect(otherKey).not.toBe(ownKey);
  });
});

describe('envelope v3: tombstones (F2, D1)', () => {
  it('a push that drops a machine carries the STORED commitment of each dropped path', async () => {
    const k = await keys();
    const stored = await push(doc(BOTH), k, { version: 1 });
    const trimmed = doc({ alpha: BOTH.alpha });
    const next = await push(trimmed, k, {
      prior: { envelopeVersion: 3, fckSalt: stored.envelope.commitments.fckSalt, base: doc(BOTH) },
    });

    const removed = next.envelope.commitments.removed ?? {};
    const dropped = removedCommitEntries(doc(BOTH), trimmed).map((e) => e.pointer);
    expect(dropped.length).toBeGreaterThan(0);
    expect(dropped.every((p) => p.startsWith('/resources/machines/secret-host/'))).toBe(true);
    expect(Object.keys(removed)).toHaveLength(dropped.length);
    for (const [key, proof] of Object.entries(removed)) {
      expect(stored.envelope.commitments.fields[key]).toEqual(proof);
      expect(next.envelope.commitments.fields).not.toHaveProperty([key]);
    }
    // Push-only blocks are not commitment state: the blob opens with them removed, as the server stores it.
    const state = { ...next.envelope.commitments };
    delete state.removed;
    delete state.migrated;
    expect(
      (await open({ ...next, envelope: { ...next.envelope, commitments: state } }, k)).machines
    ).toEqual({
      alpha: BOTH.alpha,
    });
  });

  it('a tombstone computed from a value the device never saw does not match the stored one', async () => {
    const k = await keys();
    const stored = await push(doc(BOTH), k, { version: 1 });
    const guessedBase = doc({ ...BOTH, 'secret-host': { ip: '10.0.0.99', user: 'ops' } });
    const next = await push(doc({ alpha: BOTH.alpha }), k, {
      prior: {
        envelopeVersion: 3,
        fckSalt: stored.envelope.commitments.fckSalt,
        base: guessedBase,
      },
    });
    const ipKey = await blindPointer(
      await derivePointerBlindingKey(k.cek, CONFIG),
      '/resources/machines/secret-host/ip'
    );
    expect(next.envelope.commitments.removed?.[ipKey]).toBeDefined();
    expect(next.envelope.commitments.removed?.[ipKey]).not.toEqual(
      stored.envelope.commitments.fields[ipKey]
    );
  });
});

describe('envelope v2: read for one release, upgraded by the next push (D2)', () => {
  it('a v2 payload opens under its blob HMAC and reports version 2', async () => {
    const k = await keys();
    const legacy = await legacyV2(doc(BOTH), k);
    const opened = await open(legacy, k);
    expect(opened.envelopeVersion).toBe(2);
    expect(opened.machines).toEqual(BOTH);
  });

  it('a v2 payload with a wrong or missing HMAC is refused', async () => {
    const k = await keys();
    const legacy = await legacyV2(doc(BOTH), k);
    await expect(open({ ...legacy, hmac: 'AAAA' }, k)).rejects.toBeInstanceOf(ConfigIntegrityError);
    await expect(open({ ...legacy, hmac: null }, k)).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('the upgrading push maps every committed v2 pointer to its v3 key, and tombstones in v2 form', async () => {
    const k = await keys();
    const legacy = await legacyV2(doc(BOTH), k);
    const next = await push(doc({ alpha: BOTH.alpha }), k, {
      prior: { envelopeVersion: 2, fckSalt: legacy.envelope.commitments.fckSalt, base: doc(BOTH) },
    });
    const migrated = next.envelope.commitments.migrated ?? {};
    const fields = next.envelope.commitments.fields;
    expect(Object.keys(migrated).sort()).toEqual(
      buildCommitEntries(doc({ alpha: BOTH.alpha }))
        .map((e) => e.pointer)
        .sort()
    );
    for (const key of Object.values(migrated)) expect(fields).toHaveProperty([key]);
    // Every stored v2 pointer is accounted for: migrated to a v3 key, or tombstoned with its stored commitment.
    for (const [pointer, stored] of Object.entries(legacy.envelope.commitments.fields)) {
      if (pointer in migrated) continue;
      expect(next.envelope.commitments.removed?.[pointer]).toEqual(stored);
    }
  });
});
