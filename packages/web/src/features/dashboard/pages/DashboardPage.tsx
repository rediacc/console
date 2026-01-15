import { Alert, Empty, Flex } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { useGetAuditLogs, useOrganizationDashboard } from '@/api/api-hooks.generated';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import CephDashboardWidget from '@/features/dashboard/components/CephDashboardWidget';
import SystemVersionFooter from '@/features/dashboard/components/SystemVersionFooter';
import { AlertOutlined } from '@/utils/optimizedIcons';
import AccountHealthWidget from '../widgets/AccountHealthWidget';
import DashboardAlertsWidget from '../widgets/DashboardAlertsWidget';
import QueueDetailsWidget from '../widgets/QueueDetailsWidget';
import QueueOverviewWidget from '../widgets/QueueOverviewWidget';
import RecentActivityWidget from '../widgets/RecentActivityWidget';
import ResourceUsageWidget from '../widgets/ResourceUsageWidget';
import SubscriptionPlanWidget from '../widgets/SubscriptionPlanWidget';

const RECENT_AUDIT_LOGS_COUNT = 6;

const DashboardPage: React.FC = () => {
  const { t } = useTranslation('common');
  const { data: dashboard, isLoading, error } = useOrganizationDashboard();
  const { data: auditLogs, isLoading: auditLoading } = useGetAuditLogs(
    undefined,
    undefined,
    undefined,
    RECENT_AUDIT_LOGS_COUNT
  );

  if (isLoading) {
    return (
      <Flex>
        {/* eslint-disable-next-line no-restricted-syntax */}
        <Flex style={{ width: '100%', textAlign: 'center' }}>
          <LoadingWrapper loading centered minHeight={200}>
            <Flex />
          </LoadingWrapper>
        </Flex>
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex>
        <Alert
          message={t('dashboard.errors.title')}
          description={t('dashboard.errors.loadFailed')}
          type="error"
          icon={<AlertOutlined />}
          data-testid="dashboard-error-alert"
        />
      </Flex>
    );
  }

  if (!dashboard) {
    return (
      <Flex>
        <Empty description={t('dashboard.errors.noData')} />
      </Flex>
    );
  }

  const activeSubscriptions = dashboard.allActiveSubscriptions;
  const queueStats = dashboard.queueStats;
  const teamIssues = dashboard.teamIssues;
  const machineIssues = dashboard.machineIssues;
  const hasQueueDetails = Boolean(
    queueStats && (teamIssues.length > 0 || machineIssues.length > 0)
  );
  const accountHealth = dashboard.accountHealth;
  const planLimits = dashboard.planLimits;
  const featureAccess = dashboard.featureAccess;

  return (
    <Flex>
      <Flex vertical className="w-full">
        <DashboardAlertsWidget dashboard={dashboard} accountHealth={accountHealth} />

        <ResourceUsageWidget resources={dashboard.resources} />

        <SubscriptionPlanWidget
          activeSubscription={dashboard.activeSubscription}
          allActiveSubscriptions={activeSubscriptions}
          planLimits={planLimits}
        />

        <QueueOverviewWidget queueStats={queueStats} />

        {hasQueueDetails && queueStats && (
          <QueueDetailsWidget
            queueStats={queueStats}
            teamIssues={teamIssues}
            machineIssues={machineIssues}
            featureAccess={featureAccess}
          />
        )}

        {featureAccess?.hasAdvancedAnalytics && dashboard.cephStats && (
          <CephDashboardWidget
            stats={dashboard.cephStats}
            teamBreakdown={dashboard.cephTeamBreakdown}
          />
        )}

        <AccountHealthWidget accountHealth={accountHealth} />

        <RecentActivityWidget auditLogs={auditLogs} isLoading={auditLoading} />

        <SystemVersionFooter />
      </Flex>
    </Flex>
  );
};

export default DashboardPage;
