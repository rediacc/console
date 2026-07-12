/**
 * SHA-256 fingerprint + redaction tests.
 *
 * These cover the host-side half of the old walker. The structural half moved to
 * packages/shared/src/config-schema/walker.ts and is tested there.
 */

import { describe, expect, it } from 'vitest';
import { digestForPointer, redactClone, shortFingerprint } from '../fingerprint.js';

describe('fingerprint', () => {
  const sampleConfig = {
    schemaVersion: 3 as const,
    id: '00000000-0000-0000-0000-000000000001',
    version: 1,
    account: {
      apiUrl: 'https://www.rediacc.com/api',
      token: 'secret-token',
      userEmail: 'alice@example.com',
    },
    credentials: {
      ssh: {
        privateKey: '-----BEGIN OPENSSH PRIVATE KEY-----\nABC\n-----END OPENSSH PRIVATE KEY-----',
        publicKey: 'ssh-ed25519 AAA...',
      },
      cfDnsApiToken: 'cf-token-xyz',
    },
    resources: {
      machines: {
        'web-1': { ip: '10.0.0.1', user: 'deploy', port: 22 },
        'web-2': { ip: '10.0.0.2', user: 'deploy', port: 22 },
      },
      storages: {
        's3-prod': {
          provider: 's3',
          vaultContent: { endpoint: 'https://s3.example.com', key: 'AKID' },
        },
      },
      repositories: {
        app: {
          grand: 'latest',
          tags: {
            latest: {
              repositoryGuid: '00000000-0000-0000-0000-aaaaaaaaaaaa',
              credential: 'luks-passphrase',
              secrets: {
                STRIPE_KEY: { mode: 'env' as const, value: 'sk_live_xxx' },
                DKIM_PRIVATE: { mode: 'file' as const, value: '-----BEGIN KEY-----\nABC\n' },
              },
            },
          },
        },
      },
    },
    encryption: { mode: 'plaintext' as const },
  };

  it('redactClone replaces sensitive values with stubs', () => {
    const redacted = redactClone(sampleConfig);
    expect(redacted.credentials.ssh.privateKey).toMatch(/^<redacted:credential>:[0-9a-f]{8}$/);
    expect(redacted.credentials.cfDnsApiToken).toMatch(/^<redacted:secret>:[0-9a-f]{8}$/);
    expect(redacted.account.token).toMatch(/^<redacted:secret>:[0-9a-f]{8}$/);
    expect(redacted.resources.machines['web-1'].ip).toMatch(/^<redacted:pii>:[0-9a-f]{8}$/);
    // Public fields remain as-is.
    expect(redacted.schemaVersion).toBe(3);
    expect(redacted.version).toBe(1);
    expect(redacted.resources.machines['web-1'].port).toBe(22);
  });

  it('redactClone preserves identical fingerprints for identical values', () => {
    const redacted = redactClone(sampleConfig);
    const web1Ip = redacted.resources.machines['web-1'].ip;
    const web2Ip = redacted.resources.machines['web-2'].ip;
    // Different IPs produce different fingerprints.
    expect(web1Ip).not.toBe(web2Ip);
    // Same fingerprint within the redaction stub when values match.
    const alt = redactClone({
      ...sampleConfig,
      resources: {
        ...sampleConfig.resources,
        machines: {
          'web-1': sampleConfig.resources.machines['web-1'],
          'web-clone': sampleConfig.resources.machines['web-1'],
        },
      },
    });
    const original = alt.resources.machines['web-1'].ip;
    const clone = alt.resources.machines['web-clone'].ip;
    expect(original).toBe(clone);
  });

  it('redactClone redacts secret values but leaves modes plaintext', () => {
    const redacted = redactClone(sampleConfig);
    const repo = redacted.resources.repositories.app.tags.latest;
    expect(repo.secrets.STRIPE_KEY.value).toMatch(/^<redacted:secret>:[0-9a-f]{8}$/);
    expect(repo.secrets.STRIPE_KEY.mode).toBe('env');
    expect(repo.secrets.DKIM_PRIVATE.value).toMatch(/^<redacted:secret>:[0-9a-f]{8}$/);
    expect(repo.secrets.DKIM_PRIVATE.mode).toBe('file');
  });

  it('digestForPointer returns stable SHA-256 hex for existing pointers', () => {
    const a = digestForPointer(sampleConfig, '/resources/machines/web-1/ip');
    const b = digestForPointer(sampleConfig, '/resources/machines/web-1/ip');
    expect(a).toBe(b);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
    const different = digestForPointer(sampleConfig, '/resources/machines/web-2/ip');
    expect(a).not.toBe(different);
    expect(digestForPointer(sampleConfig, '/does/not/exist')).toBeUndefined();
  });

  it('digestForPointer is stable for nested secret pointers', () => {
    const a = digestForPointer(
      sampleConfig,
      '/resources/repositories/app/tags/latest/secrets/STRIPE_KEY/value'
    );
    const b = digestForPointer(
      sampleConfig,
      '/resources/repositories/app/tags/latest/secrets/STRIPE_KEY/value'
    );
    expect(a).toBe(b);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
    const other = digestForPointer(
      sampleConfig,
      '/resources/repositories/app/tags/latest/secrets/DKIM_PRIVATE/value'
    );
    expect(a).not.toBe(other);
  });

  it('shortFingerprint distinguishes null from missing via canonicalJson', () => {
    const nullFp = shortFingerprint(null);
    const strFp = shortFingerprint('');
    const undFp = shortFingerprint(undefined);
    expect(nullFp).not.toBe(strFp);
    expect(nullFp).not.toBe(undFp);
    expect(strFp).not.toBe(undFp);
  });
});
