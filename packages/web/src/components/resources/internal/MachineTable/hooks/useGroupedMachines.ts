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

    machines.forEach((machine) => {
      let key = '';
      switch (groupBy) {
        case 'bridge':
          key = machine.bridgeName ?? '';
          break;
        case 'team':
          key = machine.teamName ?? '';
          break;
        case 'region':
          key = machine.regionName ?? 'Unknown';
          break;
        case 'repository': {
          // For repository grouping, we'll handle this differently
          const machineRepositories = getMachineRepositories(machine);
          if (machineRepositories.length === 0) {
            // Skip machines without repositories
            return;
          }
          // Add machine to each repository it has
          machineRepositories.forEach((repository) => {
            const repositoryKey = repository.name;
            const existing = result[repositoryKey] as Machine[] | undefined;
            if (existing === undefined) result[repositoryKey] = [];
            if (!result[repositoryKey].find((m) => m.machineName === machine.machineName)) {
              result[repositoryKey].push(machine);
            }
          });
          return;
        }
        case 'status': {
          const machineRepositories = getMachineRepositories(machine);
          if (machineRepositories.length === 0) {
            key = 'No Repositories';
          } else {
            // Priority-based status assignment
            const hasInaccessible = machineRepositories.some((r) => !r.accessible);
            const hasRunning = machineRepositories.some((r) => r.mounted && r.docker_running);
            const hasStopped = machineRepositories.some((r) => r.mounted && !r.docker_running);
            const hasUnmounted = machineRepositories.some((r) => !r.mounted);

            if (hasInaccessible) {
              key = 'Inaccessible';
            } else if (hasRunning) {
              key = 'Active (Running)';
            } else if (hasStopped) {
              key = 'Ready (Stopped)';
            } else if (hasUnmounted) {
              key = 'Not Mounted';
            } else {
              key = 'Unknown Status';
            }
          }
          break;
        }
        case 'grand': {
          // Group by grand repository
          const machineRepositories = getMachineRepositories(machine);
          if (machineRepositories.length === 0) return;

          machineRepositories.forEach((repository) => {
            let grandKey = 'No Grand Repository';
            if (repository.grandGuid) {
              const grandRepository = repositories.find(
                (r) => r.repositoryGuid === repository.grandGuid
              );
              if (grandRepository) {
                grandKey = grandRepository.repositoryName;
              }
            }
            const existing = result[grandKey] as Machine[] | undefined;
            if (existing === undefined) result[grandKey] = [];
            if (!result[grandKey].find((m) => m.machineName === machine.machineName)) {
              result[grandKey].push(machine);
            }
          });
          return;
        }
        default:
          break;
      }

      // Add machine to result for non-special grouping types
      if (key !== '') {
        const existing = result[key] as Machine[] | undefined;
        if (existing === undefined) result[key] = [];
        result[key].push(machine);
      }
    });

    return result;
  }, [machines, groupBy, repositories, getMachineRepositories]);
}
