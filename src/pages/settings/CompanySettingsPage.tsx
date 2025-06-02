import React, { useState } from 'react'
import { Typography, Space, Card, Row, Col, Progress, Statistic, Tag, Button, List, Badge, Tabs, Modal, Descriptions, Timeline } from 'antd'
import {
  CrownOutlined,
  SafetyOutlined,
  TeamOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  ScheduleOutlined,
  UserOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  SettingOutlined,
  LineChartOutlined,
  PieChartOutlined,
} from '@ant-design/icons'
import { Line, Pie, Column, Gauge } from '@ant-design/charts'
import VaultConfigModal from '@/components/common/VaultConfigModal'
import { 
  useSubscriptionDetails, 
  useResourceLimits, 
  useSubscriptionAnalytics,
  useUpdateCompanyVault,
  useCompanyVault
} from '@/api/queries/company'
import { useAppSelector } from '@/store/store'
import { selectCompany } from '@/store/auth/authSelectors'

const { Title, Text } = Typography

const CompanySettingsPage: React.FC = () => {
  const [vaultModalOpen, setVaultModalOpen] = useState(false)
  
  const company = useAppSelector(selectCompany)
  const { data: subscription, isLoading: subLoading } = useSubscriptionDetails()
  const { data: limits, isLoading: limitsLoading } = useResourceLimits()
  const { data: analytics, isLoading: analyticsLoading } = useSubscriptionAnalytics()
  const { data: companyVault } = useCompanyVault()
  const updateVaultMutation = useUpdateCompanyVault()

  const handleUpdateVault = async (vault: string, version: number) => {
    await updateVaultMutation.mutateAsync({
      companyVault: vault,
      vaultVersion: version,
    })
    setVaultModalOpen(false)
  }

  const getUsagePercent = (current: number, max: number) => {
    if (!max) return 0
    return Math.round((current / max) * 100)
  }

  const getUsageColor = (percent: number) => {
    if (percent >= 90) return '#ff4d4f'
    if (percent >= 70) return '#faad14'
    return '#52c41a'
  }

  // Usage trend chart config
  const usageTrendConfig = {
    data: analytics?.usageOverTime || [],
    xField: 'month',
    yField: 'value',
    seriesField: 'type',
    smooth: true,
    animation: {
      appear: {
        animation: 'path-in',
        duration: 1000,
      },
    },
    color: ['#556b2f', '#7d9b49', '#808000', '#a5b4fc'],
  }

  // Transform usage data for line chart
  const usageTrendData = analytics?.usageOverTime.flatMap(month => [
    { month: month.month, value: month.users, type: 'Users' },
    { month: month.month, value: month.teams, type: 'Teams' },
    { month: month.month, value: month.machines, type: 'Machines' },
    { month: month.month, value: month.repositories, type: 'Repositories' },
  ]) || []

  // Cost breakdown pie chart config
  const costBreakdownConfig = {
    data: analytics?.costBreakdown || [],
    angleField: 'amount',
    colorField: 'category',
    radius: 0.8,
    label: {
      type: 'spider',
      content: '{name}: ${value}',
    },
    color: ['#556b2f', '#7d9b49', '#808000', '#a5b4fc'],
  }

  // Resource usage gauges
  const resourceUsageData = limits ? [
    { 
      title: 'Users', 
      current: limits.currentUsers, 
      max: limits.maxUsers,
      icon: <UserOutlined />,
    },
    { 
      title: 'Teams', 
      current: limits.currentTeams, 
      max: limits.maxTeams,
      icon: <TeamOutlined />,
    },
    { 
      title: 'Machines', 
      current: limits.currentMachines, 
      max: limits.maxMachines,
      icon: <CloudServerOutlined />,
    },
    { 
      title: 'Repositories', 
      current: limits.currentRepositories, 
      max: limits.maxRepositories,
      icon: <DatabaseOutlined />,
    },
  ] : []

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3}>Company Settings</Title>
        <Button
          type="default"
          icon={<SettingOutlined />}
          onClick={() => setVaultModalOpen(true)}
        >
          Configure Vault
        </Button>
      </div>

      <Tabs
        defaultActiveKey="subscription"
        items={[
          {
            key: 'subscription',
            label: (
              <span>
                <CrownOutlined />
                Subscription
              </span>
            ),
            children: (
              <Space direction="vertical" size={24} style={{ width: '100%' }}>
                {/* Company Info */}
                <Card title="Company Information">
                  <Descriptions>
                    <Descriptions.Item label="Company Name">
                      {company?.companyName}
                    </Descriptions.Item>
                    <Descriptions.Item label="Created">
                      {company?.createdAt ? new Date(company.createdAt).toLocaleDateString() : 'N/A'}
                    </Descriptions.Item>
                    <Descriptions.Item label="Vault Version">
                      <Badge count={companyVault?.vaultVersion || 1} style={{ backgroundColor: '#556b2f' }} />
                    </Descriptions.Item>
                  </Descriptions>
                </Card>

                {/* Subscription Details */}
                <Card 
                  title="Subscription Plan" 
                  extra={<Tag color="gold" icon={<CrownOutlined />}>ELITE</Tag>}
                  loading={subLoading}
                >
                  <Row gutter={[16, 16]}>
                    <Col xs={24} lg={12}>
                      <Descriptions column={1}>
                        <Descriptions.Item label="Plan">
                          <Text strong>{subscription?.subscriptionPlan || 'Elite'}</Text>
                        </Descriptions.Item>
                        <Descriptions.Item label="Status">
                          <Badge status="success" text="Active" />
                        </Descriptions.Item>
                        <Descriptions.Item label="Start Date">
                          {subscription?.startDate ? new Date(subscription.startDate).toLocaleDateString() : 'N/A'}
                        </Descriptions.Item>
                        <Descriptions.Item label="End Date">
                          {subscription?.endDate ? new Date(subscription.endDate).toLocaleDateString() : 'N/A'}
                        </Descriptions.Item>
                      </Descriptions>
                    </Col>
                    <Col xs={24} lg={12}>
                      <Title level={5}>Included Features</Title>
                      <List
                        size="small"
                        dataSource={subscription?.features || []}
                        renderItem={(feature) => (
                          <List.Item>
                            <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
                            {feature}
                          </List.Item>
                        )}
                      />
                    </Col>
                  </Row>
                </Card>

                {/* Billing Overview */}
                <Row gutter={[16, 16]}>
                  <Col xs={24} lg={12}>
                    <Card title="Cost Breakdown" loading={analyticsLoading}>
                      <Pie {...costBreakdownConfig} height={300} />
                    </Card>
                  </Col>
                  <Col xs={24} lg={12}>
                    <Card title="Billing Summary">
                      <Space direction="vertical" style={{ width: '100%' }} size={16}>
                        <Statistic
                          title="Current Monthly Cost"
                          value={analytics?.costBreakdown.reduce((sum, item) => sum + item.amount, 0) || 0}
                          prefix={<DollarOutlined />}
                          precision={2}
                          valueStyle={{ color: '#556b2f' }}
                        />
                        <Statistic
                          title="Projected Next Month"
                          value={analytics?.projectedCost || 0}
                          prefix={<DollarOutlined />}
                          precision={2}
                          valueStyle={{ color: '#1890ff' }}
                        />
                        <Timeline
                          items={[
                            {
                              children: 'Next billing date: ' + new Date(Date.now() + 15 * 24 * 60 * 60 * 1000).toLocaleDateString(),
                              color: 'blue',
                            },
                            {
                              children: 'Last payment: $937.00 (30 days ago)',
                              color: 'green',
                            },
                          ]}
                        />
                      </Space>
                    </Card>
                  </Col>
                </Row>
              </Space>
            ),
          },
          {
            key: 'limits',
            label: (
              <span>
                <SafetyOutlined />
                Resource Limits
              </span>
            ),
            children: (
              <Space direction="vertical" size={24} style={{ width: '100%' }}>
                {/* Resource Usage Overview */}
                <Row gutter={[16, 16]}>
                  {resourceUsageData.map((resource) => {
                    const percent = getUsagePercent(resource.current, resource.max)
                    return (
                      <Col xs={24} sm={12} lg={6} key={resource.title}>
                        <Card>
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                              {resource.icon}
                              <Text strong>{resource.title}</Text>
                            </Space>
                            <Progress
                              percent={percent}
                              strokeColor={getUsageColor(percent)}
                              format={() => `${resource.current} / ${resource.max}`}
                            />
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {resource.max - resource.current} remaining
                            </Text>
                          </Space>
                        </Card>
                      </Col>
                    )
                  })}
                </Row>

                {/* Detailed Limits */}
                <Card title="Resource Limits Details" loading={limitsLoading}>
                  <Row gutter={[32, 16]}>
                    <Col xs={24} lg={12}>
                      <List
                        itemLayout="horizontal"
                        dataSource={[
                          { 
                            title: 'Storage', 
                            current: limits?.currentStorage || 0, 
                            max: limits?.maxStorage || 0,
                            icon: <DatabaseOutlined />,
                          },
                          { 
                            title: 'Schedules', 
                            current: limits?.currentSchedules || 0, 
                            max: limits?.maxSchedules || 0,
                            icon: <ScheduleOutlined />,
                          },
                        ]}
                        renderItem={(item) => {
                          const percent = getUsagePercent(item.current, item.max)
                          return (
                            <List.Item>
                              <List.Item.Meta
                                avatar={item.icon}
                                title={item.title}
                                description={
                                  <Progress
                                    percent={percent}
                                    strokeColor={getUsageColor(percent)}
                                    format={() => `${item.current} / ${item.max}`}
                                    size="small"
                                  />
                                }
                              />
                            </List.Item>
                          )
                        }}
                      />
                    </Col>
                    <Col xs={24} lg={12}>
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Text type="secondary">
                          Your current plan includes generous resource limits suitable for enterprise use.
                          Contact support if you need to increase any limits.
                        </Text>
                        <Button type="primary" icon={<CrownOutlined />} block>
                          Upgrade Plan
                        </Button>
                      </Space>
                    </Col>
                  </Row>
                </Card>
              </Space>
            ),
          },
          {
            key: 'analytics',
            label: (
              <span>
                <LineChartOutlined />
                Usage Analytics
              </span>
            ),
            children: (
              <Space direction="vertical" size={24} style={{ width: '100%' }}>
                {/* Usage Trends */}
                <Card title="Resource Usage Trends" extra={<Text type="secondary">Last 6 months</Text>}>
                  <Line {...usageTrendConfig} data={usageTrendData} height={300} />
                </Card>

                {/* Usage Insights */}
                <Row gutter={[16, 16]}>
                  <Col xs={24} lg={8}>
                    <Card>
                      <Statistic
                        title="Average Monthly Growth"
                        value={12.5}
                        precision={1}
                        valueStyle={{ color: '#3f8600' }}
                        prefix={<LineChartOutlined />}
                        suffix="%"
                      />
                    </Card>
                  </Col>
                  <Col xs={24} lg={8}>
                    <Card>
                      <Statistic
                        title="Most Active Team"
                        value="DevOps"
                        valueStyle={{ color: '#556b2f' }}
                        prefix={<TeamOutlined />}
                      />
                    </Card>
                  </Col>
                  <Col xs={24} lg={8}>
                    <Card>
                      <Statistic
                        title="Resource Efficiency"
                        value={87}
                        precision={0}
                        valueStyle={{ color: '#1890ff' }}
                        prefix={<PieChartOutlined />}
                        suffix="%"
                      />
                    </Card>
                  </Col>
                </Row>
              </Space>
            ),
          },
        ]}
      />

      <VaultConfigModal
        open={vaultModalOpen}
        onCancel={() => setVaultModalOpen(false)}
        onSave={handleUpdateVault}
        title="Configure Company Vault"
        initialVault={companyVault?.vault || '{}'}
        initialVersion={companyVault?.vaultVersion || 1}
        loading={updateVaultMutation.isPending}
      />
    </Space>
  )
}

export default CompanySettingsPage