import React from 'react';
import { Alert, Empty } from 'antd';
import { useRecentAuditLogs } from '@/api/queries/audit';
import { useDashboard } from '@/api/queries/dashboard';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccStack } from '@/components/ui';
import CephDashboardWidget from '@/pages/dashboard/components/CephDashboardWidget';
import SystemVersionFooter from '@/pages/dashboard/components/SystemVersionFooter';
import { PageContainer } from '@/styles/primitives';
import { AlertOutlined } from '@/utils/optimizedIcons';
import type { QueueMachineIssue, QueueTeamIssue } from '@rediacc/shared/types';
import { CenteredState } from './styles';
import AccountHealthWidget from './widgets/AccountHealthWidget';
import DashboardAlertsWidget from './widgets/DashboardAlertsWidget';
import QueueDetailsWidget from './widgets/QueueDetailsWidget';
import QueueOverviewWidget from './widgets/QueueOverviewWidget';
import RecentActivityWidget from './widgets/RecentActivityWidget';
import ResourceUsageWidget from './widgets/ResourceUsageWidget';
import SubscriptionPlanWidget from './widgets/SubscriptionPlanWidget';

const RECENT_AUDIT_LOGS_COUNT = 6;

const DashboardPage: React.FC = () => {
  const { data: dashboard, isLoading, error } = useDashboard();
  const { data: auditLogs, isLoading: auditLoading } = useRecentAuditLogs(RECENT_AUDIT_LOGS_COUNT);

  if (isLoading) {
    return (
      <PageContainer>
        <CenteredState>
          <LoadingWrapper loading centered minHeight={200}>
            <div />
          </LoadingWrapper>
        </CenteredState>
      </PageContainer>
    );
  }

  if (error) {
    return (
      <PageContainer>
        <Alert
          message="Error"
          description="Failed to load dashboard data. Please try again later."
          type="error"
          showIcon
          icon={<AlertOutlined />}
          data-testid="dashboard-error-alert"
        />
      </PageContainer>
    );
  }

  if (!dashboard) {
    return (
      <PageContainer>
        <Empty description="No dashboard data available" />
      </PageContainer>
    );
  }

  const activeSubscriptions = dashboard.allActiveSubscriptions || [];
  const queueStats = dashboard.queueStats;
  const teamIssues: QueueTeamIssue[] = Array.isArray(queueStats?.teamIssues)
    ? (queueStats!.teamIssues as QueueTeamIssue[])
    : [];
  const machineIssues: QueueMachineIssue[] = Array.isArray(queueStats?.machineIssues)
    ? (queueStats!.machineIssues as QueueMachineIssue[])
    : [];
  const hasQueueDetails = Boolean(
    queueStats && (teamIssues.length > 0 || machineIssues.length > 0)
  );
  const accountHealth = dashboard.accountHealth;
  const planLimits = dashboard.planLimits;
  const featureAccess = dashboard.featureAccess;

  return (
    <PageContainer>
      <RediaccStack variant="spaced-column" fullWidth>
        <DashboardAlertsWidget dashboard={dashboard} accountHealth={accountHealth} />

        <ResourceUsageWidget resources={dashboard.resources} />

        <SubscriptionPlanWidget
          activeSubscription={dashboard.activeSubscription}
          allActiveSubscriptions={activeSubscriptions}
          planLimits={planLimits}
        />

        <QueueOverviewWidget queueStats={queueStats} />

        {hasQueueDetails && queueStats && (
          <QueueDetailsWidget queueStats={queueStats} featureAccess={featureAccess} />
        )}

        {featureAccess?.hasAdvancedAnalytics === 1 && dashboard.cephStats && (
          <CephDashboardWidget stats={dashboard.cephStats} />
        )}

        <AccountHealthWidget accountHealth={accountHealth} />

        <RecentActivityWidget auditLogs={auditLogs} isLoading={auditLoading} />

        <SystemVersionFooter />
      </RediaccStack>
    </PageContainer>
  );
};

export default DashboardPage;
