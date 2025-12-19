import React from 'react';
import { Alert } from 'antd';
import { RediaccStack } from '@/components/ui';
import { ClockCircleOutlined, ExclamationCircleOutlined } from '@/utils/optimizedIcons';
import type { CompanyDashboardData } from '@rediacc/shared/types';

interface DashboardAlertsWidgetProps {
  dashboard: CompanyDashboardData;
  accountHealth?: CompanyDashboardData['accountHealth'];
}

const DashboardAlertsWidget: React.FC<DashboardAlertsWidgetProps> = ({
  dashboard,
  accountHealth,
}) => {
  const showSubscriptionAlert = dashboard.activeSubscription?.isExpiringSoon === 1;
  const showResourceLimitAlert = accountHealth && accountHealth.resourcesAtLimit > 0;

  if (!showSubscriptionAlert && !showResourceLimitAlert) {
    return null;
  }

  return (
    <RediaccStack variant="spaced-column" fullWidth>
      {showSubscriptionAlert && dashboard.activeSubscription && (
        <Alert
          message="Subscription Expiring Soon"
          description={`Your ${dashboard.activeSubscription.planCode} subscription expires in ${dashboard.activeSubscription.daysRemaining} days.`}
          type="warning"
          showIcon
          icon={<ClockCircleOutlined />}
          data-testid="dashboard-alert-subscription-expiring"
        />
      )}

      {showResourceLimitAlert && (
        <Alert
          message="Resource Limits Reached"
          description={`${accountHealth.resourcesAtLimit} resource type(s) have reached their limits. Consider upgrading your plan to continue scaling.`}
          type="error"
          showIcon
          icon={<ExclamationCircleOutlined />}
          data-testid="dashboard-alert-resource-limits"
        />
      )}
    </RediaccStack>
  );
};

export default DashboardAlertsWidget;
