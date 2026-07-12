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
import { generateCek, generateSdkMaster, sdkDerive } from '../../config-crypto/index.js';
import {
  buildCommitEntries,
  buildConfigPushPayload,
  decryptConfigPullPayload,
  toFullConfig,
} from '../payload.js';
import type { RdcConfig } from '../schemas.js';

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
  } as RdcConfig;
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
    expect(full.envelopeVersion).toBe(2);
    expect(full.version).toBe(5);
    expect(full.sdkEpoch).toBe(7);
    expect(full.machines).toEqual({ 'web-1': { ip: '10.0.0.1', user: 'deploy', port: 22 } });
    expect(full.ssh).toEqual({ privateKey: 'PRIVATE', publicKey: 'ssh-ed25519 AAA' });
  });

  it('push payload round-trips through selective decrypt', async () => {
    const { cek, sdkDerived } = await keys();
    const config = sampleConfig();

    const payload = await buildConfigPushPayload(config, {
      version: config.version + 1,
      sdkEpoch: 3,
      sdkDerived,
      cek,
    });

    expect(payload.envelope.envelopeVersion).toBe(2);
    expect(payload.envelope.version).toBe(5);
    expect(payload.envelope.commitments.alg).toBe('HMAC-SHA256');
    expect(payload.envelope.commitments.fckSalt).not.toBe('');
    expect(Object.keys(payload.envelope.commitments.fields)).toContain(
      '/credentials/ssh/privateKey'
    );

    const decrypted = await decryptConfigPullPayload(payload, { cek, sdkDerived });
    expect(decrypted.machines).toEqual(config.resources?.machines);
    expect(decrypted.ssh).toEqual(config.credentials?.ssh);
    expect(decrypted.version).toBe(5);
  });

  it('a tampered blob fails the integrity check', async () => {
    const { cek, sdkDerived } = await keys();
    const config = sampleConfig();
    const payload = await buildConfigPushPayload(config, {
      version: 5,
      sdkEpoch: 3,
      sdkDerived,
      cek,
    });

    const tampered = { ...payload, encryptedBlob: payload.encryptedBlob.slice(0, -4) + 'AAAA' };
    await expect(decryptConfigPullPayload(tampered, { cek, sdkDerived })).rejects.toThrow(
      /integrity check failed/i
    );
  });
});
