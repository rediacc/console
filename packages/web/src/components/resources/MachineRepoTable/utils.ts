import { isAxiosError } from 'axios';
import type { GetTeamRepositories_ResultSet1 as TeamRepo } from '@rediacc/shared/types';
import type { GroupedRepo, Repo } from './types';

export const getRepoDisplayName = (repo: Repo): string => {
  return `${repo.name}:${repo.repoTag || 'latest'}`;
};

export const getAxiosErrorMessage = (error: unknown, fallback: string) => {
  if (isAxiosError(error)) {
    const responseMessage = (error.response?.data as { message?: string } | undefined)?.message;
    return responseMessage || error.message || fallback;
  }
  return fallback;
};

export const groupReposByName = (repos: Repo[], teamRepos: TeamRepo[]): GroupedRepo[] => {
  const grouped = repos.reduce(
    (acc, repo) => {
      if (!acc[repo.name]) {
        acc[repo.name] = [];
      }
      acc[repo.name].push(repo);
      return acc;
    },
    {} as Record<string, Repo[]>
  );

  return Object.entries(grouped)
    .map(([name, tags]) => {
      const grandTag =
        tags.find((r) => {
          const tagData = teamRepos.find(
            (tr) => tr.repoName === r.name && tr.repoTag === r.repoTag
          );
          return tagData && (!tagData.parentGuid || tagData.parentGuid === tagData.repoGuid);
        }) || null;

      const forkTags = tags
        .filter((r) => r !== grandTag)
        .sort((a, b) => (a.repoTag || '').localeCompare(b.repoTag || ''));

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
