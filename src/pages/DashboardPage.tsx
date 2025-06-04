import React from 'react';
import { Card, Col, Row, Progress, Alert, Badge, Tag, Space, Typography, Statistic, Spin, Empty, Divider } from 'antd';
import { 
  AlertOutlined, 
  CheckCircleOutlined, 
  ClockCircleOutlined, 
  CreditCardOutlined, 
  ShoppingOutlined, 
  SafetyCertificateOutlined, 
  RiseOutlined,
  UserOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  CalendarOutlined,
  TeamOutlined,
  ExclamationCircleOutlined,
  CrownOutlined,
  HddOutlined,
  ApiOutlined
} from '@ant-design/icons';
import { useDashboard } from '../api/queries/dashboard';

const { Title, Text, Paragraph } = Typography;

const resourceIcons: Record<string, React.ReactNode> = {
  'User': <UserOutlined />,
  'Team': <TeamOutlined />,
  'Region': <CloudServerOutlined />,
  'Bridge': <ApiOutlined />,
  'Machine': <HddOutlined />,
  'Repo': <DatabaseOutlined />,
  'Schedule': <CalendarOutlined />,
  'Storage': <DatabaseOutlined />
};

const DashboardPage = () => {
  const { data: dashboard, isLoading, error } = useDashboard();

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

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Title level={2}>Dashboard</Title>
        <Text type="secondary">Welcome to {dashboard.companyInfo.CompanyName}</Text>
      </div>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Alerts */}
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

        {/* Main Grid */}
        <Row gutter={[16, 16]}>
          {/* Subscription Card */}
          <Col xs={24} sm={24} md={12} lg={8}>
            <Card 
              title={
                <Space>
                  <ShoppingOutlined />
                  <span>Current Plan</span>
                </Space>
              }
              style={{ height: '100%' }}
            >
              {dashboard.activeSubscription ? (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div>
                    <Space align="baseline" style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Title level={3} style={{ margin: 0 }}>{dashboard.activeSubscription.PlanName}</Title>
                      {dashboard.activeSubscription.IsTrial === 1 && (
                        <Tag color="blue">Trial</Tag>
                      )}
                    </Space>
                    <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                      {dashboard.activeSubscription.PlanDescription}
                    </Paragraph>
                  </div>
                  
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text>Expires in</Text>
                      <Text strong>{dashboard.activeSubscription.DaysRemaining} days</Text>
                    </div>
                    <Progress 
                      percent={Math.max(0, Math.min(100, (30 - dashboard.activeSubscription.DaysRemaining) / 30 * 100))}
                      status={getProgressStatus((30 - dashboard.activeSubscription.DaysRemaining) / 30 * 100)}
                      strokeColor="#556b2f"
                    />
                  </div>

                  {dashboard.billingInfo && (
                    <div style={{ paddingTop: 12, borderTop: '1px solid #f0f0f0' }}>
                      <Statistic
                        title="Billing"
                        value={dashboard.billingInfo.Price}
                        precision={2}
                        prefix="$"
                        suffix={`${dashboard.billingInfo.Currency.toUpperCase()} / ${dashboard.billingInfo.BillingInterval}`}
                      />
                    </div>
                  )}
                </Space>
              ) : (
                <Text type="secondary">No active subscription</Text>
              )}
            </Card>
          </Col>

          {/* Account Health Card */}
          <Col xs={24} sm={24} md={12} lg={8}>
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
                      <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
                    ) : (
                      <CheckCircleOutlined style={{ color: '#52c41a' }} />
                    )}
                    <Text>{dashboard.accountHealth.ResourcesAtLimit} resources at limit</Text>
                  </Space>
                  
                  <Space>
                    <ClockCircleOutlined style={{ color: '#faad14' }} />
                    <Text>{dashboard.accountHealth.ResourcesNearLimit} resources near limit</Text>
                  </Space>
                </Space>

                <div style={{ paddingTop: 12, borderTop: '1px solid #f0f0f0' }}>
                  <Text strong>{dashboard.accountHealth.UpgradeRecommendation}</Text>
                </div>
              </Space>
            </Card>
          </Col>

          {/* Feature Access Card */}
          <Col xs={24} sm={24} md={12} lg={8}>
            <Card 
              title={
                <Space>
                  <RiseOutlined />
                  <span>Feature Access</span>
                </Space>
              }
              style={{ height: '100%' }}
            >
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <FeatureItem 
                  name="Advanced Analytics" 
                  enabled={dashboard.featureAccess.HasAdvancedAnalytics === 1} 
                />
                <FeatureItem 
                  name="Priority Support" 
                  enabled={dashboard.featureAccess.HasPrioritySupport === 1} 
                />
                <FeatureItem 
                  name="Dedicated Account Manager" 
                  enabled={dashboard.featureAccess.HasDedicatedAccount === 1} 
                />
                <FeatureItem 
                  name="Custom Branding" 
                  enabled={dashboard.featureAccess.HasCustomBranding === 1} 
                />
              </Space>
            </Card>
          </Col>
        </Row>

        {/* Resource Usage */}
        <Card 
          title="Resource Usage"
          extra={<Text type="secondary">Monitor your resource consumption against plan limits</Text>}
        >
          <Row gutter={[16, 24]}>
            {dashboard.resourceLimits.map((resource) => (
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
                    strokeColor={resource.IsLimitReached === 1 ? '#ff4d4f' : '#556b2f'}
                  />
                  {resource.IsLimitReached === 1 && (
                    <Text type="danger" style={{ fontSize: 12 }}>Limit reached</Text>
                  )}
                </Space>
              </Col>
            ))}
          </Row>
        </Card>

        {/* Available Plans */}
        {dashboard.availablePlans.length > 0 && (
          <Card 
            title="Available Plans"
            extra={<Text type="secondary">Compare features and pricing across different subscription tiers</Text>}
          >
            <Row gutter={[16, 16]}>
              {dashboard.availablePlans.map((plan) => (
                <Col key={plan.PlanCode} xs={24} sm={12} md={6}>
                  <Card
                    bordered
                    style={{ 
                      borderColor: plan.IsCurrentPlan === 1 ? '#556b2f' : undefined,
                      backgroundColor: plan.IsCurrentPlan === 1 ? '#f6ffed' : undefined
                    }}
                  >
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Title level={4} style={{ margin: 0 }}>{plan.PlanName}</Title>
                        {plan.IsCurrentPlan === 1 && (
                          <Badge status="success" text="Current" />
                        )}
                      </div>
                      <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                        {plan.Description}
                      </Paragraph>
                      <div>
                        <Statistic
                          value={plan.DefaultPrice}
                          precision={0}
                          prefix="$"
                          suffix="/month"
                        />
                        <Text type="secondary">Up to {plan.MaxUsers} users</Text>
                      </div>
                    </Space>
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        )}
      </Space>
    </div>
  );
};

const FeatureItem = ({ name, enabled }: { name: string; enabled: boolean }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
    <Text>{name}</Text>
    {enabled ? (
      <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
    ) : (
      <div style={{ 
        width: 16, 
        height: 16, 
        borderRadius: '50%', 
        backgroundColor: '#f0f0f0' 
      }} />
    )}
  </div>
);

export default DashboardPage;