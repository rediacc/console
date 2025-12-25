import { useEffect, useState } from 'react';
import { isValidGuid } from '@/platform/utils/formValidation';
import type { Machine } from '@/types';
import { parseVaultStatus } from '@rediacc/shared/services/machine';
import type { GetTeamRepositories_ResultSet1 as TeamRepo } from '@rediacc/shared/types';
import { groupRepositoriesByName } from '../utils';
import type {
  Container,
  GroupedRepository,
  Repository,
  RepositoryContainersState,
  RepositoryService,
  RepositoryServicesState,
  SystemInfo,
} from '../types';

interface UseRepoTableStateProps {
  machine: Machine;
  teamRepositories: TeamRepo[];
  repositoriesLoading: boolean;
  refreshKey?: number;
}

interface UseRepoTableStateReturn {
  repositories: Repository[];
  systemInfo: SystemInfo | null;
  loading: boolean;
  error: string | null;
  servicesData: Record<string, RepositoryServicesState>;
  containersData: Record<string, RepositoryContainersState>;
  groupedRepositories: GroupedRepository[];
  setRepos: React.Dispatch<React.SetStateAction<Repository[]>>;
  setServicesData: React.Dispatch<React.SetStateAction<Record<string, RepositoryServicesState>>>;
  setContainersData: React.Dispatch<
    React.SetStateAction<Record<string, RepositoryContainersState>>
  >;
}

export const useRepositoryTableState = ({
  machine,
  teamRepositories,
  repositoriesLoading,
  refreshKey,
}: UseRepoTableStateProps): UseRepoTableStateReturn => {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [servicesData, setServicesData] = useState<Record<string, RepositoryServicesState>>({});
  const [containersData, setContainersData] = useState<Record<string, RepositoryContainersState>>(
    {}
  );
  const [groupedRepositories, setGroupedRepositories] = useState<GroupedRepository[]>([]);

  useEffect(() => {
    if (repositoriesLoading) {
      // Still loading
    } else if (machine.vaultStatus) {
      const parsed = parseVaultStatus(machine.vaultStatus);

      if (parsed.error) {
        setError('Invalid Repository data');
        setLoading(false);
      } else if (parsed.status === 'completed' && parsed.rawResult) {
        try {
          const result = JSON.parse(parsed.rawResult);
          if (result) {
            if (result.system) {
              setSystemInfo(result.system);
            }

            if (result.repositories && Array.isArray(result.repositories)) {
              const mappedRepositories = result.repositories.map((repository: Repository) => {
                const isGuid = isValidGuid(repository.name);

                if (isGuid) {
                  const matchingRepo = teamRepositories.find(
                    (r) => r.repositoryGuid === repository.name
                  );
                  if (matchingRepo) {
                    return {
                      ...repository,
                      name: matchingRepo.repositoryName,
                      repositoryTag: matchingRepo.repositoryTag,
                      isUnmapped: false,
                    };
                  }
                  return {
                    ...repository,
                    isUnmapped: true,
                    originalGuid: repository.name,
                  };
                }

                return {
                  ...repository,
                  isUnmapped: false,
                };
              });

              const reposWithPluginCounts = mappedRepositories.map((repository: Repository) => {
                let pluginCount = 0;

                if (result.containers && Array.isArray(result.containers)) {
                  result.containers.forEach((container: Container) => {
                    const belongsToRepo = container.Repository === repository.name;
                    if (belongsToRepo && container.name.startsWith('plugin-')) {
                      pluginCount++;
                    }
                  });
                }

                return {
                  ...repository,
                  plugin_count: pluginCount,
                };
              });

              const sortedRepos = reposWithPluginCounts.sort((a: Repository, b: Repository) => {
                const aData = teamRepositories.find(
                  (r) => r.repositoryName === a.name && r.repositoryTag === a.repositoryTag
                );
                const bData = teamRepositories.find(
                  (r) => r.repositoryName === b.name && r.repositoryTag === b.repositoryTag
                );

                const aFamily = aData?.grandGuid
                  ? (teamRepositories.find((r) => r.repositoryGuid === aData.grandGuid)
                      ?.repositoryName ?? a.name)
                  : a.name;
                const bFamily = bData?.grandGuid
                  ? (teamRepositories.find((r) => r.repositoryGuid === bData.grandGuid)
                      ?.repositoryName ?? b.name)
                  : b.name;

                if (aFamily !== bFamily) {
                  return aFamily.localeCompare(bFamily);
                }

                const aIsOriginal = !aData?.parentGuid;
                const bIsOriginal = !bData?.parentGuid;

                if (aIsOriginal !== bIsOriginal) {
                  return aIsOriginal ? -1 : 1;
                }

                return a.name.localeCompare(b.name);
              });

              setRepositories(sortedRepos);

              const grouped = groupRepositoriesByName(sortedRepos, teamRepositories);
              setGroupedRepositories(grouped);

              if (result.containers && Array.isArray(result.containers)) {
                const containersMap: Record<string, RepositoryContainersState> = {};

                mappedRepositories.forEach((repository: Repository) => {
                  containersMap[repository.name] = { containers: [], error: null };
                });

                result.containers.forEach((container: Container) => {
                  if (container.Repository) {
                    const repositoryGuid = container.Repository;
                    const mappedRepo = mappedRepositories.find((repository: Repository) => {
                      const originalRepo = result.repositories.find(
                        (r: Repository) => r.name === repositoryGuid
                      );
                      if (!originalRepo) return false;
                      return (
                        repository.mount_path === originalRepo.mount_path ||
                        repository.image_path === originalRepo.image_path
                      );
                    });
                    if (mappedRepo) {
                      containersMap[mappedRepo.name].containers.push(container);
                    }
                  }
                });

                setContainersData(containersMap);
              }

              if (result.services && Array.isArray(result.services)) {
                const servicesMap: Record<string, RepositoryServicesState> = {};

                mappedRepositories.forEach((repository: Repository) => {
                  servicesMap[repository.name] = { services: [], error: null };
                });

                result.services.forEach((service: RepositoryService) => {
                  if (service.Repository) {
                    const repositoryGuid = service.Repository;
                    const mappedRepo = mappedRepositories.find((repository: Repository) => {
                      const originalRepo = result.repositories.find(
                        (r: Repository) => r.name === repositoryGuid
                      );
                      if (!originalRepo) return false;
                      return (
                        repository.mount_path === originalRepo.mount_path ||
                        repository.image_path === originalRepo.image_path
                      );
                    });
                    if (mappedRepo) {
                      servicesMap[mappedRepo.name].services.push(service);
                    }
                  } else if (service.service_name || service.unit_file) {
                    const serviceName = service.service_name ?? service.unit_file ?? '';
                    const guidMatch = serviceName.match(/rediacc_([0-9a-f-]{36})_/);
                    if (guidMatch) {
                      const repositoryGuid = guidMatch[1];
                      const mappedRepo = mappedRepositories.find((repository: Repository) => {
                        const originalRepo = result.repositories.find(
                          (r: Repository) => r.name === repositoryGuid
                        );
                        if (!originalRepo) return false;
                        return (
                          repository.mount_path === originalRepo.mount_path ||
                          repository.image_path === originalRepo.image_path
                        );
                      });
                      if (mappedRepo) {
                        servicesMap[mappedRepo.name].services.push(service);
                      }
                    }
                  }
                });

                setServicesData(servicesMap);
              }
            } else {
              setRepositories([]);
            }

            setLoading(false);
          }
        } catch {
          setError('Failed to parse Repository data');
          setLoading(false);
        }
      }
    } else {
      setRepositories([]);
      setLoading(false);
    }
  }, [machine, repositoriesLoading, teamRepositories, refreshKey]);

  return {
    repositories,
    systemInfo,
    loading,
    error,
    servicesData,
    containersData,
    groupedRepositories,
    setRepos: setRepositories,
    setServicesData,
    setContainersData,
  };
};
