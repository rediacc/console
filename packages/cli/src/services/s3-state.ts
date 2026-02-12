/**
 * S3StateService - manages a single `state.json` file in an S3/R2 bucket.
 *
 * State shape:
 *   { version: 1, encrypted: boolean, machines: ..., storages: ..., repositories: ... }
 *
 * When a master password is provided, section values are encrypted with AES-256-GCM.
 * Keys (section names, record names) stay in plaintext; only values are encrypted.
 */

import { nodeCryptoProvider } from '../adapters/crypto.js';
import type { S3ClientService } from './s3-client.js';
import type {
  MachineConfig,
  RepositoryConfig,
  S3StateData,
  SSHContent,
  StorageConfig,
} from '../types/index.js';

const STATE_KEY = 'state.json';

export class S3StateService {
  private state: S3StateData;

  private constructor(
    private readonly s3: S3ClientService,
    private readonly masterPassword: string | null,
    state: S3StateData
  ) {
    this.state = state;
  }

  /**
   * Load state from S3. Creates an empty state.json if it doesn't exist.
   */
  static async load(s3: S3ClientService, masterPassword: string | null): Promise<S3StateService> {
    const raw = await s3.getJson<S3StateData>(STATE_KEY);

    if (!raw) {
      // First-time: create empty state
      const empty: S3StateData = {
        version: 1,
        encrypted: !!masterPassword,
        machines: masterPassword ? await encryptSection({}, masterPassword) : {},
        storages: masterPassword ? await encryptSection({}, masterPassword) : {},
        repositories: masterPassword ? await encryptSection({}, masterPassword) : {},
      };
      await s3.putJson(STATE_KEY, empty);

      // Return with decrypted (empty) state in memory
      return new S3StateService(s3, masterPassword, {
        version: 1,
        encrypted: !!masterPassword,
        machines: {},
        storages: {},
        repositories: {},
      });
    }

    // Decrypt if needed
    if (raw.encrypted) {
      if (!masterPassword) {
        throw new Error(
          'State is encrypted but no master password was provided. ' +
            'Use --master-password or set REDIACC_MASTER_PASSWORD.'
        );
      }

      const decrypted: S3StateData = {
        version: raw.version,
        encrypted: true,
        machines: await decryptSection<Record<string, MachineConfig>>(
          raw.machines as string,
          masterPassword
        ),
        storages: await decryptSection<Record<string, StorageConfig>>(
          raw.storages as string,
          masterPassword
        ),
        repositories: await decryptSection<Record<string, RepositoryConfig>>(
          raw.repositories as string,
          masterPassword
        ),
        ssh: raw.ssh
          ? await decryptSection<SSHContent>(raw.ssh as string, masterPassword)
          : undefined,
      };
      return new S3StateService(s3, masterPassword, decrypted);
    }

    // Plaintext — use as-is
    return new S3StateService(s3, masterPassword, raw);
  }

  // ===========================================================================
  // Getters (return decrypted data from memory)
  // ===========================================================================

  getMachines(): Record<string, MachineConfig> {
    return this.state.machines as Record<string, MachineConfig>;
  }

  getStorages(): Record<string, StorageConfig> {
    return this.state.storages as Record<string, StorageConfig>;
  }

  getRepositories(): Record<string, RepositoryConfig> {
    return this.state.repositories as Record<string, RepositoryConfig>;
  }

  getSSH(): SSHContent | null {
    const ssh = this.state.ssh;
    if (!ssh || typeof ssh === 'string') return null;
    return ssh;
  }

  // ===========================================================================
  // Setters (update in-memory state + persist to S3)
  // ===========================================================================

  async setMachines(machines: Record<string, MachineConfig>): Promise<void> {
    this.state.machines = machines;
    await this.save();
  }

  async setStorages(storages: Record<string, StorageConfig>): Promise<void> {
    this.state.storages = storages;
    await this.save();
  }

  async setRepositories(repos: Record<string, RepositoryConfig>): Promise<void> {
    this.state.repositories = repos;
    await this.save();
  }

  async setSSH(ssh: SSHContent): Promise<void> {
    this.state.ssh = ssh;
    await this.save();
  }

  // ===========================================================================
  // Persistence
  // ===========================================================================

  private async save(): Promise<void> {
    const toWrite: S3StateData = {
      version: 1,
      encrypted: !!this.masterPassword,
      machines: this.masterPassword
        ? await encryptSection(this.state.machines, this.masterPassword)
        : this.state.machines,
      storages: this.masterPassword
        ? await encryptSection(this.state.storages, this.masterPassword)
        : this.state.storages,
      repositories: this.masterPassword
        ? await encryptSection(this.state.repositories, this.masterPassword)
        : this.state.repositories,
      ssh: this.state.ssh
        ? this.masterPassword
          ? await encryptSection(this.state.ssh, this.masterPassword)
          : this.state.ssh
        : undefined,
    };

    await this.s3.putJson(STATE_KEY, toWrite);
  }
}

// =============================================================================
// Helpers
// =============================================================================

async function encryptSection(data: unknown, password: string): Promise<string> {
  const json = JSON.stringify(data);
  return nodeCryptoProvider.encrypt(json, password);
}

async function decryptSection<T>(encrypted: string, password: string): Promise<T> {
  const json = await nodeCryptoProvider.decrypt(encrypted, password);
  return JSON.parse(json) as T;
}
