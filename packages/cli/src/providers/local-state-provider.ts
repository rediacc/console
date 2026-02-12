/**
 * LocalStateProvider - wraps contextService local methods.
 * Queue/Storage/Repository operations are not supported in local mode.
 */

import { contextService } from "../services/context.js";
import type {
  IStateProvider,
  MachineProvider,
  MachineWithVaultStatusData,
  MutationResult,
  QueueProvider,
  RepositoryProvider,
  ResourceRecord,
  StorageProvider,
  VaultData,
  VaultItem,
  VaultProvider,
} from "./types.js";

class UnsupportedOperationError extends Error {
  constructor(operation: string) {
    super(`"${operation}" is not supported in local mode`);
    this.name = "UnsupportedOperationError";
  }
}

class LocalMachineProvider implements MachineProvider {
  async list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    const machines = await contextService.listLocalMachines();
    return machines.map((m) => ({
      machineName: m.name,
      ip: m.config.ip,
      user: m.config.user,
      port: m.config.port,
      datastore: m.config.datastore,
    }));
  }

  async create(params: Record<string, unknown>): Promise<MutationResult> {
    await contextService.addLocalMachine(params.machineName as string, {
      ip: params.ip as string,
      user: params.user as string,
      port: params.port as number | undefined,
      datastore: params.datastore as string | undefined,
    });
    return { success: true };
  }

  rename(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError("machine rename"));
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    await contextService.removeLocalMachine(params.machineName as string);
    return { success: true };
  }

  getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    return Promise.resolve([]);
  }

  updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(
      new UnsupportedOperationError("machine vault update"),
    );
  }

  getWithVaultStatus(_params: {
    teamName: string;
    machineName: string;
  }): Promise<MachineWithVaultStatusData | null> {
    return Promise.reject(
      new UnsupportedOperationError("machine vault status"),
    );
  }
}

class LocalQueueProvider implements QueueProvider {
  list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    return Promise.reject(new UnsupportedOperationError("queue list"));
  }

  create(_params: Record<string, unknown>): Promise<{ taskId?: string }> {
    return Promise.reject(new UnsupportedOperationError("queue create"));
  }

  trace(_taskId: string): Promise<ResourceRecord | null> {
    return Promise.reject(new UnsupportedOperationError("queue trace"));
  }

  cancel(_taskId: string): Promise<void> {
    return Promise.reject(new UnsupportedOperationError("queue cancel"));
  }

  retry(_taskId: string): Promise<void> {
    return Promise.reject(new UnsupportedOperationError("queue retry"));
  }

  delete(_taskId: string): Promise<void> {
    return Promise.reject(new UnsupportedOperationError("queue delete"));
  }
}

class LocalStorageProvider implements StorageProvider {
  async list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    const storages = await contextService.listLocalStorages();
    return storages.map((s) => ({
      storageName: s.name,
      provider: s.config.provider,
    }));
  }

  async create(params: Record<string, unknown>): Promise<MutationResult> {
    const storageName = params.storageName as string;
    const vaultContent = params.vaultContent as string;
    const parsed = JSON.parse(vaultContent) as Record<string, unknown>;
    await contextService.addLocalStorage(storageName, {
      provider: typeof parsed.provider === "string" ? parsed.provider : "unknown",
      vaultContent: parsed,
    });
    return { success: true };
  }

  rename(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError("storage rename"));
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    await contextService.removeLocalStorage(params.storageName as string);
    return { success: true };
  }

  async getVault(params: Record<string, unknown>): Promise<VaultItem[]> {
    const config = await contextService.getLocalStorage(
      params.storageName as string,
    );
    return [
      {
        vaultType: "Storage",
        vaultContent: JSON.stringify(config.vaultContent),
        vaultVersion: 1,
      },
    ];
  }

  updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(
      new UnsupportedOperationError("storage vault update"),
    );
  }
}

class LocalRepositoryProvider implements RepositoryProvider {
  list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    return Promise.reject(new UnsupportedOperationError("repository list"));
  }

  create(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError("repository create"));
  }

  rename(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError("repository rename"));
  }

  delete(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError("repository delete"));
  }

  getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    return Promise.reject(new UnsupportedOperationError("repository vault"));
  }

  updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(
      new UnsupportedOperationError("repository vault update"),
    );
  }
}

class LocalVaultProvider implements VaultProvider {
  getTeamVault(_teamName: string): Promise<VaultData | null> {
    return Promise.resolve(null);
  }

  getMachineVault(
    _teamName: string,
    _machineName: string,
  ): Promise<VaultData | null> {
    return Promise.resolve(null);
  }

  getOrganizationVault(): Promise<VaultData | null> {
    return Promise.resolve(null);
  }

  getConnectionVaults(
    _teamName: string,
    _machineName: string,
    _repositoryName?: string,
  ): Promise<{
    machineVault: VaultData;
    teamVault: VaultData;
    repositoryVault?: VaultData;
  }> {
    return Promise.resolve({ machineVault: {}, teamVault: {} });
  }
}

export class LocalStateProvider implements IStateProvider {
  readonly mode: "local" | "s3";
  readonly machines: MachineProvider;
  readonly queue: QueueProvider;
  readonly storage: StorageProvider;
  readonly repositories: RepositoryProvider;
  readonly vaults: VaultProvider;

  constructor(mode: "local" | "s3" = "local") {
    this.mode = mode;
    this.machines = new LocalMachineProvider();
    this.queue = new LocalQueueProvider();
    this.storage = new LocalStorageProvider();
    this.repositories = new LocalRepositoryProvider();
    this.vaults = new LocalVaultProvider();
  }
}
