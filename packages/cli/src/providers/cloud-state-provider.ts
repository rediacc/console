/**
 * CloudStateProvider - wraps existing typedApi + parsers.
 * Exact same behavior as the current commands, just behind the IStateProvider interface.
 */

import {
  parseCreateMachine,
  parseCreateQueueItem,
  parseGetOrganizationTeams,
  parseGetOrganizationVaults,
  parseGetQueueItemTrace,
  parseGetTeamMachines,
  parseGetTeamQueueItems,
  parseGetTeamRepositories,
  parseGetTeamStorages,
} from '@rediacc/shared/api';
import { parseVaultContent } from '@rediacc/shared/queue-vault';
import { typedApi } from '../services/api.js';
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
} from './types.js';

class CloudMachineProvider implements MachineProvider {
  async list(params: { teamName: string }): Promise<ResourceRecord[]> {
    const response = await typedApi.GetTeamMachines({ teamName: params.teamName });
    return parseGetTeamMachines(response as never) as unknown as ResourceRecord[];
  }

  async create(params: Record<string, unknown>): Promise<MutationResult> {
    const response = await typedApi.CreateMachine(params as never);
    const parsed = parseCreateMachine(response as never);
    return { success: true, ...parsed };
  }

  async rename(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.UpdateMachineName(params as never);
    return { success: true };
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.DeleteMachine(params as never);
    return { success: true };
  }

  async getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    const response = await typedApi.GetOrganizationVaults({});
    return parseGetOrganizationVaults(response as never) as unknown as VaultItem[];
  }

  async updateVault(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.UpdateMachineVault(params as never);
    return { success: true };
  }

  async getWithVaultStatus(params: {
    teamName: string;
    machineName: string;
  }): Promise<MachineWithVaultStatusData | null> {
    const response = await typedApi.GetTeamMachines({ teamName: params.teamName });
    const machines = parseGetTeamMachines(
      response as never
    ) as unknown as MachineWithVaultStatusData[];
    return machines.find((m) => m.machineName === params.machineName) ?? null;
  }
}

class CloudQueueProvider implements QueueProvider {
  async list(params: { teamName: string; maxRecords?: number }): Promise<ResourceRecord[]> {
    const response = await typedApi.GetTeamQueueItems({
      teamName: params.teamName,
      maxRecords: params.maxRecords,
    });
    const parsed = parseGetTeamQueueItems(response as never);
    return parsed.items as unknown as ResourceRecord[];
  }

  async create(params: Record<string, unknown>): Promise<{ taskId?: string }> {
    // Only pass parameters accepted by the CreateQueueItem stored procedure.
    // Extra fields (e.g. functionName used by S3 mode) cause a 400 error.
    const response = await typedApi.CreateQueueItem({
      teamName: params.teamName as string,
      machineName: params.machineName as string,
      bridgeName: params.bridgeName as string,
      vaultContent: params.vaultContent as string,
      priority: params.priority as number,
    });
    const parsed = parseCreateQueueItem(response as never);
    return { taskId: parsed.taskId ?? undefined };
  }

  async trace(taskId: string): Promise<ResourceRecord | null> {
    const response = await typedApi.GetQueueItemTrace({ taskId });
    const parsed = parseGetQueueItemTrace(response as never);
    return parsed as unknown as ResourceRecord;
  }

  async cancel(taskId: string): Promise<void> {
    await typedApi.CancelQueueItem({ taskId });
  }

  async retry(taskId: string): Promise<void> {
    await typedApi.RetryFailedQueueItem({ taskId });
  }

  async delete(taskId: string): Promise<void> {
    await typedApi.DeleteQueueItem({ taskId });
  }
}

class CloudStorageProvider implements StorageProvider {
  async list(params: { teamName: string }): Promise<ResourceRecord[]> {
    const response = await typedApi.GetTeamStorages({ teamName: params.teamName });
    return parseGetTeamStorages(response as never) as unknown as ResourceRecord[];
  }

  async create(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.CreateStorage(params as never);
    return { success: true };
  }

  async rename(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.UpdateStorageName(params as never);
    return { success: true };
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.DeleteStorage(params as never);
    return { success: true };
  }

  async getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    const response = await typedApi.GetOrganizationVaults({});
    return parseGetOrganizationVaults(response as never) as unknown as VaultItem[];
  }

  async updateVault(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.UpdateStorageVault(params as never);
    return { success: true };
  }
}

class CloudRepositoryProvider implements RepositoryProvider {
  async list(params: { teamName: string }): Promise<ResourceRecord[]> {
    const response = await typedApi.GetTeamRepositories({ teamName: params.teamName });
    return parseGetTeamRepositories(response as never) as unknown as ResourceRecord[];
  }

  async create(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.CreateRepository(params as never);
    return { success: true };
  }

  async rename(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.UpdateRepositoryName(params as never);
    return { success: true };
  }

  async delete(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.DeleteRepository(params as never);
    return { success: true };
  }

  async getVault(_params: Record<string, unknown>): Promise<VaultItem[]> {
    const response = await typedApi.GetOrganizationVaults({});
    return parseGetOrganizationVaults(response as never) as unknown as VaultItem[];
  }

  async updateVault(params: Record<string, unknown>): Promise<MutationResult> {
    await typedApi.UpdateRepositoryVault(params as never);
    return { success: true };
  }
}

class CloudVaultProvider implements VaultProvider {
  async getTeamVault(teamName: string): Promise<VaultData | null> {
    const response = await typedApi.GetOrganizationTeams({});
    const teams = parseGetOrganizationTeams(response as never) as {
      teamName?: string;
      vaultContent?: string;
    }[];
    const team = teams.find((t: { teamName?: string }) => t.teamName === teamName);
    return parseVaultContent<VaultData>(team?.vaultContent) ?? null;
  }

  async getMachineVault(teamName: string, machineName: string): Promise<VaultData | null> {
    const response = await typedApi.GetTeamMachines({ teamName });
    const machines = parseGetTeamMachines(response as never) as {
      machineName?: string;
      vaultContent?: string;
    }[];
    const machine = machines.find((m: { machineName?: string }) => m.machineName === machineName);
    return parseVaultContent<VaultData>(machine?.vaultContent) ?? null;
  }

  async getOrganizationVault(): Promise<VaultData | null> {
    try {
      const sharedApi = await import('@rediacc/shared/api');
      const parseFn = (sharedApi as Record<string, unknown>).parseGetOrganizationVault as
        | ((data: never) => { vaultContent?: string } | null)
        | undefined;
      if (!parseFn) return null;
      const response = await typedApi.GetOrganizationVault({});
      const vault = parseFn(response as never);
      return parseVaultContent<VaultData>(vault?.vaultContent) ?? null;
    } catch {
      return null;
    }
  }

  async getConnectionVaults(
    teamName: string,
    machineName: string,
    repositoryName?: string
  ): Promise<{ machineVault: VaultData; teamVault: VaultData; repositoryVault?: VaultData }> {
    const { getConnectionVaults } = await import('../utils/connectionDetails.js');
    const result = await getConnectionVaults(teamName, machineName, repositoryName);
    return {
      machineVault: result.machineVault,
      teamVault: result.teamVault,
      repositoryVault: result.repositoryVault,
    };
  }
}

export class CloudStateProvider implements IStateProvider {
  readonly mode = 'cloud' as const;
  readonly machines: MachineProvider;
  readonly queue: QueueProvider;
  readonly storage: StorageProvider;
  readonly repositories: RepositoryProvider;
  readonly vaults: VaultProvider;

  constructor() {
    this.machines = new CloudMachineProvider();
    this.queue = new CloudQueueProvider();
    this.storage = new CloudStorageProvider();
    this.repositories = new CloudRepositoryProvider();
    this.vaults = new CloudVaultProvider();
  }
}
