import { useMemo } from 'react';
import type { Machine } from '@/types';
import type { DeployedRepo } from '@rediacc/shared/services/machine';
import type { GroupByMode } from '../types';

interface Repository {
  repositoryGuid: string;
  repositoryName: string;
  grandGuid?: string | null;
}

interface UseGroupedMachinesProps {
  machines: Machine[];
  groupBy: GroupByMode;
  repositories: Repository[];
  getMachineRepositories: (machine: Machine) => DeployedRepo[];
}

// Helper to add machine to result if not already present
const addMachineToGroup = (
  result: Record<string, Machine[]>,
  key: string,
  machine: Machine
): void => {
  const existing = result[key] as Machine[] | undefined;
  if (existing === undefined) {
    result[key] = [];
  }
  if (!result[key].find((m) => m.machineName === machine.machineName)) {
    result[key].push(machine);
  }
};

// Helper to get basic grouping key
const getBasicGroupKey = (machine: Machine, groupBy: GroupByMode): string => {
  switch (groupBy) {
    case 'bridge':
      return machine.bridgeName ?? '';
    case 'team':
      return machine.teamName ?? '';
    case 'region':
      return machine.regionName ?? 'Unknown';
    default:
      return '';
  }
};

// Helper to determine status key for a machine based on its repositories
const getStatusKey = (machineRepositories: DeployedRepo[]): string => {
  if (machineRepositories.length === 0) {
    return 'No Repositories';
  }

  const hasInaccessible = machineRepositories.some((r) => !r.accessible);
  if (hasInaccessible) return 'Inaccessible';

  const hasRunning = machineRepositories.some((r) => r.mounted && r.docker_running);
  if (hasRunning) return 'Active (Running)';

  const hasStopped = machineRepositories.some((r) => r.mounted && !r.docker_running);
  if (hasStopped) return 'Ready (Stopped)';

  const hasUnmounted = machineRepositories.some((r) => !r.mounted);
  if (hasUnmounted) return 'Not Mounted';

  return 'Unknown Status';
};

// Helper to handle repository grouping
const handleRepositoryGrouping = (
  machine: Machine,
  machineRepositories: DeployedRepo[],
  result: Record<string, Machine[]>
): void => {
  for (const repository of machineRepositories) {
    const repositoryKey = repository.name;
    addMachineToGroup(result, repositoryKey, machine);
  }
};

// Helper to handle grand repository grouping
const handleGrandGrouping = (
  machine: Machine,
  machineRepositories: DeployedRepo[],
  repositories: Repository[],
  result: Record<string, Machine[]>
): void => {
  for (const repository of machineRepositories) {
    let grandKey = 'No Grand Repository';
    if (repository.grandGuid) {
      const grandRepository = repositories.find((r) => r.repositoryGuid === repository.grandGuid);
      if (grandRepository) {
        grandKey = grandRepository.repositoryName;
      }
    }
    addMachineToGroup(result, grandKey, machine);
  }
};

// Helper to process a single machine for grouping
const processMachineForGrouping = (
  machine: Machine,
  groupBy: GroupByMode,
  repositories: Repository[],
  getMachineRepositories: (machine: Machine) => DeployedRepo[],
  result: Record<string, Machine[]>
): void => {
  const machineRepositories = getMachineRepositories(machine);

  // Handle special grouping types that require repository info
  if (groupBy === 'repository') {
    if (machineRepositories.length === 0) return;
    handleRepositoryGrouping(machine, machineRepositories, result);
    return;
  }

  if (groupBy === 'grand') {
    if (machineRepositories.length === 0) return;
    handleGrandGrouping(machine, machineRepositories, repositories, result);
    return;
  }

  if (groupBy === 'status') {
    const statusKey = getStatusKey(machineRepositories);
    addMachineToGroup(result, statusKey, machine);
    return;
  }

  // Handle basic grouping types
  const key = getBasicGroupKey(machine, groupBy);
  if (key !== '') {
    addMachineToGroup(result, key, machine);
  }
};

export function useGroupedMachines({
  machines,
  groupBy,
  repositories,
  getMachineRepositories,
}: UseGroupedMachinesProps): Record<string, Machine[]> {
  return useMemo(() => {
    const result: Record<string, Machine[]> = {};

    if (groupBy === 'machine') {
      // Don't group when showing normal machine view
      return result;
    }

    for (const machine of machines) {
      processMachineForGrouping(machine, groupBy, repositories, getMachineRepositories, result);
    }

    return result;
  }, [machines, groupBy, repositories, getMachineRepositories]);
}
