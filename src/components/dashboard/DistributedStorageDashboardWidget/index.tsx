import React from 'react'
import { Row, Col, Progress, Tag, Tooltip } from 'antd'
import {
  CloudServerOutlined,
  DatabaseOutlined,
  HddOutlined,
  CopyOutlined,
  TeamOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useTheme as useStyledTheme } from 'styled-components'
import type { DistributedStorageTeamBreakdown } from '@/api/queries/dashboard'
import { DistributedStorageDashboardWidgetProps } from './types'
import {
  WidgetCard,
  HeaderContent,
  TitleIcon,
  TitleText,
  Subtitle,
  WidgetBody,
  AssignmentCard,
  AssignmentStack,
  AssignmentIcon,
  AssignmentStatistic,
  SummaryPanel,
  SummaryTitle,
  TeamSection,
  TeamHeader,
  TeamListStyled,
  TeamListItem,
  TeamListContent,
  TeamListHeader,
  TeamName,
  TeamMeta,
  TeamTagGroup,
  PercentageText,
} from './styles'

const DistributedStorageDashboardWidget: React.FC<DistributedStorageDashboardWidgetProps> = ({
  stats,
}) => {
  const { t } = useTranslation(['common', 'distributedStorage'])
  const styledTheme = useStyledTheme()

  if (!stats) {
    return null
  }

  const assignmentColors = {
    available: styledTheme.colors.success,
    cluster: styledTheme.colors.info,
    image: styledTheme.colors.warning,
    clone: styledTheme.colors.accent,
  }

  const assignmentData = [
    {
      type: 'available',
      label: t('distributedStorage:assignmentStatus.available'),
      count: stats.truly_available_machines,
      percentage: Math.round((stats.truly_available_machines / stats.total_machines) * 100),
      icon: <CloudServerOutlined />,
      color: assignmentColors.available,
    },
    {
      type: 'cluster',
      label: t('distributedStorage:assignmentStatus.cluster'),
      count: stats.cluster_assigned_machines,
      percentage: stats.cluster_percentage,
      icon: <DatabaseOutlined />,
      color: assignmentColors.cluster,
    },
    {
      type: 'image',
      label: t('distributedStorage:assignmentStatus.image'),
      count: stats.image_assigned_machines,
      percentage: stats.image_percentage,
      icon: <HddOutlined />,
      color: assignmentColors.image,
    },
    {
      type: 'clone',
      label: t('distributedStorage:assignmentStatus.clone'),
      count: stats.clone_assigned_machines,
      percentage: stats.clone_percentage,
      icon: <CopyOutlined />,
      color: assignmentColors.clone,
    },
  ]

  const utilizationPercent = Math.round(
    ((stats.total_machines - stats.truly_available_machines) / stats.total_machines) * 100,
  )

  const renderTeamItem = (item: unknown) => {
    const team = item as DistributedStorageTeamBreakdown
    if (!team) {
      return null
    }

    const teamKey = team.TeamName.toLowerCase().replace(/\s+/g, '-')

    return (
      <TeamListItem
        key={teamKey}
        data-testid={`ds-widget-team-item-${teamKey}`}
      >
        <TeamListContent>
          <TeamListHeader>
            <TeamName>{team.TeamName}</TeamName>
            <TeamMeta>{team.TotalMachines} machines</TeamMeta>
          </TeamListHeader>
          <TeamTagGroup>
            <Tooltip title={t('distributedStorage:assignmentStatus.available')}>
              <Tag data-testid={`ds-widget-team-tag-available-${teamKey}`} color="success">
                {team.AvailableMachines} available
              </Tag>
            </Tooltip>
            {team.ClusterMachines > 0 && (
              <Tooltip title={t('distributedStorage:assignmentStatus.cluster')}>
                <Tag data-testid={`ds-widget-team-tag-cluster-${teamKey}`} color="blue">
                  {team.ClusterMachines} cluster
                </Tag>
              </Tooltip>
            )}
            {team.ImageMachines > 0 && (
              <Tooltip title={t('distributedStorage:assignmentStatus.image')}>
                <Tag data-testid={`ds-widget-team-tag-image-${teamKey}`} color="purple">
                  {team.ImageMachines} image
                </Tag>
              </Tooltip>
            )}
            {team.CloneMachines > 0 && (
              <Tooltip title={t('distributedStorage:assignmentStatus.clone')}>
                <Tag data-testid={`ds-widget-team-tag-clone-${teamKey}`} color="orange">
                  {team.CloneMachines} clone
                </Tag>
              </Tooltip>
            )}
          </TeamTagGroup>
        </TeamListContent>
      </TeamListItem>
    )
  }

  return (
    <WidgetCard
      data-testid="ds-widget-card"
      title={
        <HeaderContent>
          <TitleIcon>
            <CloudServerOutlined />
          </TitleIcon>
          <TitleText>{t('distributedStorage:dashboard.title')}</TitleText>
        </HeaderContent>
      }
      extra={
        <Subtitle>
          {t('distributedStorage:dashboard.subtitle', { total: stats.total_machines })}
        </Subtitle>
      }
    >
      <WidgetBody>
        <Row gutter={[16, 16]}>
          {assignmentData.map((item) => (
            <Col key={item.type} xs={12} sm={12} md={6}>
              <AssignmentCard
                data-testid={`ds-widget-stat-${item.type}`}
                size="small"
                $borderColor={item.color}
              >
                <AssignmentStack>
                  <AssignmentIcon $color={item.color}>{item.icon}</AssignmentIcon>
                  <AssignmentStatistic
                    data-testid={`ds-widget-stat-value-${item.type}`}
                    title={item.label}
                    value={item.count}
                    suffix={<PercentageText>({item.percentage}%)</PercentageText>}
                    $color={item.color}
                  />
                </AssignmentStack>
              </AssignmentCard>
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <SummaryPanel data-testid="ds-widget-cluster-summary">
              <SummaryTitle>{t('distributedStorage:dashboard.clusterSummary')}</SummaryTitle>
              <Row gutter={16}>
                <Col span={12}>
                  <AssignmentStatistic
                    data-testid="ds-widget-stat-total-clusters"
                    title={t('distributedStorage:dashboard.totalClusters')}
                    value={stats.total_clusters}
                    $color={styledTheme.colors.textPrimary}
                  />
                </Col>
                <Col span={12}>
                  <AssignmentStatistic
                    data-testid="ds-widget-stat-avg-machines"
                    title={t('distributedStorage:dashboard.avgMachinesPerCluster')}
                    value={stats.avg_machines_per_cluster}
                    precision={1}
                    $color={styledTheme.colors.textPrimary}
                  />
                </Col>
              </Row>
            </SummaryPanel>
          </Col>

          <Col xs={24} md={12}>
            <SummaryPanel data-testid="ds-widget-machine-utilization">
              <SummaryTitle>{t('distributedStorage:dashboard.machineUtilization')}</SummaryTitle>
              <Progress
                data-testid="ds-widget-progress-utilization"
                percent={utilizationPercent}
                strokeColor={{
                  '0%': styledTheme.colors.primary,
                  '100%': styledTheme.colors.success,
                }}
                format={(percent) => `${percent}% ${t('common:utilized')}`}
              />
              <Subtitle>
                {t('distributedStorage:dashboard.utilizationDetails', {
                  used: stats.total_machines - stats.truly_available_machines,
                  total: stats.total_machines,
                })}
              </Subtitle>
            </SummaryPanel>
          </Col>
        </Row>

        {stats.team_breakdown && stats.team_breakdown.length > 0 && (
          <TeamSection data-testid="ds-widget-team-breakdown">
            <TeamHeader>
              <TitleIcon>
                <TeamOutlined />
              </TitleIcon>
              <SummaryTitle>{t('distributedStorage:dashboard.teamBreakdown')}</SummaryTitle>
            </TeamHeader>
            <TeamListStyled
              data-testid="ds-widget-team-list"
              size="small"
              dataSource={stats.team_breakdown}
              renderItem={renderTeamItem}
            />
          </TeamSection>
        )}
      </WidgetBody>
    </WidgetCard>
  )
}

export default DistributedStorageDashboardWidget
