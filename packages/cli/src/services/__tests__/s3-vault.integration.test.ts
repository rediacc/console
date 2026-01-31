/**
 * S3VaultService integration tests against a real S3-compatible server (RustFS).
 *
 * Requires S3_TEST_ENDPOINT, S3_TEST_ACCESS_KEY, S3_TEST_SECRET_KEY, S3_TEST_BUCKET.
 */

import { describe, it, expect, afterAll } from 'vitest';
import { S3VaultService } from '../s3-vault.js';
import { createTestS3Client, cleanupS3Prefix } from './s3-test-config.js';

const MASTER_PASSWORD = 'test-master-password-s3-integration';

const client = createTestS3Client();
const vault = new S3VaultService(client, MASTER_PASSWORD);

afterAll(async () => {
  await cleanupS3Prefix(client, '');
});

describe('S3VaultService (real S3)', () => {
  describe('writeVault / readVault', () => {
    it('should encrypt, store, retrieve, and decrypt round-trip', async () => {
      const data = { secret: 'top-secret', code: 42 };
      await vault.writeVault('vaults/test-roundtrip.json.enc', data);

      const result = await vault.readVault<typeof data>('vaults/test-roundtrip.json.enc');
      expect(result).toEqual(data);
    });

    it('should return null for non-existent vault', async () => {
      const result = await vault.readVault('vaults/does-not-exist-' + Date.now() + '.json.enc');
      expect(result).toBeNull();
    });

    it('should handle complex nested objects', async () => {
      const data = {
        users: [
          { name: 'Alice', roles: ['admin', 'user'] },
          { name: 'Bob', roles: ['user'] },
        ],
        config: {
          nested: { deeply: { value: true } },
          array: [1, 2, 3],
        },
      };
      await vault.writeVault('vaults/test-complex.json.enc', data);
      const result = await vault.readVault<typeof data>('vaults/test-complex.json.enc');
      expect(result).toEqual(data);
    });

    it('should fail to decrypt with wrong password', async () => {
      const data = { secret: 'cannot-read-this' };
      await vault.writeVault('vaults/test-wrong-pw.json.enc', data);

      const wrongVault = new S3VaultService(client, 'wrong-password');
      await expect(
        wrongVault.readVault('vaults/test-wrong-pw.json.enc')
      ).rejects.toThrow();
    });
  });

  describe('team vault', () => {
    it('should write and read team vault', async () => {
      const data = { SSH_PRIVATE_KEY: 'key-content', SSH_PUBLIC_KEY: 'pub-content' };
      await vault.setTeamVault(data);

      const result = await vault.getTeamVault();
      expect(result).toEqual(data);
    });

    it('should overwrite existing team vault', async () => {
      await vault.setTeamVault({ v: 1 });
      await vault.setTeamVault({ v: 2, extra: 'field' });

      const result = await vault.getTeamVault();
      expect(result).toEqual({ v: 2, extra: 'field' });
    });
  });

  describe('machine vault', () => {
    it('should write and read per-machine vault', async () => {
      const data = { DB_PASSWORD: 'secret123' };
      await vault.setMachineVault('worker-1', data);

      const result = await vault.getMachineVault('worker-1');
      expect(result).toEqual(data);
    });

    it('should handle multiple machines independently', async () => {
      await vault.setMachineVault('machine-a', { role: 'primary' });
      await vault.setMachineVault('machine-b', { role: 'replica' });

      const a = await vault.getMachineVault('machine-a');
      const b = await vault.getMachineVault('machine-b');
      expect(a).toEqual({ role: 'primary' });
      expect(b).toEqual({ role: 'replica' });
    });
  });

  describe('organization vault', () => {
    it('should write and read organization vault', async () => {
      const data = { orgName: 'TestCorp', plan: 'enterprise' };
      await vault.setOrganizationVault(data);

      const result = await vault.getOrganizationVault();
      expect(result).toEqual(data);
    });
  });

  describe('encryption integrity', () => {
    it('should produce different ciphertext for same plaintext (random IV)', async () => {
      const data = { identical: true };

      await vault.writeVault('vaults/test-iv-1.json.enc', data);
      await vault.writeVault('vaults/test-iv-2.json.enc', data);

      // Read the raw encrypted content to compare ciphertext
      const raw1 = await client.getRaw('vaults/test-iv-1.json.enc');
      const raw2 = await client.getRaw('vaults/test-iv-2.json.enc');

      expect(raw1).not.toBeNull();
      expect(raw2).not.toBeNull();
      expect(raw1).not.toBe(raw2);
    });

    it('should handle vault with SSH key material (realistic payload)', async () => {
      const sshKeyData = {
        SSH_PRIVATE_KEY:
          '-----BEGIN OPENSSH PRIVATE KEY-----\n' +
          'b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n' +
          'QyNTUxOQAAACBhbWRzZnNkZmFzZGZhc2RmYXNkZmFzZGZhc2RmYXNkZgAAAJj/////\n' +
          '-----END OPENSSH PRIVATE KEY-----',
        SSH_PUBLIC_KEY: 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGFtZHNmc2RmYXNkZmFz test@host',
      };

      await vault.setTeamVault(sshKeyData);
      const result = await vault.getTeamVault();
      expect(result).toEqual(sshKeyData);
    });
  });
});

describe('S3VaultService (plaintext mode - no master password)', () => {
  const ptClient = createTestS3Client();
  const ptVault = new S3VaultService(ptClient, null);

  afterAll(async () => {
    await cleanupS3Prefix(ptClient, '');
  });

  it('should write vault as plain JSON when no password', async () => {
    const data = { secret: 'plain-value', count: 7 };
    await ptVault.writeVault('vaults/pt-test.json.enc', data);

    // Raw content should be valid JSON, not encrypted ciphertext
    const raw = await ptClient.getRaw('vaults/pt-test.json.enc');
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed).toEqual(data);
  });

  it('should read vault from plain JSON when no password', async () => {
    const data = { key: 'readable', nested: { arr: [1, 2] } };
    await ptVault.writeVault('vaults/pt-read.json.enc', data);

    const result = await ptVault.readVault<typeof data>('vaults/pt-read.json.enc');
    expect(result).toEqual(data);
  });

  it('should return null for non-existent vault in plaintext mode', async () => {
    const result = await ptVault.readVault('vaults/pt-missing-' + Date.now() + '.json.enc');
    expect(result).toBeNull();
  });

  it('should round-trip team vault in plaintext mode', async () => {
    const data = { SSH_PRIVATE_KEY: 'plaintext-key', SSH_PUBLIC_KEY: 'pub' };
    await ptVault.setTeamVault(data);

    const result = await ptVault.getTeamVault();
    expect(result).toEqual(data);
  });
});
