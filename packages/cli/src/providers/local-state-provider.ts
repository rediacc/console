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

  async rename(_params: Record<string, unknown>): Promise<MutationResult> {
    throw new UnsupportedOperationError('machine rename');
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    await contextService.removeLocalMachine(params.machineName as string);
    return { success: true };
  }

  async getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    return [];
  }

  async updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    throw new UnsupportedOperationError('machine vault update');
  }
}

class LocalQueueProvider implements QueueProvider {
  async list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    throw new UnsupportedOperationError('queue list');
  }

  async create(_params: Record<string, unknown>): Promise<{ taskId?: string }> {
    throw new UnsupportedOperationError('queue create');
  }

  async trace(_taskId: string): Promise<ResourceRecord | null> {
    throw new UnsupportedOperationError('queue trace');
  }

  async cancel(_taskId: string): Promise<void> {
    throw new UnsupportedOperationError('queue cancel');
  }

  async retry(_taskId: string): Promise<void> {
    throw new UnsupportedOperationError('queue retry');
  }

  async delete(_taskId: string): Promise<void> {
    throw new UnsupportedOperationError('queue delete');
  }
}

class LocalStorageProvider implements StorageProvider {
  async list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    throw new UnsupportedOperationError('storage list');
  }

  async create(_params: Record<string, unknown>): Promise<MutationResult> {
    throw new UnsupportedOperationError('storage create');
  }

  async rename(_params: Record<string, unknown>): Promise<MutationResult> {
    throw new UnsupportedOperationError('storage rename');
  }

  async delete(_params: Record<string, unknown>): Promise<MutationResult> {
    throw new UnsupportedOperationError('storage delete');
  }

  async getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    throw new UnsupportedOperationError('storage vault');
  }

  async updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    throw new UnsupportedOperationError('storage vault update');
  }
}

class LocalRepositoryProvider implements RepositoryProvider {
  async list(_params: { teamName: string }): Promise<ResourceRecord[]> {
    throw new UnsupportedOperationError('repository list');
  }

  async create(_params: Record<string, unknown>): Promise<MutationResult> {
    throw new UnsupportedOperationError('repository create');
  }

  async rename(_params: Record<string, unknown>): Promise<MutationResult> {
    throw new UnsupportedOperationError('repository rename');
  }

  async delete(_params: Record<string, unknown>): Promise<MutationResult> {
    throw new UnsupportedOperationError('repository delete');
  }

  async getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    throw new UnsupportedOperationError('repository vault');
  }

  async updateVault(_params: Record<string, unknown>): Promise<MutationResult> {
    throw new UnsupportedOperationError('repository vault update');
  }
}

class LocalVaultProvider implements VaultProvider {
  async getTeamVault(_teamName: string): Promise<VaultData | null> {
    return null;
  }

  async getMachineVault(_teamName: string, _machineName: string): Promise<VaultData | null> {
    return null;
  }

  async getOrganizationVault(): Promise<VaultData | null> {
    return null;
  }

  async getConnectionVaults(
    _teamName: string,
    _machineName: string,
    _repositoryName?: string
  ): Promise<{ machineVault: VaultData; teamVault: VaultData; repositoryVault?: VaultData }> {
    return { machineVault: {}, teamVault: {} };
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
