import { describe, it, expect } from 'vitest';
import { createVaultEncryptor, isEncrypted } from '@rediacc/shared/encryption';
import { nodeCryptoProvider } from '../src/adapters/crypto.js';

describe('Vault Encryption Integration', () => {
  const encryptor = createVaultEncryptor(nodeCryptoProvider);
  const masterPassword = 'test-master-password-secure!';

  describe('vault field encryption', () => {
    it('should encrypt vault fields and leave others untouched', async () => {
      const data = {
        name: 'test-machine',
        machineVault: JSON.stringify({ ip: '192.168.1.1', user: 'admin' }),
        status: 'active',
      };

      const encrypted = await encryptor.encrypt(data, masterPassword);

      // Non-vault fields should be unchanged
      expect(encrypted.name).toBe('test-machine');
      expect(encrypted.status).toBe('active');

      // Vault field should be encrypted (different from original)
      expect(typeof encrypted.machineVault).toBe('string');
      expect(encrypted.machineVault).not.toBe(data.machineVault);
      expect(encrypted.machineVault).not.toContain('192.168.1.1');
      expect(isEncrypted(encrypted.machineVault)).toBe(true);
    });

    it('should decrypt vault fields back to original', async () => {
      const original = {
        teamVault: JSON.stringify({ SSH_PRIVATE_KEY: 'secret-key-value' }),
        teamName: 'Default',
      };

      const encrypted = await encryptor.encrypt(original, masterPassword);
      const decrypted = await encryptor.decrypt(encrypted, masterPassword);

      expect(decrypted.teamName).toBe(original.teamName);
      expect(decrypted.teamVault).toBe(original.teamVault);
    });

    it('should handle multiple vault fields', async () => {
      const original = {
        machineVault: JSON.stringify({ ip: '10.0.0.1' }),
        teamVault: JSON.stringify({ key: 'team-secret' }),
        queueVault: JSON.stringify({ params: { a: 1 } }),
        name: 'multi-vault-test',
      };

      const encrypted = await encryptor.encrypt(original, masterPassword);

      expect(encrypted.name).toBe('multi-vault-test');
      expect(isEncrypted(encrypted.machineVault)).toBe(true);
      expect(isEncrypted(encrypted.teamVault)).toBe(true);
      expect(isEncrypted(encrypted.queueVault)).toBe(true);

      const decrypted = await encryptor.decrypt(encrypted, masterPassword);
      expect(decrypted).toEqual(original);
    });

    it('should handle nested vault fields in objects', async () => {
      const original = {
        machine: {
          machineVault: JSON.stringify({ ip: '192.168.1.100' }),
          name: 'nested-machine',
        },
      };

      const encrypted = await encryptor.encrypt(original, masterPassword);

      expect(encrypted.machine.name).toBe('nested-machine');
      expect(isEncrypted(encrypted.machine.machineVault)).toBe(true);

      const decrypted = await encryptor.decrypt(encrypted, masterPassword);
      expect(decrypted).toEqual(original);
    });

    it('should handle vault fields in arrays', async () => {
      const original = {
        items: [
          { queueVault: JSON.stringify({ param: 'value1' }), id: 1 },
          { queueVault: JSON.stringify({ param: 'value2' }), id: 2 },
        ],
      };

      const encrypted = await encryptor.encrypt(original, masterPassword);

      expect(encrypted.items[0].id).toBe(1);
      expect(encrypted.items[1].id).toBe(2);
      expect(isEncrypted(encrypted.items[0].queueVault)).toBe(true);
      expect(isEncrypted(encrypted.items[1].queueVault)).toBe(true);

      const decrypted = await encryptor.decrypt(encrypted, masterPassword);
      expect(decrypted).toEqual(original);
    });
  });

  describe('hasVaultFields detection', () => {
    it('should detect vault fields in simple objects', () => {
      expect(encryptor.hasVaultFields({ machineVault: 'data' })).toBe(true);
      expect(encryptor.hasVaultFields({ name: 'test' })).toBe(false);
    });

    it('should detect nested vault fields', () => {
      expect(encryptor.hasVaultFields({ data: { machineVault: 'nested' } })).toBe(true);
    });

    it('should detect vault fields in arrays', () => {
      expect(encryptor.hasVaultFields([{ queueVault: 'item' }])).toBe(true);
    });
  });

  describe('edge cases', () => {
    it('should handle null input', async () => {
      const result = await encryptor.encrypt(null, masterPassword);
      expect(result).toBe(null);
    });

    it('should handle undefined input', async () => {
      const result = await encryptor.encrypt(undefined, masterPassword);
      expect(result).toBe(undefined);
    });

    it('should handle empty password (skip encryption)', async () => {
      const data = { machineVault: 'secret' };
      const result = await encryptor.encrypt(data, '');

      expect(result).toEqual(data);
    });

    it('should handle empty vault field values', async () => {
      const data = { machineVault: '', name: 'test' };
      const encrypted = await encryptor.encrypt(data, masterPassword);

      // Empty vault values should not be encrypted
      expect(encrypted.machineVault).toBe('');
    });

    it('should handle re-encryption of already encrypted data', async () => {
      const original = { machineVault: 'secret-data' };

      const encrypted1 = await encryptor.encrypt(original, masterPassword);

      // Verify first encryption worked
      expect(isEncrypted(encrypted1.machineVault)).toBe(true);

      // Decrypt should recover original
      const decrypted = await encryptor.decrypt(encrypted1, masterPassword);
      expect(decrypted.machineVault).toBe('secret-data');
    });
  });

  describe('wrong password handling', () => {
    it('should fail silently with wrong password (return encrypted value)', async () => {
      const original = { machineVault: 'secret-data' };
      const encrypted = await encryptor.encrypt(original, masterPassword);

      // With wrong password, decrypt should fail gracefully and return the encrypted value
      const result = await encryptor.decrypt(encrypted, 'wrong-password');

      // The value should still be the encrypted string (not decrypted)
      expect(result.machineVault).toBe(encrypted.machineVault);
    });
  });

  describe('realistic vault data', () => {
    it('should handle machine vault with connection details', async () => {
      const machineData = {
        machineName: 'production-server',
        machineVault: JSON.stringify({
          ip: '10.0.0.50',
          port: 22,
          username: 'deploy',
          privateKey: '-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----',
        }),
        status: 'ONLINE',
      };

      const encrypted = await encryptor.encrypt(machineData, masterPassword);
      expect(encrypted.machineName).toBe('production-server');
      expect(isEncrypted(encrypted.machineVault)).toBe(true);

      const decrypted = await encryptor.decrypt(encrypted, masterPassword);
      expect(decrypted).toEqual(machineData);
    });

    it('should handle team vault with SSH keys', async () => {
      const teamData = {
        teamName: 'Development',
        teamVault: JSON.stringify({
          SSH_PRIVATE_KEY: '-----BEGIN OPENSSH PRIVATE KEY-----\nbase64data...\n-----END OPENSSH PRIVATE KEY-----',
          SSH_PUBLIC_KEY: 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ...',
          DEPLOY_TOKEN: 'ghp_xxxxxxxxxxxxxxxxxxxx',
        }),
      };

      const encrypted = await encryptor.encrypt(teamData, masterPassword);
      const decrypted = await encryptor.decrypt(encrypted, masterPassword);
      expect(decrypted).toEqual(teamData);
    });

    it('should handle queue vault with task parameters', async () => {
      const queueData = {
        taskId: 'abc-123',
        queueVault: JSON.stringify({
          function: 'deploy',
          repository: 'main-app',
          version: '1.2.3',
          environment: {
            DATABASE_URL: 'postgres://user:pass@host:5432/db',
            API_KEY: 'sk-xxxxxxxxxxxx',
          },
        }),
        status: 'PENDING',
      };

      const encrypted = await encryptor.encrypt(queueData, masterPassword);
      const decrypted = await encryptor.decrypt(encrypted, masterPassword);
      expect(decrypted).toEqual(queueData);
    });
  });
});
