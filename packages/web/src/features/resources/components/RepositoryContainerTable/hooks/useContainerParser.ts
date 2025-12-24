import { useEffect, useState } from 'react';
import { parseVaultStatus } from '@rediacc/shared/services/machine';
import type { Container, Repository, VaultStatusRepo, VaultStatusResult } from '../types';
import type { TFunction } from 'i18next';

interface UseContainerParserProps {
  vaultStatus?: string;
  repository: Repository;
  refreshKey?: number;
  t: TFunction;
}

interface UseContainerParserResult {
  loading: boolean;
  error: string | null;
  containers: Container[];
  pluginContainers: Container[];
}

export function useContainerParser({
  vaultStatus,
  repository,
  refreshKey,
  t,
}: UseContainerParserProps): UseContainerParserResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [containers, setContainers] = useState<Container[]>([]);
  const [pluginContainers, setPluginContainers] = useState<Container[]>([]);

  useEffect(() => {
    const parseContainers = () => {
      setLoading(true);
      setError(null);

      try {
        if (!vaultStatus) {
          setContainers([]);
          setPluginContainers([]);
          setLoading(false);
          return;
        }

        const parsed = parseVaultStatus(vaultStatus);

        if (parsed.error) {
          setError('Invalid repository data');
          setLoading(false);
          return;
        }

        if (parsed.status === 'completed' && parsed.rawResult) {
          const result = JSON.parse(parsed.rawResult) as VaultStatusResult;

          if (
            result &&
            result.containers?.containers &&
            Array.isArray(result.containers.containers)
          ) {
            const repoContainers = result.containers.containers.filter((container: Container) => {
              const containerRepoGuid = container.repository;

              if (!containerRepoGuid) {
                return false;
              }

              const vaultRepo = result.repositories?.find(
                (r: VaultStatusRepo) => r.name === containerRepoGuid
              );

              if (!vaultRepo) {
                return false;
              }

              return (
                repository.mount_path === vaultRepo.mount_path ||
                repository.image_path === vaultRepo.image_path
              );
            });

            const plugins = repoContainers.filter(
              (c: Container) => c.name && c.name.startsWith('plugin-')
            );

            const regular = repoContainers.filter(
              (c: Container) => !c.name || !c.name.startsWith('plugin-')
            );

            setPluginContainers(plugins);
            setContainers(regular);
          } else {
            setContainers([]);
            setPluginContainers([]);
          }
        } else {
          setContainers([]);
          setPluginContainers([]);
        }

        setLoading(false);
      } catch (err: unknown) {
        const errorMessage =
          err instanceof Error ? err.message : t('resources:repositories.errorLoadingContainers');
        setError(errorMessage);
        setLoading(false);
      }
    };

    parseContainers();
  }, [vaultStatus, repository.image_path, repository.mount_path, repository.name, refreshKey, t]);

  return { loading, error, containers, pluginContainers };
}
