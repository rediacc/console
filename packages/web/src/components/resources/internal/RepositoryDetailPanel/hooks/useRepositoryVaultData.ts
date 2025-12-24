import { useMemo } from 'react';
import type { Machine } from '@/types';
import type { GetTeamRepositories_ResultSet1 as Repository } from '@rediacc/shared/types';
import type { RepositoryPanelData, RepositoryVaultData, ServiceData } from '../types';

export const useRepositoryVaultData = (
  repository: Repository | null,
  machines: Machine[]
): RepositoryPanelData | null => {
  return useMemo<RepositoryPanelData | null>(() => {
    if (!repository || !machines.length) return null;

    for (const machine of machines) {
      if (!machine.vaultStatus) continue;

      try {
        const trimmedStatus = machine.vaultStatus.trim();
        if (
          trimmedStatus.startsWith('jq:') ||
          trimmedStatus.startsWith('error:') ||
          !trimmedStatus.startsWith('{')
        ) {
          continue;
        }

        const vaultStatusData = JSON.parse(trimmedStatus);

        if (vaultStatusData.status === 'completed' && vaultStatusData.result) {
          let cleanedResult = vaultStatusData.result;
          const jsonEndMatch = cleanedResult.match(/(\}[\s\n]*$)/);
          if (jsonEndMatch) {
            const lastBraceIndex = cleanedResult.lastIndexOf('}');
            if (lastBraceIndex < cleanedResult.length - 10) {
              cleanedResult = cleanedResult.substring(0, lastBraceIndex + 1);
            }
          }

          const newlineIndex = cleanedResult.indexOf('\njq:');
          if (newlineIndex > 0) {
            cleanedResult = cleanedResult.substring(0, newlineIndex);
          }

          const result = JSON.parse(cleanedResult.trim());

          if (Array.isArray(result.repositories)) {
            const repositoryData = result.repositories.find((r: RepositoryVaultData) => {
              return r.name === repository.repositoryName || r.name === repository.repositoryGuid;
            });

            if (repositoryData) {
              const servicesForRepo: ServiceData[] = [];

              if (Array.isArray(result.services)) {
                result.services.forEach((service: ServiceData) => {
                  if (
                    service.repository === repositoryData.name ||
                    service.repository === repository.repositoryGuid
                  ) {
                    servicesForRepo.push(service);
                    return;
                  }

                  const serviceName = service.service_name || service.unit_file || '';
                  const guidMatch = serviceName.match(/rediacc_([0-9a-f-]{36})_/);
                  if (
                    guidMatch &&
                    (guidMatch[1] === repository.repositoryGuid ||
                      guidMatch[1] === repositoryData.name)
                  ) {
                    servicesForRepo.push(service);
                  }
                });
              }

              return {
                machine,
                repositoryData: repositoryData,
                systemData: result.system,
                services: servicesForRepo,
              };
            }
          }
        }
      } catch (error) {
        console.error('Error parsing vault status:', error);
      }
    }

    return null;
  }, [repository, machines]);
};
