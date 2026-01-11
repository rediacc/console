/**
 * Hook for fetching machine SSH credentials from vaults
 * Used by LocalActionsMenu to get credentials for terminal/VSCode connections
 */

import { useCallback, useState } from 'react';
import { typedApi } from '@/api/client';
import { parseVaultContentOrEmpty } from '@rediacc/shared/queue-vault';
import { extractGetTeamMachines, extractGetOrganizationTeams } from '@rediacc/shared/types';

/**
 * SSH credentials extracted from machine and team vaults
 */
export interface MachineSSHCredentials {
  /** SSH host IP or hostname */
  host: string;
  /** SSH username */
  user: string;
  /** SSH port (default: 22) */
  port: number;
  /** SSH private key (PEM format) */
  privateKey: string;
  /** SSH known_hosts entry */
  known_hosts?: string;
  /** Datastore path on the machine */
  datastore: string;
}

/**
 * Machine vault structure
 */
interface MachineVault {
  ip?: string;
  user?: string;
  port?: number | string;
  datastore?: string;
  known_hosts?: string;
}

/**
 * Team vault structure
 */
interface TeamVault {
  SSH_PRIVATE_KEY?: string;
  SSH_PUBLIC_KEY?: string;
  SSH_KNOWN_HOSTS?: string;
}

/**
 * Hook return type
 */
export interface UseMachineCredentialsReturn {
  /** Fetch SSH credentials for a machine */
  getCredentials: (teamName: string, machineName: string) => Promise<MachineSSHCredentials>;
  /** Whether credentials are currently being fetched */
  isLoading: boolean;
  /** Last error message */
  error: string | null;
}

/**
 * Hook for fetching machine SSH credentials
 *
 * Combines machine vault (ip, user, port, datastore) with team vault (SSH_PRIVATE_KEY)
 * to provide complete SSH credentials for terminal/VSCode connections.
 *
 * @example
 * ```tsx
 * const { getCredentials, isLoading, error } = useMachineCredentials();
 *
 * const handleConnect = async () => {
 *   const creds = await getCredentials('Default', 'my-machine');
 *   // Use creds.host, creds.user, creds.privateKey, etc.
 * };
 * ```
 */
export function useMachineCredentials(): UseMachineCredentialsReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getCredentials = useCallback(
    async (teamName: string, machineName: string): Promise<MachineSSHCredentials> => {
      setIsLoading(true);
      setError(null);

      try {
        // Fetch machine data
        const machinesResponse = await typedApi.GetTeamMachines({ teamName });
        const machines = extractGetTeamMachines(machinesResponse);
        const machine = machines.find((m) => m.machineName === machineName);

        if (!machine) {
          throw new Error(`Machine "${machineName}" not found in team "${teamName}"`);
        }

        // Parse machine vault
        const machineVault = parseVaultContentOrEmpty<MachineVault>(
          machine.vaultContent ?? undefined
        );

        if (!machineVault.ip) {
          throw new Error(
            'Machine vault is missing IP address. Please configure the machine vault.'
          );
        }

        if (!machineVault.user) {
          throw new Error('Machine vault is missing SSH user. Please configure the machine vault.');
        }

        // Fetch team data for SSH key
        const teamsResponse = await typedApi.GetOrganizationTeams({});
        const teams = extractGetOrganizationTeams(teamsResponse);
        const team = teams.find((t) => t.teamName === teamName);

        if (!team) {
          throw new Error(`Team "${teamName}" not found`);
        }

        // Parse team vault
        const teamVault = parseVaultContentOrEmpty<TeamVault>(team.vaultContent ?? undefined);

        if (!teamVault.SSH_PRIVATE_KEY) {
          throw new Error(
            'Team vault is missing SSH_PRIVATE_KEY. Please generate SSH keys in the team settings.'
          );
        }

        // Combine credentials
        const credentials: MachineSSHCredentials = {
          host: machineVault.ip,
          user: machineVault.user,
          port:
            typeof machineVault.port === 'string'
              ? Number.parseInt(machineVault.port, 10) || 22
              : (machineVault.port ?? 22),
          privateKey: teamVault.SSH_PRIVATE_KEY,
          known_hosts: machineVault.known_hosts ?? teamVault.SSH_KNOWN_HOSTS,
          datastore: machineVault.datastore ?? `/home/${machineVault.user}`,
        };

        return credentials;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch machine credentials';
        setError(message);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  return {
    getCredentials,
    isLoading,
    error,
  };
}
