/**
 * LocalStateProvider - wraps contextService local methods.
 * Queue/Storage/Repository operations are not supported in local mode.
 */

import { contextService } from '../services/context.js';
import type {
  IStateProvider,
  MachineProvider,
  MutationResult,
  QueueProvider,
  RepositoryProvider,
  ResourceRecord,
  StorageProvider,
  VaultData,
  VaultItem,
  VaultProvider,
} from './types.js';

class UnsupportedOperationError extends Error {
  constructor(operation: string) {
    super(`"${operation}" is not supported in local mode`);
    this.name = 'UnsupportedOperationError';
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
    return Promise.reject(new UnsupportedOperationError('machine rename'));
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    await contextService.removeLocalMachine(params.machineName as string);
    return { success: true };
  }

  getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    return Promise.resolve([]);
  }

  updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('machine vault update'));
  }
}

class LocalQueueProvider implements QueueProvider {
  list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    return Promise.reject(new UnsupportedOperationError('queue list'));
  }

  create(_params: Record<string, unknown>): Promise<{ taskId?: string }> {
    return Promise.reject(new UnsupportedOperationError('queue create'));
  }

  trace(_taskId: string): Promise<ResourceRecord | null> {
    return Promise.reject(new UnsupportedOperationError('queue trace'));
  }

  cancel(_taskId: string): Promise<void> {
    return Promise.reject(new UnsupportedOperationError('queue cancel'));
  }

  retry(_taskId: string): Promise<void> {
    return Promise.reject(new UnsupportedOperationError('queue retry'));
  }

  delete(_taskId: string): Promise<void> {
    return Promise.reject(new UnsupportedOperationError('queue delete'));
  }
}

class LocalStorageProvider implements StorageProvider {
  list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    return Promise.reject(new UnsupportedOperationError('storage list'));
  }

  create(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('storage create'));
  }

  rename(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('storage rename'));
  }

  delete(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('storage delete'));
  }

  getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    return Promise.reject(new UnsupportedOperationError('storage vault'));
  }

  updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('storage vault update'));
  }
}

class LocalRepositoryProvider implements RepositoryProvider {
  list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    return Promise.reject(new UnsupportedOperationError('repository list'));
  }

  create(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('repository create'));
  }

  rename(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('repository rename'));
  }

  delete(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('repository delete'));
  }

  getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    return Promise.reject(new UnsupportedOperationError('repository vault'));
  }

  updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    return Promise.reject(new UnsupportedOperationError('repository vault update'));
  }
}

class LocalVaultProvider implements VaultProvider {
  getTeamVault(_teamName: string): Promise<VaultData | null> {
    return Promise.resolve(null);
  }

  getMachineVault(_teamName: string, _machineName: string): Promise<VaultData | null> {
    return Promise.resolve(null);
  }

  getOrganizationVault(): Promise<VaultData | null> {
    return Promise.resolve(null);
  }

  getConnectionVaults(
    _teamName: string,
    _machineName: string,
    _repositoryName?: string
  ): Promise<{ machineVault: VaultData; teamVault: VaultData; repositoryVault?: VaultData }> {
    return Promise.resolve({ machineVault: {}, teamVault: {} });
  }
}

export class LocalStateProvider implements IStateProvider {
  readonly mode = 'local' as const;
  readonly machines: MachineProvider;
  readonly queue: QueueProvider;
  readonly storage: StorageProvider;
  readonly repositories: RepositoryProvider;
  readonly vaults: VaultProvider;

  constructor() {
    this.machines = new LocalMachineProvider();
    this.queue = new LocalQueueProvider();
    this.storage = new LocalStorageProvider();
    this.repositories = new LocalRepositoryProvider();
    this.vaults = new LocalVaultProvider();
  }
}
