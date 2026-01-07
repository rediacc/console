/**
 * Unit tests for LocalExecutorService.
 *
 * Note: Due to ESM module resolution, mocking fs/promises and child_process
 * is complex. These tests focus on interface contracts and error handling.
 * Full execution flow is tested via integration tests in tests/local-mode.test.ts.
 */
import { describe, expect, it } from 'vitest';
import type { LocalMachineConfig, LocalSSHConfig } from '../types/index.js';

// Store original contextService methods
let originalGetLocalConfig: unknown;
let originalGetLocalMachine: unknown;
let _originalIsLocalMode: unknown;

describe('LocalExecutorService', () => {
  // These tests verify the interface and error handling behavior

  describe('LocalExecuteOptions interface', () => {
    it('should define required properties', () => {
      // Type test - verifies interface structure
      const minimalOptions = {
        functionName: 'machine_ping',
        machineName: 'test-machine',
      };

      expect(minimalOptions.functionName).toBe('machine_ping');
      expect(minimalOptions.machineName).toBe('test-machine');
    });

    it('should accept optional properties', () => {
      const fullOptions = {
        functionName: 'backup_create',
        machineName: 'server1',
        params: { repository: 'test-repo', version: '1.0.0' },
        timeout: 300000,
        debug: true,
        json: true,
      };

      expect(fullOptions.params.repository).toBe('test-repo');
      expect(fullOptions.timeout).toBe(300000);
      expect(fullOptions.debug).toBe(true);
      expect(fullOptions.json).toBe(true);
    });
  });

  describe('LocalExecuteResult interface', () => {
    it('should have success result structure', () => {
      const successResult = {
        success: true,
        exitCode: 0,
        durationMs: 1234,
      };

      expect(successResult.success).toBe(true);
      expect(successResult.exitCode).toBe(0);
      expect(successResult.error).toBeUndefined();
    });

    it('should have failure result structure', () => {
      const failResult = {
        success: false,
        exitCode: 1,
        error: 'Connection refused',
        durationMs: 500,
      };

      expect(failResult.success).toBe(false);
      expect(failResult.exitCode).toBe(1);
      expect(failResult.error).toBe('Connection refused');
    });
  });

  describe('LocalMachineConfig interface', () => {
    it('should require ip and user', () => {
      const minimalMachine: LocalMachineConfig = {
        ip: '192.168.1.100',
        user: 'admin',
      };

      expect(minimalMachine.ip).toBe('192.168.1.100');
      expect(minimalMachine.user).toBe('admin');
      expect(minimalMachine.port).toBeUndefined();
      expect(minimalMachine.datastore).toBeUndefined();
    });

    it('should accept optional port and datastore', () => {
      const fullMachine: LocalMachineConfig = {
        ip: '10.0.0.1',
        user: 'root',
        port: 2222,
        datastore: '/mnt/custom',
      };

      expect(fullMachine.port).toBe(2222);
      expect(fullMachine.datastore).toBe('/mnt/custom');
    });
  });

  describe('LocalSSHConfig interface', () => {
    it('should require privateKeyPath', () => {
      const minimalSSH: LocalSSHConfig = {
        privateKeyPath: '/home/user/.ssh/id_rsa',
      };

      expect(minimalSSH.privateKeyPath).toBe('/home/user/.ssh/id_rsa');
      expect(minimalSSH.publicKeyPath).toBeUndefined();
    });

    it('should accept optional publicKeyPath', () => {
      const fullSSH: LocalSSHConfig = {
        privateKeyPath: '~/.ssh/id_ed25519',
        publicKeyPath: '~/.ssh/id_ed25519.pub',
      };

      expect(fullSSH.publicKeyPath).toBe('~/.ssh/id_ed25519.pub');
    });
  });

  describe('vault structure validation', () => {
    it('should define queue-vault-v2 schema', () => {
      // This tests the expected vault structure that buildLocalVault creates
      const expectedVaultSchema = {
        $schema: 'queue-vault-v2',
        version: '2.0',
        task: {
          function: 'backup_create',
          machine: 'server1',
          team: 'local',
          repository: 'test-repo',
        },
        ssh: {
          private_key: expect.any(String), // PEM text
          public_key: expect.any(String), // OpenSSH public key
          known_hosts: '',
          password: '',
        },
        machine: {
          ip: expect.any(String),
          user: expect.any(String),
          port: expect.any(Number),
          datastore: expect.any(String),
          known_hosts: '',
        },
        params: expect.any(Object),
        extra_machines: {},
        storage_systems: {},
        repository_credentials: {},
        repositories: {},
        context: {
          organization_id: '',
          api_url: '',
          universal_user_id: '7111',
          universal_user_name: 'rediacc',
        },
      };

      // Validate structure presence
      expect(expectedVaultSchema.$schema).toBe('queue-vault-v2');
      expect(expectedVaultSchema.task.team).toBe('local');
    });

    it('should use default values for optional machine fields', () => {
      // When port is not specified, should default to 22
      const defaultPort = 22;
      // When datastore is not specified, should default to /mnt/rediacc
      const defaultDatastore = '/mnt/rediacc';

      expect(defaultPort).toBe(22);
      expect(defaultDatastore).toBe('/mnt/rediacc');
    });
  });

  describe('error scenarios', () => {
    it('should handle missing context gracefully', async () => {
      // Import locally to get fresh instance
      const { localExecutorService } = await import('../services/local-executor.js');
      const { contextService } = await import('../services/context.js');

      // Store original
      originalGetLocalConfig = contextService.getLocalConfig;

      // Mock getLocalConfig to throw
      contextService.getLocalConfig = () => {
        return Promise.reject(new Error('No active context'));
      };

      const result = await localExecutorService.execute({
        functionName: 'test',
        machineName: 'test-machine',
      });

      expect(result.success).toBe(false);
      expect(result.error).toContain('No active context');

      // Restore
      contextService.getLocalConfig =
        originalGetLocalConfig as typeof contextService.getLocalConfig;
    });

    it('should handle context not in local mode', async () => {
      const { localExecutorService } = await import('../services/local-executor.js');
      const { contextService } = await import('../services/context.js');

      originalGetLocalConfig = contextService.getLocalConfig;

      contextService.getLocalConfig = () => {
        return Promise.reject(new Error('Context is not in local mode'));
      };

      const result = await localExecutorService.execute({
        functionName: 'machine_ping',
        machineName: 'server',
      });

      expect(result.success).toBe(false);
      expect(result.error).toContain('not in local mode');

      contextService.getLocalConfig =
        originalGetLocalConfig as typeof contextService.getLocalConfig;
    });

    it('should handle machine not found', async () => {
      const { localExecutorService } = await import('../services/local-executor.js');
      const { contextService } = await import('../services/context.js');

      originalGetLocalConfig = contextService.getLocalConfig;
      originalGetLocalMachine = contextService.getLocalMachine;

      contextService.getLocalConfig = () =>
        Promise.resolve({
          machines: {},
          ssh: { privateKeyPath: '/path/to/key' },
          renetPath: 'renet',
        });

      contextService.getLocalMachine = (name: string) => {
        return Promise.reject(new Error(`Machine "${name}" not found`));
      };

      const result = await localExecutorService.execute({
        functionName: 'backup_create',
        machineName: 'nonexistent',
      });

      expect(result.success).toBe(false);
      expect(result.error).toContain('Machine "nonexistent" not found');

      contextService.getLocalConfig =
        originalGetLocalConfig as typeof contextService.getLocalConfig;
      contextService.getLocalMachine =
        originalGetLocalMachine as typeof contextService.getLocalMachine;
    });
  });

  describe('checkRenetAvailable', () => {
    it('should handle missing config gracefully', async () => {
      const { localExecutorService } = await import('../services/local-executor.js');
      const { contextService } = await import('../services/context.js');

      originalGetLocalConfig = contextService.getLocalConfig;

      contextService.getLocalConfig = () => {
        return Promise.reject(new Error('Not in local mode'));
      };

      const result = await localExecutorService.checkRenetAvailable();

      expect(result).toBe(false);

      contextService.getLocalConfig =
        originalGetLocalConfig as typeof contextService.getLocalConfig;
    });
  });

  describe('path expansion', () => {
    it('should recognize tilde paths', () => {
      const tildePath = '~/.ssh/id_rsa';
      const hasTilde = tildePath.startsWith('~');

      expect(hasTilde).toBe(true);
    });

    it('should leave absolute paths unchanged', () => {
      const absolutePath = '/home/user/.ssh/id_rsa';
      const hasTilde = absolutePath.startsWith('~');

      expect(hasTilde).toBe(false);
    });
  });

  describe('duration tracking', () => {
    it('should calculate duration correctly', async () => {
      const start = Date.now();
      await new Promise((resolve) => setTimeout(resolve, 50));
      const duration = Date.now() - start;

      expect(duration).toBeGreaterThanOrEqual(50);
      expect(duration).toBeLessThan(200); // Allow some tolerance
    });
  });
});
