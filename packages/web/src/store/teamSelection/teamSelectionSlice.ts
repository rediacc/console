import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface PageTeamState {
  selectedTeam: string | null;
  hasInitialized: boolean;
}

interface TeamSelectionState {
  pages: Record<string, PageTeamState>;
}

const initialState: TeamSelectionState = {
  pages: {},
};

const teamSelectionSlice = createSlice({
  name: 'teamSelection',
  initialState,
  reducers: {
    initializeTeam: (state, action: PayloadAction<{ pageId: string; teamName: string }>) => {
      const { pageId, teamName } = action.payload;
      if (!(pageId in state.pages) || !state.pages[pageId].hasInitialized) {
        state.pages[pageId] = { selectedTeam: teamName, hasInitialized: true };
      }
    },
    setTeam: (state, action: PayloadAction<{ pageId: string; teamName: string | null }>) => {
      const { pageId, teamName } = action.payload;
      state.pages[pageId] = { selectedTeam: teamName, hasInitialized: true };
    },
    clearPage: (state, action: PayloadAction<string>) => {
      delete state.pages[action.payload];
    },
    resetAllTeams: () => initialState,
  },
});

export const { initializeTeam, setTeam } = teamSelectionSlice.actions;
export default teamSelectionSlice.reducer;
