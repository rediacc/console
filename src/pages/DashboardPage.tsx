import React from 'react'
import { Row, Col, Card, Statistic, Space, Typography, Spin, Progress, Timeline, Badge } from 'antd'
import {
  TeamOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  ThunderboltOutlined,
  UserOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  RiseOutlined,
} from '@ant-design/icons'
import { Pie, Column, Line, Bar } from '@ant-design/charts'
import { useTranslation } from 'react-i18next'
import { useDashboardMetrics, useQueueAnalytics, useTeamComparison } from '@/api/queries/dashboard'
import { useTheme } from '@/context/ThemeContext'

const { Title, Text } = Typography

const DashboardPage: React.FC = () => {
  const { theme } = useTheme()
  const { t } = useTranslation('dashboard')
  const { data: metrics, isLoading: metricsLoading } = useDashboardMetrics(30)
  const { data: queueAnalytics, isLoading: queueLoading } = useQueueAnalytics()
  const { data: teamComparison, isLoading: teamLoading } = useTeamComparison()

  if (metricsLoading || queueLoading || teamLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" />
      </div>
    )
  }

  // Resource distribution pie chart config
  const resourceDistributionConfig = {
    data: [
      { type: t('dashboard.charts.resourceDistribution.teams'), value: metrics?.totalTeams || 0 },
      { type: t('dashboard.charts.resourceDistribution.machines'), value: metrics?.totalMachines || 0 },
      { type: t('dashboard.charts.resourceDistribution.repositories'), value: metrics?.totalRepositories || 0 },
      { type: t('dashboard.charts.resourceDistribution.users'), value: metrics?.totalUsers || 0 },
    ],
    angleField: 'value',
    colorField: 'type',
    radius: 0.8,
    label: {
      formatter: (data: any) => {
        if (!data) return '';
        return `${data.type || ''}: ${data.value || 0}`;
      },
    },
    color: ['#556b2f', '#7d9b49', '#808000', '#a5b4fc'],
  }

  // Queue activity trend line chart config
  const queueActivityConfig = {
    data: metrics?.queueActivityByDay || [],
    xField: 'date',
    yField: 'value',
    seriesField: 'type',
    xAxis: {
      type: 'time',
      tickCount: 7,
    },
    smooth: true,
    animation: {
      appear: {
        animation: 'path-in',
        duration: 1000,
      },
    },
    color: ['#22c55e', '#ef4444', '#f59e0b'],
  }

  // Transform queue activity data for line chart
  const queueActivityData = metrics?.queueActivityByDay.flatMap(day => [
    { date: day.date, value: day.created, type: t('dashboard.charts.queueActivity.created') },
    { date: day.date, value: day.completed, type: t('dashboard.charts.queueActivity.completed') },
    { date: day.date, value: day.failed, type: t('dashboard.charts.queueActivity.failed') },
  ]) || []

  // Queue status distribution config
  const queueStatusConfig = {
    data: queueAnalytics?.statusDistribution || [],
    xField: 'status',
    yField: 'count',
    label: {
      position: 'top',
      style: {
        fill: '#556b2f',
      },
    },
    color: (datum: any) => {
      const colors: Record<string, string> = {
        pending: '#faad14',
        processing: '#1890ff',
        completed: '#52c41a',
        failed: '#ff4d4f',
      }
      return colors[datum.status] || '#556b2f'
    },
    columnStyle: {
      radius: [4, 4, 0, 0],
    },
  }

  // Team resources comparison config
  const teamResourcesConfig = {
    data: teamComparison?.teams.flatMap(team => [
      { team: team.teamName, type: t('dashboard.charts.teamComparison.machines'), value: team.resources.machines },
      { team: team.teamName, type: t('dashboard.charts.teamComparison.repositories'), value: team.resources.repositories },
      { team: team.teamName, type: t('dashboard.charts.teamComparison.storage'), value: team.resources.storage },
    ]) || [],
    xField: 'team',
    yField: 'value',
    seriesField: 'type',
    isGroup: true,
    columnStyle: {
      radius: [4, 4, 0, 0],
    },
    color: ['#556b2f', '#7d9b49', '#808000'],
  }

  // System health score - handle division by zero
  const calculateHealthScore = () => {
    if (!metrics?.systemHealth || metrics.systemHealth.totalBridges === 0) {
      return 100 // Default to 100% if no bridges exist yet
    }
    return (metrics.systemHealth.activeBridges / metrics.systemHealth.totalBridges) * 100
  }
  
  const systemHealthScore = calculateHealthScore()

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <Title level={3}>{t('dashboard.title')}</Title>
      
      {/* Summary Statistics */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title={t('dashboard.stats.totalTeams')}
              value={metrics?.totalTeams || 0}
              prefix={<TeamOutlined />}
              valueStyle={{ color: '#556b2f' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title={t('dashboard.stats.activeMachines')}
              value={metrics?.totalMachines || 0}
              prefix={<CloudServerOutlined />}
              valueStyle={{ color: '#3b82f6' }}
              suffix={
                <Text type="success" style={{ fontSize: 14 }}>
                  <RiseOutlined /> {t('dashboard.stats.growthPercentage', { percentage: 12 })}
                </Text>
              }
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title={t('dashboard.stats.repositories')}
              value={metrics?.totalRepositories || 0}
              prefix={<DatabaseOutlined />}
              valueStyle={{ color: '#8b5cf6' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title={t('dashboard.stats.activeQueueItems')}
              value={metrics?.activeQueueItems || 0}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: '#f59e0b' }}
              suffix={
                <Badge
                  count={metrics?.failedQueueItems || 0}
                  style={{ backgroundColor: '#ff4d4f' }}
                />
              }
            />
          </Card>
        </Col>
      </Row>

      {/* Charts Row 1 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title={t('dashboard.charts.resourceDistribution.title')} extra={<Text type="secondary">{t('dashboard.charts.resourceDistribution.subtitle')}</Text>}>
            <Pie {...resourceDistributionConfig} height={300} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={t('dashboard.charts.systemHealth.title')} extra={<Text type="secondary">{t('dashboard.charts.systemHealth.subtitle')}</Text>}>
            <Row gutter={16}>
              <Col span={12}>
                <div style={{ textAlign: 'center', padding: '20px 0' }}>
                  <Progress
                    type="circle"
                    percent={systemHealthScore}
                    size={180}
                    strokeColor={systemHealthScore > 80 ? '#52c41a' : systemHealthScore > 60 ? '#faad14' : '#ff4d4f'}
                    format={(percent) => (
                      <div>
                        <div style={{ fontSize: '36px', fontWeight: 'bold', color: '#556b2f' }}>
                          {Math.round(percent || 0)}%
                        </div>
                        <div style={{ fontSize: '14px' }} className="text-secondary">
                          {t('dashboard.charts.systemHealth.healthScore')}
                        </div>
                      </div>
                    )}
                  />
                  <div style={{ marginTop: 16 }}>
                    <Text strong>{t('dashboard.charts.systemHealth.overallHealth')}</Text>
                  </div>
                </div>
              </Col>
              <Col span={12}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <div>
                    <Text type="secondary">{t('dashboard.charts.systemHealth.activeRegions')}</Text>
                    <Progress
                      percent={
                        metrics?.systemHealth?.totalRegions && metrics.systemHealth.totalRegions > 0
                          ? (metrics.systemHealth.activeRegions / metrics.systemHealth.totalRegions) * 100
                          : 100
                      }
                      strokeColor="#556b2f"
                      format={() => `${metrics?.systemHealth?.activeRegions || 0}/${metrics?.systemHealth?.totalRegions || 0}`}
                    />
                  </div>
                  <div>
                    <Text type="secondary">{t('dashboard.charts.systemHealth.activeBridges')}</Text>
                    <Progress
                      percent={
                        metrics?.systemHealth?.totalBridges && metrics.systemHealth.totalBridges > 0
                          ? (metrics.systemHealth.activeBridges / metrics.systemHealth.totalBridges) * 100
                          : 100
                      }
                      strokeColor="#7d9b49"
                      format={() => `${metrics?.systemHealth?.activeBridges || 0}/${metrics?.systemHealth?.totalBridges || 0}`}
                    />
                  </div>
                  <div>
                    <Text type="secondary">{t('dashboard.charts.systemHealth.systemUptime')}</Text>
                    <Progress percent={99.9} strokeColor="#22c55e" />
                  </div>
                </Space>
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>

      {/* Charts Row 2 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card 
            title={t('dashboard.charts.queueActivity.title')} 
            extra={<Text type="secondary">{t('dashboard.charts.queueActivity.subtitle')}</Text>}
          >
            <Line {...queueActivityConfig} data={queueActivityData} height={300} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title={t('dashboard.charts.queueStatus.title')}>
            <Column {...queueStatusConfig} height={300} />
          </Card>
        </Col>
      </Row>

      {/* Charts Row 3 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title={t('dashboard.charts.teamComparison.title')}>
            <Bar {...teamResourcesConfig} height={300} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title={t('dashboard.recentActivity.title')}>
            <Timeline
              items={[
                {
                  dot: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
                  children: (
                    <>
                      <Text strong>{t('dashboard.recentActivity.newTeamCreated')}</Text>
                      <br />
                      <Text type="secondary">{t('dashboard.recentActivity.teamDetails', { teamName: 'DevOps team', time: '2 hours ago' })}</Text>
                    </>
                  ),
                },
                {
                  dot: <ThunderboltOutlined style={{ color: '#f59e0b' }} />,
                  children: (
                    <>
                      <Text strong>{t('dashboard.recentActivity.queueJobCompleted')}</Text>
                      <br />
                      <Text type="secondary">{t('dashboard.recentActivity.jobDetails', { jobName: 'repo_backup', serverName: 'prod-server-1', time: '3 hours ago' })}</Text>
                    </>
                  ),
                },
                {
                  dot: <UserOutlined style={{ color: '#1890ff' }} />,
                  children: (
                    <>
                      <Text strong>{t('dashboard.recentActivity.newUserAdded')}</Text>
                      <br />
                      <Text type="secondary">{t('dashboard.recentActivity.userDetails', { email: 'john.doe@company.com', time: '5 hours ago' })}</Text>
                    </>
                  ),
                },
                {
                  dot: <CloudServerOutlined style={{ color: '#8b5cf6' }} />,
                  children: (
                    <>
                      <Text strong>{t('dashboard.recentActivity.machineDeployed')}</Text>
                      <br />
                      <Text type="secondary">{t('dashboard.recentActivity.machineDetails', { machineName: 'staging-server-2', region: 'US-East', time: '1 day ago' })}</Text>
                    </>
                  ),
                },
                {
                  dot: <SyncOutlined spin style={{ color: '#556b2f' }} />,
                  children: (
                    <>
                      <Text strong>{t('dashboard.recentActivity.systemMaintenance')}</Text>
                      <br />
                      <Text type="secondary">{t('dashboard.recentActivity.maintenanceDetails', { schedule: 'tomorrow 2:00 AM' })}</Text>
                    </>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      {/* Resource Usage by Team */}
      <Card title={t('dashboard.resourceUsage.title')}>
        <Row gutter={[16, 16]}>
          {metrics?.resourceUsageByTeam.slice(0, 4).map((team) => (
            <Col xs={24} sm={12} lg={6} key={team.teamName}>
              <Card size="small" style={{ backgroundColor: theme === 'light' ? '#f9fafb' : '#2a2a2a' }}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Text strong>{team.teamName}</Text>
                  <Progress
                    percent={75}
                    size="small"
                    strokeColor="#556b2f"
                    format={() => t('dashboard.resourceUsage.resourceCount', { count: team.machines + team.repositories + team.storage })}
                  />
                  <Space style={{ fontSize: 12 }}>
                    <Text type="secondary">
                      <CloudServerOutlined /> {team.machines}
                    </Text>
                    <Text type="secondary">
                      <DatabaseOutlined /> {team.repositories}
                    </Text>
                    <Text type="secondary">
                      <ThunderboltOutlined /> {team.queueItems}
                    </Text>
                  </Space>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </Space>
  )
}

export default DashboardPage