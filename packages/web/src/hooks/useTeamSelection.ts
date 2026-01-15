import type { GetOrganizationTeams_ResultSet1 } from '@rediacc/shared/types';
import { useMemo, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useGetOrganizationTeams } from '@/api/api-hooks.generated';
import { RootState } from '@/store/store';
import { initializeTeam, setTeam } from '@/store/teamSelection/teamSelectionSlice';

export interface UseTeamSelectionOptions {
  /** Required page identifier for per-page isolation */
  pageId: string;
  /** Custom logic to select initial team (e.g., for simple UI mode) */
  getInitialTeam?: (teams: GetOrganizationTeams_ResultSet1[], uiMode: string) => string;
  /** Whether to auto-select first team when none selected */
  autoSelect?: boolean;
}

export interface UseTeamSelectionReturn {
  teams: GetOrganizationTeams_ResultSet1[];
  selectedTeam: string | null;
  setSelectedTeam: (team: string | null) => void;
  isLoading: boolean;
  hasInitialized: boolean;
}

export function useTeamSelection(options: UseTeamSelectionOptions): UseTeamSelectionReturn {
  const { pageId, autoSelect = true, getInitialTeam } = options;
  const dispatch = useDispatch();
  const initRef = useRef(false);

  const { data: teamsData, isLoading } = useGetOrganizationTeams();
  const teams = useMemo(() => teamsData ?? [], [teamsData]);

  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const pageState = useSelector((state: RootState) => state.teamSelection.pages[pageId]);

  // Initialize team synchronously during render (matches old behavior)
  const shouldInitialize =
    !isLoading && autoSelect && teams.length > 0 && !pageState?.hasInitialized && !initRef.current;

  if (shouldInitialize) {
    initRef.current = true;
    let initialTeam: string;

    if (getInitialTeam) {
      initialTeam = getInitialTeam(teams, uiMode);
    } else if (uiMode === 'simple') {
      const privateTeam = teams.find((team) => team.teamName === 'Private Team');
      initialTeam = privateTeam?.teamName ?? teams[0]?.teamName ?? '';
    } else {
      initialTeam = teams[0]?.teamName ?? '';
    }

    dispatch(initializeTeam({ pageId, teamName: initialTeam }));
  }

  const setSelectedTeam = (team: string | null) => {
    dispatch(setTeam({ pageId, teamName: team }));
  };

  return {
    teams,
    selectedTeam: pageState?.selectedTeam ?? null,
    setSelectedTeam,
    isLoading,
    hasInitialized: pageState?.hasInitialized ?? false,
  };
}
