import type { Machine } from '@/types';
import { parseListResult } from '@rediacc/shared/services/machine';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import type { RepositoryPanelData, RepositoryVaultData, ServiceData } from '../types';

// Helper to check if service matches repository
const serviceMatchesRepository = (
  service: ServiceData,
  repositoryData: RepositoryVaultData,
  repositoryGuid: string
): boolean => {
  // Direct repository match
  if (service.repository === repositoryData.name || service.repository === repositoryGuid) {
    return true;
  }

  // Extract GUID from service name
  const serviceName = service.service_name ?? service.unit_file ?? '';
  const guidMatch = /rediacc_([0-9a-f-]{36})_/.exec(serviceName);

  if (!guidMatch) return false;

  return guidMatch[1] === repositoryGuid || guidMatch[1] === repositoryData.name;
};

// Helper to find services for a repository
const findServicesForRepository = (
  services: ServiceData[],
  repositoryData: RepositoryVaultData,
  repositoryGuid: string
): ServiceData[] => {
  const result: ServiceData[] = [];

  for (const service of services) {
    if (serviceMatchesRepository(service, repositoryData, repositoryGuid)) {
      result.push(service);
    }
  }

  return result;
};

// Helper to find repository data in machine vault
const findRepositoryInMachine = (
  machine: Machine,
  repository: GetTeamRepositories_ResultSet1
): RepositoryPanelData | null => {
  if (!machine.vaultStatus) return null;

  const listResult = parseListResult(machine.vaultStatus);
  if (!listResult || !Array.isArray(listResult.repositories)) return null;

  const repositoryData = listResult.repositories.find((r) => {
    return r.name === repository.repositoryName || r.name === repository.repositoryGuid;
  }) as RepositoryVaultData | undefined;

  if (!repositoryData) return null;

  const services = listResult.services?.services ?? [];
  const servicesForRepo =
    Array.isArray(services) && repository.repositoryGuid
      ? findServicesForRepository(services, repositoryData, repository.repositoryGuid)
      : [];

  return {
    machine,
    repositoryData,
    systemData: listResult.system,
    services: servicesForRepo,
  };
};

export const useRepositoryVaultData = (
  repository: GetTeamRepositories_ResultSet1 | null,
  machines: Machine[]
): RepositoryPanelData | null => {
  if (!repository || !machines.length) return null;

  for (const machine of machines) {
    const result = findRepositoryInMachine(machine, repository);
    if (result) return result;
  }

  return null;
};
