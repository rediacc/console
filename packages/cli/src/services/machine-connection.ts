/**
 * MachineConnectionManager - refcounted SSH/SFTP connection pool.
 *
 * Connections are keyed by host:port:user and shared across concurrent
 * callers via leases. The first acquire opens the connection, subsequent
 * acquires reuse it (concurrent connects are deduped on a shared promise),
 * and the last release() closes it. Dead sessions are evicted and replaced
 * with a fresh SFTPClient instance — an ended ssh2 client is never reused.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient } from '../shared-desktop/sftp/index.js';
import type { MachineConfig } from '../types/index.js';
import { configService } from './config-resources.js';
import { readSSHKey } from './renet-execution.js';

/** A refcounted handle on a shared machine connection. */
export interface MachineConnectionLease {
  /** Live SFTP client (replaced transparently after a dead-session evict). */
  readonly sftp: SFTPClient;
  readonly machine: MachineConfig;
  readonly sshPrivateKey: string;
  /** Re-check liveness, reconnecting if the session died. Returns the live client. */
  ensure(): Promise<SFTPClient>;
  /** Drop this lease's reference. The last release closes the connection. */
  release(): void;
}

interface ConnectionEntry {
  key: string;
  machine: MachineConfig;
  sshPrivateKey: string;
  sftp: SFTPClient;
  refCount: number;
  /** In-flight connect/reconnect, shared so concurrent acquires dedupe. */
  connectPromise: Promise<void> | null;
}

function connectionKey(machine: MachineConfig): string {
  return `${machine.ip}:${machine.port ?? DEFAULTS.SSH.PORT}:${machine.user}`;
}

function createClient(machine: MachineConfig, sshPrivateKey: string): SFTPClient {
  return new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
    ...(machine.knownHosts ? { knownHosts: machine.knownHosts } : {}),
  });
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
    const key = connectionKey(machine);
    let entry = this.entries.get(key);
    if (!entry) {
      entry = this.createEntry(key, machine, sshPrivateKey);
      this.entries.set(key, entry);
    }
    // Reserve the lease BEFORE awaiting the shared connect: with two
    // concurrent first acquires, the early waiter could otherwise acquire,
    // release, and close the entry while the late waiter is still awaiting
    // connectPromise — handing the late waiter a closed session.
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
    return this.createLease(entry);
  }

  private createEntry(key: string, machine: MachineConfig, sshPrivateKey: string): ConnectionEntry {
    const entry: ConnectionEntry = {
      key,
      machine,
      sshPrivateKey,
      sftp: createClient(machine, sshPrivateKey),
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
      // Best effort — the session is already dead.
    }
    const fresh = createClient(entry.machine, entry.sshPrivateKey);
    entry.sftp = fresh;
    entry.connectPromise = Promise.resolve(fresh.connect()).finally(() => {
      entry.connectPromise = null;
    });
    return entry.connectPromise;
  }

  private createLease(entry: ConnectionEntry): MachineConnectionLease {
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
      machine: entry.machine,
      sshPrivateKey: entry.sshPrivateKey,
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
      // Best effort — closing a dead session is fine.
    }
  }
}

export const machineConnections = new MachineConnectionManager();
