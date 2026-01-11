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

interface VaultBuilderParams {
  selectedSource: string;
  machineName: string;
  teamName: string;
  storageSources: SourceOption[];
  machinesData?: Machine[];
  storageData?: Storage[];
  teamsData?: Team[];
}

function safeParseJSON<T>(json: string, errorMessage: string): T | null {
  try {
    return JSON.parse(json) as T;
  } catch (e) {
    console.error(errorMessage, e);
    return null;
  }
}

function addMachineVault(
  vaultData: AdditionalVaultData,
  machinesData: Machine[] | undefined,
  machineName: string
): void {
  const machine = machinesData?.find((m) => m.machineName === machineName);
  if (machine?.vaultContent) {
    vaultData.machineVault = machine.vaultContent;
  }
}

function addTeamVault(
  vaultData: AdditionalVaultData,
  teamsData: Team[] | undefined,
  teamName: string
): void {
  const team = teamsData?.find((t) => t.teamName === teamName);
  if (team?.vaultContent) {
    vaultData.teamVault = team.vaultContent;
  }
}

function addStorageVault(
  vaultData: AdditionalVaultData,
  storageData: Storage[] | undefined,
  selectedSource: string
): void {
  const storage = storageData?.find((s) => s.storageName === selectedSource);
  if (!storage?.vaultContent) return;

  const parsed = safeParseJSON(storage.vaultContent, 'Failed to parse storage vault:');
  if (parsed) {
    vaultData.additionalStorageData = { [selectedSource]: parsed };
  }
}

function addSourceMachineVault(
  vaultData: AdditionalVaultData,
  machinesData: Machine[] | undefined,
  selectedSource: string
): void {
  const sourceMachine = machinesData?.find((m) => m.machineName === selectedSource);
  if (!sourceMachine?.vaultContent) return;

  const parsed = safeParseJSON(sourceMachine.vaultContent, 'Failed to parse source machine vault:');
  if (parsed) {
    vaultData.additionalMachineData = { [selectedSource]: parsed };
  }
}

function isStorageSourceType(storageSources: SourceOption[], selectedSource: string): boolean {
  const sourceDetails = storageSources.find((s) => s.value === selectedSource);
  return sourceDetails?.type === 'storage';
}

export function buildPullQueueVault(params: VaultBuilderParams): AdditionalVaultData {
  const {
    selectedSource,
    machineName,
    teamName,
    storageSources,
    machinesData,
    storageData,
    teamsData,
  } = params;
  const vaultData: AdditionalVaultData = {};
  const isStorageSource = isStorageSourceType(storageSources, selectedSource);

  addMachineVault(vaultData, machinesData, machineName);
  addTeamVault(vaultData, teamsData, teamName);

  if (isStorageSource) {
    addStorageVault(vaultData, storageData, selectedSource);
  } else if (selectedSource !== machineName) {
    addSourceMachineVault(vaultData, machinesData, selectedSource);
  }

  return vaultData;
}

export function buildListQueueVault(params: VaultBuilderParams): AdditionalVaultData {
  const {
    selectedSource,
    machineName,
    teamName,
    storageSources,
    machinesData,
    storageData,
    teamsData,
  } = params;
  const vaultData: AdditionalVaultData = {};
  const isStorageSource = isStorageSourceType(storageSources, selectedSource);

  addMachineVault(vaultData, machinesData, machineName);
  addTeamVault(vaultData, teamsData, teamName);

  if (isStorageSource) {
    addStorageVault(vaultData, storageData, selectedSource);
  } else if (selectedSource !== machineName) {
    addSourceMachineVault(vaultData, machinesData, selectedSource);
  }

  return vaultData;
}
