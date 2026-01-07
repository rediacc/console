import type { Machine } from '@/types';
import { parseListResult } from '@rediacc/shared/services/machine';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import type { RepositoryPanelData, RepositoryVaultData, ServiceData } from '../types';

export const useRepositoryVaultData = (
  repository: GetTeamRepositories_ResultSet1 | null,
  machines: Machine[]
): RepositoryPanelData | null => {
  if (!repository || !machines.length) return null;

  for (const machine of machines) {
    if (!machine.vaultStatus) continue;

    const listResult = parseListResult(machine.vaultStatus);
    if (!listResult || !Array.isArray(listResult.repositories)) continue;

    const repositoryData = listResult.repositories.find((r) => {
      return r.name === repository.repositoryName || r.name === repository.repositoryGuid;
    }) as RepositoryVaultData | undefined;

    if (repositoryData) {
      const servicesForRepo: ServiceData[] = [];
      const services = listResult.services?.services ?? [];

      if (Array.isArray(services)) {
        services.forEach((service: ServiceData) => {
          if (
            service.repository === repositoryData.name ||
            service.repository === repository.repositoryGuid
          ) {
            servicesForRepo.push(service);
            return;
          }

          const serviceName = service.service_name ?? service.unit_file ?? '';
          const guidMatch = serviceName.match(/rediacc_([0-9a-f-]{36})_/);
          if (
            guidMatch &&
            (guidMatch[1] === repository.repositoryGuid || guidMatch[1] === repositoryData.name)
          ) {
            servicesForRepo.push(service);
          }
        });
      }

      return {
        machine,
        repositoryData,
        systemData: listResult.system,
        services: servicesForRepo,
      };
    }
  }

  return null;
};
