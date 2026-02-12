import { describe, expect, it } from 'vitest';
import { buildLocalVault } from '../renet-execution.js';

/**
 * Creates a minimal set of options for buildLocalVault.
 * Override specific fields in individual tests.
 */
function baseOpts() {
  const machine: {
    ip: string;
    user: string;
    port?: number;
    datastore?: string;
  } = { ip: '10.0.0.1', user: 'root' };
  const params: Record<string, unknown> = {};
  return {
    functionName: 'machine_ping',
    machineName: 'test-machine',
    machine,
    sshPrivateKey: '---PRIVATE-KEY---',
    sshPublicKey: '---PUBLIC-KEY---',
    sshKnownHosts: '10.0.0.1 ssh-ed25519 AAAA...',
    params,
  };
}

// ============================================
// buildLocalVault Tests
// ============================================

describe('buildLocalVault', () => {
  describe('base structure', () => {
    it('should return valid JSON string', () => {
      const result = buildLocalVault(baseOpts());
      expect(() => JSON.parse(result)).not.toThrow();
    });

    it('should contain schema and version fields', () => {
      const vault = JSON.parse(buildLocalVault(baseOpts()));
      expect(vault.$schema).toBe('queue-vault-v2');
      expect(vault.version).toBe('2.0');
    });

    it('should populate task section with function, machine, and team', () => {
      const vault = JSON.parse(buildLocalVault(baseOpts()));
      expect(vault.task.function).toBe('machine_ping');
      expect(vault.task.machine).toBe('test-machine');
      expect(vault.task.team).toBe('local');
    });

    it('should populate ssh section with keys and known_hosts', () => {
      const vault = JSON.parse(buildLocalVault(baseOpts()));
      expect(vault.ssh.private_key).toBe('---PRIVATE-KEY---');
      expect(vault.ssh.public_key).toBe('---PUBLIC-KEY---');
      expect(vault.ssh.known_hosts).toBe('10.0.0.1 ssh-ed25519 AAAA...');
      expect(vault.ssh.password).toBe('');
    });
  });

  describe('machine section', () => {
    it('should populate ip, user, and port from machine config', () => {
      const opts = baseOpts();
      opts.machine.port = 2222;
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.machine.ip).toBe('10.0.0.1');
      expect(vault.machine.user).toBe('root');
      expect(vault.machine.port).toBe(2222);
    });

    it('should use default port 22 when not specified', () => {
      const vault = JSON.parse(buildLocalVault(baseOpts()));
      expect(vault.machine.port).toBe(22);
    });

    it('should use default datastore path when not specified', () => {
      const vault = JSON.parse(buildLocalVault(baseOpts()));
      expect(vault.machine.datastore).toBe('/mnt/rediacc');
    });
  });

  describe('storage_systems', () => {
    it('should be empty object when no storages provided', () => {
      const vault = JSON.parse(buildLocalVault(baseOpts()));
      expect(vault.storage_systems).toEqual({});
    });

    it('should build entry with backend from provider field', () => {
      const opts = {
        ...baseOpts(),
        storages: {
          'my-s3': {
            vaultContent: {
              provider: 's3',
              access_key_id: 'AKIA123',
              secret_access_key: 'secret',
            },
          },
        },
      };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.storage_systems['my-s3'].backend).toBe('s3');
    });

    it('should extract bucket and region to top-level fields', () => {
      const opts = {
        ...baseOpts(),
        storages: {
          'my-s3': {
            vaultContent: {
              provider: 's3',
              bucket: 'my-bucket',
              region: 'us-east-1',
              access_key_id: 'AKIA123',
            },
          },
        },
      };
      const vault = JSON.parse(buildLocalVault(opts));
      const storage = vault.storage_systems['my-s3'];
      expect(storage.bucket).toBe('my-bucket');
      expect(storage.region).toBe('us-east-1');
      // bucket and region should NOT be in parameters
      expect(storage.parameters?.bucket).toBeUndefined();
      expect(storage.parameters?.region).toBeUndefined();
    });

    it('should put remaining fields into parameters sub-object', () => {
      const opts = {
        ...baseOpts(),
        storages: {
          'my-s3': {
            vaultContent: {
              provider: 's3',
              bucket: 'my-bucket',
              access_key_id: 'AKIA123',
              secret_access_key: 'secret',
              endpoint: 'https://s3.example.com',
            },
          },
        },
      };
      const vault = JSON.parse(buildLocalVault(opts));
      const params = vault.storage_systems['my-s3'].parameters;
      expect(params.access_key_id).toBe('AKIA123');
      expect(params.secret_access_key).toBe('secret');
      expect(params.endpoint).toBe('https://s3.example.com');
      // provider should NOT be in parameters
      expect(params.provider).toBeUndefined();
    });

    it('should handle multiple storages', () => {
      const opts = {
        ...baseOpts(),
        storages: {
          'my-s3': {
            vaultContent: { provider: 's3', bucket: 'bucket1' },
          },
          'my-drive': {
            vaultContent: { provider: 'drive', token: { access_token: 'xyz' } },
          },
        },
      };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(Object.keys(vault.storage_systems)).toHaveLength(2);
      expect(vault.storage_systems['my-s3'].backend).toBe('s3');
      expect(vault.storage_systems['my-drive'].backend).toBe('drive');
    });

    it('should skip storages with empty provider', () => {
      const opts = {
        ...baseOpts(),
        storages: {
          'bad-storage': {
            vaultContent: { provider: '', bucket: 'test' },
          },
          'good-storage': {
            vaultContent: { provider: 's3', bucket: 'test' },
          },
        },
      };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.storage_systems['bad-storage']).toBeUndefined();
      expect(vault.storage_systems['good-storage']).toBeDefined();
    });

    it('should extract folder field to top level', () => {
      const opts = {
        ...baseOpts(),
        storages: {
          'my-drive': {
            vaultContent: {
              provider: 'drive',
              folder: 'backups/2026',
              token: { access_token: 'xyz' },
            },
          },
        },
      };
      const vault = JSON.parse(buildLocalVault(opts));
      const storage = vault.storage_systems['my-drive'];
      expect(storage.folder).toBe('backups/2026');
      expect(storage.parameters?.folder).toBeUndefined();
    });
  });

  describe('extra_machines', () => {
    it('should inject SSH credentials into each extra machine entry', () => {
      const opts = {
        ...baseOpts(),
        extraMachines: {
          worker1: { ip: '10.0.0.2', user: 'admin' },
          worker2: { ip: '10.0.0.3', port: 2222, user: 'deploy' },
        },
      };
      const vault = JSON.parse(buildLocalVault(opts));
      const w1 = vault.extra_machines.worker1;
      expect(w1.ip).toBe('10.0.0.2');
      expect(w1.user).toBe('admin');
      expect(w1.port).toBe(22); // default
      expect(w1.ssh.private_key).toBe('---PRIVATE-KEY---');
      expect(w1.ssh.public_key).toBe('---PUBLIC-KEY---');

      const w2 = vault.extra_machines.worker2;
      expect(w2.port).toBe(2222);
    });
  });

  describe('repositories', () => {
    it('should build repositories section when repository param is set', () => {
      const opts = baseOpts();
      opts.params = { repository: 'myrepo' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories.myrepo).toBeDefined();
      expect(vault.repositories.myrepo.guid).toBe('local-myrepo');
      expect(vault.repositories.myrepo.name).toBe('myrepo');
      expect(vault.task.repository).toBe('myrepo');
    });

    it('should include network_id when provided as param', () => {
      const opts = baseOpts();
      opts.params = { repository: 'myrepo', network_id: 2816 };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories.myrepo.network_id).toBe(2816);
    });

    it('should include network_id from repositoryConfigs', () => {
      const opts = {
        ...baseOpts(),
        repositoryConfigs: {
          myrepo: { guid: 'guid-123', name: 'myrepo', networkId: 2880 },
        },
      };
      opts.params = { repository: 'myrepo' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories.myrepo.network_id).toBe(2880);
      expect(vault.repositories.myrepo.guid).toBe('guid-123');
    });

    it('should prefer repositoryConfigs.networkId over params.network_id', () => {
      const opts = {
        ...baseOpts(),
        repositoryConfigs: {
          myrepo: { guid: 'guid-123', name: 'myrepo', networkId: 2944 },
        },
      };
      opts.params = { repository: 'myrepo', network_id: 2816 };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories.myrepo.network_id).toBe(2944);
    });

    it('should not include network_id when 0 or missing', () => {
      const opts = baseOpts();
      opts.params = { repository: 'myrepo' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories.myrepo.network_id).toBeUndefined();
    });

    it('should not include network_id when repositoryConfigs.networkId is 0', () => {
      const opts = {
        ...baseOpts(),
        repositoryConfigs: {
          myrepo: { guid: 'guid-123', name: 'myrepo', networkId: 0 },
        },
      };
      opts.params = { repository: 'myrepo' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories.myrepo.network_id).toBeUndefined();
    });
  });
});
