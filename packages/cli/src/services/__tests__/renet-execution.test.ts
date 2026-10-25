import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import { buildLocalVault } from '../renet/renet-execution.js';

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
      expect(vault.machine.datastore).toBe(WK_DATASTORE_PATH);
    });
  });

  describe('storage_systems', () => {
    it('is not part of the vault: the storage section was removed', () => {
      const vault = JSON.parse(buildLocalVault(baseOpts()));
      expect(vault).not.toHaveProperty('storage_systems');
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
      opts.params = { repository: 'myrepo', guid: 'guid-123' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories['guid-123']).toBeDefined();
      expect(vault.repositories['guid-123'].guid).toBe('guid-123');
      expect(vault.repositories['guid-123'].name).toBe('myrepo');
      expect(vault.task.repository).toBe('guid-123');
      expect(vault.task.repo_name).toBe('myrepo');
    });

    it('throws instead of using the name as the GUID', () => {
      const opts = baseOpts();
      opts.params = { repository: 'myrepo' };
      expect(() => buildLocalVault(opts)).toThrow(/no GUID/);
    });

    it('accepts a ref that is itself a GUID', () => {
      const guid = '11111111-2222-3333-4444-555555555555';
      const opts = baseOpts();
      opts.params = { repository: guid };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.task.repository).toBe(guid);
      expect(vault.repositories[guid].guid).toBe(guid);
    });

    it('resolves a ref given as GUID to the configured friendly name', () => {
      const opts = {
        ...baseOpts(),
        repositoryConfigs: { myrepo: { guid: 'guid-123', name: 'myrepo' } },
      };
      opts.params = { repository: 'guid-123' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.task.repository).toBe('guid-123');
      expect(vault.task.repo_name).toBe('myrepo');
    });

    it('resolves a bare family name to the grand, not a fork', () => {
      const opts = {
        ...baseOpts(),
        repositoryConfigs: {
          'myrepo:fix': { guid: 'guid-fork', name: 'myrepo:fix', grandGuid: 'guid-grand' },
          'myrepo:latest': { guid: 'guid-grand', name: 'myrepo:latest', grandGuid: 'guid-grand' },
        },
      };
      opts.params = { repository: 'myrepo' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.task.repository).toBe('guid-grand');
      expect(vault.task.repo_name).toBe('myrepo:latest');
    });

    it('should include network_id when provided as param', () => {
      const opts = baseOpts();
      opts.params = { repository: 'myrepo', guid: 'guid-123', network_id: 2816 };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories['guid-123'].network_id).toBe(2816);
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
      expect(vault.repositories['guid-123'].network_id).toBe(2880);
      expect(vault.repositories['guid-123'].guid).toBe('guid-123');
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
      expect(vault.repositories['guid-123'].network_id).toBe(2944);
    });

    it('should not include network_id when 0 or missing', () => {
      const opts = baseOpts();
      opts.params = { repository: 'myrepo', guid: 'guid-123' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories['guid-123'].network_id).toBeUndefined();
    });

    it('should not include network_id when repositoryConfigs.networkId is 0', () => {
      const opts = {
        ...baseOpts(),
        repositoryConfigs: {
          myrepo: { guid: 'guid-123', name: 'myrepo', networkId: 0 },
        },
      };
      opts.params = { repository: 'myrepo', guid: 'guid-123' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories['guid-123'].network_id).toBeUndefined();
    });

    // ── secret_files (file-mode), single-repo path ──────────────────
    //
    // This is the contract that makes `repo migrate` and `repo push --up` automatically carry secrets across machines. Both invoke `repo up` on
    // the target machine through this exact code path; the repo entry in
    // local config travels with all its secrets baked in.

    it('emits secret_files in single-repo entry when repositoryConfigs has them', () => {
      const opts = {
        ...baseOpts(),
        repositoryConfigs: {
          myrepo: {
            guid: 'guid-123',
            name: 'myrepo',
            networkId: 2816,
            secretFiles: [
              { name: 'STRIPE_KEY', value: 'sk_live_x' },
              { name: 'DKIM', value: '----PEM----' },
            ],
          },
        },
      };
      opts.params = { repository: 'myrepo' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories['guid-123'].secret_files).toEqual([
        { name: 'STRIPE_KEY', value: 'sk_live_x' },
        { name: 'DKIM', value: '----PEM----' },
      ]);
    });

    it('omits secret_files when repo has none (cleaner JSON)', () => {
      const opts = {
        ...baseOpts(),
        repositoryConfigs: {
          myrepo: { guid: 'guid-123', name: 'myrepo', networkId: 2816 },
        },
      };
      opts.params = { repository: 'myrepo' };
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories['guid-123'].secret_files).toBeUndefined();
    });

    it('emits secret_files per-repo in multi-repo (up-all / migrate-all) mode', () => {
      const opts = {
        ...baseOpts(),
        repositoryConfigs: {
          a: {
            guid: 'guid-a',
            name: 'a',
            networkId: 1024,
            secretFiles: [{ name: 'A_KEY', value: 'a-val' }],
          },
          b: { guid: 'guid-b', name: 'b', networkId: 1025 },
        },
      };
      // No params.repository → multi-repo branch in buildRepositories
      const vault = JSON.parse(buildLocalVault(opts));
      expect(vault.repositories.a.secret_files).toEqual([{ name: 'A_KEY', value: 'a-val' }]);
      expect(vault.repositories.b.secret_files).toBeUndefined();
    });
  });
});
