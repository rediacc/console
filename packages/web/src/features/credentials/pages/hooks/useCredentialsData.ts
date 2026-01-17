import {
  useGetTeamMachines,
  useGetTeamRepositories,
  useGetTeamStorages,
} from '@/api/api-hooks.generated';
import { useDropdownData } from '@/api/queries/useDropdownData';

export const useCredentialsData = (selectedTeam: string | null) => {
  const { data: dropdownData } = useDropdownData();
  const {
    data: repositories = [],
    isLoading: repositoriesLoading,
    refetch: refetchRepos,
  } = useGetTeamRepositories(selectedTeam ?? undefined);
  const { data: machines = [] } = useGetTeamMachines(selectedTeam ?? undefined);
  const { data: storages = [] } = useGetTeamStorages(selectedTeam ?? undefined);

  return { dropdownData, repositories, repositoriesLoading, refetchRepos, machines, storages };
};
