/**
 * MachineConnectionManager - refcounted SSH/SFTP connection pool.
 *
 * This is the only module in the CLI allowed to construct an SFTPClient; the
 * `custom/no-direct-sftp-client` ESLint rule enforces that. Everything else takes
 * a lease:
 *
 *   const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
 *   try { ... lease.sftp ... } finally { lease.release(); }
 *
 * Connections are keyed by host:port:user plus a fingerprint of the credentials
 * they were opened with, and are shared across concurrent callers via leases. The
 * first acquire opens the connection, subsequent acquires reuse it (concurrent
 * connects are deduped on a shared promise), and the last release() closes it.
 * Dead sessions are evicted and replaced with a fresh SFTPClient instance, because
 * an ended ssh2 client is never reused.
 */

import { createHash } from 'node:crypto';
import { DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient, type SFTPClientConfig } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { configService } from '../config/config-resources.js';
import { readSSHKey } from './ssh-key.js';

/**
 * A refcounted handle on a shared SSH/SFTP connection, acquired from raw connect
 * options. Internal: config-based callers go through withPooledSftp, which owns
 * the lease for them. Machine-based callers get a MachineConnectionLease.
 */
interface SftpConnectionLease {
  /** Live SFTP client (replaced transparently after a dead-session evict). */
  readonly sftp: SFTPClient;
  /** Re-check liveness, reconnecting if the session died. Returns the live client. */
  ensure(): Promise<SFTPClient>;
  /** Drop this lease's reference. The last release closes the connection. */
  release(): void;
}

/** A lease acquired for a configured machine, carrying the resolved machine and key. */
export interface MachineConnectionLease {
  /** Live SFTP client (replaced transparently after a dead-session evict). */
  readonly sftp: SFTPClient;
  /** Re-check liveness, reconnecting if the session died. Returns the live client. */
  ensure(): Promise<SFTPClient>;
  /** Drop this lease's reference. The last release closes the connection. */
  release(): void;
  readonly machine: MachineConfig;
  readonly sshPrivateKey: string;
}

interface ConnectionEntry {
  key: string;
  clientConfig: SFTPClientConfig;
  sftp: SFTPClient;
  refCount: number;
  /** In-flight connect/reconnect, shared so concurrent acquires dedupe. */
  connectPromise: Promise<void> | null;
}

/**
 * Sessions to the same host:port:user opened with different credentials are not
 * interchangeable: a per-repo key (which the remote authorizes with a `command=`
 * sandbox) must never be served out of a session opened with the team key, and a
 * session opened without host-key pinning must not satisfy a caller that asked
 * for it. Fold the credentials into the pool key so those are separate entries.
 */
function credentialFingerprint(config: SFTPClientConfig): string {
  // JSON encoding keeps the three fields unambiguously separated.
  const material = JSON.stringify([
    config.privateKey,
    config.passphrase ?? '',
    config.knownHosts ?? '',
  ]);
  return createHash('sha256').update(material).digest('hex').slice(0, 16);
}

function connectionKey(config: SFTPClientConfig): string {
  const port = config.port ?? DEFAULTS.SSH.PORT;
  return `${config.host}:${port}:${config.username}:${credentialFingerprint(config)}`;
}

/** The canonical SFTP connect options for a configured machine. */
export function sftpConfigForMachine(
  machine: MachineConfig,
  sshPrivateKey: string
): SFTPClientConfig {
  return {
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
    ...(machine.knownHosts ? { knownHosts: machine.knownHosts } : {}),
  };
}

class MachineConnectionManager {
  private readonly entries = new Map<string, ConnectionEntry>();

  /**
   * Resolve the machine and team SSH key from the active config, then
   * acquire a pooled connection lease for it.
   */
  async acquire(machineName: string): Promise<MachineConnectionLease> {
    const config = await configService.getLocalConfig();
    const machine = await configService.getLocalMachine(machineName);
    const sshPrivateKey = config.sshPrivateKey ?? (await readSSHKey(config.ssh.privateKeyPath));
    if (!sshPrivateKey) {
      throw new Error(
        `No SSH key available for machine "${machineName}": config has neither sshPrivateKey nor a readable ssh.privateKeyPath`
      );
    }
    return this.acquireFor(machine, sshPrivateKey);
  }

  /** Acquire a pooled connection lease for an already-resolved machine. */
  async acquireFor(machine: MachineConfig, sshPrivateKey: string): Promise<MachineConnectionLease> {
    const entry = await this.acquireEntry(sftpConfigForMachine(machine, sshPrivateKey));
    const lease = this.createLease(entry);
    return {
      get sftp() {
        return lease.sftp;
      },
      machine,
      sshPrivateKey,
      ensure: lease.ensure,
      release: lease.release,
    };
  }

  /**
   * Acquire a pooled connection lease from raw connect options, for callers that
   * hold connection details rather than a MachineConfig (repo sync resolves a
   * per-repo key and host keys from the vault, renet provisioning takes a config).
   */
  async acquireForConfig(config: SFTPClientConfig): Promise<SftpConnectionLease> {
    return this.createLease(await this.acquireEntry(config));
  }

  /** Reserve a reference on the (possibly new) entry for these connect options. */
  private async acquireEntry(config: SFTPClientConfig): Promise<ConnectionEntry> {
    const key = connectionKey(config);
    let entry = this.entries.get(key);
    if (!entry) {
      entry = this.createEntry(key, config);
      this.entries.set(key, entry);
    }
    // Reserve the lease BEFORE awaiting the shared connect: with two
    // concurrent first acquires, the early waiter could otherwise acquire,
    // release, and close the entry while the late waiter is still awaiting
    // connectPromise, handing the late waiter a closed session.
    entry.refCount += 1;
    try {
      await this.ensureLive(entry);
    } catch (error) {
      entry.refCount -= 1;
      // A failed connect with no holders leaves nothing worth caching.
      if (entry.refCount === 0 && this.entries.get(key) === entry) {
        this.entries.delete(key);
      }
      throw error;
    }
    return entry;
  }

  private createEntry(key: string, clientConfig: SFTPClientConfig): ConnectionEntry {
    const entry: ConnectionEntry = {
      key,
      clientConfig,
      sftp: new SFTPClient(clientConfig),
      refCount: 0,
      connectPromise: null,
    };
    entry.connectPromise = Promise.resolve(entry.sftp.connect()).finally(() => {
      entry.connectPromise = null;
    });
    return entry;
  }

  /**
   * Wait for any in-flight connect, then verify the session is alive.
   * A dead session is evicted: the old client is closed (best effort) and
   * a fresh SFTPClient replaces it. Concurrent callers share the reconnect.
   */
  private ensureLive(entry: ConnectionEntry): Promise<void> {
    if (entry.connectPromise) return entry.connectPromise;
    if (entry.sftp.isConnected()) return Promise.resolve();
    try {
      entry.sftp.close();
    } catch {
      // Best effort: the session is already dead.
    }
    const fresh = new SFTPClient(entry.clientConfig);
    entry.sftp = fresh;
    entry.connectPromise = Promise.resolve(fresh.connect()).finally(() => {
      entry.connectPromise = null;
    });
    return entry.connectPromise;
  }

  private createLease(entry: ConnectionEntry): SftpConnectionLease {
    let released = false;
    const release = () => {
      if (released) return;
      released = true;
      this.releaseEntry(entry);
    };
    const ensure = async (): Promise<SFTPClient> => {
      if (released) {
        throw new Error('Machine connection lease was already released');
      }
      await this.ensureLive(entry);
      return entry.sftp;
    };
    return {
      get sftp() {
        return entry.sftp;
      },
      ensure,
      release,
    };
  }

  private releaseEntry(entry: ConnectionEntry): void {
    entry.refCount -= 1;
    if (entry.refCount > 0) return;
    if (this.entries.get(entry.key) === entry) {
      this.entries.delete(entry.key);
    }
    try {
      entry.sftp.close();
    } catch {
      // Best effort: closing a dead session is fine.
    }
  }
}

export const machineConnections = new MachineConnectionManager();

/** Borrow a pooled connection for the duration of `fn`, releasing it afterwards. */
export async function withPooledSftp<T>(
  config: SFTPClientConfig,
  fn: (sftp: SFTPClient) => Promise<T>
): Promise<T> {
  const lease = await machineConnections.acquireForConfig(config);
  try {
    return await fn(lease.sftp);
  } finally {
    lease.release();
  }
}

/**
 * Run `fn` on a caller-supplied client when there is one, else on a pooled
 * connection held only for the duration of the call. Callers that already hold a
 * lease pass `lease.sftp` and keep owning its lifetime.
 */
export async function withSharedOrPooledSftp<T>(
  sharedSftp: SFTPClient | undefined,
  config: SFTPClientConfig,
  fn: (sftp: SFTPClient) => Promise<T>
): Promise<T> {
  if (sharedSftp) return fn(sharedSftp);
  return withPooledSftp(config, fn);
}
