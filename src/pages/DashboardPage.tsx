import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Card, Col, Row, Progress, Alert, Badge, Tag, Space, Typography, Statistic, Spin, Empty, Divider, Tooltip, theme, Timeline, List, Table } from 'antd';
import { 
  AlertOutlined, 
  CheckCircleOutlined, 
  ClockCircleOutlined, 
  CreditCardOutlined, 
  ShoppingOutlined, 
  SafetyCertificateOutlined, 
  RiseOutlined,
  UserOutlined,
  CloudOutlined,
  CalendarOutlined,
  TeamOutlined,
  ExclamationCircleOutlined,
  CrownOutlined,
  DesktopOutlined,
  ApiOutlined,
  EnvironmentOutlined,
  InboxOutlined,
  HistoryOutlined,
  FileTextOutlined,
  CloseCircleOutlined,
  EditOutlined,
  LoginOutlined,
  SwapOutlined,
  InfoCircleOutlined,
  SyncOutlined,
  HourglassOutlined,
  CheckOutlined,
  StopOutlined,
  ThunderboltOutlined,
  WarningOutlined,
  FieldTimeOutlined,
  RobotOutlined
} from '@/utils/optimizedIcons';
import { useDashboard } from '../api/queries/dashboard';
import { useRecentAuditLogs } from '../api/queries/audit';
import { fetchPricingConfig, getPlanPrice, PricingConfig } from '../api/pricingService';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/context/ThemeContext';
import DistributedStorageDashboardWidget from '../components/dashboard/DistributedStorageDashboardWidget';

const { Title, Text, Paragraph } = Typography;

const resourceIcons: Record<string, React.ReactNode> = {
  'User': <UserOutlined />,
  'Team': <TeamOutlined />,
  'Region': <EnvironmentOutlined />,
  'Bridge': <ApiOutlined />,
  'Machine': <DesktopOutlined />,
  'Repo': <InboxOutlined />,
  'Schedule': <CalendarOutlined />,
  'Storage': <CloudOutlined />
};

// Constants
const CRITICAL_DAYS_THRESHOLD = 30;
const MAX_NOTIFICATIONS = 50;
const RECENT_AUDIT_LOGS_COUNT = 10;
const DESCRIPTION_TRUNCATE_LENGTH = 100;

const DashboardPage = () => {
  const { data: dashboard, isLoading, error } = useDashboard();
  const { data: auditLogs, isLoading: auditLoading } = useRecentAuditLogs(RECENT_AUDIT_LOGS_COUNT);
  const [pricing, setPricing] = useState<PricingConfig | null>(null);
  const [pricingLoading, setPricingLoading] = useState(true);
  const { t } = useTranslation('common');
  const { theme: currentTheme } = useTheme();
  const { token } = theme.useToken();

  // Fetch pricing configuration
  useEffect(() => {
    const loadPricing = async () => {
      setPricingLoading(true);
      try {
        const pricingData = await fetchPricingConfig();
        setPricing(pricingData);
      } catch (error) {
        setPricing(null);
      } finally {
        setPricingLoading(false);
      }
    };
    
    loadPricing();
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
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Title level={2}>Dashboard</Title>
        <Text type="secondary">Welcome to {dashboard.companyInfo.CompanyName}</Text>
      </div>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Alerts - Moved to top for immediate visibility */}
        {dashboard.activeSubscription?.IsExpiringSoon === 1 && (
          <Alert
            message="Subscription Expiring Soon"
            description={`Your ${dashboard.activeSubscription.PlanName} subscription expires in ${dashboard.activeSubscription.DaysRemaining} days.${!dashboard.activeSubscription.AutoRenew ? ' Enable auto-renewal to avoid service interruption.' : ''}`}
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

        {/* Account Health & Queue Statistics - Side by side */}
        <Row gutter={[16, 16]}>
          {/* Account Health Card */}
          <Col xs={24} lg={12}>
            <Card 
              data-testid="dashboard-account-health-card"
              title={
                <Space>
                  <SafetyCertificateOutlined />
                  <span>Account Health</span>
                </Space>
              }
              style={{ height: '100%' }}
              data-testid="dashboard-card-account-health"
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
          </Col>

          {/* Queue Overview Card */}
          <Col xs={24} lg={12}>
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
                style={{ height: '100%' }}
                data-testid="dashboard-card-queue-overview"
              >
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  {/* Status Grid */}
                  <Row gutter={[16, 16]}>
                    <Col span={6}>
                      <Statistic
                        title="Pending"
                        value={dashboard.queueStats.pending_count || 0}
                        valueStyle={{ color: token.colorWarning }}
                        prefix={<ClockCircleOutlined />}
                        data-testid="dashboard-stat-pending"
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="Processing"
                        value={dashboard.queueStats.active_count || 0}
                        valueStyle={{ color: token.colorInfo }}
                        prefix={<SyncOutlined spin />}
                        data-testid="dashboard-stat-processing"
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="Completed"
                        value={dashboard.queueStats.completed_count || 0}
                        valueStyle={{ color: token.colorSuccess }}
                        prefix={<CheckCircleOutlined />}
                        data-testid="dashboard-stat-completed"
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="Failed"
                        value={dashboard.queueStats.failed_count || 0}
                        valueStyle={{ color: token.colorError }}
                        prefix={<ExclamationCircleOutlined />}
                        data-testid="dashboard-stat-failed"
                      />
                    </Col>
                  </Row>

                  {/* Queue Alerts */}
                  {(dashboard.queueStats.has_stale_items === 1 || 
                    dashboard.queueStats.has_old_pending_items === 1) && (
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      {dashboard.queueStats.has_stale_items === 1 && (
                        <Alert
                          message={`${dashboard.queueStats.stale_count || 0} stale items`}
                          type="warning"
                          showIcon
                          icon={<WarningOutlined />}
                          data-testid="dashboard-alert-stale-items"
                        />
                      )}
                      {dashboard.queueStats.has_old_pending_items === 1 && (
                        <Alert
                          message={`Oldest: ${Math.floor((dashboard.queueStats.oldest_pending_age_minutes || 0) / 60)}h`}
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
                style={{ height: '100%' }}
                data-testid="dashboard-card-queue-overview-empty"
              >
                <Empty description="No queue data available" />
              </Card>
            )}
          </Col>
        </Row>

        {/* Resource Usage */}
        <Card 
          title="Resource Usage"
          extra={<Text type="secondary">Monitor your resource consumption against plan limits</Text>}
          data-testid="dashboard-card-resource-usage"
        >
          <Row gutter={[16, 24]}>
            {dashboard.resources.map((resource) => (
              <Col key={resource.ResourceType} xs={24} sm={12} md={8}>
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Space>
                      {resourceIcons[resource.ResourceType]}
                      <Text strong>{resource.ResourceType}s</Text>
                    </Space>
                    <Text type="secondary">
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
                  />
                  {resource.IsLimitReached === 1 && (
                    <Text type="danger" style={{ fontSize: 12 }}>Limit reached</Text>
                  )}
                </Space>
              </Col>
            ))}
          </Row>
        </Card>

        {/* Recent Activity - Audit Logs */}
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
              items={auditLogs.map((log, index) => ({
                key: index,
                dot: getActionIcon(log.action),
                children: (
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Space>
                        <Text strong>{log.action.replace(/_/g, ' ')}</Text>
                        <Tag>{log.entity}</Tag>
                      </Space>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {formatTimestamp(log.timestamp)}
                      </Text>
                    </div>
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      {log.entityName} • By {log.actionByUser}
                    </Text>
                    {log.details && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {log.details.length > DESCRIPTION_TRUNCATE_LENGTH ? `${log.details.substring(0, DESCRIPTION_TRUNCATE_LENGTH)}...` : log.details}
                      </Text>
                    )}
                  </Space>
                )
              }))}
            />
          ) : (
            <Empty description="No recent activity" />
          )}
        </Card>

        {/* Queue Details - Team and Machine breakdown */}
        {dashboard.queueStats && (
          (dashboard.queueStats.team_issues || dashboard.queueStats.TeamIssues) && 
          Array.isArray(dashboard.queueStats.team_issues || dashboard.queueStats.TeamIssues) && 
          (dashboard.queueStats.team_issues || dashboard.queueStats.TeamIssues).length > 0 ||
          (dashboard.queueStats.machine_issues || dashboard.queueStats.MachineIssues) && 
          Array.isArray(dashboard.queueStats.machine_issues || dashboard.queueStats.MachineIssues) && 
          (dashboard.queueStats.machine_issues || dashboard.queueStats.MachineIssues).length > 0
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
                  borderRadius: 8,
                  border: `1px solid ${token.colorBorder}`,
                  height: '100%'
                }}>
                  <Text strong style={{ display: 'block', marginBottom: 12 }}>Today's Activity</Text>
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">Created</Text>
                      <Text strong style={{ fontSize: 18 }} data-testid="dashboard-stat-created-today">{dashboard.queueStats.created_today || 0}</Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">Completed</Text>
                      <Text strong style={{ fontSize: 18, color: token.colorSuccess }} data-testid="dashboard-stat-completed-today">{dashboard.queueStats.completed_today || 0}</Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">Cancelled</Text>
                      <Text strong style={{ fontSize: 18, color: token.colorError }} data-testid="dashboard-stat-cancelled-today">{dashboard.queueStats.cancelled_today || 0}</Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">Failed</Text>
                      <Text strong style={{ fontSize: 18, color: token.colorError }} data-testid="dashboard-stat-failed-today">{dashboard.queueStats.failed_today || 0}</Text>
                    </div>
                  </Space>
                </div>
              </Col>

              {/* Team and Machine Issues */}
              <Col xs={24} lg={16}>
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  {/* Team Issues */}
                  {dashboard.queueStats.team_issues && 
                   Array.isArray(dashboard.queueStats.team_issues || dashboard.queueStats.TeamIssues) && 
                   (dashboard.queueStats.team_issues || dashboard.queueStats.TeamIssues).length > 0 && (
                    <div>
                      <Text strong style={{ display: 'block', marginBottom: 12 }}>
                        <TeamOutlined /> Team Queue Status
                      </Text>
                      <List
                        size="small"
                        dataSource={dashboard.queueStats.team_issues || dashboard.queueStats.TeamIssues}
                        data-testid="dashboard-list-team-issues"
                        renderItem={(team) => (
                          <List.Item style={{ paddingLeft: 0, paddingRight: 0 }}>
                            <div style={{ width: '100%' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                <Text strong>{team.team_name}</Text>
                                <Space size="small">
                                  {(team.stale_items || 0) > 0 && (
                                    <Tag color="warning">
                                      <WarningOutlined /> {team.stale_items} stale
                                    </Tag>
                                  )}
                                  <Tag color="blue">{team.pending_items || 0} pending</Tag>
                                  <Tag color="processing">{team.active_items || 0} active</Tag>
                                </Space>
                              </div>
                            </div>
                          </List.Item>
                        )}
                      />
                    </div>
                  )}

                  {/* Machine Issues */}
                  {(dashboard.queueStats.machine_issues || dashboard.queueStats.MachineIssues) && 
                   Array.isArray(dashboard.queueStats.machine_issues || dashboard.queueStats.MachineIssues) && 
                   (dashboard.queueStats.machine_issues || dashboard.queueStats.MachineIssues).length > 0 && (
                    <div>
                      <Text strong style={{ display: 'block', marginBottom: 12 }}>
                        <DesktopOutlined /> Machine Queue Status
                      </Text>
                      <div style={{ overflowX: 'auto' }}>
                        <Table
                          size="small"
                          dataSource={dashboard.queueStats.machine_issues || dashboard.queueStats.MachineIssues}
                          pagination={false}
                          data-testid="dashboard-table-machine-issues"
                          columns={[
                            {
                              title: 'Machine',
                              dataIndex: 'MachineName',
                              key: 'MachineName',
                              ellipsis: true,
                              render: (value, record) => record.machine_name || record.MachineName || value,
                            },
                            {
                              title: 'Team',
                              dataIndex: 'TeamName',
                              key: 'TeamName',
                              ellipsis: true,
                              render: (value, record) => record.team_name || record.TeamName || value,
                            },
                            {
                              title: 'Status',
                              key: 'status',
                              width: 200,
                              render: (_, record) => (
                                <Space size="small">
                                  {(record.stale_items || record.StaleItems || 0) > 0 && (
                                    <Tag color="warning">{record.stale_items || record.StaleItems} stale</Tag>
                                  )}
                                  <Tag color="blue">{record.pending_items || record.PendingItems || 0} pending</Tag>
                                  <Tag color="processing">{record.active_items || record.ActiveItems || 0} active</Tag>
                                </Space>
                              ),
                            },
                          ]}
                        />
                      </div>
                    </div>
                  )}

                  {/* Priority Breakdown (Premium/Elite only) */}
                  {(dashboard.featureAccess.has_advanced_analytics || dashboard.featureAccess.HasAdvancedAnalytics) === 1 && 
                   (dashboard.queueStats.highest_priority_pending !== null || dashboard.queueStats.HighestPriorityPending !== null) && (
                    <div style={{ 
                      padding: '16px', 
                      backgroundColor: currentTheme === 'dark' ? token.colorBgContainer : token.colorBgLayout, 
                      borderRadius: 8,
                      border: `1px solid ${token.colorBorder}`
                    }}>
                      <Text strong style={{ display: 'block', marginBottom: 12 }}>
                        <ThunderboltOutlined /> Priority Breakdown
                      </Text>
                      <Space direction="vertical" size="small" style={{ width: '100%' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>Highest Priority</Text>
                          <Badge count={dashboard.queueStats.highest_priority_pending ?? dashboard.queueStats.HighestPriorityPending ?? 0} style={{ backgroundColor: token.colorError }} data-testid="dashboard-badge-highest-priority" />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>High Priority</Text>
                          <Badge count={dashboard.queueStats.high_priority_pending ?? dashboard.queueStats.HighPriorityPending ?? 0} style={{ backgroundColor: token.colorWarning }} data-testid="dashboard-badge-high-priority" />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>Normal Priority</Text>
                          <Badge count={dashboard.queueStats.normal_priority_pending ?? dashboard.queueStats.NormalPriorityPending ?? 0} style={{ backgroundColor: token.colorInfo }} data-testid="dashboard-badge-normal-priority" />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>Low Priority</Text>
                          <Badge count={dashboard.queueStats.low_priority_pending ?? dashboard.queueStats.LowPriorityPending ?? 0} style={{ backgroundColor: token.colorTextSecondary }} data-testid="dashboard-badge-low-priority" />
                        </div>
                      </Space>
                    </div>
                  )}
                </Space>
              </Col>
            </Row>
          </Card>
        )}

        {/* Distributed Storage Machine Statistics - Premium/Elite only */}
        {dashboard.featureAccess?.HasAdvancedAnalytics === 1 && dashboard.distributedStorageStats && (
          <DistributedStorageDashboardWidget stats={dashboard.distributedStorageStats} />
        )}

        {/* Subscription & Plans Card - Full Width */}
        <Card 
          title={
            <Space>
              <CrownOutlined />
              <span>Subscription & Plans</span>
              {dashboard.allActiveSubscriptions && dashboard.allActiveSubscriptions.length > 0 && (
                <Badge count={dashboard.allActiveSubscriptions.length} style={{ backgroundColor: '#333333' }} />
              )}
            </Space>
          }
          data-testid="dashboard-card-subscription-plans"
        >
          <Row gutter={[24, 24]}>
            {/* Current Subscription Section */}
            <Col xs={24} md={8}>
              {dashboard.activeSubscription ? (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>CURRENT SUBSCRIPTION</Text>
                    <Title level={4} style={{ margin: '8px 0' }}>{dashboard.activeSubscription.PlanName}</Title>
                    <Paragraph type="secondary" style={{ marginBottom: 16 }}>
                      {dashboard.activeSubscription.PlanDescription}
                    </Paragraph>
                    
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

                  {/* Billing Info */}
                  {!pricingLoading && pricing && (
                    <div style={{ 
                      padding: '16px', 
                      backgroundColor: currentTheme === 'dark' ? token.colorBgContainer : token.colorBgLayout, 
                      borderRadius: 8,
                      border: `1px solid ${token.colorBorder}`
                    }}>
                      <Space direction="vertical" size="small" style={{ width: '100%' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Text strong>Monthly Cost</Text>
                          <Title level={3} style={{ margin: 0 }} data-testid="dashboard-stat-monthly-cost">
                            ${(() => {
                              let totalMonthlyCost = 0;
                              
                              // Calculate from all active subscriptions if available
                              if (dashboard.allActiveSubscriptions && dashboard.allActiveSubscriptions.length > 0) {
                                dashboard.allActiveSubscriptions.forEach(sub => {
                                  const planPrice = getPlanPrice(pricing, sub.planCode);
                                  if (planPrice !== null && sub.isTrial !== 1) {
                                    totalMonthlyCost += planPrice * sub.quantity;
                                  }
                                });
                              } else if (dashboard.billingInfo && dashboard.activeSubscription) {
                                // Fallback to single subscription calculation
                                totalMonthlyCost = dashboard.billingInfo.Price * (dashboard.activeSubscription.Quantity || 1);
                              }
                              
                              return totalMonthlyCost.toFixed(2);
                            })()}
                          </Title>
                        </div>
                        <Text type="secondary">
                          {dashboard.allActiveSubscriptions && dashboard.allActiveSubscriptions.length > 1
                            ? `Total from ${dashboard.allActiveSubscriptions.length} active subscriptions`
                            : dashboard.billingInfo 
                              ? `Billed ${dashboard.billingInfo.BillingInterval}ly • ${dashboard.billingInfo.Currency.toUpperCase()}`
                              : 'Monthly subscription cost'
                          }
                        </Text>
                        {dashboard.activeSubscription?.IsTrial === 1 && (
                          <Tag color="blue">Trial Period</Tag>
                        )}
                      </Space>
                    </div>
                  )}
                </Space>
              ) : (
                <Empty description="No active subscription" />
              )}
            </Col>

            {/* Active Licenses Section */}
            {dashboard.allActiveSubscriptions && dashboard.allActiveSubscriptions.length > 0 && (
              <Col xs={24} md={8}>
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
                              <Text strong>{sub.planName}</Text>
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

            {/* Available Plans Section */}
            {dashboard.availablePlans.length > 0 && (
              <Col xs={24} md={dashboard.allActiveSubscriptions && dashboard.allActiveSubscriptions.length > 0 ? 8 : 16}>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {(() => {
                        const currentPlan = dashboard.availablePlans.find(plan => plan.IsCurrentPlan === 1);
                        return currentPlan && currentPlan.PlanCode !== 'ELITE' ? 'UPGRADE OPTIONS' : 'AVAILABLE PLANS';
                      })()}
                    </Text>
                    <Title level={4} style={{ margin: '8px 0' }}>Choose Your Plan</Title>
                  </div>
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    {(() => {
                      const planHierarchy = ['COMMUNITY', 'ADVANCED', 'PREMIUM', 'ELITE'];
                      const currentPlan = dashboard.availablePlans.find(plan => plan.IsCurrentPlan === 1);
                      const currentPlanIndex = currentPlan ? planHierarchy.indexOf(currentPlan.PlanCode) : -1;
                      
                      const filteredPlans = dashboard.availablePlans
                        .filter(plan => {
                          const planIndex = planHierarchy.indexOf(plan.PlanCode);
                          return planIndex >= currentPlanIndex;
                        });
                      
                      return filteredPlans.map((plan) => (
                        <div 
                          key={plan.PlanCode} 
                          style={{ 
                            padding: '12px 16px',
                            backgroundColor: plan.IsCurrentPlan === 1 
                              ? (currentTheme === 'dark' ? token.colorBgElevated : token.colorBgContainer)
                              : (currentTheme === 'dark' ? token.colorBgContainer : token.colorBgLayout),
                            borderRadius: 6,
                            border: plan.IsCurrentPlan === 1 
                              ? `2px solid ${token.colorPrimary}` 
                              : `1px solid ${token.colorBorder}`
                          }}
                          data-testid={`dashboard-plan-item-${plan.PlanCode.toLowerCase()}`}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ flex: 1 }}>
                              <Space>
                                <Text strong>{plan.PlanName}</Text>
                                {plan.IsCurrentPlan === 1 && <Tag color="success">Current</Tag>}
                              </Space>
                              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                                Up to {plan.MaxUsers} users • {plan.Description}
                              </Text>
                            </div>
                            {!pricingLoading && pricing && (
                              (() => {
                                const planPrice = getPlanPrice(pricing, plan.PlanCode);
                                return planPrice !== null && (
                                  <Text strong style={{ fontSize: 16, minWidth: 80, textAlign: 'right' }}>
                                    {planPrice === 0 ? 'Free' : `$${planPrice}/mo`}
                                  </Text>
                                );
                              })()
                            )}
                          </div>
                        </div>
                      ));
                    })()}
                  </Space>
                </Space>
              </Col>
            )}
          </Row>
        </Card>

      </Space>
    </div>
  );
};

export default DashboardPage;