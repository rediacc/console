/**
 * Repository Parsers
 */

import { extractPrimaryOrSecondary, extractFirstByIndex } from './base';
import type { GetTeamRepositories_ResultSet1 } from '../../types';
import type { ApiResponse } from '../../types/api';

export interface NormalizedRepository extends GetTeamRepositories_ResultSet1 {
  repositoryTag: string;
}

function normalizeRepository(repository: GetTeamRepositories_ResultSet1): NormalizedRepository {
  return {
    ...repository,
    repositoryTag: repository.repositoryTag ?? 'latest',
  };
}

export function parseGetTeamRepositories(
  response: ApiResponse<GetTeamRepositories_ResultSet1>
): NormalizedRepository[] {
  return extractPrimaryOrSecondary(response)
    .filter((repo) => Boolean(repo.repositoryName))
    .map(normalizeRepository);
}

export function parseCreateRepository(
  response: ApiResponse<GetTeamRepositories_ResultSet1>
): NormalizedRepository | null {
  const row =
    extractFirstByIndex<GetTeamRepositories_ResultSet1>(response, 1) ??
    extractFirstByIndex<GetTeamRepositories_ResultSet1>(response, 0);
  return row ? normalizeRepository(row) : null;
}

export const parseRepositoryList = parseGetTeamRepositories;
