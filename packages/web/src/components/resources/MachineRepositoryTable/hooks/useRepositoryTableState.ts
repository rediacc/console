import {
  getContainers,
  getServices,
  isListResult,
} from '@rediacc/shared/queue-vault/data/list-types.generated';
import { parseVaultStatus } from '@rediacc/shared/services/machine';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import { useMemo, useState } from 'react';
import { isValidGuid } from '@/platform/utils/formValidation';
import type { Machine } from '@/types';
import type {
  Container,
  GroupedRepository,
  Repository,
  RepositoryContainersState,
  RepositoryService,
  RepositoryServicesState,
  SystemInfo,
} from '../types';
import { groupRepositoriesByName } from '../utils';

interface UseRepoTableStateProps {
  machine: Machine;
  teamRepositories: GetTeamRepositories_ResultSet1[];
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

// Helper to map a single repository from GUID to name
const mapRepository = (
  repository: Repository,
  teamRepositories: GetTeamRepositories_ResultSet1[]
): Repository => {
  const isGuid = isValidGuid(repository.name);

  if (!isGuid) {
    return { ...repository, isUnmapped: false };
  }

  const matchingRepo = teamRepositories.find((r) => r.repositoryGuid === repository.name);
  if (matchingRepo) {
    return {
      ...repository,
      name: matchingRepo.repositoryName ?? repository.name,
      repositoryTag: matchingRepo.repositoryTag ?? undefined,
      isUnmapped: false,
    };
  }

  return {
    ...repository,
    isUnmapped: true,
    originalGuid: repository.name,
  };
};

// Helper to count plugins for a repository
const countPlugins = (repository: Repository, containers: Container[]): number => {
  let count = 0;
  for (const container of containers) {
    const belongsToRepo = container.Repository === repository.name;
    if (belongsToRepo && container.name.startsWith('plugin-')) {
      count++;
    }
  }
  return count;
};

// Helper to get family name for sorting
const getFamilyName = (
  repoData: GetTeamRepositories_ResultSet1 | undefined,
  teamRepositories: GetTeamRepositories_ResultSet1[],
  fallbackName: string
): string => {
  if (!repoData?.grandGuid) return fallbackName;

  const grandRepo = teamRepositories.find((r) => r.repositoryGuid === repoData.grandGuid);
  return grandRepo?.repositoryName ?? fallbackName;
};

// Helper to sort repositories
const sortRepositories = (
  repos: Repository[],
  teamRepositories: GetTeamRepositories_ResultSet1[]
): Repository[] => {
  return repos.sort((a, b) => {
    const aData = teamRepositories.find(
      (r) => r.repositoryName === a.name && r.repositoryTag === a.repositoryTag
    );
    const bData = teamRepositories.find(
      (r) => r.repositoryName === b.name && r.repositoryTag === b.repositoryTag
    );

    const aFamily = getFamilyName(aData, teamRepositories, a.name);
    const bFamily = getFamilyName(bData, teamRepositories, b.name);

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
};

// Helper to find mapped repository by container
const findMappedRepoByContainer = (
  container: { Repository?: string },
  mappedRepositories: Repository[],
  rawRepositories: Repository[]
): Repository | undefined => {
  const repositoryGuid = container.Repository;
  if (!repositoryGuid) return undefined;

  return mappedRepositories.find((repository) => {
    const originalRepo = rawRepositories.find((r) => r.name === repositoryGuid);
    if (!originalRepo) return false;
    return (
      repository.mount_path === originalRepo.mount_path ||
      repository.image_path === originalRepo.image_path
    );
  });
};

// Helper to build containers map
const buildContainersMap = (
  mappedRepositories: Repository[],
  containers: Container[],
  rawRepositories: Repository[]
): Record<string, RepositoryContainersState> => {
  const containersMap: Record<string, RepositoryContainersState> = {};

  // Initialize empty containers for all repositories
  for (const repository of mappedRepositories) {
    containersMap[repository.name] = { containers: [], error: null };
  }

  // Map containers to repositories
  for (const container of containers) {
    if (!container.Repository) continue;

    const mappedRepo = findMappedRepoByContainer(container, mappedRepositories, rawRepositories);
    if (mappedRepo) {
      containersMap[mappedRepo.name].containers.push(container);
    }
  }

  return containersMap;
};

// Helper to extract GUID from service name
const extractGuidFromServiceName = (serviceName: string): string | null => {
  const guidMatch = /rediacc_([0-9a-f-]{36})_/.exec(serviceName);
  return guidMatch ? guidMatch[1] : null;
};

// Helper to check if service matches repository
const serviceMatchesRepository = (
  service: RepositoryService,
  repositoryData: Repository,
  repositoryGuid: string
): boolean => {
  if (service.repository === repositoryData.name || service.repository === repositoryGuid) {
    return true;
  }

  const serviceName = service.service_name ?? service.unit_file ?? '';
  const extractedGuid = extractGuidFromServiceName(serviceName);

  return Boolean(
    extractedGuid && (extractedGuid === repositoryGuid || extractedGuid === repositoryData.name)
  );
};

// Helper to check if paths match between mapped and original repository
const pathsMatch = (mappedRepo: Repository, originalRepo: Repository): boolean => {
  return (
    mappedRepo.mount_path === originalRepo.mount_path ||
    mappedRepo.image_path === originalRepo.image_path
  );
};

// Helper to assign service to repository if it matches
const tryAssignServiceToRepo = (
  service: RepositoryService,
  mappedRepo: Repository,
  repositoryGuid: string,
  rawRepositories: Repository[],
  servicesMap: Record<string, RepositoryServicesState>
): boolean => {
  if (!serviceMatchesRepository(service, mappedRepo, repositoryGuid)) {
    return false;
  }

  const originalRepo = rawRepositories.find((r) => r.name === repositoryGuid);
  if (!originalRepo || !pathsMatch(mappedRepo, originalRepo)) {
    return false;
  }

  servicesMap[mappedRepo.name].services.push(service);
  return true;
};

// Helper to build services map
const buildServicesMap = (
  mappedRepositories: Repository[],
  services: RepositoryService[],
  rawRepositories: Repository[],
  teamRepositories: GetTeamRepositories_ResultSet1[]
): Record<string, RepositoryServicesState> => {
  const servicesMap: Record<string, RepositoryServicesState> = {};

  // Initialize empty services for all repositories
  for (const repository of mappedRepositories) {
    servicesMap[repository.name] = { services: [], error: null };
  }

  // Map services to repositories
  for (const service of services) {
    for (const mappedRepo of mappedRepositories) {
      const teamRepo = teamRepositories.find(
        (r) => r.repositoryName === mappedRepo.name && r.repositoryTag === mappedRepo.repositoryTag
      );
      const repositoryGuid = teamRepo?.repositoryGuid ?? '';

      const assigned = tryAssignServiceToRepo(
        service,
        mappedRepo,
        repositoryGuid,
        rawRepositories,
        servicesMap
      );
      if (assigned) break; // Service assigned, move to next service
    }
  }

  return servicesMap;
};

// Helper to process parsed result
interface ProcessedResult {
  systemInfo: SystemInfo | null;
  repositories: Repository[];
  containersMap: Record<string, RepositoryContainersState>;
  servicesMap: Record<string, RepositoryServicesState>;
  grouped: GroupedRepository[];
}

const processVaultResult = (
  result: unknown,
  teamRepositories: GetTeamRepositories_ResultSet1[]
): ProcessedResult | null => {
  if (!result || typeof result !== 'object') return null;

  // Use type guard to validate result structure
  if (!isListResult(result)) {
    // Fallback for non-standard result format
    const legacyResult = result as { system?: SystemInfo; repositories?: Repository[] };
    const systemInfo = legacyResult.system ?? null;

    if (!legacyResult.repositories || !Array.isArray(legacyResult.repositories)) {
      return {
        systemInfo,
        repositories: [],
        containersMap: {},
        servicesMap: {},
        grouped: [],
      };
    }

    // Handle legacy format with no containers/services
    const mappedRepositories = legacyResult.repositories.map((repo) =>
      mapRepository(repo, teamRepositories)
    );
    const sortedRepos = sortRepositories(mappedRepositories, teamRepositories);
    const grouped = groupRepositoriesByName(sortedRepos, teamRepositories);

    return {
      systemInfo,
      repositories: sortedRepos,
      containersMap: {},
      servicesMap: {},
      grouped,
    };
  }

  // result.system is optional in ListResult, result.repositories is required
  const systemInfo = (result.system as SystemInfo | undefined) ?? null;
  const rawRepositories = result.repositories as Repository[];
  // Use proper extraction functions to get nested arrays
  const containers = getContainers(result) as unknown as Container[];
  const services = getServices(result) as unknown as RepositoryService[];

  // Map repositories
  const mappedRepositories = rawRepositories.map((repo) => mapRepository(repo, teamRepositories));

  // Add plugin counts
  const reposWithPlugins = mappedRepositories.map((repo) => ({
    ...repo,
    plugin_count: countPlugins(repo, containers),
  }));

  // Sort repositories
  const sortedRepos = sortRepositories(reposWithPlugins, teamRepositories);

  // Build containers map
  const containersMap = buildContainersMap(mappedRepositories, containers, rawRepositories);

  // Build services map
  const servicesMap = buildServicesMap(
    mappedRepositories,
    services,
    rawRepositories,
    teamRepositories
  );

  // Group repositories
  const grouped = groupRepositoriesByName(sortedRepos, teamRepositories);

  return {
    systemInfo,
    repositories: sortedRepos,
    containersMap,
    servicesMap,
    grouped,
  };
};

// Helper to handle error state
const getErrorMessage = (errorType: string): string => {
  if (errorType === 'encrypted') {
    return 'Machine status is encrypted. Enter master password to view.';
  }
  return 'Invalid Repository data';
};

// Helper to compute derived state from vault status
interface DerivedState {
  repositories: Repository[];
  systemInfo: SystemInfo | null;
  error: string | null;
  servicesData: Record<string, RepositoryServicesState>;
  containersData: Record<string, RepositoryContainersState>;
  groupedRepositories: GroupedRepository[];
}

const computeDerivedState = (
  machine: Machine,
  teamRepositories: GetTeamRepositories_ResultSet1[],
  repositoriesLoading: boolean
): DerivedState => {
  const emptyState: DerivedState = {
    repositories: [],
    systemInfo: null,
    error: null,
    servicesData: {},
    containersData: {},
    groupedRepositories: [],
  };

  // Still loading
  if (repositoriesLoading) return emptyState;

  // No vault status
  if (!machine.vaultStatus) return emptyState;

  const parsed = parseVaultStatus(machine.vaultStatus);

  // Handle error states
  if (parsed.error) {
    return { ...emptyState, error: getErrorMessage(parsed.error) };
  }

  // Check for completed status with raw result
  if (parsed.status !== 'completed' || !parsed.rawResult) return emptyState;

  // Parse and process the result
  try {
    const result: unknown = JSON.parse(parsed.rawResult);
    const processed = processVaultResult(result, teamRepositories);

    if (!processed) return emptyState;

    return {
      repositories: processed.repositories,
      systemInfo: processed.systemInfo,
      error: null,
      servicesData: processed.servicesMap,
      containersData: processed.containersMap,
      groupedRepositories: processed.grouped,
    };
  } catch {
    return { ...emptyState, error: 'Failed to parse Repository data' };
  }
};

export const useRepositoryTableState = ({
  machine,
  teamRepositories,
  repositoriesLoading,
  refreshKey,
}: UseRepoTableStateProps): UseRepoTableStateReturn => {
  // Use useMemo to compute derived state without triggering cascading renders
  const derivedState = useMemo(
    () => computeDerivedState(machine, teamRepositories, repositoriesLoading),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refreshKey is used to force recalculation
    [machine, teamRepositories, repositoriesLoading, refreshKey]
  );

  // Keep these as state for imperative updates from parent components
  const [repositoriesOverride, setRepositoriesOverride] = useState<Repository[] | null>(null);
  const [servicesDataOverride, setServicesDataOverride] = useState<Record<
    string,
    RepositoryServicesState
  > | null>(null);
  const [containersDataOverride, setContainersDataOverride] = useState<Record<
    string,
    RepositoryContainersState
  > | null>(null);

  // Merge derived state with overrides
  const repositories = repositoriesOverride ?? derivedState.repositories;
  const servicesData = servicesDataOverride ?? derivedState.servicesData;
  const containersData = containersDataOverride ?? derivedState.containersData;

  return {
    repositories,
    systemInfo: derivedState.systemInfo,
    loading: false,
    error: derivedState.error,
    servicesData,
    containersData,
    groupedRepositories: derivedState.groupedRepositories,
    setRepos: setRepositoriesOverride as React.Dispatch<React.SetStateAction<Repository[]>>,
    setServicesData: setServicesDataOverride as React.Dispatch<
      React.SetStateAction<Record<string, RepositoryServicesState>>
    >,
    setContainersData: setContainersDataOverride as React.Dispatch<
      React.SetStateAction<Record<string, RepositoryContainersState>>
    >,
  };
};
