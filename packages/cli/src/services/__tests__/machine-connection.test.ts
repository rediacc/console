import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MachineConfig } from '../../types/index.js';

const { MockSFTPClient, mockGetLocalConfig, mockGetLocalMachine, mockReadSSHKey } = vi.hoisted(
  () => {
    interface MockSFTPConfig {
      host: string;
      port?: number;
      username: string;
      privateKey: string;
      knownHosts?: string;
    }
    class MockSFTPClient {
      static instances: MockSFTPClient[] = [];
      static nextConnectImpl: (() => Promise<void>) | null = null;
      readonly config: MockSFTPConfig;
      connected = false;
      connectCount = 0;
      closeCount = 0;
      connectImpl: () => Promise<void>;
      constructor(config: MockSFTPConfig) {
        this.config = config;
        this.connectImpl = MockSFTPClient.nextConnectImpl ?? (() => Promise.resolve());
        MockSFTPClient.instances.push(this);
      }
      async connect(): Promise<void> {
        this.connectCount += 1;
        await this.connectImpl();
        this.connected = true;
      }
      isConnected(): boolean {
        return this.connected;
      }
      close(): void {
        this.closeCount += 1;
        this.connected = false;
      }
    }
    return {
      MockSFTPClient,
      mockGetLocalConfig: vi.fn(),
      mockGetLocalMachine: vi.fn(),
      mockReadSSHKey: vi.fn(),
    };
  }
);

vi.mock('@rediacc/shared-desktop/sftp', () => ({ SFTPClient: MockSFTPClient }));

vi.mock('../config-resources.js', () => ({
  configService: {
    getLocalConfig: mockGetLocalConfig,
    getLocalMachine: mockGetLocalMachine,
  },
}));

vi.mock('../renet-execution.js', () => ({ readSSHKey: mockReadSSHKey }));

const { machineConnections } = await import('../machine-connection.js');

// The manager is a module singleton, so every test uses a unique machine to
// get an isolated pool entry.
let nextHostId = 0;
function makeMachine(overrides: Partial<MachineConfig> = {}): MachineConfig {
  nextHostId += 1;
  return { ip: `host-${nextHostId}.test`, user: 'root', port: 22, ...overrides };
}

function instancesFor(host: string) {
  return MockSFTPClient.instances.filter((i) => i.config.host === host);
}

describe('machineConnections', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockSFTPClient.instances.length = 0;
    MockSFTPClient.nextConnectImpl = null;
  });

  it('shares one connection across leases and closes at zero refcount', async () => {
    const machine = makeMachine();
    const a = await machineConnections.acquireFor(machine, 'KEY');
    const b = await machineConnections.acquireFor(machine, 'KEY');

    expect(instancesFor(machine.ip)).toHaveLength(1);
    expect(a.sftp).toBe(b.sftp);
    const client = a.sftp as unknown as InstanceType<typeof MockSFTPClient>;
    expect(client.connectCount).toBe(1);

    a.release();
    expect(client.closeCount).toBe(0);
    b.release();
    expect(client.closeCount).toBe(1);

    // A new acquire after close gets a fresh client, never a reused one.
    const c = await machineConnections.acquireFor(machine, 'KEY');
    expect(c.sftp).not.toBe(client);
    c.release();
  });

  it('release is idempotent per lease', async () => {
    const machine = makeMachine();
    const a = await machineConnections.acquireFor(machine, 'KEY');
    const b = await machineConnections.acquireFor(machine, 'KEY');
    const client = a.sftp as unknown as InstanceType<typeof MockSFTPClient>;

    a.release();
    a.release();
    expect(client.closeCount).toBe(0);
    b.release();
    expect(client.closeCount).toBe(1);
  });

  it('dedupes concurrent acquires onto a single connect', async () => {
    const machine = makeMachine();
    let resolveConnect!: () => void;
    const gate = new Promise<void>((resolve) => {
      resolveConnect = resolve;
    });
    MockSFTPClient.nextConnectImpl = () => gate;

    const p1 = machineConnections.acquireFor(machine, 'KEY');
    const p2 = machineConnections.acquireFor(machine, 'KEY');
    resolveConnect();
    const [a, b] = await Promise.all([p1, p2]);

    const instances = instancesFor(machine.ip);
    expect(instances).toHaveLength(1);
    expect(instances[0].connectCount).toBe(1);
    expect(a.sftp).toBe(b.sftp);
    a.release();
    b.release();
  });

  it('early release during a shared connect does not close the late waiter (refcount reserved before await)', async () => {
    const machine = makeMachine();
    let resolveConnect!: () => void;
    const gate = new Promise<void>((resolve) => {
      resolveConnect = resolve;
    });
    MockSFTPClient.nextConnectImpl = () => gate;

    const p1 = machineConnections.acquireFor(machine, 'KEY');
    const p2 = machineConnections.acquireFor(machine, 'KEY');
    resolveConnect();
    const a = await p1;
    // First waiter acquires and releases before the second waiter resumes.
    a.release();
    const b = await p2;

    const instances = instancesFor(machine.ip);
    expect(instances).toHaveLength(1);
    // The shared session must still be open for the late waiter.
    expect(instances[0].closeCount).toBe(0);
    expect(b.sftp.isConnected()).toBe(true);
    b.release();
    expect(instances[0].closeCount).toBe(1);
  });

  it('evicts a dead session and reconnects with a fresh client', async () => {
    const machine = makeMachine();
    const a = await machineConnections.acquireFor(machine, 'KEY');
    const first = a.sftp as unknown as InstanceType<typeof MockSFTPClient>;
    first.connected = false; // simulate dropped session

    const b = await machineConnections.acquireFor(machine, 'KEY');
    const second = b.sftp as unknown as InstanceType<typeof MockSFTPClient>;
    expect(second).not.toBe(first);
    expect(second.isConnected()).toBe(true);
    expect(first.closeCount).toBe(1);
    // Existing leases see the replacement client transparently.
    expect(a.sftp).toBe(b.sftp);

    a.release();
    b.release();
    expect(second.closeCount).toBe(1);
  });

  it('ensure() reconnects a dead session and returns the live client', async () => {
    const machine = makeMachine();
    const lease = await machineConnections.acquireFor(machine, 'KEY');
    const first = lease.sftp as unknown as InstanceType<typeof MockSFTPClient>;
    first.connected = false;

    const live = await lease.ensure();
    expect(live).not.toBe(first);
    expect(live.isConnected()).toBe(true);
    expect(lease.sftp).toBe(live);
    lease.release();
  });

  it('ensure() rejects after the lease was released', async () => {
    const machine = makeMachine();
    const lease = await machineConnections.acquireFor(machine, 'KEY');
    lease.release();
    await expect(lease.ensure()).rejects.toThrow('already released');
  });

  it('evicts the entry when the initial connect fails, allowing a retry', async () => {
    const machine = makeMachine();
    MockSFTPClient.nextConnectImpl = () => Promise.reject(new Error('connect boom'));
    await expect(machineConnections.acquireFor(machine, 'KEY')).rejects.toThrow('connect boom');

    MockSFTPClient.nextConnectImpl = null;
    const lease = await machineConnections.acquireFor(machine, 'KEY');
    expect(instancesFor(machine.ip)).toHaveLength(2);
    expect(lease.sftp.isConnected()).toBe(true);
    lease.release();
  });

  it('keys connections by host:port:user', async () => {
    const machine = makeMachine();
    const otherUser = { ...machine, user: 'deploy' };
    const a = await machineConnections.acquireFor(machine, 'KEY');
    const b = await machineConnections.acquireFor(otherUser, 'KEY');
    expect(a.sftp).not.toBe(b.sftp);
    expect(instancesFor(machine.ip)).toHaveLength(2);
    a.release();
    b.release();
  });

  it('passes knownHosts and connection parameters to the client', async () => {
    const machine = makeMachine({ port: 2222, knownHosts: 'host ssh-ed25519 AAAA' });
    const lease = await machineConnections.acquireFor(machine, 'PRIV_KEY');
    const client = lease.sftp as unknown as InstanceType<typeof MockSFTPClient>;
    expect(client.config).toMatchObject({
      host: machine.ip,
      port: 2222,
      username: 'root',
      privateKey: 'PRIV_KEY',
      knownHosts: 'host ssh-ed25519 AAAA',
    });
    lease.release();
  });

  it('acquire(name) resolves the machine and SSH key from config', async () => {
    const machine = makeMachine();
    mockGetLocalConfig.mockResolvedValue({ ssh: { privateKeyPath: '/tmp/team-key' } });
    mockGetLocalMachine.mockResolvedValue(machine);
    mockReadSSHKey.mockResolvedValue('FILE_KEY');

    const lease = await machineConnections.acquire('prod-1');
    expect(mockGetLocalMachine).toHaveBeenCalledWith('prod-1');
    expect(mockReadSSHKey).toHaveBeenCalledWith('/tmp/team-key');
    expect(lease.machine).toBe(machine);
    expect(lease.sshPrivateKey).toBe('FILE_KEY');
    const client = lease.sftp as unknown as InstanceType<typeof MockSFTPClient>;
    expect(client.config.privateKey).toBe('FILE_KEY');
    lease.release();
  });

  it('acquire(name) prefers the inline config key over the key file', async () => {
    const machine = makeMachine();
    mockGetLocalConfig.mockResolvedValue({
      sshPrivateKey: 'INLINE_KEY',
      ssh: { privateKeyPath: '/tmp/team-key' },
    });
    mockGetLocalMachine.mockResolvedValue(machine);

    const lease = await machineConnections.acquire('prod-1');
    expect(mockReadSSHKey).not.toHaveBeenCalled();
    expect(lease.sshPrivateKey).toBe('INLINE_KEY');
    lease.release();
  });
});
