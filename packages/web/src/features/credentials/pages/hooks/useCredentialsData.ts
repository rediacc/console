import {
  useGetTeamMachines,
  useGetTeamRepositories,
  useGetTeamStorages,
} from '@/api/api-hooks.generated';
import { useDropdownData } from '@/api/queries/useDropdownData';

export const useCredentialsData = (selectedTeams: string[]) => {
  const selectedTeam = selectedTeams.length > 0 ? selectedTeams[0] : undefined;
  const { data: dropdownData } = useDropdownData();
  const {
    data: repositories = [],
    isLoading: repositoriesLoading,
    refetch: refetchRepos,
  } = useGetTeamRepositories(selectedTeam);
  const { data: machines = [] } = useGetTeamMachines(selectedTeam);
  const { data: storages = [] } = useGetTeamStorages(selectedTeam);

  return { dropdownData, repositories, repositoriesLoading, refetchRepos, machines, storages };
};
