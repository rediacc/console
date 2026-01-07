/**
 * Unit tests for ContextService local mode methods.
 *
 * Tests the local mode functionality: isLocalMode, getLocalConfig,
 * createLocal, addLocalMachine, removeLocalMachine, etc.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { configStorage } from '../adapters/storage.js';
import { contextService } from '../services/context.js';
import type { LocalMachineConfig, LocalSSHConfig, NamedContext } from '../types/index.js';

describe('ContextService Local Mode', () => {
  const timestamp = Date.now();
  const testLocalContext = `test-local-${timestamp}`;
  const testCloudContext = `test-cloud-${timestamp}`;

  // Sample machine configs
  const sampleMachine: LocalMachineConfig = {
    ip: '192.168.1.100',
    user: 'testuser',
    port: 22,
    datastore: '/mnt/rediacc',
  };

  const sampleSSHConfig: LocalSSHConfig = {
    privateKeyPath: '~/.ssh/id_rsa',
    publicKeyPath: '~/.ssh/id_rsa.pub',
  };

  beforeEach(async () => {
    // Create test contexts for testing
    // First create a cloud context
    await contextService.create({
      name: testCloudContext,
      apiUrl: 'https://test.example.com/api',
      mode: 'cloud',
    });

    // Create a local context with machines
    const localContext: NamedContext = {
      name: testLocalContext,
      mode: 'local',
      apiUrl: 'local://',
      ssh: sampleSSHConfig,
      machines: {
        server1: sampleMachine,
        server2: { ip: '192.168.1.101', user: 'admin' },
      },
      renetPath: '/usr/local/bin/renet',
    };
    await configStorage.update((config) => ({
      ...config,
      contexts: {
        ...config.contexts,
        [testLocalContext]: localContext,
      },
    }));
  });

  afterEach(async () => {
    // Cleanup test contexts
    try {
      await contextService.delete(testLocalContext);
    } catch {
      // Ignore if already deleted
    }
    try {
      await contextService.delete(testCloudContext);
    } catch {
      // Ignore if already deleted
    }
  });

  describe('isLocalMode', () => {
    it('should return true for local context', async () => {
      await contextService.use(testLocalContext);

      const isLocal = await contextService.isLocalMode();

      expect(isLocal).toBe(true);
    });

    it('should return false for cloud context', async () => {
      await contextService.use(testCloudContext);

      const isLocal = await contextService.isLocalMode();

      expect(isLocal).toBe(false);
    });

    it('should return false when no context is active', async () => {
      // Clear current context by updating storage directly
      await configStorage.update((config) => ({
        ...config,
        currentContext: '',
      }));

      const isLocal = await contextService.isLocalMode();

      expect(isLocal).toBe(false);
    });
  });

  describe('isLocalContext', () => {
    it('should return true for local context by name', async () => {
      const isLocal = await contextService.isLocalContext(testLocalContext);

      expect(isLocal).toBe(true);
    });

    it('should return false for cloud context by name', async () => {
      const isLocal = await contextService.isLocalContext(testCloudContext);

      expect(isLocal).toBe(false);
    });

    it('should return false for non-existent context', async () => {
      const isLocal = await contextService.isLocalContext('nonexistent-context');

      expect(isLocal).toBe(false);
    });
  });

  describe('getLocalConfig', () => {
    it('should return local config for active local context', async () => {
      await contextService.use(testLocalContext);

      const config = await contextService.getLocalConfig();

      expect(config.machines).toBeDefined();
      expect(config.ssh).toBeDefined();
      expect(config.renetPath).toBe('/usr/local/bin/renet');
    });

    it('should throw for cloud context', async () => {
      await contextService.use(testCloudContext);

      await expect(contextService.getLocalConfig()).rejects.toThrow('not in local mode');
    });

    it('should throw for context without machines', async () => {
      // Create context with no machines
      const emptyContext: NamedContext = {
        name: 'empty-local',
        mode: 'local',
        apiUrl: 'local://',
        ssh: sampleSSHConfig,
        machines: {},
      };
      await configStorage.update((config) => ({
        ...config,
        contexts: {
          ...config.contexts,
          'empty-local': emptyContext,
        },
        currentContext: 'empty-local',
      }));

      await expect(contextService.getLocalConfig()).rejects.toThrow('no machines configured');

      // Cleanup
      await contextService.delete('empty-local');
    });

    it('should throw for context without SSH key', async () => {
      // Create context with no SSH config
      const noSSHContext: NamedContext = {
        name: 'no-ssh-local',
        mode: 'local',
        apiUrl: 'local://',
        machines: { test: sampleMachine },
      };
      await configStorage.update((config) => ({
        ...config,
        contexts: {
          ...config.contexts,
          'no-ssh-local': noSSHContext,
        },
        currentContext: 'no-ssh-local',
      }));

      await expect(contextService.getLocalConfig()).rejects.toThrow('no SSH key configured');

      // Cleanup
      await contextService.delete('no-ssh-local');
    });

    it('should default renetPath to "renet" if not set', async () => {
      // Create context without renetPath
      const noPathContext: NamedContext = {
        name: 'no-path-local',
        mode: 'local',
        apiUrl: 'local://',
        ssh: sampleSSHConfig,
        machines: { test: sampleMachine },
      };
      await configStorage.update((config) => ({
        ...config,
        contexts: {
          ...config.contexts,
          'no-path-local': noPathContext,
        },
        currentContext: 'no-path-local',
      }));

      const config = await contextService.getLocalConfig();

      expect(config.renetPath).toBe('renet');

      // Cleanup
      await contextService.delete('no-path-local');
    });
  });

  describe('getLocalMachine', () => {
    beforeEach(async () => {
      await contextService.use(testLocalContext);
    });

    it('should return machine config by name', async () => {
      const machine = await contextService.getLocalMachine('server1');

      expect(machine.ip).toBe('192.168.1.100');
      expect(machine.user).toBe('testuser');
      expect(machine.port).toBe(22);
    });

    it('should throw for non-existent machine', async () => {
      await expect(contextService.getLocalMachine('nonexistent')).rejects.toThrow(
        'Machine "nonexistent" not found'
      );
    });

    it('should list available machines in error message', async () => {
      try {
        await contextService.getLocalMachine('nonexistent');
        expect.fail('Should have thrown');
      } catch (err) {
        expect((err as Error).message).toContain('Available:');
      }
    });
  });

  describe('createLocal', () => {
    const newLocalContext = `new-local-${timestamp}`;

    afterEach(async () => {
      try {
        await contextService.delete(newLocalContext);
      } catch {
        // Ignore
      }
    });

    it('should create a new local context', async () => {
      await contextService.createLocal(newLocalContext, '~/.ssh/id_ed25519');

      const context = await contextService.get(newLocalContext);

      expect(context).toBeDefined();
      expect(context?.mode).toBe('local');
      expect(context?.ssh?.privateKeyPath).toBe('~/.ssh/id_ed25519');
      expect(context?.ssh?.publicKeyPath).toBe('~/.ssh/id_ed25519.pub');
      expect(context?.machines).toEqual({});
    });

    it('should accept custom renet path', async () => {
      await contextService.createLocal(newLocalContext, '~/.ssh/key', {
        renetPath: '/opt/bin/renet',
      });

      const context = await contextService.get(newLocalContext);

      expect(context?.renetPath).toBe('/opt/bin/renet');
    });

    it('should throw if context name already exists', async () => {
      await expect(contextService.createLocal(testLocalContext, '~/.ssh/key')).rejects.toThrow(
        'already exists'
      );
    });
  });

  describe('addLocalMachine', () => {
    beforeEach(async () => {
      await contextService.use(testLocalContext);
    });

    it('should add a new machine', async () => {
      const newMachine: LocalMachineConfig = {
        ip: '192.168.1.200',
        user: 'deploy',
        port: 2222,
        datastore: '/data',
      };

      await contextService.addLocalMachine('new-server', newMachine);

      const machine = await contextService.getLocalMachine('new-server');
      expect(machine.ip).toBe('192.168.1.200');
      expect(machine.user).toBe('deploy');
      expect(machine.port).toBe(2222);
    });

    it('should throw for cloud context', async () => {
      await contextService.use(testCloudContext);

      await expect(contextService.addLocalMachine('server', sampleMachine)).rejects.toThrow(
        'not in local mode'
      );
    });

    it('should preserve existing machines', async () => {
      await contextService.addLocalMachine('new-server', {
        ip: '10.0.0.1',
        user: 'root',
      });

      // Original machines should still exist
      const server1 = await contextService.getLocalMachine('server1');
      expect(server1.ip).toBe('192.168.1.100');
    });
  });

  describe('removeLocalMachine', () => {
    beforeEach(async () => {
      await contextService.use(testLocalContext);
    });

    it('should remove a machine', async () => {
      await contextService.removeLocalMachine('server1');

      await expect(contextService.getLocalMachine('server1')).rejects.toThrow(
        'Machine "server1" not found'
      );
    });

    it('should throw for non-existent machine', async () => {
      await expect(contextService.removeLocalMachine('nonexistent')).rejects.toThrow('not found');
    });

    it('should preserve other machines', async () => {
      await contextService.removeLocalMachine('server1');

      // server2 should still exist
      const server2 = await contextService.getLocalMachine('server2');
      expect(server2).toBeDefined();
    });

    it('should throw for cloud context', async () => {
      await contextService.use(testCloudContext);

      await expect(contextService.removeLocalMachine('server1')).rejects.toThrow(
        'not in local mode'
      );
    });
  });

  describe('listLocalMachines', () => {
    beforeEach(async () => {
      await contextService.use(testLocalContext);
    });

    it('should list all machines', async () => {
      const machines = await contextService.listLocalMachines();

      expect(machines).toHaveLength(2);
      expect(machines.map((m) => m.name)).toContain('server1');
      expect(machines.map((m) => m.name)).toContain('server2');
    });

    it('should include machine config in each entry', async () => {
      const machines = await contextService.listLocalMachines();

      const server1 = machines.find((m) => m.name === 'server1');
      expect(server1?.config.ip).toBe('192.168.1.100');
      expect(server1?.config.user).toBe('testuser');
    });

    it('should throw for cloud context', async () => {
      await contextService.use(testCloudContext);

      await expect(contextService.listLocalMachines()).rejects.toThrow('not in local mode');
    });
  });

  describe('setLocalSSH', () => {
    beforeEach(async () => {
      await contextService.use(testLocalContext);
    });

    it('should update SSH configuration', async () => {
      const newSSH: LocalSSHConfig = {
        privateKeyPath: '/new/path/id_ed25519',
        publicKeyPath: '/new/path/id_ed25519.pub',
      };

      await contextService.setLocalSSH(newSSH);

      const config = await contextService.getLocalConfig();
      expect(config.ssh.privateKeyPath).toBe('/new/path/id_ed25519');
      expect(config.ssh.publicKeyPath).toBe('/new/path/id_ed25519.pub');
    });

    it('should throw for cloud context', async () => {
      await contextService.use(testCloudContext);

      await expect(contextService.setLocalSSH({ privateKeyPath: '/path' })).rejects.toThrow(
        'not in local mode'
      );
    });
  });

  describe('setRenetPath', () => {
    beforeEach(async () => {
      await contextService.use(testLocalContext);
    });

    it('should update renet path', async () => {
      await contextService.setRenetPath('/opt/custom/renet');

      const config = await contextService.getLocalConfig();
      expect(config.renetPath).toBe('/opt/custom/renet');
    });

    it('should throw for cloud context', async () => {
      await contextService.use(testCloudContext);

      await expect(contextService.setRenetPath('/path')).rejects.toThrow('not in local mode');
    });
  });

  describe('context list display', () => {
    it('should show mode field in list', async () => {
      const contexts = await contextService.list();

      const localCtx = contexts.find((c) => c.name === testLocalContext);
      const cloudCtx = contexts.find((c) => c.name === testCloudContext);

      expect(localCtx?.mode).toBe('local');
      // Cloud mode is explicitly set
      expect(cloudCtx?.mode).toBe('cloud');
    });

    it('should include machines count for local context', async () => {
      const contexts = await contextService.list();
      const localCtx = contexts.find((c) => c.name === testLocalContext);

      expect(localCtx?.machines).toBeDefined();
      expect(Object.keys(localCtx?.machines ?? {}).length).toBe(2);
    });
  });

  describe('edge cases', () => {
    it('should handle undefined mode as cloud', async () => {
      // Create context without explicit mode
      const undefinedModeContext: NamedContext = {
        name: 'undefined-mode',
        apiUrl: 'https://example.com/api',
        // mode is undefined
      };
      await configStorage.update((config) => ({
        ...config,
        contexts: {
          ...config.contexts,
          'undefined-mode': undefinedModeContext,
        },
        currentContext: 'undefined-mode',
      }));

      const isLocal = await contextService.isLocalMode();
      expect(isLocal).toBe(false);

      // Cleanup
      await contextService.delete('undefined-mode');
    });

    it('should handle empty machines object', async () => {
      const emptyMachines: NamedContext = {
        name: 'empty-machines',
        mode: 'local',
        apiUrl: 'local://',
        ssh: sampleSSHConfig,
        machines: {},
      };
      await configStorage.update((config) => ({
        ...config,
        contexts: {
          ...config.contexts,
          'empty-machines': emptyMachines,
        },
        currentContext: 'empty-machines',
      }));

      await expect(contextService.getLocalConfig()).rejects.toThrow('no machines');

      // Cleanup
      await contextService.delete('empty-machines');
    });

    it('should handle machine with minimal config', async () => {
      await contextService.use(testLocalContext);

      // server2 has only ip and user
      const machine = await contextService.getLocalMachine('server2');

      expect(machine.ip).toBe('192.168.1.101');
      expect(machine.user).toBe('admin');
      expect(machine.port).toBeUndefined();
      expect(machine.datastore).toBeUndefined();
    });
  });
});
