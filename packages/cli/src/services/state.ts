/**
 * State provider - the local adapter's view of machines, storage, and vaults.
 *
 * Backed entirely by the config file via configService. A single
 * implementation (LocalStateProvider) is exposed through getStateProvider().
 */

import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { configService } from './config/config-resources.js';
import { readSSHKey } from './renet/renet-execution.js';

/** Generic mutation result */
interface MutationResult {
  success: boolean;
  message?: string;
  [key: string]: unknown;
}

/** Generic resource record */
type ResourceRecord = Record<string, unknown>;

/** Vault data */
type VaultData = Record<string, unknown>;

/** Machine data including vaultStatus for health/containers/services/repos/vault-status commands */
interface MachineWithVaultStatusData {
  machineName: string | null;
  vaultStatus?: string | null;
  vaultContent?: string | null;
  vaultVersion?: number | null;
  [key: string]: unknown;
}

export interface MachineProvider {
  list(params: { teamName: string }): Promise<ResourceRecord[]>;
  create(params: Record<string, unknown>): Promise<MutationResult>;
  rename(params: Record<string, unknown>): Promise<MutationResult>;
  delete(params: Record<string, unknown>): Promise<MutationResult>;
  /** Get a single machine with vaultStatus data (for health/services/containers/repos) */
  getWithVaultStatus(params: {
    teamName: string;
    machineName: string;
  }): Promise<MachineWithVaultStatusData | null>;
}

export interface StorageProvider {
  list(params: { teamName: string }): Promise<ResourceRecord[]>;
  create(params: Record<string, unknown>): Promise<MutationResult>;
  rename(params: Record<string, unknown>): Promise<MutationResult>;
  delete(params: Record<string, unknown>): Promise<MutationResult>;
}

export interface VaultProvider {
  getConnectionVaults(
    teamName: string,
    machineName: string,
    repositoryName?: string
  ): Promise<{
    machineVault: VaultData;
    teamVault: VaultData;
    repositoryVault?: VaultData;
  }>;
}

export interface IStateProvider {
  readonly machines: MachineProvider;
  readonly storage: StorageProvider;
  readonly vaults: VaultProvider;
}

class UnsupportedOperationError extends Error {
  constructor(operation: string) {
    super(`"${operation}" is not supported by the local adapter`);
    this.name = 'UnsupportedOperationError';
  }
}

class LocalMachineProvider implements MachineProvider {
  async list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    const machines = await configService.listMachines();
    return machines.map((m) => ({
      machineName: m.name,
      ip: m.config.ip,
      user: m.config.user,
      port: m.config.port,
      datastore: m.config.datastore,
    }));
  }

  async create(params: Record<string, unknown>): Promise<MutationResult> {
    await configService.addMachine(params.machineName as string, {
      ip: params.ip as string,
      user: params.user as string,
      port: params.port as number | undefined,
      datastore: params.datastore as string | undefined,
    });
    return { success: true };
  }

  rename(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('machine rename'));
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    await configService.removeMachine(params.machineName as string);
    return { success: true };
  }

  async getWithVaultStatus(params: {
    teamName: string;
    machineName: string;
  }): Promise<MachineWithVaultStatusData | null> {
    const { fetchMachineStatus } = await import('./machine/machine-status.js');
    const listResult = await fetchMachineStatus(params.machineName);
    return {
      machineName: params.machineName,
      vaultStatus: JSON.stringify(listResult),
    };
  }
}

class LocalStorageProvider implements StorageProvider {
  async list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    const storages = await configService.listStorages();
    return storages.map((s) => ({
      storageName: s.name,
      provider: s.config.provider,
    }));
  }

  async create(params: Record<string, unknown>): Promise<MutationResult> {
    const storageName = params.storageName as string;
    const vaultContent = params.vaultContent;
    if (typeof vaultContent !== 'string' || vaultContent.length === 0) {
      throw new Error('storage create requires --vault <json> with the storage configuration');
    }
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(vaultContent) as Record<string, unknown>;
    } catch {
      throw new Error('--vault must be valid JSON (e.g. \'{"provider":"s3",...}\')');
    }
    await configService.addStorage(storageName, {
      provider: typeof parsed.provider === 'string' ? parsed.provider : 'unknown',
      vaultContent: parsed,
    });
    return { success: true };
  }

  rename(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('storage rename'));
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    await configService.removeStorage(params.storageName as string);
    return { success: true };
  }
}

class LocalVaultProvider implements VaultProvider {
  async getConnectionVaults(
    _teamName: string,
    machineName: string,
    repositoryName?: string
  ): Promise<{
    machineVault: VaultData;
    teamVault: VaultData;
    repositoryVault?: VaultData;
  }> {
    const localConfig = await configService.getLocalConfig();
    const machine = localConfig.machines[machineName];
    if (!machine) {
      const available = Object.keys(localConfig.machines).join(', ');
      throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
    }

    const sshPrivateKey =
      localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

    const currentConfig = await configService.getCurrent();
    const machineVault: VaultData = {
      ip: machine.ip,
      host: machine.ip,
      port: machine.port ?? DEFAULTS.SSH.PORT,
      user: machine.user,
      known_hosts: machine.knownHosts ?? '',
      datastore: machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
      universalUser: currentConfig?.defaults?.universalUser ?? DEFAULTS.REPOSITORY.UNIVERSAL_USER,
    };

    const teamVault: VaultData = {
      SSH_PRIVATE_KEY: sshPrivateKey,
    };

    let repositoryVault: VaultData | undefined;
    if (repositoryName) {
      const repoConfig = await configService.getRepository(repositoryName);
      if (!repoConfig) {
        const repos = await configService.listRepositories();
        const available = repos.map((r) => r.name).join(', ');
        throw new Error(
          `Repository "${repositoryName}" not found. Available: ${available || '(none)'}`
        );
      }
      const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
      machineVault.dockerHost = `unix:///var/run/rediacc/docker-${repoConfig.networkId}.sock`;
      machineVault.dockerSocket = `/var/run/rediacc/docker-${repoConfig.networkId}.sock`;

      // Resolve per-repo secrets into the two delivery channels:
      //   env  → REDIACC_SECRET_<NAME> in the SSH/renet shell; compose
      //          interpolation picks them up via existing ${REDIACC_*} allowlist.
      //   file → tmpfs file at /var/run/rediacc/secrets/<networkId>/<NAME>
      //          (materialized by renet at repo-up time). Carried in vault
      //          but never leaked into the SSH session env.
      const envSecrets: Record<string, string> = {};
      const secretFiles: { name: string; value: string }[] = [];
      for (const [name, entry] of Object.entries(repoConfig.secrets ?? {})) {
        if (entry.mode === 'env') {
          envSecrets[`REDIACC_SECRET_${name}`] = entry.value;
        } else {
          secretFiles.push({ name, value: entry.value });
        }
      }

      repositoryVault = {
        repositoryGuid: repoConfig.repositoryGuid,
        networkId: repoConfig.networkId,
        path: `/home/${repositoryName}`,
        workingDirectory: `${datastore}/mounts/${repoConfig.repositoryGuid}`,
        environment: envSecrets,
        secretFiles,
      };
    }

    return { machineVault, teamVault, repositoryVault };
  }
}

export class LocalStateProvider implements IStateProvider {
  readonly machines: MachineProvider;
  readonly storage: StorageProvider;
  readonly vaults: VaultProvider;

  constructor() {
    this.machines = new LocalMachineProvider();
    this.storage = new LocalStorageProvider();
    this.vaults = new LocalVaultProvider();
  }
}

let provider: LocalStateProvider | undefined;

/** Get the state provider (config-file backed local adapter). */
export function getStateProvider(): IStateProvider {
  return (provider ??= new LocalStateProvider());
}
