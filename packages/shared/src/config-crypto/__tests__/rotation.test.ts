/**
 * Rotation Tests — the full org-wide CEK rotation sequence, real crypto only.
 *
 * Drives the exact path the portal wizard and `rdc config rotate-cek` share:
 * push a config under the old CEK, re-encrypt it under a new one, distribute
 * the new CEK (self-wrap for the initiator, X25519 handoff for everyone else),
 * and prove every party can decrypt afterwards — and that the old CEK cannot.
 *
 * Imports go through the '@rediacc/shared/config-crypto/rotation' subpath on
 * purpose: rotation is deliberately kept out of the barrel (import-cycle
 * guard), so this test also pins that the subpath consumers use keeps working.
 */

import type { RotationIdentity } from '@rediacc/shared/config-crypto/rotation';
import {
  distributeNewCek,
  generateCek,
  reencryptConfig,
} from '@rediacc/shared/config-crypto/rotation';
import { describe, expect, it } from 'vitest';
import type { RdcConfig } from '../../config-schema/index.js';
import { buildConfigPushPayload, decryptConfigPullPayload } from '../../config-schema/index.js';
import {
  cekHandoffDecrypt,
  cekUnwrap,
  deriveWrappingKey,
  exportAesKey,
  generateSdkMaster,
  generateServerSecret,
  importAesKey,
  randomBytes,
  sdkDerive,
  toBase64,
} from '../index.js';
import type { CekHandoffBlob } from '../types.js';

const TEST_CONFIG: RdcConfig = {
  schemaVersion: 3,
  id: '550e8400-e29b-41d4-a716-446655440000',
  version: 1,
  account: { userEmail: 'admin@example.com' },
  resources: {
    machines: { prod: { ip: '10.0.0.1', user: 'rediacc' } },
    // v3 families: rotation re-encrypts through fullConfigToRdcConfig, which
    // silently dropped these before the family-drop fix. Carried here so the
    // rotation path itself pins the round trip, not just the push/pull tests.
    datastores: { ds1: { backend: { kind: 'local', machine: 'prod', path: '/mnt/pool' } } },
    clusters: {
      c1: { provider: 'kvm', pools: [{ name: 'p', role: 'hyperconverged', count: 1 }] },
    },
    backupStrategies: {
      nightly: {
        destinations: [{ kind: 'storage', name: 'off', storage: 's1' }],
        schedule: '0 3 * * *',
      },
    },
    deletedRepositories: [
      {
        name: 'gone',
        tag: 'base',
        deletedAt: '2026-07-01T00:00:00Z',
        repositoryGuid: '1a2b3c4d-5e6f-4a8b-9c0d-e1f2a3b4c5d6',
        credential: 'archived-cred',
      },
    ],
  },
  credentials: {
    ssh: { privateKey: '-----BEGIN OPENSSH PRIVATE KEY-----\nrotation-test\n' },
  },
  encryption: { mode: 'plaintext' },
};

describe('CEK rotation', () => {
  it('reencryptConfig + distributeNewCek: initiator and handed-off member both decrypt', async () => {
    // ── Store state before rotation ──
    const sdkMaster = generateSdkMaster();
    const serverSecret = generateServerSecret();
    const oldCek = await generateCek();

    const pullEpoch = 5913166;
    const pushEpoch = 5913167;
    const sdkForPull = await sdkDerive(sdkMaster, pullEpoch);
    const sdkForPush = await sdkDerive(sdkMaster, pushEpoch);

    // The config as it sits on the server: pushed under the OLD CEK.
    const pulled = await buildConfigPushPayload(TEST_CONFIG, {
      version: 1,
      sdkEpoch: pullEpoch,
      sdkDerived: sdkForPull,
      cek: oldCek,
      teamId: 'team-1',
    });

    // ── Rotation: re-encrypt under a NEW CEK ──
    const newCek = await generateCek();
    const reencrypted = await reencryptConfig({
      pulled,
      oldCek,
      newCek,
      sdkDerivedForPull: sdkForPull,
      sdkDerivedForPush: sdkForPush,
      sdkEpoch: pushEpoch,
      version: 2,
      teamId: 'team-1',
    });

    expect(reencrypted.envelope.version).toBe(2);
    expect(reencrypted.envelope.sdkEpoch).toBe(pushEpoch);
    // Fresh FCK salt: the old envelope's commitment HMACs must be dead.
    expect(reencrypted.envelope.commitments.fckSalt).not.toBe(pulled.envelope.commitments.fckSalt);

    // The old CEK is dead against the new blob.
    await expect(
      decryptConfigPullPayload(reencrypted, { cek: oldCek, sdkDerived: sdkForPush })
    ).rejects.toThrow();

    // ── Distribution: initiator self-wrap + member handoff ──
    const initiatorPrf = randomBytes(32);
    const initiatorWrappingKey = await deriveWrappingKey(initiatorPrf, serverSecret);
    const memberKeyPair = await crypto.subtle.generateKey({ name: 'X25519' }, true, ['deriveBits']);
    const memberSpki = new Uint8Array(
      await crypto.subtle.exportKey('spki', memberKeyPair.publicKey)
    );

    const identities: RotationIdentity[] = [
      { userId: 'initiator', x25519PublicKey: 'unused-for-self' },
      { userId: 'member', x25519PublicKey: toBase64(memberSpki) },
    ];

    const { wrappedCek, handoffs } = await distributeNewCek({
      newCek,
      selfUserId: 'initiator',
      wrappingKey: initiatorWrappingKey,
      identities,
    });

    // Initiator is wrapped directly, never handed off.
    expect(handoffs.map((h) => h.targetUserId)).toEqual(['member']);

    // Initiator: unwrap own wrapped CEK → decrypt the re-encrypted config.
    const initiatorCek = await cekUnwrap(wrappedCek, initiatorWrappingKey);
    const initiatorView = await decryptConfigPullPayload(reencrypted, {
      cek: initiatorCek,
      sdkDerived: sdkForPush,
    });
    expect(initiatorView.machines).toEqual({ prod: { ip: '10.0.0.1', user: 'rediacc' } });

    // Member: accept the handoff → unwrap → decrypt.
    const blob = JSON.parse(handoffs[0].encryptedCek) as CekHandoffBlob;
    const memberCekRaw = await cekHandoffDecrypt(blob, memberKeyPair.privateKey);
    expect(toBase64(memberCekRaw)).toBe(toBase64(await exportAesKey(newCek)));

    const memberCek = await importAesKey(memberCekRaw);
    const memberView = await decryptConfigPullPayload(reencrypted, {
      cek: memberCek,
      sdkDerived: sdkForPush,
    });
    expect(memberView.ssh).toEqual({
      privateKey: '-----BEGIN OPENSSH PRIVATE KEY-----\nrotation-test\n',
    });
    expect(memberView.teamId).toBe('team-1');

    // The committed account section and the v3 families made it through the
    // re-encryption intact.
    expect(memberView.account).toEqual(TEST_CONFIG.account);
    expect(memberView.datastores).toEqual(TEST_CONFIG.resources?.datastores);
    expect(memberView.clusters).toEqual(TEST_CONFIG.resources?.clusters);
    expect(memberView.backupStrategies).toEqual(TEST_CONFIG.resources?.backupStrategies);
    expect(memberView.deletedRepositories).toEqual(TEST_CONFIG.resources?.deletedRepositories);
  });
});
