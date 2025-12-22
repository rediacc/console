import type { AdditionalVaultData, SourceOption } from './types';

interface Machine {
  machineName: string;
  vaultContent?: string | null;
}

interface Storage {
  storageName: string;
  vaultContent?: string | null;
}

interface Team {
  teamName: string;
  vaultContent?: string | null;
}

export function buildPullQueueVault(params: {
  selectedSource: string;
  machineName: string;
  teamName: string;
  storageSources: SourceOption[];
  machinesData?: Machine[];
  storageData?: Storage[];
  teamsData?: Team[];
}): AdditionalVaultData {
  const { selectedSource, machineName, storageSources, machinesData, storageData, teamsData } =
    params;

  const additionalVaultData: AdditionalVaultData = {};

  const sourceDetails = storageSources.find((s) => s.value === selectedSource);
  const isStorageSource = sourceDetails?.type === 'storage';

  const currentMachine = machinesData?.find((m) => m.machineName === machineName);
  if (currentMachine?.vaultContent) {
    additionalVaultData.machineVault = currentMachine.vaultContent;
  }

  const currentTeam = teamsData?.find((t) => t.teamName === params.teamName);
  if (currentTeam?.vaultContent) {
    additionalVaultData.teamVault = currentTeam.vaultContent;
  }

  if (isStorageSource) {
    const storage = storageData?.find((s) => s.storageName === selectedSource);
    if (storage?.vaultContent) {
      try {
        const storageVaultData = JSON.parse(storage.vaultContent);
        additionalVaultData.additionalStorageData = {
          [selectedSource]: storageVaultData,
        };
      } catch (e) {
        console.error('Failed to parse storage vault:', e);
      }
    }
  }

  if (!isStorageSource && selectedSource !== machineName) {
    const sourceMachine = machinesData?.find((m) => m.machineName === selectedSource);
    if (sourceMachine?.vaultContent) {
      try {
        const sourceMachineData = JSON.parse(sourceMachine.vaultContent);
        additionalVaultData.additionalMachineData = {
          [selectedSource]: sourceMachineData,
        };
      } catch (e) {
        console.error('Failed to parse source machine vault:', e);
      }
    }
  }

  return additionalVaultData;
}

export function buildListQueueVault(params: {
  selectedSource: string;
  machineName: string;
  storageSources: SourceOption[];
  machinesData?: Machine[];
  storageData?: Storage[];
  teamsData?: Team[];
  teamName: string;
}): AdditionalVaultData {
  const {
    selectedSource,
    machineName,
    storageSources,
    machinesData,
    storageData,
    teamsData,
    teamName,
  } = params;

  const additionalVaultData: AdditionalVaultData = {};

  const sourceDetails = storageSources.find((s) => s.value === selectedSource);
  const isStorageSource = sourceDetails?.type === 'storage';

  const currentMachine = machinesData?.find((m) => m.machineName === machineName);
  if (currentMachine?.vaultContent) {
    additionalVaultData.machineVault = currentMachine.vaultContent;
  }

  const currentTeam = teamsData?.find((t) => t.teamName === teamName);
  if (currentTeam?.vaultContent) {
    additionalVaultData.teamVault = currentTeam.vaultContent;
  }

  if (!isStorageSource && selectedSource !== machineName) {
    const sourceMachine = machinesData?.find((m) => m.machineName === selectedSource);
    if (sourceMachine?.vaultContent) {
      try {
        const sourceMachineData = JSON.parse(sourceMachine.vaultContent);
        additionalVaultData.additionalMachineData = {
          [selectedSource]: sourceMachineData,
        };
      } catch (e) {
        console.error('Failed to parse source machine vault:', e);
      }
    }
  }

  if (isStorageSource) {
    const storage = storageData?.find((s) => s.storageName === selectedSource);
    if (storage?.vaultContent) {
      try {
        const storageVaultData = JSON.parse(storage.vaultContent);
        additionalVaultData.additionalStorageData = {
          [selectedSource]: storageVaultData,
        };
      } catch (e) {
        console.error('Failed to parse storage vault:', e);
      }
    }
  }

  return additionalVaultData;
}
