import type { OrganizationDashboardData } from '@rediacc/shared/types';
import { Alert, Flex } from 'antd';
import React from 'react';
import { ClockCircleOutlined, ExclamationCircleOutlined } from '@/utils/optimizedIcons';

interface DashboardAlertsWidgetProps {
  dashboard: OrganizationDashboardData;
  accountHealth?: OrganizationDashboardData['accountHealth'];
}

const DashboardAlertsWidget: React.FC<DashboardAlertsWidgetProps> = ({
  dashboard,
  accountHealth,
}) => {
  const showSubscriptionAlert = dashboard.activeSubscription?.isExpiringSoon;
  const showResourceLimitAlert = accountHealth && (accountHealth.resourcesAtLimit ?? 0) > 0;

  if (!showSubscriptionAlert && !showResourceLimitAlert) {
    return null;
  }

  return (
    <Flex vertical className="w-full">
      {showSubscriptionAlert && dashboard.activeSubscription && (
        <Alert
          message="Subscription Expiring Soon"
          description={`Your ${dashboard.activeSubscription.planCode} subscription expires in ${dashboard.activeSubscription.daysRemaining} days.`}
          type="warning"
          icon={<ClockCircleOutlined />}
          data-testid="dashboard-alert-subscription-expiring"
        />
      )}

      {showResourceLimitAlert && (
        <Alert
          message="Resource Limits Reached"
          description={`${accountHealth.resourcesAtLimit} resource type(s) have reached their limits. Consider upgrading your plan to continue scaling.`}
          type="error"
          icon={<ExclamationCircleOutlined />}
          data-testid="dashboard-alert-resource-limits"
        />
      )}
    </Flex>
  );
};

export default DashboardAlertsWidget;
