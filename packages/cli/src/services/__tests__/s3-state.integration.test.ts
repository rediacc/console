/**
 * S3StateService integration tests against a real S3-compatible server (RustFS).
 *
 * Tests the single state.json approach with both plaintext and encrypted modes.
 * Uses unified types (MachineConfig, StorageConfig, RepositoryConfig).
 *
 * Requires S3_TEST_ENDPOINT, S3_TEST_ACCESS_KEY, S3_TEST_SECRET_KEY, S3_TEST_BUCKET.
 */

import { describe, it, expect, afterAll } from 'vitest';
import { S3StateService } from '../s3-state.js';
import { createTestS3Client, cleanupS3Prefix } from './s3-test-config.js';
import type { S3StateData } from '../../types/index.js';

const MASTER_PASSWORD = 'test-master-password-s3-state';

// ===========================================================================
// Plaintext mode
// ===========================================================================

describe('S3StateService (plaintext)', () => {
  const client = createTestS3Client();

  afterAll(async () => {
    await cleanupS3Prefix(client, '');
  });

  it('should create empty state.json if not exists', async () => {
    const service = await S3StateService.load(client, null);
    expect(service.getMachines()).toEqual({});
    expect(service.getStorages()).toEqual({});
    expect(service.getRepositories()).toEqual({});

    // Verify it was persisted
    const raw = await client.getJson<S3StateData>('state.json');
    expect(raw).not.toBeNull();
    expect(raw!.version).toBe(1);
    expect(raw!.encrypted).toBe(false);
  });

  it('should read existing state.json', async () => {
    // Write state directly using unified MachineConfig
    await client.putJson('state.json', {
      version: 1,
      encrypted: false,
      machines: { web1: { ip: '10.0.0.1', user: 'ubuntu', port: 22 } },
      storages: {},
      repositories: {},
    });

    const service = await S3StateService.load(client, null);
    const machines = service.getMachines();
    expect(machines.web1).toBeDefined();
    expect(machines.web1.ip).toBe('10.0.0.1');
    expect(machines.web1.user).toBe('ubuntu');
  });

  it('should round-trip machines', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, null);

    await service.setMachines({
      kvm1: { ip: '1.2.3.4', user: 'root', port: 22, datastore: '/mnt/data' },
      kvm2: { ip: '5.6.7.8', user: 'admin' },
    });

    const service2 = await S3StateService.load(client, null);
    const machines = service2.getMachines();
    expect(Object.keys(machines)).toHaveLength(2);
    expect(machines.kvm1.ip).toBe('1.2.3.4');
    expect(machines.kvm1.datastore).toBe('/mnt/data');
    expect(machines.kvm2.user).toBe('admin');
  });

  it('should round-trip machines with knownHosts', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, null);

    await service.setMachines({
      web1: {
        ip: '10.0.0.1',
        user: 'ubuntu',
        port: 22,
        knownHosts: '10.0.0.1 ssh-ed25519 AAAA...',
      },
    });

    const service2 = await S3StateService.load(client, null);
    expect(service2.getMachines().web1.knownHosts).toBe('10.0.0.1 ssh-ed25519 AAAA...');
  });

  it('should round-trip storages with unified StorageConfig', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, null);

    await service.setStorages({
      's3-do': { provider: 's3', vaultContent: { provider: 's3', bucket: 'test' } },
      google: { provider: 'drive', vaultContent: { provider: 'drive', scope: 'drive' } },
    });

    const service2 = await S3StateService.load(client, null);
    const storages = service2.getStorages();
    expect(Object.keys(storages)).toHaveLength(2);
    expect(storages['s3-do'].provider).toBe('s3');
    expect(storages['s3-do'].vaultContent).toEqual({ provider: 's3', bucket: 'test' });
    expect(storages.google.provider).toBe('drive');
  });

  it('should round-trip repositories with unified RepositoryConfig', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, null);

    await service.setRepositories({
      erpnext: {
        repositoryGuid: 'aaaa-bbbb',
        tag: 'latest',
        credential: 'secret123',
        networkId: 2816,
      },
      gitlab: {
        repositoryGuid: 'cccc-dddd',
      },
    });

    const service2 = await S3StateService.load(client, null);
    const repos = service2.getRepositories();
    expect(Object.keys(repos)).toHaveLength(2);
    expect(repos.erpnext.repositoryGuid).toBe('aaaa-bbbb');
    expect(repos.erpnext.tag).toBe('latest');
    expect(repos.erpnext.credential).toBe('secret123');
    expect(repos.erpnext.networkId).toBe(2816);
    expect(repos.gitlab.repositoryGuid).toBe('cccc-dddd');
  });

  it('should round-trip SSH content', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, null);

    await service.setSSH({
      privateKey: '-----BEGIN OPENSSH PRIVATE KEY-----\nfakekey\n-----END OPENSSH PRIVATE KEY-----',
      publicKey: 'ssh-ed25519 AAAA... user@host',
    });

    const service2 = await S3StateService.load(client, null);
    const ssh = service2.getSSH();
    expect(ssh).not.toBeNull();
    expect(ssh!.privateKey).toContain('BEGIN OPENSSH PRIVATE KEY');
    expect(ssh!.publicKey).toBe('ssh-ed25519 AAAA... user@host');
  });

  it('should return null SSH when not set', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, null);
    expect(service.getSSH()).toBeNull();
  });

  it('should store plain objects in state.json (not encrypted strings)', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, null);
    await service.setMachines({ web: { ip: '10.0.0.1', user: 'root' } });

    const raw = await client.getJson<S3StateData>('state.json');
    expect(raw!.encrypted).toBe(false);
    expect(typeof raw!.machines).toBe('object');
    expect((raw!.machines as Record<string, unknown>).web).toBeDefined();
  });
});

// ===========================================================================
// Encrypted mode
// ===========================================================================

describe('S3StateService (encrypted)', () => {
  const client = createTestS3Client();

  afterAll(async () => {
    await cleanupS3Prefix(client, '');
  });

  it('should create encrypted state.json on first load', async () => {
    const service = await S3StateService.load(client, MASTER_PASSWORD);
    expect(service.getMachines()).toEqual({});

    const raw = await client.getJson<S3StateData>('state.json');
    expect(raw!.encrypted).toBe(true);
    expect(typeof raw!.machines).toBe('string');
    expect(typeof raw!.storages).toBe('string');
    expect(typeof raw!.repositories).toBe('string');
  });

  it('should encrypt and decrypt machines round-trip', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, MASTER_PASSWORD);

    await service.setMachines({
      prod: { ip: '192.168.1.1', user: 'deploy', port: 2222, knownHosts: 'host keys...' },
    });

    const raw = await client.getJson<S3StateData>('state.json');
    expect(typeof raw!.machines).toBe('string');

    const service2 = await S3StateService.load(client, MASTER_PASSWORD);
    const machines = service2.getMachines();
    expect(machines.prod.ip).toBe('192.168.1.1');
    expect(machines.prod.user).toBe('deploy');
    expect(machines.prod.port).toBe(2222);
    expect(machines.prod.knownHosts).toBe('host keys...');
  });

  it('should encrypt and decrypt storages round-trip', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, MASTER_PASSWORD);

    await service.setStorages({
      backblaze: { provider: 'b2', vaultContent: { key: 'secret123' } },
    });

    const service2 = await S3StateService.load(client, MASTER_PASSWORD);
    expect(service2.getStorages().backblaze.provider).toBe('b2');
    expect(service2.getStorages().backblaze.vaultContent).toEqual({ key: 'secret123' });
  });

  it('should encrypt and decrypt repositories round-trip', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, MASTER_PASSWORD);

    await service.setRepositories({
      myapp: { repositoryGuid: 'uuid-123', tag: 'v2', credential: 'pass', networkId: 2880 },
    });

    const service2 = await S3StateService.load(client, MASTER_PASSWORD);
    const repos = service2.getRepositories();
    expect(repos.myapp.repositoryGuid).toBe('uuid-123');
    expect(repos.myapp.tag).toBe('v2');
    expect(repos.myapp.credential).toBe('pass');
    expect(repos.myapp.networkId).toBe(2880);
  });

  it('should encrypt and decrypt SSH content round-trip', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, MASTER_PASSWORD);

    await service.setSSH({
      privateKey:
        '-----BEGIN OPENSSH PRIVATE KEY-----\nencrypted-key\n-----END OPENSSH PRIVATE KEY-----',
      publicKey: 'ssh-ed25519 BBBB...',
    });

    const raw = await client.getJson<S3StateData>('state.json');
    expect(typeof raw!.ssh).toBe('string');

    const service2 = await S3StateService.load(client, MASTER_PASSWORD);
    const ssh = service2.getSSH();
    expect(ssh).not.toBeNull();
    expect(ssh!.privateKey).toContain('encrypted-key');
    expect(ssh!.publicKey).toBe('ssh-ed25519 BBBB...');
  });

  it('should fail to load with wrong password', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, MASTER_PASSWORD);
    await service.setMachines({ x: { ip: '1.1.1.1', user: 'root' } });

    await expect(S3StateService.load(client, 'wrong-password')).rejects.toThrow();
  });

  it('should throw when encrypted state loaded without password', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, MASTER_PASSWORD);
    await service.setMachines({ y: { ip: '2.2.2.2', user: 'root' } });

    await expect(S3StateService.load(client, null)).rejects.toThrow(/master password/i);
  });

  it('should produce different ciphertext for same plaintext (random IV)', async () => {
    await client.deleteObject('state.json');
    const service = await S3StateService.load(client, MASTER_PASSWORD);
    await service.setMachines({ a: { ip: '1.1.1.1', user: 'root' } });
    const raw1 = await client.getRaw('state.json');

    await service.setMachines({ a: { ip: '1.1.1.1', user: 'root' } });
    const raw2 = await client.getRaw('state.json');

    expect(raw1).not.toBe(raw2);
  });
});
