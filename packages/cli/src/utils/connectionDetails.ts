/**
 * Shared utility for fetching SSH/rsync connection details from the API.
 * Uses type-safe typedApi instead of raw apiClient calls.
 */
import {
  parseGetTeamMachines,
  parseGetOrganizationTeams,
  parseGetTeamRepositories,
} from '@rediacc/shared/api';
import { parseVaultContent } from '@rediacc/shared/queue-vault';
import { typedApi } from '../services/api.js';

/** Parsed vault data */
export type VaultData = Record<string, unknown>;

/** Connection details returned by the helper */
export interface ConnectionVaults {
  machineVault: VaultData;
  teamVault: VaultData;
  repositoryVault?: VaultData;
  /** Machine name that was found */
  machineName?: string | null;
  /** Repository name that was found */
  repositoryName?: string | null;
}

/**
 * Fetches connection-related vault data from the API using type-safe endpoints.
 *
 * @param teamName - Name of the team
 * @param machineName - Name of the machine
 * @param repositoryName - Optional name of the repository
 * @returns Promise with machine, team, and optionally repository vault data
 * @throws Error if machine or team is not found
 */
export async function getConnectionVaults(
  teamName: string,
  machineName: string,
  repositoryName?: string
): Promise<ConnectionVaults> {
  // Fetch machine and team data in parallel for efficiency
  const [machinesResponse, teamsResponse] = await Promise.all([
    typedApi.GetTeamMachines({ teamName }),
    typedApi.GetOrganizationTeams({}),
  ]);

  // Parse and find machine
  const machines = parseGetTeamMachines(machinesResponse as never);
  const machine = machines.find((m) => m.machineName === machineName);

  if (!machine) {
    throw new Error(`Machine '${machineName}' not found in team '${teamName}'`);
  }

  // Parse and find team
  const teams = parseGetOrganizationTeams(teamsResponse as never);
  const team = teams.find((t) => t.teamName === teamName);

  if (!team) {
    throw new Error(`Team '${teamName}' not found`);
  }

  // Parse vault contents
  const machineVault = parseVaultContent<VaultData>(machine.vaultContent) ?? {};
  const teamVault = parseVaultContent<VaultData>(team.vaultContent) ?? {};

  const result: ConnectionVaults = {
    machineVault,
    teamVault,
    machineName: machine.machineName,
  };

  // Fetch repository data if requested
  if (repositoryName) {
    const reposResponse = await typedApi.GetTeamRepositories({ teamName });
    const repositories = parseGetTeamRepositories(reposResponse as never);
    const repository = repositories.find((r) => r.repositoryName === repositoryName);

    if (!repository) {
      throw new Error(
        `Repository '${repositoryName}' not found on machine '${machineName}' in team '${teamName}'`
      );
    }

    result.repositoryVault = parseVaultContent<VaultData>(repository.vaultContent) ?? {};
    result.repositoryName = repository.repositoryName;
  }

  return result;
}
