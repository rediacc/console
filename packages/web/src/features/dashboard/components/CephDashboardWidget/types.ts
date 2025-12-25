import type { CompanyCephStats } from '@rediacc/shared/types';

export interface CephDashboardWidgetProps {
  stats: CompanyCephStats | null | undefined;
}
