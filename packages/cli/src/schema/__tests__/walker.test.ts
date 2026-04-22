/**
 * Walker + redaction tests for the v2 schema registry.
 */

import { describe, expect, it } from 'vitest';
import {
  buildPointer,
  canonicalJson,
  digestForPointer,
  getByPointer,
  pathsToCommit,
  redactClone,
  shortFingerprint,
  walkSensitive,
} from '../walker.js';
import { listSensitivityTemplates, SENSITIVITY_REGISTRY } from '../sensitivity.js';

describe('walker', () => {
  const sampleConfig = {
    schemaVersion: 2 as const,
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
        'app:latest': {
          repositoryGuid: '00000000-0000-0000-0000-aaaaaaaaaaaa',
          credential: 'luks-passphrase',
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
    expect(pointers).toContain('/resources/repositories/app:latest/credential');
    expect(pointers).toContain('/resources/repositories/app:latest/repositoryGuid');
  });

  it('redactClone replaces sensitive values with stubs', () => {
    const redacted = redactClone(sampleConfig);
    expect(redacted.credentials.ssh.privateKey).toMatch(/^<redacted:credential>:[0-9a-f]{8}$/);
    expect(redacted.credentials.cfDnsApiToken).toMatch(/^<redacted:secret>:[0-9a-f]{8}$/);
    expect(redacted.account.token).toMatch(/^<redacted:secret>:[0-9a-f]{8}$/);
    expect(redacted.resources.machines['web-1'].ip).toMatch(/^<redacted:pii>:[0-9a-f]{8}$/);
    // Public fields remain as-is.
    expect(redacted.schemaVersion).toBe(2);
    expect(redacted.version).toBe(1);
    expect(redacted.resources.machines['web-1'].port).toBe(22);
  });

  it('redactClone preserves identical fingerprints for identical values', () => {
    const redacted = redactClone(sampleConfig);
    const web1Ip = redacted.resources.machines['web-1'].ip;
    const web2Ip = redacted.resources.machines['web-2'].ip;
    // Different IPs → different fingerprints.
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

  it('pathsToCommit excludes public fields and returns sorted pointers', () => {
    const paths = pathsToCommit(sampleConfig);
    expect(paths).toEqual([...paths].sort()); // sorted
    expect(paths).not.toContain('/schemaVersion');
    expect(paths).not.toContain('/version');
    expect(paths).toContain('/resources/machines/web-1/ip');
    expect(paths).toContain('/credentials/ssh/privateKey');
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

  it('shortFingerprint distinguishes null from missing via canonicalJson', () => {
    const nullFp = shortFingerprint(null);
    const strFp = shortFingerprint('');
    const undFp = shortFingerprint(undefined);
    expect(nullFp).not.toBe(strFp);
    expect(nullFp).not.toBe(undFp);
    expect(strFp).not.toBe(undFp);
  });

  it('canonicalJson is stable across key-insertion-order differences', () => {
    const a = canonicalJson({ x: 1, y: 2, z: 3 });
    const b = canonicalJson({ z: 3, y: 2, x: 1 });
    expect(a).toBe(b);
  });

  it('buildPointer escapes segments correctly', () => {
    expect(buildPointer([])).toBe('');
    expect(buildPointer(['a', 'b'])).toBe('/a/b');
    expect(buildPointer(['a/b', 'c~d'])).toBe('/a~1b/c~0d');
  });
});
