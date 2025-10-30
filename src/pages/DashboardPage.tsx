import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Card, Col, Row, Progress, Alert, Badge, Tag, Space, Typography, Statistic, Spin, Empty, Tooltip, theme, Timeline, List, Table } from 'antd';
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
  TeamOutlined
} from '@/utils/optimizedIcons';
import { borderRadius } from '@/utils/styleConstants';
import { useDashboard } from '../api/queries/dashboard';
import { useRecentAuditLogs } from '../api/queries/audit';
import { useTheme } from '@/context/ThemeContext';
import DistributedStorageDashboardWidget from '../components/dashboard/DistributedStorageDashboardWidget';

const { Title, Text } = Typography;

const resourceIcons: Record<string, React.ReactNode> = {
  'Machine': <DesktopOutlined />,
  'Repo': <InboxOutlined />
};

// Constants
const CRITICAL_DAYS_THRESHOLD = 30;
const RECENT_AUDIT_LOGS_COUNT = 6; // Reduced for better information density
const DESCRIPTION_TRUNCATE_LENGTH = 80; // Shorter for mobile readability

const DashboardPage = () => {
  const { data: dashboard, isLoading, error } = useDashboard();
  const { data: auditLogs, isLoading: auditLoading } = useRecentAuditLogs(RECENT_AUDIT_LOGS_COUNT);
  const [isMobile, setIsMobile] = useState(false);
  const { theme: currentTheme } = useTheme();
  const { token } = theme.useToken();

  // Handle responsive behavior
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  if (isLoading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          message="Error"
          description="Failed to load dashboard data. Please try again later."
          type="error"
          showIcon
          icon={<AlertOutlined />}
          data-testid="dashboard-error-alert"
        />
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div style={{ padding: 24 }}>
        <Empty description="No dashboard data available" />
      </div>
    );
  }


  const STATUS_TYPE_MAP: Record<string, 'success' | 'warning' | 'error'> = {
    'Critical': 'error',
    'Warning': 'warning',
    'Good': 'success'
  };

  const PROGRESS_THRESHOLDS = {
    EXCEPTION: 90,
    NORMAL: 75
  };

  const getStatusType = (status: string): 'success' | 'warning' | 'error' => {
    return STATUS_TYPE_MAP[status] || 'success';
  };

  const getProgressStatus = (percentage: number): 'exception' | 'normal' | 'success' => {
    if (percentage >= PROGRESS_THRESHOLDS.EXCEPTION) return 'exception';
    if (percentage >= PROGRESS_THRESHOLDS.NORMAL) return 'normal';
    return 'success';
  };

  const getActionIcon = (action: string) => {
    const actionLower = action.toLowerCase();
    if (actionLower.includes('create')) return <CheckCircleOutlined style={{ color: token.colorSuccess }} />;
    if (actionLower.includes('delete')) return <CloseCircleOutlined style={{ color: token.colorError }} />;
    if (actionLower.includes('update') || actionLower.includes('modify')) return <EditOutlined style={{ color: token.colorWarning }} />;
    if (actionLower.includes('login') || actionLower.includes('auth')) return <LoginOutlined style={{ color: token.colorInfo }} />;
    if (actionLower.includes('export') || actionLower.includes('import')) return <SwapOutlined style={{ color: token.colorPrimary }} />;
    return <InfoCircleOutlined style={{ color: token.colorTextSecondary }} />;
  };

  const TIME_UNITS = {
    MINUTE: 60000,
    HOUR: 60,
    DAY: 24,
    WEEK: 7
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / TIME_UNITS.MINUTE);

    if (diffMins < 1) return 'just now';
    if (diffMins < TIME_UNITS.HOUR) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;

    const diffHours = Math.floor(diffMins / TIME_UNITS.HOUR);
    if (diffHours < TIME_UNITS.DAY) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;

    const diffDays = Math.floor(diffHours / TIME_UNITS.DAY);
    if (diffDays < TIME_UNITS.WEEK) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

    return date.toLocaleDateString();
  };

  return (
    <div style={{ padding: isMobile ? 16 : 24 }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* 1. Alerts - Immediate visibility of critical issues */}
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

        {/* 2. Resource Usage - Critical capacity monitoring */}
        <Card
          title="Resource Usage"
          extra={<Text type="secondary">Monitor your resource consumption against plan limits</Text>}
          data-testid="dashboard-card-resource-usage"
        >
          <Row gutter={[16, 24]}>
            {dashboard.resources
              .filter((resource) => resource.ResourceType === 'Machine' || resource.ResourceType === 'Repo')
              .map((resource) => (
              <Col key={resource.ResourceType} xs={24} sm={12} md={8}>
                <div style={{
                  padding: '16px',
                  borderRadius: borderRadius('LG'),
                  border: `1px solid ${token.colorBorderSecondary}`,
                  backgroundColor: currentTheme === 'dark' ? token.colorBgContainer : token.colorBgLayout,
                  height: '100%',
                  transition: 'all 0.2s ease'
                }}>
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Space size="small">
                        {resourceIcons[resource.ResourceType]}
                        <Text strong>{resource.ResourceType}s</Text>
                      </Space>
                      <Text type="secondary" style={{ fontWeight: 500 }}>
                        {resource.CurrentUsage} / {resource.ResourceLimit === 0 ? '∞' : resource.ResourceLimit}
                      </Text>
                    </div>
                    <Progress
                      percent={resource.ResourceLimit === 0 ? 0 : resource.UsagePercentage}
                      status={getProgressStatus(resource.UsagePercentage)}
                      strokeColor={resource.IsLimitReached === 1 ?
                        (currentTheme === 'dark' ? '#ff6b6b' : token.colorError) :
                        (currentTheme === 'dark' ? '#7d9b49' : token.colorPrimary)}
                      data-testid={`dashboard-progress-${resource.ResourceType.toLowerCase()}`}
                      style={{ margin: '8px 0' }}
                    />
                    {resource.IsLimitReached === 1 && (
                      <Text type="danger" style={{ fontSize: 12, fontWeight: 500 }}>Limit reached</Text>
                    )}
                  </Space>
                </div>
              </Col>
            ))}
          </Row>
        </Card>

        {/* 3. Subscription & Plan Details - Plan context and limits */}
        <Card
          title={
            <Space>
              <CrownOutlined />
              <span>Subscription & Plan Details - {dashboard.planLimits.PlanCode}</span>
              {dashboard.allActiveSubscriptions && dashboard.allActiveSubscriptions.length > 0 && (
                <Badge count={dashboard.allActiveSubscriptions.length} style={{ backgroundColor: '#333333' }} />
              )}
            </Space>
          }
          data-testid="dashboard-card-subscription-plans"
        >
          {/* Row 1: Subscription Overview */}
          <Row gutter={[24, 24]}>
            {/* Current Subscription Section */}
            <Col xs={24} md={dashboard.allActiveSubscriptions && dashboard.allActiveSubscriptions.length > 0 ? 12 : 24}>
              {dashboard.activeSubscription ? (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>CURRENT SUBSCRIPTION</Text>
                    <Title level={4} style={{ margin: '8px 0 16px 0' }}>{dashboard.activeSubscription.PlanCode}</Title>

                    <Row gutter={[16, 16]}>
                      <Col span={12}>
                        <Statistic
                          title="Active Licenses"
                          value={dashboard.activeSubscription.TotalActivePurchases}
                          valueStyle={{ color: token.colorText }}
                          data-testid="dashboard-stat-active-licenses"
                        />
                      </Col>
                      <Col span={12}>
                        <Statistic
                          title="Days Remaining"
                          value={dashboard.activeSubscription.DaysRemaining}
                          valueStyle={{ color: dashboard.activeSubscription.DaysRemaining <= CRITICAL_DAYS_THRESHOLD ? token.colorError : token.colorText }}
                          data-testid="dashboard-stat-days-remaining"
                        />
                      </Col>
                    </Row>
                  </div>
                </Space>
              ) : (
                <Empty description="No active subscription" />
              )}
            </Col>

            {/* Active Licenses Section */}
            {dashboard.allActiveSubscriptions && dashboard.allActiveSubscriptions.length > 0 && (
              <Col xs={24} md={12}>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>ALL ACTIVE LICENSES</Text>
                    <Title level={4} style={{ margin: '8px 0' }}>{dashboard.allActiveSubscriptions.length} Total</Title>
                  </div>
                  <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      {dashboard.allActiveSubscriptions.map((sub, index) => (
                        <div key={index} style={{
                          padding: '12px',
                          backgroundColor: currentTheme === 'dark' ? token.colorBgContainer : token.colorBgLayout,
                          borderRadius: 6,
                          border: `1px solid ${token.colorBorder}`
                        }}
                        data-testid={`dashboard-license-item-${index}`}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                            <Space>
                              <Text strong>{sub.planCode}</Text>
                              <Badge count={`×${sub.quantity}`} style={{ backgroundColor: '#52c41a' }} />
                              {sub.isTrial === 1 && <Tag color="blue">Trial</Tag>}
                            </Space>
                            <Text type={sub.daysRemaining <= CRITICAL_DAYS_THRESHOLD ? 'danger' : 'secondary'} style={{ fontSize: 12 }}>
                              {sub.daysRemaining} {sub.daysRemaining === 1 ? 'day' : 'days'} remaining
                            </Text>
                          </div>
                          <Tooltip title={`From ${new Date(sub.startDate).toLocaleDateString()} to ${new Date(sub.endDate).toLocaleDateString()}`}>
                            <Progress
                              data-testid={`dashboard-progress-subscription-${sub.planCode}`}
                              percent={(() => {
                                // Calculate total subscription duration in days
                                const startDate = new Date(sub.startDate);
                                const endDate = new Date(sub.endDate);
                                const now = new Date();

                                // If we haven't started yet, show 0%
                                if (now < startDate) return 0;

                                // If we're past the end date, show 100%
                                if (now > endDate) return 100;

                                // Calculate total duration and elapsed time
                                const totalDuration = endDate.getTime() - startDate.getTime();
                                const elapsedDuration = now.getTime() - startDate.getTime();

                                // Calculate percentage
                                const percentConsumed = Math.max(0, Math.min(100, (elapsedDuration / totalDuration) * 100));

                                return Math.round(percentConsumed);
                              })()}
                              showInfo={false}
                              size="small"
                              strokeColor={sub.daysRemaining <= CRITICAL_DAYS_THRESHOLD ?
                                (currentTheme === 'dark' ? '#ff6b6b' : token.colorError) :
                                (currentTheme === 'dark' ? '#7d9b49' : token.colorPrimary)}
                            />
                          </Tooltip>
                        </div>
                      ))}
                    </Space>
                  </div>
                </Space>
              </Col>
            )}
          </Row>

          {/* Row 2: Plan Capabilities */}
          <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
            <Col xs={24}>
              <div>
                <Text type="secondary" style={{ fontSize: 12, marginBottom: 16, display: 'block' }}>PLAN CAPABILITIES</Text>
                <Row gutter={[16, 16]}>
                  <Col xs={24} sm={12} md={6}>
                    <Statistic
                      title="Max Active Jobs"
                      value={dashboard.planLimits.MaxActiveJobs}
                      valueStyle={{ color: token.colorPrimary }}
                    />
                  </Col>
                  <Col xs={24} sm={12} md={6}>
                    <Statistic
                      title="Max Reserved Jobs"
                      value={dashboard.planLimits.MaxReservedJobs}
                      valueStyle={{ color: token.colorPrimary }}
                    />
                  </Col>
                  <Col xs={24} sm={12} md={6}>
                    <Statistic
                      title="Job Timeout"
                      value={dashboard.planLimits.JobTimeoutHours}
                      suffix="hours"
                      valueStyle={{ color: token.colorPrimary }}
                    />
                  </Col>
                  <Col xs={24} sm={12} md={6}>
                    <Statistic
                      title="Max Repo Size"
                      value={dashboard.planLimits.MaxRepoSize}
                      suffix="GB"
                      valueStyle={{ color: token.colorPrimary }}
                    />
                  </Col>
                </Row>
              </div>
            </Col>
          </Row>
        </Card>

        {/* 4. Queue Overview - Operations snapshot */}
        {dashboard.queueStats ? (
          <Card
            title={
              <Space>
                <RobotOutlined />
                <span>Queue Overview</span>
              </Space>
            }
            extra={
              <Link to="/queue" style={{ color: token.colorPrimary }} data-testid="dashboard-queue-manage-link">Manage</Link>
            }
            data-testid="dashboard-card-queue-overview"
          >
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              {/* Status Grid */}
              <Row gutter={[16, 16]}>
                <Col span={6}>
                  <Statistic
                    title="Pending"
                    value={dashboard.queueStats.PendingCount || 0}
                    valueStyle={{ color: token.colorWarning }}
                    prefix={<ClockCircleOutlined />}
                    data-testid="dashboard-stat-pending"
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="Processing"
                    value={dashboard.queueStats.ActiveCount || 0}
                    valueStyle={{ color: token.colorInfo }}
                    prefix={<SyncOutlined spin />}
                    data-testid="dashboard-stat-processing"
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="Completed"
                    value={dashboard.queueStats.CompletedCount || 0}
                    valueStyle={{ color: token.colorSuccess }}
                    prefix={<CheckCircleOutlined />}
                    data-testid="dashboard-stat-completed"
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="Failed"
                    value={dashboard.queueStats.FailedCount || 0}
                    valueStyle={{ color: token.colorError }}
                    prefix={<ExclamationCircleOutlined />}
                    data-testid="dashboard-stat-failed"
                  />
                </Col>
              </Row>

              {/* Queue Alerts */}
              {(dashboard.queueStats.HasStaleItems === 1 ||
                dashboard.queueStats.HasOldPendingItems === 1) && (
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  {dashboard.queueStats.HasStaleItems === 1 && (
                    <Alert
                      message={`${dashboard.queueStats.StaleCount || 0} stale items`}
                      type="warning"
                      showIcon
                      icon={<WarningOutlined />}
                      data-testid="dashboard-alert-stale-items"
                    />
                  )}
                  {dashboard.queueStats.HasOldPendingItems === 1 && (
                    <Alert
                      message={`Oldest: ${Math.floor((dashboard.queueStats.OldestPendingAgeMinutes || 0) / 60)}h`}
                      type="info"
                      showIcon
                      icon={<FieldTimeOutlined />}
                      data-testid="dashboard-alert-old-pending"
                    />
                  )}
                </Space>
              )}
            </Space>
          </Card>
        ) : (
          <Card
            title={
              <Space>
                <RobotOutlined />
                <span>Queue Overview</span>
              </Space>
            }
            data-testid="dashboard-card-queue-overview-empty"
          >
            <Empty description="No queue data available" />
          </Card>
        )}

        {/* 5. Queue Details - Detailed queue breakdown */}
        {dashboard.queueStats && (
          (Array.isArray(dashboard.queueStats.TeamIssues) && dashboard.queueStats.TeamIssues.length > 0) ||
          (Array.isArray(dashboard.queueStats.MachineIssues) && dashboard.queueStats.MachineIssues.length > 0)
        ) && (
          <Card
            title={
              <Space>
                <RobotOutlined />
                <span>Queue Details</span>
              </Space>
            }
            data-testid="dashboard-card-queue-details"
          >
            <Row gutter={[16, 16]}>
              {/* Today's Activity */}
              <Col xs={24} lg={8}>
                <div style={{
                  padding: '16px',
                  backgroundColor: currentTheme === 'dark' ? token.colorBgContainer : token.colorBgLayout,
                  borderRadius: borderRadius('LG'),
                  border: `1px solid ${token.colorBorder}`,
                  height: '100%'
                }}>
                  <Text strong style={{ display: 'block', marginBottom: 12 }}>Today&apos;s Activity</Text>
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">Created</Text>
                      <Text strong style={{ fontSize: 18 }} data-testid="dashboard-stat-created-today">{dashboard.queueStats.CreatedToday || 0}</Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">Completed</Text>
                      <Text strong style={{ fontSize: 18, color: token.colorSuccess }} data-testid="dashboard-stat-completed-today">{dashboard.queueStats.CompletedToday || 0}</Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">Cancelled</Text>
                      <Text strong style={{ fontSize: 18, color: token.colorError }} data-testid="dashboard-stat-cancelled-today">{dashboard.queueStats.CancelledToday || 0}</Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">Failed</Text>
                      <Text strong style={{ fontSize: 18, color: token.colorError }} data-testid="dashboard-stat-failed-today">{dashboard.queueStats.FailedToday || 0}</Text>
                    </div>
                  </Space>
                </div>
              </Col>

              {/* Team and Machine Issues */}
              <Col xs={24} lg={16}>
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  {/* Team Issues */}
                  {Array.isArray(dashboard.queueStats.TeamIssues) &&
                   dashboard.queueStats.TeamIssues.length > 0 && (
                    <div>
                      <Text strong style={{ display: 'block', marginBottom: 12 }}>
                        <TeamOutlined /> Team Queue Status
                      </Text>
                      <List
                        size="small"
                        dataSource={dashboard.queueStats.TeamIssues}
                        data-testid="dashboard-list-team-issues"
                        renderItem={(team) => (
                          <List.Item style={{ paddingLeft: 0, paddingRight: 0 }}>
                            <div style={{ width: '100%' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                <Text strong>{team.TeamName}</Text>
                                <Space size="small">
                                  {(team.StaleItems || 0) > 0 && (
                                    <Tag color="warning">
                                      <WarningOutlined /> {team.StaleItems} stale
                                    </Tag>
                                  )}
                                  <Tag color="blue">{team.PendingItems || 0} pending</Tag>
                                  <Tag color="processing">{team.ActiveItems || 0} active</Tag>
                                </Space>
                              </div>
                            </div>
                          </List.Item>
                        )}
                      />
                    </div>
                  )}

                  {/* Machine Issues */}
                  {Array.isArray(dashboard.queueStats.MachineIssues) &&
                   dashboard.queueStats.MachineIssues.length > 0 && (
                    <div>
                      <Text strong style={{ display: 'block', marginBottom: 12 }}>
                        <DesktopOutlined /> Machine Queue Status
                      </Text>
                      <div style={{ overflowX: 'auto' }}>
                        <Table
                          size="small"
                          dataSource={dashboard.queueStats.MachineIssues}
                          pagination={false}
                          data-testid="dashboard-table-machine-issues"
                          columns={[
                            {
                              title: 'Machine',
                              dataIndex: 'MachineName',
                              key: 'MachineName',
                              ellipsis: true,
                            },
                            {
                              title: 'Team',
                              dataIndex: 'TeamName',
                              key: 'TeamName',
                              ellipsis: true,
                            },
                            {
                              title: 'Status',
                              key: 'status',
                              width: 200,
                              render: (_, record) => (
                                <Space size="small">
                                  {(record.StaleItems || 0) > 0 && (
                                    <Tag color="warning">{record.StaleItems} stale</Tag>
                                  )}
                                  <Tag color="blue">{record.PendingItems || 0} pending</Tag>
                                  <Tag color="processing">{record.ActiveItems || 0} active</Tag>
                                </Space>
                              ),
                            },
                          ]}
                        />
                      </div>
                    </div>
                  )}

                  {/* Priority Breakdown (Business/Enterprise only) */}
                  {dashboard.featureAccess.HasAdvancedAnalytics === 1 &&
                   dashboard.queueStats.HighestPriorityPending !== null && (
                    <div style={{
                      padding: '16px',
                      backgroundColor: currentTheme === 'dark' ? token.colorBgContainer : token.colorBgLayout,
                      borderRadius: borderRadius('LG'),
                      border: `1px solid ${token.colorBorder}`
                    }}>
                      <Text strong style={{ display: 'block', marginBottom: 12 }}>
                        <ThunderboltOutlined /> Priority Breakdown
                      </Text>
                      <Space direction="vertical" size="small" style={{ width: '100%' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>Highest Priority</Text>
                          <Badge count={dashboard.queueStats.HighestPriorityPending ?? 0} style={{ backgroundColor: token.colorError }} data-testid="dashboard-badge-highest-priority" />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>High Priority</Text>
                          <Badge count={dashboard.queueStats.HighPriorityPending ?? 0} style={{ backgroundColor: token.colorWarning }} data-testid="dashboard-badge-high-priority" />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>Normal Priority</Text>
                          <Badge count={dashboard.queueStats.NormalPriorityPending ?? 0} style={{ backgroundColor: token.colorInfo }} data-testid="dashboard-badge-normal-priority" />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>Low Priority</Text>
                          <Badge count={dashboard.queueStats.LowPriorityPending ?? 0} style={{ backgroundColor: token.colorTextSecondary }} data-testid="dashboard-badge-low-priority" />
                        </div>
                      </Space>
                    </div>
                  )}
                </Space>
              </Col>
            </Row>
          </Card>
        )}

        {/* 6. Distributed Storage - Storage statistics (Business/Enterprise only) */}
        {dashboard.featureAccess?.HasAdvancedAnalytics === 1 && dashboard.distributedStorageStats && (
          <DistributedStorageDashboardWidget stats={dashboard.distributedStorageStats} />
        )}

        {/* 7. Account Health - System health monitoring */}
        <Card
          data-testid="dashboard-account-health-card"
          title={
            <Space>
              <SafetyCertificateOutlined />
              <span>Account Health</span>
            </Space>
          }
        >
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>Overall Status</Text>
              <Tag color={getStatusType(dashboard.accountHealth.SubscriptionStatus)}>
                {dashboard.accountHealth.SubscriptionStatus}
              </Tag>
            </div>

            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <Space>
                {dashboard.accountHealth.ResourcesAtLimit > 0 ? (
                  <ExclamationCircleOutlined style={{ color: token.colorWarning }} />
                ) : (
                  <CheckCircleOutlined style={{ color: token.colorSuccess }} />
                )}
                <Text>{dashboard.accountHealth.ResourcesAtLimit} resources at limit</Text>
              </Space>

              <Space>
                <ClockCircleOutlined style={{ color: token.colorTextSecondary }} />
                <Text>{dashboard.accountHealth.ResourcesNearLimit} resources near limit</Text>
              </Space>
            </Space>

            <div style={{ paddingTop: 12, borderTop: `1px solid ${token.colorBorder}` }}>
              <Text strong>{dashboard.accountHealth.UpgradeRecommendation}</Text>
            </div>
          </Space>
        </Card>

        {/* 8. Recent Activity - Historical activity log */}
        <Card
          title={
            <Space>
              <HistoryOutlined />
              <span>Recent Activity</span>
            </Space>
          }
          extra={
            <Link to="/audit" style={{ color: token.colorPrimary }} data-testid="dashboard-activity-viewall-link">View All</Link>
          }
          data-testid="dashboard-card-recent-activity"
        >
          {auditLoading ? (
            <div style={{ textAlign: 'center', padding: '20px' }}>
              <Spin />
            </div>
          ) : auditLogs && auditLogs.length > 0 ? (
            <Timeline
              items={auditLogs
                .filter(log => {
                  // Filter out repetitive low-value activities
                  const action = log.action.toLowerCase();
                  const isTokenValidation = action.includes('token') && action.includes('validat');
                  const isRoutineAuth = action.includes('login') && action.includes('success');

                  // Show only meaningful activities, skip routine validations
                  return !isTokenValidation && !isRoutineAuth;
                })
                .slice(0, 5) // Show max 5 meaningful activities
                .map((log, index) => ({
                key: index,
                dot: getActionIcon(log.action),
                children: (
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <Space size={8}>
                        <Text strong style={{ fontSize: 14 }}>{log.action.replace(/_/g, ' ')}</Text>
                        <Tag>{log.entity}</Tag>
                      </Space>
                      <Text type="secondary" style={{ fontSize: 11, flexShrink: 0, marginLeft: 8 }}>
                        {formatTimestamp(log.timestamp)}
                      </Text>
                    </div>
                    <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.4 }}>
                      {log.entityName} {log.actionByUser && `• ${log.actionByUser}`}
                    </Text>
                    {log.details && log.details.trim() && (
                      <Text type="secondary" style={{ fontSize: 11, opacity: 0.8 }}>
                        {log.details.length > DESCRIPTION_TRUNCATE_LENGTH ? `${log.details.substring(0, DESCRIPTION_TRUNCATE_LENGTH)}...` : log.details}
                      </Text>
                    )}
                  </Space>
                )
              }))}
            />
          ) : (
            <Empty
              description="No recent activity"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              style={{ padding: '20px 0' }}
            />
          )}
        </Card>

      </Space>
    </div>
  );
};

export default DashboardPage;