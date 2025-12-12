import React from 'react';
import { Alert, Col, Empty, Row, Table, Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useTheme as useStyledTheme } from 'styled-components';
import { useRecentAuditLogs } from '@/api/queries/audit';
import { useDashboard } from '@/api/queries/dashboard';
import { createTruncatedColumn } from '@/components/common/columns';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccCard, RediaccStack, RediaccStatistic, RediaccText } from '@/components/ui';
import CephDashboardWidget from '@/pages/dashboard/components/CephDashboardWidget';
import SystemVersionFooter from '@/pages/dashboard/components/SystemVersionFooter';
import { createSorter } from '@/platform';
import { EmptyStateWrapper, PageContainer } from '@/styles/primitives';
import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  CrownOutlined,
  DesktopOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  FieldTimeOutlined,
  HistoryOutlined,
  InboxOutlined,
  InfoCircleOutlined,
  LoginOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SwapOutlined,
  SyncOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import type { QueueMachineIssue, QueueTeamIssue } from '@rediacc/shared/types';
import {
  ActionIcon,
  AuditMeta,
  BorderlessList,
  BorderlessListItem,
  CenteredState,
  DaysRemainingText,
  ErrorText,
  FlexBetween,
  HorizontalScroll,
  InlineLink,
  InlineStack,
  LicenseHeader,
  LicenseItem,
  PlanCountBadge,
  QuantityBadge,
  QueueBadge,
  QueueBadgeRow,
  ResourceProgress,
  ResourceTile,
  ScrollContainer,
  SectionFooter,
  SectionLabelWrapper,
  SectionTitle,
  SectionTitleWrapper,
  StatRow,
  StatusIcon,
  StatValue,
  TileHeader,
  TileMeta,
  TimelineWrapper,
} from './styles';
import type { ColumnsType } from 'antd/es/table';

const resourceIcons: Record<string, React.ReactNode> = {
  Machine: <DesktopOutlined />,
  Repo: <InboxOutlined />,
};

const CRITICAL_DAYS_THRESHOLD = 30;
const RECENT_AUDIT_LOGS_COUNT = 6;
const DESCRIPTION_TRUNCATE_LENGTH = 80;

const STATUS_TYPE_MAP: Record<string, 'success' | 'warning' | 'error'> = {
  Critical: 'error',
  Warning: 'warning',
  Good: 'success',
};

const PROGRESS_THRESHOLDS = {
  EXCEPTION: 90,
  NORMAL: 75,
};

const getProgressStatus = (percentage: number): 'exception' | 'normal' | 'success' => {
  if (percentage >= PROGRESS_THRESHOLDS.EXCEPTION) return 'exception';
  if (percentage >= PROGRESS_THRESHOLDS.NORMAL) return 'normal';
  return 'success';
};

const DashboardPage: React.FC = () => {
  const { t } = useTranslation('system');
  const { data: dashboard, isLoading, error } = useDashboard();
  const { data: auditLogs, isLoading: auditLoading } = useRecentAuditLogs(RECENT_AUDIT_LOGS_COUNT);
  const theme = useStyledTheme();

  const getActionIcon = (action: string) => {
    const actionLower = action.toLowerCase();
    if (actionLower.includes('create'))
      return (
        <ActionIcon $color="success">
          <CheckCircleOutlined />
        </ActionIcon>
      );
    if (actionLower.includes('delete'))
      return (
        <ActionIcon $color="error">
          <CloseCircleOutlined />
        </ActionIcon>
      );
    if (actionLower.includes('update') || actionLower.includes('modify'))
      return (
        <ActionIcon $color="warning">
          <EditOutlined />
        </ActionIcon>
      );
    if (actionLower.includes('login') || actionLower.includes('auth'))
      return (
        <ActionIcon $color="info">
          <LoginOutlined />
        </ActionIcon>
      );
    if (actionLower.includes('export') || actionLower.includes('import'))
      return (
        <ActionIcon $color="primary">
          <SwapOutlined />
        </ActionIcon>
      );
    return (
      <ActionIcon $color="textSecondary">
        <InfoCircleOutlined />
      </ActionIcon>
    );
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;

    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

    return date.toLocaleDateString();
  };

  const machineNameColumn = createTruncatedColumn<QueueMachineIssue>({
    title: 'Machine',
    dataIndex: 'machineName',
    key: 'machineName',
    sorter: createSorter<QueueMachineIssue>('machineName'),
  });

  const teamColumn = createTruncatedColumn<QueueMachineIssue>({
    title: 'Team',
    dataIndex: 'teamName',
    key: 'teamName',
    sorter: createSorter<QueueMachineIssue>('teamName'),
  });

  const machineIssueColumns: ColumnsType<QueueMachineIssue> = [
    machineNameColumn,
    teamColumn,
    {
      title: 'Status',
      key: 'status',
      width: 200,
      render: (_: unknown, record: QueueMachineIssue) => (
        <InlineStack>
          {(record.staleItems || 0) > 0 && <Tag color="warning">{record.staleItems} stale</Tag>}
          <Tag color="processing">{record.pendingItems || 0} pending</Tag>
          <Tag color="blue">{record.activeItems || 0} active</Tag>
        </InlineStack>
      ),
    },
  ];

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
        {dashboard.activeSubscription?.isExpiringSoon === 1 && (
          <Alert
            message="Subscription Expiring Soon"
            description={`Your ${dashboard.activeSubscription.planCode} subscription expires in ${dashboard.activeSubscription.daysRemaining} days.`}
            type="warning"
            showIcon
            icon={<ClockCircleOutlined />}
            data-testid="dashboard-alert-subscription-expiring"
          />
        )}

        {accountHealth && accountHealth.resourcesAtLimit > 0 && (
          <Alert
            message="Resource Limits Reached"
            description={`${accountHealth.resourcesAtLimit} resource type(s) have reached their limits. Consider upgrading your plan to continue scaling.`}
            type="error"
            showIcon
            icon={<ExclamationCircleOutlined />}
            data-testid="dashboard-alert-resource-limits"
          />
        )}

        <RediaccCard
          fullWidth
          title={
            <InlineStack>
              <ThunderboltOutlined />
              <span>Resource Usage</span>
            </InlineStack>
          }
          extra={
            <RediaccText variant="description">
              Monitor your resource consumption against plan limits
            </RediaccText>
          }
          data-testid="dashboard-card-resource-usage"
        >
          <Row gutter={[16, 24]}>
            {dashboard.resources
              .filter(
                (resource) =>
                  resource.resourceType === 'Machine' || resource.resourceType === 'Repo'
              )
              .map((resource) => {
                const progressColor =
                  resource.isLimitReached === 1 ? theme.colors.error : theme.colors.primary;
                return (
                  <Col key={resource.resourceType} xs={24} sm={12} md={8}>
                    <ResourceTile>
                      <RediaccStack direction="vertical" gap="md" fullWidth>
                        <TileHeader>
                          <InlineStack>
                            {resourceIcons[resource.resourceType]}
                            <RediaccText weight="bold">{resource.resourceType}s</RediaccText>
                          </InlineStack>
                          <TileMeta>
                            {resource.currentUsage} /{' '}
                            {resource.resourceLimit === 0 ? '∞' : resource.resourceLimit}
                          </TileMeta>
                        </TileHeader>
                        <ResourceProgress
                          percent={resource.resourceLimit === 0 ? 0 : resource.usagePercentage}
                          status={getProgressStatus(resource.usagePercentage)}
                          strokeColor={progressColor}
                          data-testid={`dashboard-progress-${resource.resourceType.toLowerCase()}`}
                        />
                        {resource.isLimitReached === 1 && (
                          <ErrorText variant="caption" as="span">
                            Limit reached
                          </ErrorText>
                        )}
                      </RediaccStack>
                    </ResourceTile>
                  </Col>
                );
              })}
          </Row>
        </RediaccCard>

        <RediaccCard
          fullWidth
          title={
            <InlineStack>
              <CrownOutlined />
              <span>Subscription & Plan Details - {planLimits?.planCode ?? 'N/A'}</span>
              {activeSubscriptions.length > 0 && (
                <PlanCountBadge count={activeSubscriptions.length} />
              )}
            </InlineStack>
          }
          data-testid="dashboard-card-subscription-plans"
        >
          <Row gutter={[24, 24]}>
            <Col xs={24} md={activeSubscriptions.length > 0 ? 12 : 24}>
              {dashboard.activeSubscription ? (
                <RediaccStack direction="vertical" gap="md" fullWidth>
                  <div>
                    <SectionLabelWrapper>
                      <RediaccText variant="label">CURRENT SUBSCRIPTION</RediaccText>
                    </SectionLabelWrapper>
                    <SectionTitleWrapper level={4}>
                      {dashboard.activeSubscription.planCode}
                    </SectionTitleWrapper>
                    <Row gutter={[16, 16]}>
                      <Col span={12}>
                        <RediaccStatistic
                          title={t('dashboard.activeLicenses')}
                          value={dashboard.activeSubscription.totalActivePurchases}
                          variant="textPrimary"
                          data-testid="dashboard-stat-active-licenses"
                        />
                      </Col>
                      <Col span={12}>
                        <RediaccStatistic
                          title={t('dashboard.daysRemaining')}
                          value={dashboard.activeSubscription.daysRemaining}
                          critical={
                            dashboard.activeSubscription.daysRemaining <= CRITICAL_DAYS_THRESHOLD
                          }
                          data-testid="dashboard-stat-days-remaining"
                        />
                      </Col>
                    </Row>
                  </div>
                </RediaccStack>
              ) : (
                <Empty description={t('dashboard.noSubscription')} />
              )}
            </Col>

            {activeSubscriptions.length > 0 && (
              <Col xs={24} md={12}>
                <RediaccStack direction="vertical" gap="md" fullWidth>
                  <div>
                    <SectionLabelWrapper>
                      <RediaccText variant="label">ALL ACTIVE LICENSES</RediaccText>
                    </SectionLabelWrapper>
                    <SectionTitleWrapper level={4}>
                      {activeSubscriptions.length} Total
                    </SectionTitleWrapper>
                  </div>
                  <ScrollContainer>
                    <RediaccStack direction="vertical" gap="sm" fullWidth>
                      {activeSubscriptions.map((sub, index) => {
                        const percent = (() => {
                          const startDate = new Date(sub.startDate);
                          const endDate = new Date(sub.endDate);
                          const now = new Date();

                          if (now < startDate) return 0;
                          if (now > endDate) return 100;

                          const total = endDate.getTime() - startDate.getTime();
                          const elapsed = now.getTime() - startDate.getTime();
                          return Math.round(Math.max(0, Math.min(100, (elapsed / total) * 100)));
                        })();

                        const strokeColor =
                          sub.daysRemaining <= CRITICAL_DAYS_THRESHOLD
                            ? theme.colors.error
                            : theme.colors.primary;

                        return (
                          <LicenseItem
                            key={`${sub.planCode}-${index}`}
                            data-testid={`dashboard-license-item-${index}`}
                          >
                            <LicenseHeader>
                              <InlineStack>
                                <RediaccText weight="bold">{sub.planCode}</RediaccText>
                                <QuantityBadge count={sub.quantity} />
                                {sub.isTrial === 1 && <Tag color="blue">Trial</Tag>}
                              </InlineStack>
                              <DaysRemainingText
                                variant="caption"
                                as="span"
                                $critical={sub.daysRemaining <= CRITICAL_DAYS_THRESHOLD}
                              >
                                {sub.daysRemaining} {sub.daysRemaining === 1 ? 'day' : 'days'}{' '}
                                remaining
                              </DaysRemainingText>
                            </LicenseHeader>
                            <Tooltip
                              title={`From ${new Date(sub.startDate).toLocaleDateString()} to ${new Date(sub.endDate).toLocaleDateString()}`}
                            >
                              <ResourceProgress
                                percent={percent}
                                showInfo={false}
                                size="sm"
                                strokeColor={strokeColor}
                                data-testid={`dashboard-progress-subscription-${sub.planCode}`}
                              />
                            </Tooltip>
                          </LicenseItem>
                        );
                      })}
                    </RediaccStack>
                  </ScrollContainer>
                </RediaccStack>
              </Col>
            )}
          </Row>

          {planLimits ? (
            <Row gutter={[24, 24]}>
              <Col xs={24} md={6}>
                <RediaccStatistic
                  title={t('dashboard.maxActiveJobs')}
                  value={planLimits.maxActiveJobs}
                  variant="primary"
                />
              </Col>
              <Col xs={24} md={6}>
                <RediaccStatistic
                  title={t('dashboard.maxReservedJobs')}
                  value={planLimits.maxReservedJobs}
                  variant="primary"
                />
              </Col>
              <Col xs={24} md={6}>
                <RediaccStatistic
                  title={t('dashboard.jobTimeout')}
                  value={planLimits.jobTimeoutHours}
                  suffix="hours"
                  variant="primary"
                />
              </Col>
              <Col xs={24} md={6}>
                <RediaccStatistic
                  title={t('dashboard.maxRepoSize')}
                  value={planLimits.maxRepoSize}
                  suffix="GB"
                  variant="primary"
                />
              </Col>
            </Row>
          ) : (
            <Empty description={t('dashboard.noPlanData')} />
          )}
        </RediaccCard>

        {queueStats ? (
          <RediaccCard
            fullWidth
            title={
              <InlineStack>
                <RobotOutlined />
                <span>Queue Overview</span>
              </InlineStack>
            }
            extra={
              <InlineLink to="/queue" data-testid="dashboard-queue-manage-link">
                Manage
              </InlineLink>
            }
            data-testid="dashboard-card-queue-overview"
          >
            <RediaccStack direction="vertical" gap="md" fullWidth>
              <Row gutter={[16, 16]}>
                <Col xs={12} md={6}>
                  <RediaccStatistic
                    title={t('dashboard.pending')}
                    value={queueStats.pendingCount || 0}
                    variant="warning"
                    prefix={<ClockCircleOutlined />}
                    data-testid="dashboard-stat-pending"
                  />
                </Col>
                <Col xs={12} md={6}>
                  <RediaccStatistic
                    title={t('dashboard.processing')}
                    value={queueStats.activeCount || 0}
                    variant="info"
                    prefix={<SyncOutlined spin />}
                    data-testid="dashboard-stat-processing"
                  />
                </Col>
                <Col xs={12} md={6}>
                  <RediaccStatistic
                    title={t('dashboard.completed')}
                    value={queueStats.completedCount || 0}
                    variant="success"
                    prefix={<CheckCircleOutlined />}
                    data-testid="dashboard-stat-completed"
                  />
                </Col>
                <Col xs={12} md={6}>
                  <RediaccStatistic
                    title={t('dashboard.failed')}
                    value={queueStats.failedCount || 0}
                    variant="error"
                    prefix={<ExclamationCircleOutlined />}
                    data-testid="dashboard-stat-failed"
                  />
                </Col>
              </Row>

              {(queueStats.hasStaleItems === 1 || queueStats.hasOldPendingItems === 1) && (
                <RediaccStack direction="vertical" gap="sm" fullWidth>
                  {queueStats.hasStaleItems === 1 && (
                    <Alert
                      message={`${queueStats.staleCount || 0} stale items`}
                      type="warning"
                      showIcon
                      icon={<WarningOutlined />}
                      data-testid="dashboard-alert-stale-items"
                    />
                  )}
                  {queueStats.hasOldPendingItems === 1 && (
                    <Alert
                      message={`Oldest: ${Math.floor((queueStats.oldestPendingAgeMinutes || 0) / 60)}h`}
                      type="info"
                      showIcon
                      icon={<FieldTimeOutlined />}
                      data-testid="dashboard-alert-old-pending"
                    />
                  )}
                </RediaccStack>
              )}
            </RediaccStack>
          </RediaccCard>
        ) : (
          <RediaccCard
            fullWidth
            title={
              <InlineStack>
                <RobotOutlined />
                <span>Queue Overview</span>
              </InlineStack>
            }
            data-testid="dashboard-card-queue-overview-empty"
          >
            <Empty description="No queue data available" />
          </RediaccCard>
        )}

        {hasQueueDetails && queueStats && (
          <RediaccCard
            fullWidth
            title={
              <InlineStack>
                <RobotOutlined />
                <span>Queue Details</span>
              </InlineStack>
            }
            data-testid="dashboard-card-queue-details"
          >
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={8}>
                <ResourceTile>
                  <RediaccText weight="bold">Today&apos;s Activity</RediaccText>
                  <RediaccStack direction="vertical" gap="md" fullWidth>
                    <StatRow>
                      <RediaccText variant="caption" color="secondary">
                        Created
                      </RediaccText>
                      <StatValue data-testid="dashboard-stat-created-today">
                        {queueStats.createdToday || 0}
                      </StatValue>
                    </StatRow>
                    <StatRow>
                      <RediaccText variant="caption" color="secondary">
                        Completed
                      </RediaccText>
                      <StatValue $variant="success" data-testid="dashboard-stat-completed-today">
                        {queueStats.completedToday || 0}
                      </StatValue>
                    </StatRow>
                    <StatRow>
                      <RediaccText variant="caption" color="secondary">
                        Cancelled
                      </RediaccText>
                      <StatValue $variant="error" data-testid="dashboard-stat-cancelled-today">
                        {queueStats.cancelledToday || 0}
                      </StatValue>
                    </StatRow>
                    <StatRow>
                      <RediaccText variant="caption" color="secondary">
                        Failed
                      </RediaccText>
                      <StatValue $variant="error" data-testid="dashboard-stat-failed-today">
                        {queueStats.failedToday || 0}
                      </StatValue>
                    </StatRow>
                  </RediaccStack>
                </ResourceTile>
              </Col>

              <Col xs={24} lg={16}>
                <RediaccStack direction="vertical" gap="md" fullWidth>
                  {teamIssues.length > 0 && (
                    <div>
                      <SectionTitle weight="bold">
                        <TeamOutlined /> Team Queue Status
                      </SectionTitle>
                      <BorderlessList
                        size="sm"
                        dataSource={teamIssues}
                        data-testid="dashboard-list-team-issues"
                        renderItem={(team) => {
                          const teamIssue = team as QueueTeamIssue;
                          return (
                            <BorderlessListItem>
                              <FlexBetween>
                                <RediaccText weight="bold">{teamIssue.teamName}</RediaccText>
                                <InlineStack>
                                  {(teamIssue.staleItems || 0) > 0 && (
                                    <Tag color="warning">
                                      <WarningOutlined /> {teamIssue.staleItems} stale
                                    </Tag>
                                  )}
                                  <Tag color="processing">
                                    {teamIssue.pendingItems || 0} pending
                                  </Tag>
                                  <Tag color="blue">{teamIssue.activeItems || 0} active</Tag>
                                </InlineStack>
                              </FlexBetween>
                            </BorderlessListItem>
                          );
                        }}
                      />
                    </div>
                  )}

                  {machineIssues.length > 0 && (
                    <div>
                      <SectionTitle weight="bold">
                        <DesktopOutlined /> Machine Queue Status
                      </SectionTitle>
                      <HorizontalScroll>
                        <Table
                          size="small"
                          dataSource={machineIssues}
                          pagination={false}
                          columns={machineIssueColumns}
                          data-testid="dashboard-table-machine-issues"
                          rowKey={(record) => `${record.teamName}-${record.machineName}`}
                        />
                      </HorizontalScroll>
                    </div>
                  )}

                  {featureAccess?.hasAdvancedAnalytics === 1 &&
                    queueStats.highestPriorityPending !== null && (
                      <ResourceTile>
                        <RediaccText weight="bold">
                          <ThunderboltOutlined /> Priority Breakdown
                        </RediaccText>
                        <QueueBadgeRow>
                          <FlexBetween>
                            <RediaccText>Highest Priority</RediaccText>
                            <QueueBadge
                              $variant="error"
                              count={queueStats.highestPriorityPending ?? 0}
                              data-testid="dashboard-badge-highest-priority"
                            />
                          </FlexBetween>
                          <FlexBetween>
                            <RediaccText>High Priority</RediaccText>
                            <QueueBadge
                              $variant="warning"
                              count={queueStats.highPriorityPending ?? 0}
                              data-testid="dashboard-badge-high-priority"
                            />
                          </FlexBetween>
                          <FlexBetween>
                            <RediaccText>Normal Priority</RediaccText>
                            <QueueBadge
                              $variant="info"
                              count={queueStats.normalPriorityPending ?? 0}
                              data-testid="dashboard-badge-normal-priority"
                            />
                          </FlexBetween>
                          <FlexBetween>
                            <RediaccText>Low Priority</RediaccText>
                            <QueueBadge
                              $variant="muted"
                              count={queueStats.lowPriorityPending ?? 0}
                              data-testid="dashboard-badge-low-priority"
                            />
                          </FlexBetween>
                        </QueueBadgeRow>
                      </ResourceTile>
                    )}
                </RediaccStack>
              </Col>
            </Row>
          </RediaccCard>
        )}

        {featureAccess?.hasAdvancedAnalytics === 1 && dashboard.cephStats && (
          <CephDashboardWidget stats={dashboard.cephStats} />
        )}

        {accountHealth ? (
          <RediaccCard
            fullWidth
            data-testid="dashboard-account-health-card"
            title={
              <InlineStack>
                <SafetyCertificateOutlined />
                <span>Account Health</span>
              </InlineStack>
            }
          >
            <RediaccStack direction="vertical" gap="md" fullWidth>
              <FlexBetween>
                <RediaccText>Overall Status</RediaccText>
                <Tag color={STATUS_TYPE_MAP[accountHealth.subscriptionStatus] || 'success'}>
                  {accountHealth.subscriptionStatus}
                </Tag>
              </FlexBetween>

              <RediaccStack direction="vertical" gap="sm" fullWidth>
                <InlineStack>
                  {accountHealth.resourcesAtLimit > 0 ? (
                    <StatusIcon $variant="warning">
                      <ExclamationCircleOutlined />
                    </StatusIcon>
                  ) : (
                    <StatusIcon $variant="success">
                      <CheckCircleOutlined />
                    </StatusIcon>
                  )}
                  <RediaccText>{accountHealth.resourcesAtLimit} resources at limit</RediaccText>
                </InlineStack>

                <InlineStack>
                  <StatusIcon $variant="secondary">
                    <ClockCircleOutlined />
                  </StatusIcon>
                  <RediaccText>{accountHealth.resourcesNearLimit} resources near limit</RediaccText>
                </InlineStack>
              </RediaccStack>

              <SectionFooter>
                <RediaccText weight="bold">{accountHealth.upgradeRecommendation}</RediaccText>
              </SectionFooter>
            </RediaccStack>
          </RediaccCard>
        ) : (
          <RediaccCard
            fullWidth
            data-testid="dashboard-account-health-card"
            title={
              <InlineStack>
                <SafetyCertificateOutlined />
                <span>Account Health</span>
              </InlineStack>
            }
          >
            <Empty description="No account health data available" />
          </RediaccCard>
        )}

        <RediaccCard
          fullWidth
          title={
            <InlineStack>
              <HistoryOutlined />
              <span>Recent Activity</span>
            </InlineStack>
          }
          extra={
            <InlineLink to="/audit" data-testid="dashboard-activity-viewall-link">
              View All
            </InlineLink>
          }
          data-testid="dashboard-card-recent-activity"
        >
          {auditLoading ? (
            <EmptyStateWrapper>
              <LoadingWrapper loading centered minHeight={120}>
                <div />
              </LoadingWrapper>
            </EmptyStateWrapper>
          ) : auditLogs && auditLogs.length > 0 ? (
            <TimelineWrapper
              items={auditLogs
                .filter((log) => {
                  const action = log.action.toLowerCase();
                  const isTokenValidation = action.includes('token') && action.includes('validat');
                  const isRoutineAuth = action.includes('login') && action.includes('success');
                  return !isTokenValidation && !isRoutineAuth;
                })
                .slice(0, 5)
                .map((log, index) => ({
                  key: index,
                  dot: getActionIcon(log.action),
                  children: (
                    <RediaccStack direction="vertical" gap="sm" fullWidth>
                      <FlexBetween>
                        <InlineStack>
                          <RediaccText weight="bold">{log.action.replace(/_/g, ' ')}</RediaccText>
                          <Tag>{log.entity}</Tag>
                        </InlineStack>
                        <AuditMeta>{formatTimestamp(log.timestamp)}</AuditMeta>
                      </FlexBetween>
                      <AuditMeta>
                        {log.entityName} {log.actionByUser && `• ${log.actionByUser}`}
                      </AuditMeta>
                      {log.details && log.details.trim() && (
                        <AuditMeta>
                          {log.details.length > DESCRIPTION_TRUNCATE_LENGTH
                            ? `${log.details.substring(0, DESCRIPTION_TRUNCATE_LENGTH)}...`
                            : log.details}
                        </AuditMeta>
                      )}
                    </RediaccStack>
                  ),
                }))}
            />
          ) : (
            <EmptyStateWrapper>
              <Empty description="No recent activity" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </EmptyStateWrapper>
          )}
        </RediaccCard>

        <SystemVersionFooter />
      </RediaccStack>
    </PageContainer>
  );
};

export default DashboardPage;
