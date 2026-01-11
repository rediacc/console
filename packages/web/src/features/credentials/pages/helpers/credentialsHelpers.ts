import type { DynamicQueueActionParams } from '@/services/queue';
import type { GetTeamMachines_ResultSet1, GetTeamStorages_ResultSet1 } from '@rediacc/shared/types';

interface TeamInfo {
  teamName: string | null;
  vaultContent?: string | null;
}

interface RepositoryResource {
  teamName: string | null;
  repositoryGuid: string | null;
  vaultContent: string | null;
  repositoryNetworkId: number | null;
  repositoryNetworkMode: string | null;
  repositoryTag: string | null;
}

interface MachineEntry {
  value: string;
  bridgeName?: string;
}

interface SelectedMachine {
  vaultContent?: string | null;
}

interface FunctionData {
  params: Record<string, unknown>;
  priority: number;
  description: string;
}

export function buildQueuePayload(
  functionData: FunctionData,
  machineEntry: MachineEntry,
  selectedMachine: SelectedMachine | undefined,
  currentResource: RepositoryResource | undefined,
  teams: TeamInfo[]
): Omit<DynamicQueueActionParams, 'functionName'> | null {
  if (!currentResource) return null;

  return {
    params: functionData.params,
    teamName: currentResource.teamName ?? '',
    machineName: machineEntry.value,
    bridgeName: machineEntry.bridgeName ?? '',
    priority: functionData.priority,
    description: functionData.description,
    addedVia: 'repository-table',
    teamVault:
      teams.find((team) => team.teamName === currentResource.teamName)?.vaultContent ?? '{}',
    repositoryGuid: currentResource.repositoryGuid ?? undefined,
    vaultContent: currentResource.vaultContent ?? '{}',
    repositoryNetworkId: currentResource.repositoryNetworkId ?? undefined,
    repositoryNetworkMode: currentResource.repositoryNetworkMode ?? undefined,
    repositoryTag: currentResource.repositoryTag ?? undefined,
    machineVault: selectedMachine?.vaultContent ?? '{}',
  };
}

export function addBackupPullVaults(
  queuePayload: Omit<DynamicQueueActionParams, 'functionName'>,
  params: Record<string, unknown>,
  machines: GetTeamMachines_ResultSet1[],
  storages: GetTeamStorages_ResultSet1[]
): void {
  if (params.sourceType === 'machine' && params.from) {
    const sourceMachine = machines.find((machine) => machine.machineName === params.from);
    if (sourceMachine?.vaultContent) {
      queuePayload.sourceMachineVault = sourceMachine.vaultContent;
    }
  }

  if (params.sourceType === 'storage' && params.from) {
    const sourceStorage = storages.find((storage) => storage.storageName === params.from);
    if (sourceStorage?.vaultContent) {
      queuePayload.sourceStorageVault = sourceStorage.vaultContent;
    }
  }
}
