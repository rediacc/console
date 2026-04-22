/**
 * Regression test: `rdc config init --ssh-key <path>` must read the file
 * and inline its content under `credentials.ssh.privateKey`.
 *
 * The v1→v2 schema refactor briefly turned the SSH-key branch of the `init`
 * action into a no-op with a misleading comment ("content is read + inlined
 * at first mutation"). No such mutation existed, so every E2E test that
 * seeded SSH via this flag produced a config with `credentials.ssh` absent
 * and failed the first `rdc run` invocation with
 *   "Config <ctx> has no SSH key configured".
 *
 * This spec pins both halves of the fix:
 *   - `readSshKeyForInit` reads the file + optional .pub sibling
 *   - `mergeInitUpdates` threads the result into `credentials.ssh`
 */

import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { mergeInitUpdates, readSshKeyForInit } from '../config.js';
import type { RdcConfig } from '../../types/index.js';

const PRIVATE_KEY_BODY =
  '-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAA==\n-----END OPENSSH PRIVATE KEY-----';
const PUBLIC_KEY_BODY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICGJtmxsvlC7O6eD test@host';

function baseConfig(): RdcConfig {
  return {
    schemaVersion: 2,
    id: '00000000-0000-0000-0000-000000000001',
    version: 1,
    encryption: { mode: 'plaintext' },
  };
}

describe('readSshKeyForInit', () => {
  let tmpRoot: string;
  let privatePath: string;

  beforeEach(() => {
    tmpRoot = mkdtempSync(join(tmpdir(), 'rdc-init-ssh-'));
    privatePath = join(tmpRoot, 'id_ed25519');
  });

  afterEach(() => {
    rmSync(tmpRoot, { recursive: true, force: true });
  });

  it('reads the private key and an adjacent .pub public key', async () => {
    writeFileSync(privatePath, `${PRIVATE_KEY_BODY}\n`);
    writeFileSync(`${privatePath}.pub`, `${PUBLIC_KEY_BODY}\n`);

    const result = await readSshKeyForInit(privatePath);

    expect(result.privateKey).toBe(PRIVATE_KEY_BODY);
    expect(result.publicKey).toBe(PUBLIC_KEY_BODY);
  });

  it('returns privateKey only when no .pub sibling exists', async () => {
    writeFileSync(privatePath, PRIVATE_KEY_BODY);
    // no .pub file

    const result = await readSshKeyForInit(privatePath);

    expect(result.privateKey).toBe(PRIVATE_KEY_BODY);
    expect(result.publicKey).toBeUndefined();
  });

  it('throws a descriptive error when the private key file is missing', async () => {
    await expect(readSshKeyForInit(join(tmpRoot, 'does-not-exist'))).rejects.toThrow(
      /Failed to read SSH key/
    );
  });
});

describe('mergeInitUpdates', () => {
  it('inlines SSH content under credentials.ssh when --ssh-key was supplied', () => {
    const merged = mergeInitUpdates(baseConfig(), {
      sshContent: { privateKey: PRIVATE_KEY_BODY, publicKey: PUBLIC_KEY_BODY },
      mpUpdate: {},
      apiUrlUpdate: {},
    });

    expect(merged.credentials?.ssh?.privateKey).toBe(PRIVATE_KEY_BODY);
    expect(merged.credentials?.ssh?.publicKey).toBe(PUBLIC_KEY_BODY);
  });

  it('leaves credentials absent when --ssh-key and --master-password are both absent', () => {
    const merged = mergeInitUpdates(baseConfig(), {
      mpUpdate: {},
      apiUrlUpdate: {},
    });

    expect(merged.credentials).toBeUndefined();
  });

  it('merges SSH content alongside a master-password verifier', () => {
    const merged = mergeInitUpdates(baseConfig(), {
      sshContent: { privateKey: PRIVATE_KEY_BODY },
      mpUpdate: {
        credentials: { masterPasswordVerifier: 'hashed-mp' },
        encryption: { mode: 'master-password' },
      },
      apiUrlUpdate: {},
    });

    expect(merged.credentials?.ssh?.privateKey).toBe(PRIVATE_KEY_BODY);
    expect(merged.credentials?.masterPasswordVerifier).toBe('hashed-mp');
    expect(merged.encryption?.mode).toBe('master-password');
  });

  it('preserves account.accountServer from --server and apiUrl from --api-url', () => {
    const merged = mergeInitUpdates(baseConfig(), {
      accountUpdate: { accountServer: 'https://edge.example.com' },
      apiUrlUpdate: { account: { apiUrl: 'https://api.example.com' } },
      mpUpdate: {},
    });

    expect(merged.account?.accountServer).toBe('https://edge.example.com');
    expect(merged.account?.apiUrl).toBe('https://api.example.com');
  });

  it('persists renetPath to the top-level field', () => {
    const merged = mergeInitUpdates(baseConfig(), {
      renetPath: '/opt/bin/renet',
      mpUpdate: {},
      apiUrlUpdate: {},
    });

    expect(merged.renetPath).toBe('/opt/bin/renet');
  });

  it('does not clobber pre-existing credentials when no new SSH / MP is supplied', () => {
    const existing = {
      ...baseConfig(),
      credentials: {
        ssh: { privateKey: 'existing-key' },
        cfDnsApiToken: 'existing-cf-token',
      },
    };

    const merged = mergeInitUpdates(existing, { mpUpdate: {}, apiUrlUpdate: {} });

    expect(merged.credentials?.ssh?.privateKey).toBe('existing-key');
    expect(merged.credentials?.cfDnsApiToken).toBe('existing-cf-token');
  });
});
