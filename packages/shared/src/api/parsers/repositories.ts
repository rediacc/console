/**
 * Repository Parsers
 */

import { extractFirstByIndex, extractPrimaryOrSecondary } from './base';
import { DEFAULTS } from '../../config';
import type { GetTeamRepositories_ResultSet1 } from '../../types';
import type { ApiResponse } from '../../types/api';

export interface NormalizedRepository extends GetTeamRepositories_ResultSet1 {
  repositoryTag: string;
}

function normalizeRepository(repository: GetTeamRepositories_ResultSet1): NormalizedRepository {
  return {
    ...repository,
    repositoryTag: repository.repositoryTag ?? DEFAULTS.REPOSITORY.TAG,
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
