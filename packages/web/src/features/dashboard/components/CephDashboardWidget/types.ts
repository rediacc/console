import type { CephTeamBreakdown, CompanyCephStats } from '@rediacc/shared/types';

export interface CephDashboardWidgetProps {
  stats: CompanyCephStats | null | undefined;
  teamBreakdown?: CephTeamBreakdown[];
}
