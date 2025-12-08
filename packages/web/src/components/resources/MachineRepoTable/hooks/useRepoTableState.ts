import { useState, useEffect } from 'react';
import type { GetTeamRepositories_ResultSet1 as TeamRepo } from '@rediacc/shared/types';
import { parseVaultStatus } from '@rediacc/shared/services/machine';
import { isValidGuid } from '@/platform/utils/validation';
import type {
  Repo,
  SystemInfo,
  GroupedRepo,
  RepoServicesState,
  RepoContainersState,
  Container,
  RepoService,
} from '../types';
import { groupReposByName } from '../utils';
import type { Machine } from '@/types';

interface UseRepoTableStateProps {
  machine: Machine;
  teamRepos: TeamRepo[];
  reposLoading: boolean;
  refreshKey?: number;
}

interface UseRepoTableStateReturn {
  repos: Repo[];
  systemInfo: SystemInfo | null;
  loading: boolean;
  error: string | null;
  servicesData: Record<string, RepoServicesState>;
  containersData: Record<string, RepoContainersState>;
  groupedRepos: GroupedRepo[];
  setRepos: React.Dispatch<React.SetStateAction<Repo[]>>;
  setServicesData: React.Dispatch<React.SetStateAction<Record<string, RepoServicesState>>>;
  setContainersData: React.Dispatch<React.SetStateAction<Record<string, RepoContainersState>>>;
}

export const useRepoTableState = ({
  machine,
  teamRepos,
  reposLoading,
  refreshKey,
}: UseRepoTableStateProps): UseRepoTableStateReturn => {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [servicesData, setServicesData] = useState<Record<string, RepoServicesState>>({});
  const [containersData, setContainersData] = useState<Record<string, RepoContainersState>>({});
  const [groupedRepos, setGroupedRepos] = useState<GroupedRepo[]>([]);

  useEffect(() => {
    if (!reposLoading && machine) {
      if (machine.vaultStatus) {
        const parsed = parseVaultStatus(machine.vaultStatus);

        if (parsed.error) {
          setError('Invalid Repo data');
          setLoading(false);
        } else if (parsed.status === 'completed' && parsed.rawResult) {
          try {
            const result = JSON.parse(parsed.rawResult);
            if (result) {
              if (result.system) {
                setSystemInfo(result.system);
              }

              if (result.repositories && Array.isArray(result.repositories)) {
                const mappedRepos = result.repositories.map((repo: Repo) => {
                  const isGuid = isValidGuid(repo.name);

                  if (isGuid) {
                    const matchingRepo = teamRepos.find((r) => r.repoGuid === repo.name);
                    if (matchingRepo) {
                      return {
                        ...repo,
                        name: matchingRepo.repoName,
                        repoTag: matchingRepo.repoTag,
                        isUnmapped: false,
                      };
                    } else {
                      return {
                        ...repo,
                        isUnmapped: true,
                        originalGuid: repo.name,
                      };
                    }
                  }

                  return {
                    ...repo,
                    isUnmapped: false,
                  };
                });

                const reposWithPluginCounts = mappedRepos.map((repo: Repo) => {
                  let pluginCount = 0;

                  if (result.containers && Array.isArray(result.containers)) {
                    result.containers.forEach((container: Container) => {
                      const belongsToRepo = container.Repo === repo.name;
                      if (belongsToRepo && container.name && container.name.startsWith('plugin-')) {
                        pluginCount++;
                      }
                    });
                  }

                  return {
                    ...repo,
                    plugin_count: pluginCount,
                  };
                });

                const sortedRepos = reposWithPluginCounts.sort((a: Repo, b: Repo) => {
                  const aData = teamRepos.find(
                    (r) => r.repoName === a.name && r.repoTag === a.repoTag
                  );
                  const bData = teamRepos.find(
                    (r) => r.repoName === b.name && r.repoTag === b.repoTag
                  );

                  const aFamily = aData?.grandGuid
                    ? teamRepos.find((r) => r.repoGuid === aData.grandGuid)?.repoName || a.name
                    : a.name;
                  const bFamily = bData?.grandGuid
                    ? teamRepos.find((r) => r.repoGuid === bData.grandGuid)?.repoName || b.name
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

                setRepos(sortedRepos);

                const grouped = groupReposByName(sortedRepos, teamRepos);
                setGroupedRepos(grouped);

                if (result.containers && Array.isArray(result.containers)) {
                  const containersMap: Record<string, RepoContainersState> = {};

                  mappedRepos.forEach((repo: Repo) => {
                    containersMap[repo.name] = { containers: [], error: null };
                  });

                  result.containers.forEach((container: Container) => {
                    if (container.Repo) {
                      const repoGuid = container.Repo;
                      const mappedRepo = mappedRepos.find((repo: Repo) => {
                        const originalRepo = result.repositories.find(
                          (r: Repo) => r.name === repoGuid
                        );
                        if (!originalRepo) return false;
                        return (
                          repo.mount_path === originalRepo.mount_path ||
                          repo.image_path === originalRepo.image_path
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
                  const servicesMap: Record<string, RepoServicesState> = {};

                  mappedRepos.forEach((repo: Repo) => {
                    servicesMap[repo.name] = { services: [], error: null };
                  });

                  result.services.forEach((service: RepoService) => {
                    if (service.Repo) {
                      const repoGuid = service.Repo;
                      const mappedRepo = mappedRepos.find((repo: Repo) => {
                        const originalRepo = result.repositories.find(
                          (r: Repo) => r.name === repoGuid
                        );
                        if (!originalRepo) return false;
                        return (
                          repo.mount_path === originalRepo.mount_path ||
                          repo.image_path === originalRepo.image_path
                        );
                      });
                      if (mappedRepo) {
                        servicesMap[mappedRepo.name].services.push(service);
                      }
                    } else if (service.service_name || service.unit_file) {
                      const serviceName = service.service_name || service.unit_file || '';
                      const guidMatch = serviceName.match(/rediacc_([0-9a-f-]{36})_/);
                      if (guidMatch) {
                        const repoGuid = guidMatch[1];
                        const mappedRepo = mappedRepos.find((repo: Repo) => {
                          const originalRepo = result.repositories.find(
                            (r: Repo) => r.name === repoGuid
                          );
                          if (!originalRepo) return false;
                          return (
                            repo.mount_path === originalRepo.mount_path ||
                            repo.image_path === originalRepo.image_path
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
                setRepos([]);
              }

              setLoading(false);
            }
          } catch {
            setError('Failed to parse Repo data');
            setLoading(false);
          }
        }
      } else {
        setRepos([]);
        setLoading(false);
      }
    }
  }, [machine, reposLoading, teamRepos, refreshKey]);

  return {
    repos,
    systemInfo,
    loading,
    error,
    servicesData,
    containersData,
    groupedRepos,
    setRepos,
    setServicesData,
    setContainersData,
  };
};
