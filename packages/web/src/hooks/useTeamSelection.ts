import { useMemo, useCallback, useReducer } from 'react'
import { useSelector } from 'react-redux'
import { useTeams, Team } from '@/api/queries/teams'
import { RootState } from '@/store/store'

export interface UseTeamSelectionOptions {
  /** Custom logic to select initial team (e.g., for simple UI mode) */
  getInitialTeam?: (teams: Team[], uiMode: string) => string
  /** Whether to auto-select first team when none selected */
  autoSelect?: boolean
}

export interface UseTeamSelectionReturn {
  teams: Team[]
  selectedTeams: string[]
  setSelectedTeams: (teams: string[]) => void
  isLoading: boolean
  hasInitialized: boolean
}

interface SelectionState {
  selectedTeams: string[]
  hasInitialized: boolean
}

type SelectionAction =
  | { type: 'INITIALIZE'; teams: string[] }
  | { type: 'SET_TEAMS'; teams: string[] }

function selectionReducer(state: SelectionState, action: SelectionAction): SelectionState {
  switch (action.type) {
    case 'INITIALIZE':
      if (state.hasInitialized) return state
      return { selectedTeams: action.teams, hasInitialized: true }
    case 'SET_TEAMS':
      return { ...state, selectedTeams: action.teams }
    default:
      return state
  }
}

export function useTeamSelection(
  options: UseTeamSelectionOptions = {}
): UseTeamSelectionReturn {
  const { autoSelect = true, getInitialTeam } = options

  const { data: teamsData, isLoading } = useTeams()
  const teams = useMemo<Team[]>(() => teamsData || [], [teamsData])
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)

  const [state, dispatch] = useReducer(selectionReducer, {
    selectedTeams: [],
    hasInitialized: false,
  })

  // Compute initial team selection when data is ready
  const shouldInitialize = !isLoading && autoSelect && teams.length > 0 && !state.hasInitialized

  if (shouldInitialize) {
    let initialTeam: string

    if (getInitialTeam) {
      initialTeam = getInitialTeam(teams, uiMode)
    } else if (uiMode === 'simple') {
      const privateTeam = teams.find((team) => team.teamName === 'Private Team')
      initialTeam = privateTeam?.teamName || teams[0].teamName
    } else {
      initialTeam = teams[0].teamName
    }

    dispatch({ type: 'INITIALIZE', teams: [initialTeam] })
  }

  const setSelectedTeams = useCallback((teams: string[]) => {
    dispatch({ type: 'SET_TEAMS', teams })
  }, [])

  return {
    teams,
    selectedTeams: state.selectedTeams,
    setSelectedTeams,
    isLoading,
    hasInitialized: state.hasInitialized,
  }
}
