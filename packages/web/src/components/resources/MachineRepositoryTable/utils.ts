import { isAxiosError } from 'axios';
import type { GetTeamRepositories_ResultSet1 as TeamRepo } from '@rediacc/shared/types';
import type { GroupedRepository, Repository } from './types';

export const getRepositoryDisplayName = (repository: Repository): string => {
  return `${repository.name}:${repository.repositoryTag || 'latest'}`;
};

export const getAxiosErrorMessage = (error: unknown, fallback: string) => {
  if (isAxiosError(error)) {
    const responseMessage = (error.response?.data as { message?: string } | undefined)?.message;
    return responseMessage || error.message || fallback;
  }
  return fallback;
};

export const groupRepositoriesByName = (
  repositories: Repository[],
  teamRepositories: TeamRepo[]
): GroupedRepository[] => {
  const grouped = repositories.reduce(
    (acc, repository) => {
      if (!acc[repository.name]) {
        acc[repository.name] = [];
      }
      acc[repository.name].push(repository);
      return acc;
    },
    {} as Record<string, Repository[]>
  );

  return Object.entries(grouped)
    .map(([name, tags]) => {
      const grandTag =
        tags.find((r) => {
          const tagData = teamRepositories.find(
            (tr) => tr.repositoryName === r.name && tr.repositoryTag === r.repositoryTag
          );
          return tagData && (!tagData.parentGuid || tagData.parentGuid === tagData.repositoryGuid);
        }) || null;

      const forkTags = tags
        .filter((r) => r !== grandTag)
        .sort((a, b) => (a.repositoryTag || '').localeCompare(b.repositoryTag || ''));

      return {
        name,
        tags,
        grandTag,
        forkTags,
        isExpanded: false,
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
};
