import { useEffect, useState } from 'react';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { parseVaultStatus } from '@rediacc/shared/services/machine';
import type { Container, Repository, VaultStatusRepo, VaultStatusResult } from '../types';

interface UseContainerParserProps {
  vaultStatus?: string;
  repository: Repository;
  refreshKey?: number;
  t: TypedTFunction;
}

interface UseContainerParserResult {
  loading: boolean;
  error: string | null;
  containers: Container[];
  pluginContainers: Container[];
}

function isContainerForRepository(
  container: Container,
  repositoryProps: Pick<Repository, 'mount_path' | 'image_path'>,
  vaultRepositories: VaultStatusRepo[] | undefined
): boolean {
  const containerRepoGuid = container.repository;
  if (!containerRepoGuid) return false;

  const vaultRepo = vaultRepositories?.find((r: VaultStatusRepo) => r.name === containerRepoGuid);
  if (!vaultRepo) return false;

  return (
    repositoryProps.mount_path === vaultRepo.mount_path ||
    repositoryProps.image_path === vaultRepo.image_path
  );
}

function extractContainersFromResult(
  result: VaultStatusResult,
  repositoryProps: Pick<Repository, 'mount_path' | 'image_path'>
): { regular: Container[]; plugins: Container[] } {
  const containerList = result.containers?.containers;
  if (!containerList || !Array.isArray(containerList)) {
    return { regular: [], plugins: [] };
  }

  const repoContainers = containerList.filter((container: Container) =>
    isContainerForRepository(container, repositoryProps, result.repositories)
  );

  return {
    plugins: repoContainers.filter((c: Container) => c.name.startsWith('plugin-')),
    regular: repoContainers.filter((c: Container) => !c.name.startsWith('plugin-')),
  };
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

        if (parsed.status !== 'completed' || !parsed.rawResult) {
          setContainers([]);
          setPluginContainers([]);
          setLoading(false);
          return;
        }

        const result = JSON.parse(parsed.rawResult) as VaultStatusResult;
        const repositoryProps = {
          mount_path: repository.mount_path,
          image_path: repository.image_path,
        };
        const { regular, plugins } = extractContainersFromResult(result, repositoryProps);
        setPluginContainers(plugins);
        setContainers(regular);
        setLoading(false);
      } catch (err: unknown) {
        const errorMessage =
          err instanceof Error ? err.message : t('resources:repositories.errorLoadingContainers');
        setError(errorMessage);
        setLoading(false);
      }
    };

    parseContainers();
  }, [vaultStatus, repository.image_path, repository.mount_path, refreshKey, t]);

  return { loading, error, containers, pluginContainers };
}
