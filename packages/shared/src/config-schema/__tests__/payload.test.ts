/**
 * Push-payload composition tests.
 *
 * The CLI, the web console editor, and the CEK rotation flow all push through
 * buildConfigPushPayload. If they ever diverged, the server-side precondition
 * check would reject the push, so these tests pin the composition: which
 * pointers get committed, what the envelope carries, and that a round trip
 * through the crypto layer returns the same sensitive data.
 */

import { describe, expect, it } from 'vitest';
import {
  blindPointer,
  derivePointerBlindingKey,
  generateCek,
  generateSdkMaster,
  sdkDerive,
} from '../../config-crypto/index.js';
import {
  buildCommitEntries,
  buildConfigPushPayload,
  decryptConfigPullPayload,
  toFullConfig,
} from '../payload.js';
import type { RdcConfig } from '../schemas.js';

/** Every payload of this file lives in one store; a reader binds to the config it asked for. */
const STORE_ID = 'store-1';
function readerBinding(payload: { envelope: { id: string; teamId?: string } }) {
  return {
    storeId: STORE_ID,
    configId: payload.envelope.id,
    teamId: payload.envelope.teamId ?? null,
  };
}

function sampleConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-0000-0000-000000000001',
    version: 4,
    defaults: { language: 'en', datastoreSize: '95%' },
    account: { userEmail: 'op@example.com' },
    credentials: {
      ssh: { privateKey: 'PRIVATE', publicKey: 'ssh-ed25519 AAA' },
    },
    resources: {
      machines: { 'web-1': { ip: '10.0.0.1', user: 'deploy', port: 22 } },
      repositories: {},
      storages: {},
    },
    encryption: { mode: 'plaintext' },
  };
}

async function keys(): Promise<{ cek: CryptoKey; sdkDerived: CryptoKey }> {
  const cek = await generateCek();
  const sdkDerived = await sdkDerive(generateSdkMaster(), 1);
  return { cek, sdkDerived };
}

describe('config push payload', () => {
  it('commit entries are schema-derived, sorted, and carry current values', () => {
    const entries = buildCommitEntries(sampleConfig());
    const pointers = entries.map((e) => e.pointer);

    expect(pointers).toEqual([...pointers].sort());
    expect(pointers).toContain('/credentials/ssh/privateKey');
    expect(pointers).toContain('/resources/machines/web-1/ip');
    // Public fields are never committed.
    expect(pointers).not.toContain('/schemaVersion');
    expect(pointers).not.toContain('/version');

    const ip = entries.find((e) => e.pointer === '/resources/machines/web-1/ip');
    expect(ip?.value).toBe('10.0.0.1');
  });

  it('toFullConfig writes the incremented version, not the pulled one', () => {
    const full = toFullConfig(sampleConfig(), { version: 5, sdkEpoch: 7 });
    expect(full.envelopeVersion).toBe(3);
    expect(full.version).toBe(5);
    expect(full.sdkEpoch).toBe(7);
    expect(full.machines).toEqual({ 'web-1': { ip: '10.0.0.1', user: 'deploy', port: 22 } });
    expect(full.ssh).toEqual({ privateKey: 'PRIVATE', publicKey: 'ssh-ed25519 AAA' });
  });

  it('push payload round-trips through selective decrypt', async () => {
    const { cek, sdkDerived } = await keys();
    const config = sampleConfig();

    const payload = await buildConfigPushPayload(config, {
      storeId: STORE_ID,
      version: config.version + 1,
      sdkEpoch: 3,
      sdkDerived,
      cek,
    });

    expect(payload.envelope.envelopeVersion).toBe(3);
    expect(payload.envelope.version).toBe(5);
    expect(payload.envelope.commitments.alg).toBe('HMAC-SHA256');
    expect(payload.envelope.commitments.fckSalt).not.toBe('');
    // Keyed by the blinded pointer (envelope v3): the server never reads the name.
    const blinding = await derivePointerBlindingKey(cek, config.id);
    expect(Object.keys(payload.envelope.commitments.fields)).toContain(
      await blindPointer(blinding, '/credentials/ssh/privateKey')
    );
    expect(Object.keys(payload.envelope.commitments.fields)).not.toContain(
      '/credentials/ssh/privateKey'
    );

    const decrypted = await decryptConfigPullPayload(payload, {
      cek,
      sdkDerived,
      binding: readerBinding(payload),
    });
    expect(decrypted.machines).toEqual(config.resources?.machines);
    expect(decrypted.ssh).toEqual(config.credentials?.ssh);
    expect(decrypted.version).toBe(5);
  });

  it('a tampered blob fails the integrity check', async () => {
    const { cek, sdkDerived } = await keys();
    const config = sampleConfig();
    const payload = await buildConfigPushPayload(config, {
      storeId: STORE_ID,
      version: 5,
      sdkEpoch: 3,
      sdkDerived,
      cek,
    });

    const tampered = { ...payload, encryptedBlob: `${payload.encryptedBlob.slice(0, -4)}AAAA` };
    await expect(
      decryptConfigPullPayload(tampered, { cek, sdkDerived, binding: readerBinding(tampered) })
    ).rejects.toThrow(/integrity check failed/i);
  });

  it('carries every account and defaults key but the login through a push and pull (D3; logout is per device)', async () => {
    const account = {
      userEmail: 'op@example.com',
      accountServer: 'https://eu.example.com',
      e2ePublicKey: 'SPKI',
      updateChannel: 'edge',
      releasesUrl: 'https://releases.example.com',
    };
    const defaults = {
      language: 'de',
      universalUser: 'deploy',
      datastoreSize: '90%',
      pruneGraceDays: 7,
    };
    const config = { ...sampleConfig(), account, defaults } as RdcConfig;
    const { cek, sdkDerived } = await keys();

    const payload = await buildConfigPushPayload(config, {
      storeId: STORE_ID,
      version: 5,
      sdkEpoch: 1,
      sdkDerived,
      cek,
    });
    const decrypted = await decryptConfigPullPayload(payload, {
      cek,
      sdkDerived,
      binding: readerBinding(payload),
    });

    // The login (server and its key) is per device (ruling 2026-09-25): it stays home.
    const { accountServer: _server, e2ePublicKey: _key, ...synced } = account;
    expect(decrypted.account).toEqual(synced);
    expect(decrypted.defaults).toEqual(defaults);
  });
});
