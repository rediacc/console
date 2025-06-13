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
} from '@ant-design/icons';
import { useDashboard } from '../api/queries/dashboard';
import { useRecentAuditLogs } from '../api/queries/audit';
import { fetchPricingConfig, getPlanPrice, PricingConfig } from '../api/pricingService';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/context/ThemeContext';

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

const DashboardPage = () => {
  const { data: dashboard, isLoading, error } = useDashboard();
  const { data: auditLogs, isLoading: auditLoading } = useRecentAuditLogs(10);
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
        console.error('Failed to load pricing:', error);
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


  const getStatusType = (status: string): 'success' | 'warning' | 'error' => {
    switch (status) {
      case 'Critical': return 'error';
      case 'Warning': return 'warning';
      case 'Good': return 'success';
      default: return 'success';
    }
  };

  const getProgressStatus = (percentage: number): 'exception' | 'normal' | 'success' => {
    if (percentage >= 90) return 'exception';
    if (percentage >= 75) return 'normal';
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
          />
        )}

        {dashboard.accountHealth.ResourcesAtLimit > 0 && (
          <Alert
            message="Resource Limits Reached"
            description={`${dashboard.accountHealth.ResourcesAtLimit} resource type(s) have reached their limits. Consider upgrading your plan to continue scaling.`}
            type="error"
            showIcon
            icon={<ExclamationCircleOutlined />}
          />
        )}

        {/* Account Health & Queue Statistics - Side by side */}
        <Row gutter={[16, 16]}>
          {/* Account Health Card */}
          <Col xs={24} lg={12}>
            <Card 
              title={
                <Space>
                  <SafetyCertificateOutlined />
                  <span>Account Health</span>
                </Space>
              }
              style={{ height: '100%' }}
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
                  <Link to="/queue" style={{ color: token.colorPrimary }}>Manage</Link>
                }
                style={{ height: '100%' }}
              >
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  {/* Status Grid */}
                  <Row gutter={[16, 16]}>
                    <Col span={6}>
                      <Statistic
                        title="Pending"
                        value={dashboard.queueStats.PendingCount}
                        valueStyle={{ color: token.colorWarning }}
                        prefix={<ClockCircleOutlined />}
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="Processing"
                        value={dashboard.queueStats.ActiveCount}
                        valueStyle={{ color: token.colorInfo }}
                        prefix={<SyncOutlined spin />}
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="Completed"
                        value={dashboard.queueStats.CompletedCount}
                        valueStyle={{ color: token.colorSuccess }}
                        prefix={<CheckCircleOutlined />}
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="Failed"
                        value={dashboard.queueStats.FailedCount || 0}
                        valueStyle={{ color: token.colorError }}
                        prefix={<ExclamationCircleOutlined />}
                      />
                    </Col>
                  </Row>

                  {/* Queue Alerts */}
                  {(dashboard.queueStats.HasStaleItems === 1 || dashboard.queueStats.HasOldPendingItems === 1) && (
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      {dashboard.queueStats.HasStaleItems === 1 && (
                        <Alert
                          message={`${dashboard.queueStats.StaleCount} stale items`}
                          type="warning"
                          showIcon
                          icon={<WarningOutlined />}
                        />
                      )}
                      {dashboard.queueStats.HasOldPendingItems === 1 && (
                        <Alert
                          message={`Oldest: ${Math.floor(dashboard.queueStats.OldestPendingAgeMinutes / 60)}h`}
                          type="info"
                          showIcon
                          icon={<FieldTimeOutlined />}
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
            <Link to="/audit" style={{ color: token.colorPrimary }}>View All</Link>
          }
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
                        {log.details.length > 100 ? `${log.details.substring(0, 100)}...` : log.details}
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
          dashboard.queueStats.TeamIssues && Array.isArray(dashboard.queueStats.TeamIssues) && dashboard.queueStats.TeamIssues.length > 0 ||
          dashboard.queueStats.MachineIssues && Array.isArray(dashboard.queueStats.MachineIssues) && dashboard.queueStats.MachineIssues.length > 0
        ) && (
          <Card 
            title={
              <Space>
                <RobotOutlined />
                <span>Queue Details</span>
              </Space>
            }
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
                      <Text strong style={{ fontSize: 18 }}>{dashboard.queueStats.CreatedToday}</Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">Completed</Text>
                      <Text strong style={{ fontSize: 18, color: token.colorSuccess }}>{dashboard.queueStats.CompletedToday}</Text>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary">Cancelled</Text>
                      <Text strong style={{ fontSize: 18, color: token.colorError }}>{dashboard.queueStats.CancelledToday}</Text>
                    </div>
                  </Space>
                </div>
              </Col>

              {/* Team and Machine Issues */}
              <Col xs={24} lg={16}>
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  {/* Team Issues */}
                  {dashboard.queueStats.TeamIssues && Array.isArray(dashboard.queueStats.TeamIssues) && dashboard.queueStats.TeamIssues.length > 0 && (
                    <div>
                      <Text strong style={{ display: 'block', marginBottom: 12 }}>
                        <TeamOutlined /> Team Queue Status
                      </Text>
                      <List
                        size="small"
                        dataSource={dashboard.queueStats.TeamIssues}
                        renderItem={(team) => (
                          <List.Item style={{ paddingLeft: 0, paddingRight: 0 }}>
                            <div style={{ width: '100%' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                <Text strong>{team.TeamName}</Text>
                                <Space size="small">
                                  {team.StaleItems > 0 && (
                                    <Tag color="warning">
                                      <WarningOutlined /> {team.StaleItems} stale
                                    </Tag>
                                  )}
                                  <Tag color="blue">{team.PendingItems} pending</Tag>
                                  <Tag color="processing">{team.ActiveItems} active</Tag>
                                </Space>
                              </div>
                            </div>
                          </List.Item>
                        )}
                      />
                    </div>
                  )}

                  {/* Machine Issues */}
                  {dashboard.queueStats.MachineIssues && Array.isArray(dashboard.queueStats.MachineIssues) && dashboard.queueStats.MachineIssues.length > 0 && (
                    <div>
                      <Text strong style={{ display: 'block', marginBottom: 12 }}>
                        <DesktopOutlined /> Machine Queue Status
                      </Text>
                      <div style={{ overflowX: 'auto' }}>
                        <Table
                          size="small"
                          dataSource={dashboard.queueStats.MachineIssues}
                          pagination={false}
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
                                  {record.StaleItems > 0 && (
                                    <Tag color="warning">{record.StaleItems} stale</Tag>
                                  )}
                                  <Tag color="blue">{record.PendingItems} pending</Tag>
                                  <Tag color="processing">{record.ActiveItems} active</Tag>
                                </Space>
                              ),
                            },
                          ]}
                        />
                      </div>
                    </div>
                  )}

                  {/* Priority Breakdown (Premium/Elite only) */}
                  {dashboard.featureAccess.HasAdvancedAnalytics === 1 && 
                   dashboard.queueStats.HighestPriorityPending !== null && (
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
                          <Badge count={dashboard.queueStats.HighestPriorityPending} style={{ backgroundColor: token.colorError }} />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>High Priority</Text>
                          <Badge count={dashboard.queueStats.HighPriorityPending} style={{ backgroundColor: token.colorWarning }} />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>Normal Priority</Text>
                          <Badge count={dashboard.queueStats.NormalPriorityPending} style={{ backgroundColor: token.colorInfo }} />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text>Low Priority</Text>
                          <Badge count={dashboard.queueStats.LowPriorityPending} style={{ backgroundColor: token.colorTextSecondary }} />
                        </div>
                      </Space>
                    </div>
                  )}
                </Space>
              </Col>
            </Row>
          </Card>
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
                        />
                      </Col>
                      <Col span={12}>
                        <Statistic
                          title="Days Remaining"
                          value={dashboard.activeSubscription.DaysRemaining}
                          valueStyle={{ color: dashboard.activeSubscription.DaysRemaining <= 30 ? token.colorError : token.colorText }}
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
                          <Title level={3} style={{ margin: 0 }}>
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
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                            <Space>
                              <Text strong>{sub.planName}</Text>
                              <Badge count={`×${sub.quantity}`} style={{ backgroundColor: '#52c41a' }} />
                              {sub.isTrial === 1 && <Tag color="blue">Trial</Tag>}
                            </Space>
                            <Text type={sub.daysRemaining <= 30 ? 'danger' : 'secondary'} style={{ fontSize: 12 }}>
                              {sub.daysRemaining} {sub.daysRemaining === 1 ? 'day' : 'days'} remaining
                            </Text>
                          </div>
                          <Tooltip title={`From ${new Date(sub.startDate).toLocaleDateString()} to ${new Date(sub.endDate).toLocaleDateString()}`}>
                            <Progress 
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
                              strokeColor={sub.daysRemaining <= 30 ? 
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