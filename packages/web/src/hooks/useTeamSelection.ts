import { useMemo, useEffect, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useGetOrganizationTeams } from '@/api/api-hooks.generated';
import { RootState } from '@/store/store';
import { initializeTeam, setTeam } from '@/store/teamSelection/teamSelectionSlice';
import type { GetOrganizationTeams_ResultSet1 } from '@rediacc/shared/types';

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
  const hasInitializedRef = useRef(false);

  const { data: teamsData, isLoading } = useGetOrganizationTeams();
  const teams = useMemo(() => teamsData ?? [], [teamsData]);

  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const pageState = useSelector((state: RootState) => state.teamSelection.pages[pageId]);

  // Use useEffect to avoid accessing refs during render
  useEffect(() => {
    const shouldInitialize =
      !isLoading &&
      autoSelect &&
      teams.length > 0 &&
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, @typescript-eslint/prefer-optional-chain -- pageState may be undefined during initialization
      !(pageState && pageState.hasInitialized) &&
      !hasInitializedRef.current;

    if (shouldInitialize) {
      hasInitializedRef.current = true;
      let initialTeam: string;

      if (getInitialTeam) {
        const result = getInitialTeam(teams, uiMode);
        initialTeam = result || '';
      } else if (uiMode === 'simple') {
        const privateTeam = teams.find((team) => team.teamName === 'Private Team');
        const teamName = privateTeam ? privateTeam.teamName : teams[0]?.teamName;
        initialTeam = teamName || '';
      } else {
        const teamName = teams[0]?.teamName;
        initialTeam = teamName || '';
      }

      dispatch(initializeTeam({ pageId, teamName: initialTeam }));
    }
  }, [isLoading, autoSelect, teams, pageState, uiMode, getInitialTeam, dispatch, pageId]);

  const setSelectedTeam = (team: string | null) => {
    dispatch(setTeam({ pageId, teamName: team }));
  };

  return {
    teams,
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- pageState may be undefined during initialization
    selectedTeam: pageState?.selectedTeam ?? null,
    setSelectedTeam,
    isLoading,
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- pageState may be undefined during initialization
    hasInitialized: pageState?.hasInitialized ?? false,
  };
}
