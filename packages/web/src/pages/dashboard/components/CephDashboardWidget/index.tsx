import React from 'react';
import { Col, Progress, Row } from 'antd';
import { useTranslation } from 'react-i18next';
import { useTheme as useStyledTheme } from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccTag, RediaccTooltip } from '@/components/ui';
import { RediaccStatistic, RediaccText } from '@/components/ui';
import {
  CloudServerOutlined,
  CopyOutlined,
  DatabaseOutlined,
  HddOutlined,
  TeamOutlined,
} from '@/utils/optimizedIcons';
import type { CephTeamBreakdown } from '@rediacc/shared/types';
import {
  AssignmentCard,
  AssignmentIcon,
  AssignmentStack,
  PercentageText,
  SummaryPanel,
  TeamHeader,
  TeamListContent,
  TeamListHeader,
  TeamListItem,
  TeamListStyled,
  TeamMeta,
  TeamName,
  TeamSection,
  TeamTagGroup,
  TitleIcon,
  TitleText,
  WidgetBody,
  WidgetCard,
} from './styles';
import { CephDashboardWidgetProps } from './types';

const CephDashboardWidget: React.FC<CephDashboardWidgetProps> = ({ stats }) => {
  const { t } = useTranslation(['common', 'ceph']);
  const styledTheme = useStyledTheme();

  if (!stats) {
    return null;
  }

  const assignmentColors = {
    available: styledTheme.colors.success,
    cluster: styledTheme.colors.info,
    image: styledTheme.colors.warning,
    clone: styledTheme.colors.textTertiary, // Was accent (light gray)
  };

  const assignmentData = [
    {
      type: 'available',
      label: t('ceph:assignmentStatus.available'),
      count: stats.truly_available_machines,
      percentage: Math.round((stats.truly_available_machines / stats.total_machines) * 100),
      icon: <CloudServerOutlined />,
      color: assignmentColors.available,
    },
    {
      type: 'cluster',
      label: t('ceph:assignmentStatus.cluster'),
      count: stats.cluster_assigned_machines,
      percentage: stats.cluster_percentage,
      icon: <DatabaseOutlined />,
      color: assignmentColors.cluster,
    },
    {
      type: 'image',
      label: t('ceph:assignmentStatus.image'),
      count: stats.image_assigned_machines,
      percentage: stats.image_percentage,
      icon: <HddOutlined />,
      color: assignmentColors.image,
    },
    {
      type: 'clone',
      label: t('ceph:assignmentStatus.clone'),
      count: stats.clone_assigned_machines,
      percentage: stats.clone_percentage,
      icon: <CopyOutlined />,
      color: assignmentColors.clone,
    },
  ];

  const utilizationPercent = Math.round(
    ((stats.total_machines - stats.truly_available_machines) / stats.total_machines) * 100
  );

  const renderTeamItem = (item: unknown) => {
    const team = item as CephTeamBreakdown;
    if (!team) {
      return null;
    }

    const teamKey = team.teamName.toLowerCase().replace(/\s+/g, '-');

    return (
      <TeamListItem key={teamKey} data-testid={`ds-widget-team-item-${teamKey}`}>
        <TeamListContent>
          <TeamListHeader>
            <TeamName>{team.teamName}</TeamName>
            <TeamMeta>{team.totalMachines} machines</TeamMeta>
          </TeamListHeader>
          <TeamTagGroup>
            <RediaccTooltip title={t('ceph:assignmentStatus.available')}>
              <RediaccTag data-testid={`ds-widget-team-tag-available-${teamKey}`} variant="success">
                {team.availableMachines} available
              </RediaccTag>
            </RediaccTooltip>
            {team.clusterMachines > 0 && (
              <RediaccTooltip title={t('ceph:assignmentStatus.cluster')}>
                <RediaccTag data-testid={`ds-widget-team-tag-cluster-${teamKey}`} variant="info">
                  {team.clusterMachines} cluster
                </RediaccTag>
              </RediaccTooltip>
            )}
            {team.imageMachines > 0 && (
              <RediaccTooltip title={t('ceph:assignmentStatus.image')}>
                <RediaccTag data-testid={`ds-widget-team-tag-image-${teamKey}`} variant="neutral">
                  {team.imageMachines} image
                </RediaccTag>
              </RediaccTooltip>
            )}
            {team.cloneMachines > 0 && (
              <RediaccTooltip title={t('ceph:assignmentStatus.clone')}>
                <RediaccTag data-testid={`ds-widget-team-tag-clone-${teamKey}`} variant="warning">
                  {team.cloneMachines} clone
                </RediaccTag>
              </RediaccTooltip>
            )}
          </TeamTagGroup>
        </TeamListContent>
      </TeamListItem>
    );
  };

  return (
    <WidgetCard
      data-testid="ds-widget-card"
      title={
        <InlineStack>
          <TitleIcon>
            <CloudServerOutlined />
          </TitleIcon>
          <TitleText>{t('ceph:dashboard.title')}</TitleText>
        </InlineStack>
      }
      extra={
        <RediaccText variant="description">
          {t('ceph:dashboard.subtitle', { total: stats.total_machines })}
        </RediaccText>
      }
    >
      <WidgetBody>
        <Row gutter={[16, 16]}>
          {assignmentData.map((item) => (
            <Col key={item.type} xs={12} sm={12} md={6}>
              <AssignmentCard
                data-testid={`ds-widget-stat-${item.type}`}
                size="sm"
                $borderColor={item.color}
              >
                <AssignmentStack>
                  <AssignmentIcon $color={item.color}>{item.icon}</AssignmentIcon>
                  <RediaccStatistic
                    data-testid={`ds-widget-stat-value-${item.type}`}
                    title={item.label}
                    value={item.count}
                    suffix={<PercentageText>({item.percentage}%)</PercentageText>}
                    color={item.color}
                  />
                </AssignmentStack>
              </AssignmentCard>
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <SummaryPanel data-testid="ds-widget-cluster-summary">
              <RediaccText variant="title">{t('ceph:dashboard.clusterSummary')}</RediaccText>
              <Row gutter={16}>
                <Col span={12}>
                  <RediaccStatistic
                    data-testid="ds-widget-stat-total-clusters"
                    title={t('ceph:dashboard.totalClusters')}
                    value={stats.total_clusters}
                    variant="textPrimary"
                  />
                </Col>
                <Col span={12}>
                  <RediaccStatistic
                    data-testid="ds-widget-stat-avg-machines"
                    title={t('ceph:dashboard.avgMachinesPerCluster')}
                    value={stats.avg_machines_per_cluster}
                    precision={1}
                    variant="textPrimary"
                  />
                </Col>
              </Row>
            </SummaryPanel>
          </Col>

          <Col xs={24} md={12}>
            <SummaryPanel data-testid="ds-widget-machine-utilization">
              <RediaccText variant="title">{t('ceph:dashboard.machineUtilization')}</RediaccText>
              <Progress
                data-testid="ds-widget-progress-utilization"
                percent={utilizationPercent}
                strokeColor={{
                  '0%': styledTheme.colors.primary,
                  '100%': styledTheme.colors.success,
                }}
                format={(percent) => `${percent}% ${t('common:utilized')}`}
              />
              <RediaccText variant="description">
                {t('ceph:dashboard.utilizationDetails', {
                  used: stats.total_machines - stats.truly_available_machines,
                  total: stats.total_machines,
                })}
              </RediaccText>
            </SummaryPanel>
          </Col>
        </Row>

        {stats.team_breakdown && stats.team_breakdown.length > 0 && (
          <TeamSection data-testid="ds-widget-team-breakdown">
            <TeamHeader>
              <TitleIcon>
                <TeamOutlined />
              </TitleIcon>
              <RediaccText variant="title">{t('ceph:dashboard.teamBreakdown')}</RediaccText>
            </TeamHeader>
            <TeamListStyled
              data-testid="ds-widget-team-list"
              size="sm"
              dataSource={stats.team_breakdown}
              renderItem={renderTeamItem}
            />
          </TeamSection>
        )}
      </WidgetBody>
    </WidgetCard>
  );
};

export default CephDashboardWidget;
