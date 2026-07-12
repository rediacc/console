/**
 * Structural walker tests (registry, pointer traversal, commit paths).
 *
 * The SHA-256 fingerprint half of the old walker (redactClone, digestForPointer,
 * shortFingerprint) now lives in the CLI, and so do its tests:
 * packages/cli/src/schema/__tests__/fingerprint.test.ts.
 */

import { describe, expect, it } from 'vitest';
import { listSensitivityTemplates, SENSITIVITY_REGISTRY } from '../sensitivity.js';
import {
  buildPointer,
  canonicalJson,
  getByPointer,
  pathsToCommit,
  walkSensitive,
} from '../walker.js';

describe('walker', () => {
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

  it('registry is populated from sensitivity.ts declarations', () => {
    expect(SENSITIVITY_REGISTRY.size).toBeGreaterThan(30);
    expect(listSensitivityTemplates()).toContain('/credentials/ssh/privateKey');
    expect(listSensitivityTemplates()).toContain('/resources/machines/*/ip');
  });

  it('walkSensitive yields entries for every registered concrete path in the config', () => {
    const entries = Array.from(walkSensitive(sampleConfig));
    const pointers = entries.map((e) => e.pointer).sort();
    expect(pointers).toContain('/account/apiUrl');
    expect(pointers).toContain('/account/token');
    expect(pointers).toContain('/account/userEmail');
    expect(pointers).toContain('/credentials/ssh/privateKey');
    expect(pointers).toContain('/credentials/cfDnsApiToken');
    expect(pointers).toContain('/resources/machines/web-1/ip');
    expect(pointers).toContain('/resources/machines/web-1/user');
    expect(pointers).toContain('/resources/machines/web-2/ip');
    expect(pointers).toContain('/resources/storages/s3-prod/vaultContent');
    expect(pointers).toContain('/resources/repositories/app/tags/latest/credential');
    expect(pointers).toContain('/resources/repositories/app/tags/latest/repositoryGuid');
  });

  it('pathsToCommit excludes public fields and returns sorted pointers', () => {
    const paths = pathsToCommit(sampleConfig);
    expect(paths).toEqual([...paths].sort()); // sorted
    expect(paths).not.toContain('/schemaVersion');
    expect(paths).not.toContain('/version');
    expect(paths).toContain('/resources/machines/web-1/ip');
    expect(paths).toContain('/credentials/ssh/privateKey');
  });

  it('getByPointer handles RFC 6901 escapes and array indices', () => {
    const config = {
      ...sampleConfig,
      resources: {
        ...sampleConfig.resources,
        deletedRepositories: [{ name: 'old', credential: 'pass', deletedAt: '2026-01-01' }],
      },
    };
    expect(getByPointer(config, '/resources/deletedRepositories/0/credential')).toBe('pass');
    expect(getByPointer(config, '/resources/deletedRepositories/99')).toBeUndefined();
    // Special-character record key.
    const withSlash = { 'a/b': { x: 1 } };
    expect(getByPointer(withSlash, '/a~1b/x')).toBe(1);
  });

  it('canonicalJson is stable across key-insertion-order differences', () => {
    const a = canonicalJson({ x: 1, y: 2, z: 3 });
    const b = canonicalJson({ z: 3, y: 2, x: 1 });
    expect(a).toBe(b);
  });

  it('canonicalJson distinguishes null, undefined, and empty string', () => {
    expect(canonicalJson(null)).not.toBe(canonicalJson(undefined));
    expect(canonicalJson(null)).not.toBe(canonicalJson(''));
    expect(canonicalJson(undefined)).not.toBe(canonicalJson(''));
  });

  it('buildPointer escapes segments correctly', () => {
    expect(buildPointer([])).toBe('');
    expect(buildPointer(['a', 'b'])).toBe('/a/b');
    expect(buildPointer(['a/b', 'c~d'])).toBe('/a~1b/c~0d');
  });

  it('per-repo secret values walk as kind=secret; modes walk as kind=public', () => {
    const entries = Array.from(walkSensitive(sampleConfig));
    const stripeValue = entries.find(
      (e) => e.pointer === '/resources/repositories/app/tags/latest/secrets/STRIPE_KEY/value'
    );
    const stripeMode = entries.find(
      (e) => e.pointer === '/resources/repositories/app/tags/latest/secrets/STRIPE_KEY/mode'
    );
    expect(stripeValue?.meta.kind).toBe('secret');
    expect(stripeMode?.meta.kind).toBe('public');
  });

  it('pathsToCommit includes secret values, excludes modes (public)', () => {
    const paths = pathsToCommit(sampleConfig);
    expect(paths).toContain('/resources/repositories/app/tags/latest/secrets/STRIPE_KEY/value');
    expect(paths).not.toContain('/resources/repositories/app/tags/latest/secrets/STRIPE_KEY/mode');
  });
});
