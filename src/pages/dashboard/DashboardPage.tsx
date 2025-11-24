import React from 'react'
import { Col, Row, Alert, Tag, Typography, Statistic, Spin, Empty, Tooltip, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useTheme as useStyledTheme } from 'styled-components'
import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  SafetyCertificateOutlined,
  ExclamationCircleOutlined,
  CrownOutlined,
  DesktopOutlined,
  InboxOutlined,
  HistoryOutlined,
  CloseCircleOutlined,
  EditOutlined,
  LoginOutlined,
  SwapOutlined,
  InfoCircleOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  WarningOutlined,
  FieldTimeOutlined,
  RobotOutlined,
  TeamOutlined,
} from '@/utils/optimizedIcons'
import { useDashboard, type QueueTeamIssue, type QueueMachineIssue } from '@/api/queries/dashboard'
import { useRecentAuditLogs } from '@/api/queries/audit'
import DistributedStorageDashboardWidget from '@/components/dashboard/DistributedStorageDashboardWidget'
import { createSorter } from '@/core'
import {
  PageWrapper,
  ContentStack,
  CenteredState,
  DashboardCard,
  SectionDescription,
  ResourceTile,
  TileHeader,
  TileMeta,
  ResourceProgress,
  SectionLabel,
  SectionTitle,
  ScrollContainer,
  LicenseItem,
  LicenseHeader,
  FlexBetween,
  InlineStack,
  StatList,
  StatRow,
  StatLabel,
  StatValue,
  InlineLink,
  QueueBadgeRow,
  QueueBadge,
  TimelineWrapper,
  BorderlessList,
  BorderlessListItem,
  AuditMeta,
  EmptyState,
  Divider,
  SectionFooter,
  PlanCountBadge,
  QuantityBadge,
  HorizontalScroll,
} from './styles'

const { Text } = Typography

const resourceIcons: Record<string, React.ReactNode> = {
  Machine: <DesktopOutlined />,
  Repo: <InboxOutlined />,
}

const CRITICAL_DAYS_THRESHOLD = 30
const RECENT_AUDIT_LOGS_COUNT = 6
const DESCRIPTION_TRUNCATE_LENGTH = 80

const STATUS_TYPE_MAP: Record<string, 'success' | 'warning' | 'error'> = {
  Critical: 'error',
  Warning: 'warning',
  Good: 'success',
}

const PROGRESS_THRESHOLDS = {
  EXCEPTION: 90,
  NORMAL: 75,
}

const getProgressStatus = (percentage: number): 'exception' | 'normal' | 'success' => {
  if (percentage >= PROGRESS_THRESHOLDS.EXCEPTION) return 'exception'
  if (percentage >= PROGRESS_THRESHOLDS.NORMAL) return 'normal'
  return 'success'
}

const DashboardPage: React.FC = () => {
  const { data: dashboard, isLoading, error } = useDashboard()
  const { data: auditLogs, isLoading: auditLoading } = useRecentAuditLogs(RECENT_AUDIT_LOGS_COUNT)
  const theme = useStyledTheme()

  const getActionIcon = (action: string) => {
    const actionLower = action.toLowerCase()
    if (actionLower.includes('create')) return <CheckCircleOutlined style={{ color: theme.colors.success }} />
    if (actionLower.includes('delete')) return <CloseCircleOutlined style={{ color: theme.colors.error }} />
    if (actionLower.includes('update') || actionLower.includes('modify')) return <EditOutlined style={{ color: theme.colors.warning }} />
    if (actionLower.includes('login') || actionLower.includes('auth')) return <LoginOutlined style={{ color: theme.colors.info }} />
    if (actionLower.includes('export') || actionLower.includes('import')) return <SwapOutlined style={{ color: theme.colors.primary }} />
    return <InfoCircleOutlined style={{ color: theme.colors.textSecondary }} />
  }

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    if (diffMins < 1) return 'just now'
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`

    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`

    const diffDays = Math.floor(diffHours / 24)
    if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`

    return date.toLocaleDateString()
  }

  const machineIssueColumns: ColumnsType<QueueMachineIssue> = [
    {
      title: 'Machine',
      dataIndex: 'MachineName',
      key: 'MachineName',
      ellipsis: true,
      sorter: createSorter<QueueMachineIssue>('MachineName'),
    },
    {
      title: 'Team',
      dataIndex: 'TeamName',
      key: 'TeamName',
      ellipsis: true,
      sorter: createSorter<QueueMachineIssue>('TeamName'),
    },
    {
      title: 'Status',
      key: 'status',
      width: 200,
      render: (_: unknown, record: QueueMachineIssue) => (
        <InlineStack>
          {(record.StaleItems || 0) > 0 && <Tag color="warning">{record.StaleItems} stale</Tag>}
          <Tag color="blue">{record.PendingItems || 0} pending</Tag>
          <Tag color="processing">{record.ActiveItems || 0} active</Tag>
        </InlineStack>
      ),
    },
  ]

  if (isLoading) {
    return (
      <PageWrapper>
        <CenteredState>
          <Spin size="large" />
        </CenteredState>
      </PageWrapper>
    )
  }

  if (error) {
    return (
      <PageWrapper>
        <Alert
          message="Error"
          description="Failed to load dashboard data. Please try again later."
          type="error"
          showIcon
          icon={<AlertOutlined />}
          data-testid="dashboard-error-alert"
        />
      </PageWrapper>
    )
  }

  if (!dashboard) {
    return (
      <PageWrapper>
        <Empty description="No dashboard data available" />
      </PageWrapper>
    )
  }

  const activeSubscriptions = dashboard.allActiveSubscriptions || []
  const queueStats = dashboard.queueStats
  const teamIssues: QueueTeamIssue[] = Array.isArray(queueStats?.TeamIssues)
    ? (queueStats!.TeamIssues as QueueTeamIssue[])
    : []
  const machineIssues: QueueMachineIssue[] = Array.isArray(queueStats?.MachineIssues)
    ? (queueStats!.MachineIssues as QueueMachineIssue[])
    : []
  const hasQueueDetails = Boolean(queueStats && (teamIssues.length > 0 || machineIssues.length > 0))

  return (
    <PageWrapper>
      <ContentStack>
        {dashboard.activeSubscription?.IsExpiringSoon === 1 && (
          <Alert
            message="Subscription Expiring Soon"
            description={`Your ${dashboard.activeSubscription.PlanCode} subscription expires in ${dashboard.activeSubscription.DaysRemaining} days.`}
            type="warning"
            showIcon
            icon={<ClockCircleOutlined />}
            data-testid="dashboard-alert-subscription-expiring"
          />
        )}

        {dashboard.accountHealth.ResourcesAtLimit > 0 && (
          <Alert
            message="Resource Limits Reached"
            description={`${dashboard.accountHealth.ResourcesAtLimit} resource type(s) have reached their limits. Consider upgrading your plan to continue scaling.`}
            type="error"
            showIcon
            icon={<ExclamationCircleOutlined />}
            data-testid="dashboard-alert-resource-limits"
          />
        )}

        <DashboardCard
          title={
            <InlineStack>
              <ThunderboltOutlined />
              <span>Resource Usage</span>
            </InlineStack>
          }
          extra={<SectionDescription>Monitor your resource consumption against plan limits</SectionDescription>}
          data-testid="dashboard-card-resource-usage"
        >
          <Row gutter={[16, 24]}>
            {dashboard.resources
              .filter((resource) => resource.ResourceType === 'Machine' || resource.ResourceType === 'Repo')
              .map((resource) => {
                const progressColor = resource.IsLimitReached === 1 ? theme.colors.error : theme.colors.primary
                return (
                  <Col key={resource.ResourceType} xs={24} sm={12} md={8}>
                    <ResourceTile>
                      <StatList>
                        <TileHeader>
                          <InlineStack>
                            {resourceIcons[resource.ResourceType]}
                            <Text strong>{resource.ResourceType}s</Text>
                          </InlineStack>
                          <TileMeta>
                            {resource.CurrentUsage} / {resource.ResourceLimit === 0 ? '∞' : resource.ResourceLimit}
                          </TileMeta>
                        </TileHeader>
                        <ResourceProgress
                          percent={resource.ResourceLimit === 0 ? 0 : resource.UsagePercentage}
                          status={getProgressStatus(resource.UsagePercentage)}
                          strokeColor={progressColor}
                          data-testid={`dashboard-progress-${resource.ResourceType.toLowerCase()}`}
                        />
                        {resource.IsLimitReached === 1 && (
                          <StatLabel as="span" style={{ color: theme.colors.error }}>
                            Limit reached
                          </StatLabel>
                        )}
                      </StatList>
                    </ResourceTile>
                  </Col>
                )
              })}
          </Row>
        </DashboardCard>

        <DashboardCard
          title={
            <InlineStack>
              <CrownOutlined />
              <span>Subscription & Plan Details - {dashboard.planLimits.PlanCode}</span>
              {activeSubscriptions.length > 0 && <PlanCountBadge count={activeSubscriptions.length} />}
            </InlineStack>
          }
          data-testid="dashboard-card-subscription-plans"
        >
          <Row gutter={[24, 24]}>
            <Col xs={24} md={activeSubscriptions.length > 0 ? 12 : 24}>
              {dashboard.activeSubscription ? (
                <StatList>
                  <div>
                    <SectionLabel>CURRENT SUBSCRIPTION</SectionLabel>
                    <SectionTitle level={4}>{dashboard.activeSubscription.PlanCode}</SectionTitle>
                    <Row gutter={[16, 16]}>
                      <Col span={12}>
                        <Statistic
                          title="Active Licenses"
                          value={dashboard.activeSubscription.TotalActivePurchases}
                          valueStyle={{ color: theme.colors.textPrimary }}
                          data-testid="dashboard-stat-active-licenses"
                        />
                      </Col>
                      <Col span={12}>
                        <Statistic
                          title="Days Remaining"
                          value={dashboard.activeSubscription.DaysRemaining}
                          valueStyle={{
                            color:
                              dashboard.activeSubscription.DaysRemaining <= CRITICAL_DAYS_THRESHOLD
                                ? theme.colors.error
                                : theme.colors.textPrimary,
                          }}
                          data-testid="dashboard-stat-days-remaining"
                        />
                      </Col>
                    </Row>
                  </div>
                </StatList>
              ) : (
                <Empty description="No active subscription" />
              )}
            </Col>

            {activeSubscriptions.length > 0 && (
              <Col xs={24} md={12}>
                <StatList>
                  <div>
                    <SectionLabel>ALL ACTIVE LICENSES</SectionLabel>
                    <SectionTitle level={4}>{activeSubscriptions.length} Total</SectionTitle>
                  </div>
                  <ScrollContainer>
                    <StatList size="small">
                      {activeSubscriptions.map((sub, index) => {
                        const percent = (() => {
                          const startDate = new Date(sub.startDate)
                          const endDate = new Date(sub.endDate)
                          const now = new Date()

                          if (now < startDate) return 0
                          if (now > endDate) return 100

                          const total = endDate.getTime() - startDate.getTime()
                          const elapsed = now.getTime() - startDate.getTime()
                          return Math.round(Math.max(0, Math.min(100, (elapsed / total) * 100)))
                        })()

                        const strokeColor =
                          sub.daysRemaining <= CRITICAL_DAYS_THRESHOLD ? theme.colors.error : theme.colors.primary

                        return (
                          <LicenseItem key={`${sub.planCode}-${index}`} data-testid={`dashboard-license-item-${index}`}>
                            <LicenseHeader>
                              <InlineStack>
                                <Text strong>{sub.planCode}</Text>
                                <QuantityBadge count={`×${sub.quantity}`} />
                                {sub.isTrial === 1 && <Tag color="blue">Trial</Tag>}
                              </InlineStack>
                              <StatLabel as="span" style={{ color: sub.daysRemaining <= CRITICAL_DAYS_THRESHOLD ? theme.colors.error : theme.colors.textSecondary }}>
                                {sub.daysRemaining} {sub.daysRemaining === 1 ? 'day' : 'days'} remaining
                              </StatLabel>
                            </LicenseHeader>
                            <Tooltip
                              title={`From ${new Date(sub.startDate).toLocaleDateString()} to ${new Date(sub.endDate).toLocaleDateString()}`}
                            >
                              <ResourceProgress
                                percent={percent}
                                showInfo={false}
                                size="small"
                                strokeColor={strokeColor}
                                data-testid={`dashboard-progress-subscription-${sub.planCode}`}
                              />
                            </Tooltip>
                          </LicenseItem>
                        )
                      })}
                    </StatList>
                  </ScrollContainer>
                </StatList>
              </Col>
            )}
          </Row>

          <Divider />
          <SectionLabel>PLAN CAPABILITIES</SectionLabel>
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} md={6}>
              <Statistic title="Max Active Jobs" value={dashboard.planLimits.MaxActiveJobs} valueStyle={{ color: theme.colors.primary }} />
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Statistic title="Max Reserved Jobs" value={dashboard.planLimits.MaxReservedJobs} valueStyle={{ color: theme.colors.primary }} />
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Statistic title="Job Timeout" value={dashboard.planLimits.JobTimeoutHours} suffix="hours" valueStyle={{ color: theme.colors.primary }} />
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Statistic title="Max Repo Size" value={dashboard.planLimits.MaxRepoSize} suffix="GB" valueStyle={{ color: theme.colors.primary }} />
            </Col>
          </Row>
        </DashboardCard>

        {queueStats ? (
          <DashboardCard
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
            <StatList>
              <Row gutter={[16, 16]}>
                <Col xs={12} md={6}>
                  <Statistic
                    title="Pending"
                    value={queueStats.PendingCount || 0}
                    valueStyle={{ color: theme.colors.warning }}
                    prefix={<ClockCircleOutlined />}
                    data-testid="dashboard-stat-pending"
                  />
                </Col>
                <Col xs={12} md={6}>
                  <Statistic
                    title="Processing"
                    value={queueStats.ActiveCount || 0}
                    valueStyle={{ color: theme.colors.info }}
                    prefix={<SyncOutlined spin />}
                    data-testid="dashboard-stat-processing"
                  />
                </Col>
                <Col xs={12} md={6}>
                  <Statistic
                    title="Completed"
                    value={queueStats.CompletedCount || 0}
                    valueStyle={{ color: theme.colors.success }}
                    prefix={<CheckCircleOutlined />}
                    data-testid="dashboard-stat-completed"
                  />
                </Col>
                <Col xs={12} md={6}>
                  <Statistic
                    title="Failed"
                    value={queueStats.FailedCount || 0}
                    valueStyle={{ color: theme.colors.error }}
                    prefix={<ExclamationCircleOutlined />}
                    data-testid="dashboard-stat-failed"
                  />
                </Col>
              </Row>

              {(queueStats.HasStaleItems === 1 || queueStats.HasOldPendingItems === 1) && (
                <StatList size="small">
                  {queueStats.HasStaleItems === 1 && (
                    <Alert
                      message={`${queueStats.StaleCount || 0} stale items`}
                      type="warning"
                      showIcon
                      icon={<WarningOutlined />}
                      data-testid="dashboard-alert-stale-items"
                    />
                  )}
                  {queueStats.HasOldPendingItems === 1 && (
                    <Alert
                      message={`Oldest: ${Math.floor((queueStats.OldestPendingAgeMinutes || 0) / 60)}h`}
                      type="info"
                      showIcon
                      icon={<FieldTimeOutlined />}
                      data-testid="dashboard-alert-old-pending"
                    />
                  )}
                </StatList>
              )}
            </StatList>
          </DashboardCard>
        ) : (
          <DashboardCard
            title={
              <InlineStack>
                <RobotOutlined />
                <span>Queue Overview</span>
              </InlineStack>
            }
            data-testid="dashboard-card-queue-overview-empty"
          >
            <Empty description="No queue data available" />
          </DashboardCard>
        )}

        {hasQueueDetails && queueStats && (
          <DashboardCard
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
                  <Text strong>Today&apos;s Activity</Text>
                  <StatList>
                    <StatRow>
                      <StatLabel>Created</StatLabel>
                      <StatValue data-testid="dashboard-stat-created-today">{queueStats.CreatedToday || 0}</StatValue>
                    </StatRow>
                    <StatRow>
                      <StatLabel>Completed</StatLabel>
                      <StatValue $variant="success" data-testid="dashboard-stat-completed-today">
                        {queueStats.CompletedToday || 0}
                      </StatValue>
                    </StatRow>
                    <StatRow>
                      <StatLabel>Cancelled</StatLabel>
                      <StatValue $variant="error" data-testid="dashboard-stat-cancelled-today">
                        {queueStats.CancelledToday || 0}
                      </StatValue>
                    </StatRow>
                    <StatRow>
                      <StatLabel>Failed</StatLabel>
                      <StatValue $variant="error" data-testid="dashboard-stat-failed-today">
                        {queueStats.FailedToday || 0}
                      </StatValue>
                    </StatRow>
                  </StatList>
                </ResourceTile>
              </Col>

              <Col xs={24} lg={16}>
                <StatList>
                  {teamIssues.length > 0 && (
                    <div>
                      <Text strong style={{ marginBottom: theme.spacing.SM }}> 
                        <TeamOutlined /> Team Queue Status
                      </Text>
                      <BorderlessList
                        size="small"
                        dataSource={teamIssues}
                        data-testid="dashboard-list-team-issues"
                        renderItem={(team) => {
                          const teamIssue = team as QueueTeamIssue
                          return (
                            <BorderlessListItem>
                              <FlexBetween>
                                <Text strong>{teamIssue.TeamName}</Text>
                                <InlineStack>
                                  {(teamIssue.StaleItems || 0) > 0 && (
                                    <Tag color="warning">
                                      <WarningOutlined /> {teamIssue.StaleItems} stale
                                    </Tag>
                                  )}
                                  <Tag color="blue">{teamIssue.PendingItems || 0} pending</Tag>
                                  <Tag color="processing">{teamIssue.ActiveItems || 0} active</Tag>
                                </InlineStack>
                              </FlexBetween>
                            </BorderlessListItem>
                          )
                        }}
                      />
                    </div>
                  )}

                  {machineIssues.length > 0 && (
                    <div>
                      <Text strong style={{ marginBottom: theme.spacing.SM }}>
                        <DesktopOutlined /> Machine Queue Status
                      </Text>
                      <HorizontalScroll>
                        <Table
                          size="small"
                          dataSource={machineIssues}
                          pagination={false}
                          columns={machineIssueColumns}
                          data-testid="dashboard-table-machine-issues"
                          rowKey={(record) => `${record.TeamName}-${record.MachineName}`}
                        />
                      </HorizontalScroll>
                    </div>
                  )}

                  {dashboard.featureAccess.HasAdvancedAnalytics === 1 &&
                    queueStats.HighestPriorityPending !== null && (
                      <ResourceTile>
                        <Text strong>
                          <ThunderboltOutlined /> Priority Breakdown
                        </Text>
                        <QueueBadgeRow>
                          <FlexBetween>
                            <Text>Highest Priority</Text>
                            <QueueBadge
                              $variant="error"
                              count={queueStats.HighestPriorityPending ?? 0}
                              data-testid="dashboard-badge-highest-priority"
                            />
                          </FlexBetween>
                          <FlexBetween>
                            <Text>High Priority</Text>
                            <QueueBadge
                              $variant="warning"
                              count={queueStats.HighPriorityPending ?? 0}
                              data-testid="dashboard-badge-high-priority"
                            />
                          </FlexBetween>
                          <FlexBetween>
                            <Text>Normal Priority</Text>
                            <QueueBadge
                              $variant="info"
                              count={queueStats.NormalPriorityPending ?? 0}
                              data-testid="dashboard-badge-normal-priority"
                            />
                          </FlexBetween>
                          <FlexBetween>
                            <Text>Low Priority</Text>
                            <QueueBadge
                              $variant="muted"
                              count={queueStats.LowPriorityPending ?? 0}
                              data-testid="dashboard-badge-low-priority"
                            />
                          </FlexBetween>
                        </QueueBadgeRow>
                      </ResourceTile>
                    )}
                </StatList>
              </Col>
            </Row>
          </DashboardCard>
        )}

        {dashboard.featureAccess?.HasAdvancedAnalytics === 1 && dashboard.distributedStorageStats && (
          <DistributedStorageDashboardWidget stats={dashboard.distributedStorageStats} />
        )}

        <DashboardCard
          data-testid="dashboard-account-health-card"
          title={
            <InlineStack>
              <SafetyCertificateOutlined />
              <span>Account Health</span>
            </InlineStack>
          }
        >
          <StatList>
            <FlexBetween>
              <Text>Overall Status</Text>
              <Tag color={STATUS_TYPE_MAP[dashboard.accountHealth.SubscriptionStatus] || 'success'}>
                {dashboard.accountHealth.SubscriptionStatus}
              </Tag>
            </FlexBetween>

            <StatList size="small">
              <InlineStack>
                {dashboard.accountHealth.ResourcesAtLimit > 0 ? (
                  <ExclamationCircleOutlined style={{ color: theme.colors.warning }} />
                ) : (
                  <CheckCircleOutlined style={{ color: theme.colors.success }} />
                )}
                <Text>{dashboard.accountHealth.ResourcesAtLimit} resources at limit</Text>
              </InlineStack>

              <InlineStack>
                <ClockCircleOutlined style={{ color: theme.colors.textSecondary }} />
                <Text>{dashboard.accountHealth.ResourcesNearLimit} resources near limit</Text>
              </InlineStack>
            </StatList>

            <SectionFooter>
              <Text strong>{dashboard.accountHealth.UpgradeRecommendation}</Text>
            </SectionFooter>
          </StatList>
        </DashboardCard>

        <DashboardCard
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
            <EmptyState>
              <Spin />
            </EmptyState>
          ) : auditLogs && auditLogs.length > 0 ? (
            <TimelineWrapper
              items={auditLogs
                .filter((log) => {
                  const action = log.action.toLowerCase()
                  const isTokenValidation = action.includes('token') && action.includes('validat')
                  const isRoutineAuth = action.includes('login') && action.includes('success')
                  return !isTokenValidation && !isRoutineAuth
                })
                .slice(0, 5)
                .map((log, index) => ({
                  key: index,
                  dot: getActionIcon(log.action),
                  children: (
                    <StatList size="small">
                      <FlexBetween>
                        <InlineStack>
                          <Text strong>{log.action.replace(/_/g, ' ')}</Text>
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
                    </StatList>
                  ),
                }))}
            />
          ) : (
            <EmptyState>
              <Empty description="No recent activity" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </EmptyState>
          )}
        </DashboardCard>
      </ContentStack>
    </PageWrapper>
  )
}

export default DashboardPage
