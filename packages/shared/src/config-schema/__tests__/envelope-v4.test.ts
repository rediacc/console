/**
 * Envelope v4 through the push builder (PLAN-config-sync-hardening T8/T9, operator rulings D1, D2,
 * D6; PLAN-rmcp-policy-record.md Design 8).
 *
 * - The blob is sealed under the config's content key and bound to (store, config, team, version,
 *   epoch, content-key version, commitment state) by the AES-GCM AAD: a reader that asks for one
 *   config opens nothing else (F1).
 * - Commitment keys are pointers blinded under the content key: the envelope carries no document
 *   name (F14), and a push built from the stored wrap keeps every key.
 * - A push that drops a committed path carries a tombstone equal to the STORED commitment (F2).
 * - A stored v3 envelope opens under the CEK, and the push that upgrades it maps every CEK-blinded
 *   key to its content-key one. A v2 envelope still opens for one release, under its blob HMAC (D2),
 *   and the push that upgrades it maps every v2 pointer to its v4 key.
 */

import { describe, expect, it } from 'vitest';
import { sealEnvelopeV3 } from '../../config-crypto/__tests__/fixtures/envelope-v3.js';
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
  unwrapEnvelopeConfigKey,
} from '../../config-crypto/index.js';
import {
  buildCommitEntries,
  buildConfigPushPayload,
  decryptConfigPullPayload,
  envelopeConfigKeyWrap,
  type PushPrior,
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
    resources: { machines, repositories: {} },
    credentials: { ssh: { privateKey: 'PRIVATE-KEY-BYTES', publicKey: 'ssh-ed25519 AAA' } },
  };
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
    cekGeneration: 1,
    storeId: STORE,
    ...extra,
  });
}

/** The prior a device holds after pulling `stored`: its version, salt and content-key wrap. */
function priorOf(stored: EncryptedConfigPayload, base?: RdcConfig): PushPrior {
  const wrap = envelopeConfigKeyWrap(stored.envelope);
  return {
    envelopeVersion: stored.envelope.envelopeVersion,
    fckSalt: stored.envelope.commitments.fckSalt,
    ...(base ? { base } : {}),
    ...(wrap ? { configKey: wrap } : {}),
  };
}

/** The pointer-blinding key of a v4 payload: derived from its content key, unwrapped with the CEK. */
async function blindingOf(payload: EncryptedConfigPayload, cek: CryptoKey) {
  const key = await unwrapEnvelopeConfigKey(payload.envelope, cek, {
    storeId: STORE,
    configId: CONFIG,
    teamId: null,
  });
  return derivePointerBlindingKey(key, CONFIG);
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

describe('envelope v4: the AAD binding (F1)', () => {
  it('opens for the binding it was sealed for', async () => {
    const k = await keys();
    const payload = await push(doc(BOTH), k);
    expect(payload.envelope.envelopeVersion).toBe(4);
    expect(payload.envelope.configKeyVersion).toBe(1);
    expect(payload.envelope.cekGeneration).toBe(1);
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
    [
      'content-key version',
      (p: EncryptedConfigPayload) => ({
        ...p.envelope,
        configKeyVersion: (p.envelope.configKeyVersion ?? 1) + 1,
      }),
    ],
    [
      'CEK generation',
      (p: EncryptedConfigPayload) => ({
        ...p.envelope,
        cekGeneration: (p.envelope.cekGeneration ?? 1) + 1,
      }),
    ],
  ])('refuses an envelope whose %s the server edited', async (_label, edit) => {
    const k = await keys();
    const payload = await push(doc(BOTH), k);
    const tampered: EncryptedConfigPayload = { ...payload, envelope: edit(payload) };
    await expect(open(tampered, k)).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('a blob sealed under another CEK reads as an integrity failure', async () => {
    const k = await keys();
    const payload = await push(doc(BOTH), k);
    const other = { ...k, cek: await generateCek() };
    await expect(open(payload, other)).rejects.toBeInstanceOf(ConfigIntegrityError);
  });
});

describe('envelope v4: blinded pointers (F14, D6)', () => {
  it('carries no machine, repo or credential name', async () => {
    const k = await keys();
    const payload = await push(doc(BOTH), k);
    const json = JSON.stringify(payload.envelope);
    expect(json).not.toMatch(/secret-host|alpha|machines|credentials|privateKey|\/resources/);
  });

  it('one pointer keeps one key across pushes, and another config gets unrelated keys', async () => {
    const k = await keys();
    const first = await push(doc(BOTH), k);
    const second = await push(doc(BOTH), k, { version: 3, prior: priorOf(first) });
    expect(second.envelope.configKeyVersion).toBe(first.envelope.configKeyVersion);
    expect(
      Object.keys(second.envelope.commitments.fields).sort((a, b) => Number(a > b) - Number(a < b))
    ).toEqual(
      Object.keys(first.envelope.commitments.fields).sort((a, b) => Number(a > b) - Number(a < b))
    );
    const ownKey = await blindPointer(
      await blindingOf(first, k.cek),
      '/resources/machines/alpha/ip'
    );
    const otherKey = await blindPointer(
      await derivePointerBlindingKey(k.cek, CONFIG),
      '/resources/machines/alpha/ip'
    );
    expect(first.envelope.commitments.fields).toHaveProperty([ownKey]);
    // A key blinded under the CEK (a v3 store's) is unrelated to the content-key one.
    expect(otherKey).not.toBe(ownKey);
  });

  it('control: a push without the stored wrap seals under a fresh content key, so every key moves', async () => {
    const k = await keys();
    const first = await push(doc(BOTH), k);
    const fresh = await push(doc(BOTH), k, { version: 3 });
    expect(Object.keys(fresh.envelope.commitments.fields)).not.toEqual(
      Object.keys(first.envelope.commitments.fields)
    );
  });

  it('a v4 prior without its wrap is refused, never sealed under a fresh key', async () => {
    const k = await keys();
    const first = await push(doc(BOTH), k);
    const { configKey: _dropped, ...noWrap } = priorOf(first);
    await expect(push(doc(BOTH), k, { version: 3, prior: noWrap })).rejects.toThrow(
      /carries no content-key wrap/
    );
  });

  it('a wrap that does not open under this CEK is refused', async () => {
    const k = await keys();
    const first = await push(doc(BOTH), k);
    const other = { ...k, cek: await generateCek() };
    await expect(
      push(doc(BOTH), other, { version: 3, prior: priorOf(first) })
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });
});

describe('envelope v4: tombstones (F2, D1)', () => {
  it('a push that drops a machine carries the STORED commitment of each dropped path', async () => {
    const k = await keys();
    const stored = await push(doc(BOTH), k, { version: 1 });
    const trimmed = doc({ alpha: BOTH.alpha });
    const next = await push(trimmed, k, { prior: priorOf(stored, doc(BOTH)) });
    expect(next.envelope.commitments.migrated).toBeUndefined();

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
      prior: priorOf(stored, guessedBase),
    });
    const ipKey = await blindPointer(
      await blindingOf(stored, k.cek),
      '/resources/machines/secret-host/ip'
    );
    expect(next.envelope.commitments.removed?.[ipKey]).toBeDefined();
    expect(next.envelope.commitments.removed?.[ipKey]).not.toEqual(
      stored.envelope.commitments.fields[ipKey]
    );
  });
});

describe('envelope v3: read, upgraded by the next push', () => {
  function storedV3(config: RdcConfig, k: { cek: CryptoKey; sdkDerived: CryptoKey }) {
    const full = toFullConfig(JSON.parse(JSON.stringify(config)) as RdcConfig, {
      version: 1,
      sdkEpoch: 11,
    });
    return sealEnvelopeV3({ ...full, envelopeVersion: 3 }, k.sdkDerived, k.cek, {
      storeId: STORE,
      sdkEpoch: 11,
      commitEntries: buildCommitEntries(config),
    });
  }

  it('a stored v3 payload opens under the CEK and reports version 3', async () => {
    const k = await keys();
    const v3 = await storedV3(doc(BOTH), k);
    const opened = await open(v3, k);
    expect(opened.envelopeVersion).toBe(3);
    expect(opened.machines).toEqual(BOTH);
  });

  it('the upgrading push maps every CEK-blinded key to its content-key one, and tombstones under the stored keys', async () => {
    const k = await keys();
    const v3 = await storedV3(doc(BOTH), k);
    const next = await push(doc({ alpha: BOTH.alpha }), k, { prior: priorOf(v3, doc(BOTH)) });
    expect(next.envelope.envelopeVersion).toBe(4);
    expect(next.envelope.configKeyVersion).toBe(1);
    const migrated = next.envelope.commitments.migrated ?? {};
    const fields = next.envelope.commitments.fields;
    expect(Object.keys(migrated).length).toBeGreaterThan(0);
    for (const [storedKey, nextKey] of Object.entries(migrated)) {
      expect(v3.envelope.commitments.fields).toHaveProperty([storedKey]);
      expect(fields).toHaveProperty([nextKey]);
    }
    for (const [key, stored] of Object.entries(v3.envelope.commitments.fields)) {
      if (key in migrated) continue;
      expect(next.envelope.commitments.removed?.[key]).toEqual(stored);
    }
    expect(Object.keys(next.envelope.commitments.removed ?? {}).length).toBeGreaterThan(0);
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

  it('the upgrading push maps every committed v2 pointer to its v4 key, and tombstones in v2 form', async () => {
    const k = await keys();
    const legacy = await legacyV2(doc(BOTH), k);
    const next = await push(doc({ alpha: BOTH.alpha }), k, {
      prior: { envelopeVersion: 2, fckSalt: legacy.envelope.commitments.fckSalt, base: doc(BOTH) },
    });
    const migrated = next.envelope.commitments.migrated ?? {};
    const fields = next.envelope.commitments.fields;
    expect(Object.keys(migrated).sort((a, b) => Number(a > b) - Number(a < b))).toEqual(
      buildCommitEntries(doc({ alpha: BOTH.alpha }))
        .map((e) => e.pointer)
        .sort((a, b) => Number(a > b) - Number(a < b))
    );
    for (const key of Object.values(migrated)) expect(fields).toHaveProperty([key]);
    // Every stored v2 pointer is accounted for: migrated to a v4 key, or tombstoned with its stored commitment.
    for (const [pointer, stored] of Object.entries(legacy.envelope.commitments.fields)) {
      if (pointer in migrated) continue;
      expect(next.envelope.commitments.removed?.[pointer]).toEqual(stored);
    }
  });
});
