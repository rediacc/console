import React, { useState, useEffect } from 'react';
import { Card, Col, Row, Progress, Alert, Badge, Tag, Space, Typography, Statistic, Spin, Empty, Divider, Tooltip } from 'antd';
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
  InboxOutlined
} from '@ant-design/icons';
import { useDashboard } from '../api/queries/dashboard';
import { fetchPricingConfig, getPlanPrice, PricingConfig } from '../api/pricingService';
import { useTranslation } from 'react-i18next';

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
  const [pricing, setPricing] = useState<PricingConfig | null>(null);
  const [pricingLoading, setPricingLoading] = useState(true);
  const { t } = useTranslation('common');

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
                      <ExclamationCircleOutlined style={{ color: '#666666' }} />
                    ) : (
                      <CheckCircleOutlined style={{ color: '#333333' }} />
                    )}
                    <Text>{dashboard.accountHealth.ResourcesAtLimit} resources at limit</Text>
                  </Space>
                  
                  <Space>
                    <ClockCircleOutlined style={{ color: '#999999' }} />
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
                    strokeColor={resource.IsLimitReached === 1 ? '#666666' : '#333333'}
                  />
                  {resource.IsLimitReached === 1 && (
                    <Text type="danger" style={{ fontSize: 12 }}>Limit reached</Text>
                  )}
                </Space>
              </Col>
            ))}
          </Row>
        </Card>

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
                          valueStyle={{ color: '#333333' }}
                        />
                      </Col>
                      <Col span={12}>
                        <Statistic
                          title="Days Remaining"
                          value={dashboard.activeSubscription.DaysRemaining}
                          valueStyle={{ color: dashboard.activeSubscription.DaysRemaining <= 30 ? '#ff4d4f' : '#333333' }}
                        />
                      </Col>
                    </Row>
                  </div>

                  {/* Billing Info */}
                  {!pricingLoading && pricing && (
                    <div style={{ 
                      padding: '16px', 
                      backgroundColor: '#fafafa', 
                      borderRadius: 8,
                      border: '1px solid #f0f0f0'
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
                              ? `Billed ${dashboard.billingInfo.BillingInterval}ly in ${dashboard.billingInfo.Currency.toUpperCase()}`
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
                          backgroundColor: '#fafafa', 
                          borderRadius: 6,
                          border: '1px solid #f0f0f0'
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                            <Space>
                              <Text strong>{sub.planName}</Text>
                              <Badge count={`×${sub.quantity}`} style={{ backgroundColor: '#52c41a' }} />
                              {sub.isTrial === 1 && <Tag color="blue">Trial</Tag>}
                            </Space>
                            <Text type={sub.daysRemaining <= 30 ? 'danger' : 'secondary'} style={{ fontSize: 12 }}>
                              {sub.daysRemaining} days left
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
                              strokeColor={sub.daysRemaining <= 30 ? '#ff4d4f' : '#333333'}
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
                            backgroundColor: plan.IsCurrentPlan === 1 ? '#f5f5f5' : '#fafafa',
                            borderRadius: 6,
                            border: plan.IsCurrentPlan === 1 ? '2px solid #333333' : '1px solid #f0f0f0'
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

const FeatureItem = ({ name, enabled }: { name: string; enabled: boolean }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
    <Text>{name}</Text>
    {enabled ? (
      <CheckCircleOutlined style={{ color: '#333333', fontSize: 16 }} />
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