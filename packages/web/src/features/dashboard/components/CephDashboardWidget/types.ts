import type {
  GetOrganizationDashboard_ResultSet13,
  GetOrganizationDashboard_ResultSet15,
} from '@rediacc/shared/types';

export interface CephDashboardWidgetProps {
  stats: GetOrganizationDashboard_ResultSet13 | null | undefined;
  teamBreakdown?: GetOrganizationDashboard_ResultSet15[];
}
