import React from 'react';
import { Card, Col, Flex, List, Progress, Row, Statistic, Tag, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  CloudServerOutlined,
  CopyOutlined,
  DatabaseOutlined,
  HddOutlined,
  TeamOutlined,
} from '@/utils/optimizedIcons';
import type { CephTeamBreakdown } from '@rediacc/shared/types';
import { CephDashboardWidgetProps } from './types';

const CephDashboardWidget: React.FC<CephDashboardWidgetProps> = ({ stats }) => {
  const { t } = useTranslation(['common', 'ceph']);

  if (stats === null || stats === undefined) {
    return null;
  }

  const assignmentData = [
    {
      type: 'available',
      label: t('ceph:assignmentStatus.available'),
      count: stats.truly_available_machines,
      percentage: Math.round((stats.truly_available_machines / stats.total_machines) * 100),
      icon: <CloudServerOutlined />,
    },
    {
      type: 'cluster',
      label: t('ceph:assignmentStatus.cluster'),
      count: stats.cluster_assigned_machines,
      percentage: stats.cluster_percentage,
      icon: <DatabaseOutlined />,
    },
    {
      type: 'image',
      label: t('ceph:assignmentStatus.image'),
      count: stats.image_assigned_machines,
      percentage: stats.image_percentage,
      icon: <HddOutlined />,
    },
    {
      type: 'clone',
      label: t('ceph:assignmentStatus.clone'),
      count: stats.clone_assigned_machines,
      percentage: stats.clone_percentage,
      icon: <CopyOutlined />,
    },
  ];

  const utilizationPercent = Math.round(
    ((stats.total_machines - stats.truly_available_machines) / stats.total_machines) * 100
  );

  const renderTeamItem = (item: unknown) => {
    const team = item as CephTeamBreakdown | null | undefined;
    if (team === null || team === undefined) {
      return null;
    }

    const teamKey = team.teamName.toLowerCase().replace(/\s+/g, '-');

    return (
      <List.Item key={teamKey} data-testid={`ds-widget-team-item-${teamKey}`}>
        <Flex vertical className="w-full">
          <Flex align="center" justify="space-between">
            <Typography.Text strong>{team.teamName}</Typography.Text>
            <Typography.Text>{team.totalMachines} machines</Typography.Text>
          </Flex>
          <Flex align="center" gap={8} wrap>
            <Tooltip title={t('ceph:assignmentStatus.available')}>
              <Tag data-testid={`ds-widget-team-tag-available-${teamKey}`}>
                {team.availableMachines} available
              </Tag>
            </Tooltip>
            {team.clusterMachines > 0 && (
              <Tooltip title={t('ceph:assignmentStatus.cluster')}>
                <Tag data-testid={`ds-widget-team-tag-cluster-${teamKey}`}>
                  {team.clusterMachines} cluster
                </Tag>
              </Tooltip>
            )}
            {team.imageMachines > 0 && (
              <Tooltip title={t('ceph:assignmentStatus.image')}>
                <Tag data-testid={`ds-widget-team-tag-image-${teamKey}`}>
                  {team.imageMachines} image
                </Tag>
              </Tooltip>
            )}
            {team.cloneMachines > 0 && (
              <Tooltip title={t('ceph:assignmentStatus.clone')}>
                <Tag data-testid={`ds-widget-team-tag-clone-${teamKey}`}>
                  {team.cloneMachines} clone
                </Tag>
              </Tooltip>
            )}
          </Flex>
        </Flex>
      </List.Item>
    );
  };

  return (
    <Card
      data-testid="ds-widget-card"
      title={
        <Flex align="center" gap={8} wrap className="inline-flex">
          <Flex align="center" className="inline-flex">
            <CloudServerOutlined />
          </Flex>
          <Typography.Text>{t('ceph:dashboard.title')}</Typography.Text>
        </Flex>
      }
      extra={
        <Typography.Text>
          {t('ceph:dashboard.subtitle', { total: stats.total_machines })}
        </Typography.Text>
      }
    >
      <Flex vertical gap={16} className="w-full">
        <Row gutter={[16, 16]}>
          {assignmentData.map((item) => (
            <Col key={item.type} xs={12} sm={12} md={6}>
              <Card data-testid={`ds-widget-stat-${item.type}`} size="small">
                <Flex vertical align="center">
                  <Flex>{item.icon}</Flex>
                  <Statistic
                    data-testid={`ds-widget-stat-value-${item.type}`}
                    title={item.label}
                    value={item.count}
                    suffix={<Typography.Text>({item.percentage}%)</Typography.Text>}
                  />
                </Flex>
              </Card>
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <Flex vertical gap={8} data-testid="ds-widget-cluster-summary">
              <Typography.Text strong>{t('ceph:dashboard.clusterSummary')}</Typography.Text>
              <Row gutter={16}>
                <Col span={12}>
                  <Statistic
                    data-testid="ds-widget-stat-total-clusters"
                    title={t('ceph:dashboard.totalClusters')}
                    value={stats.total_clusters}
                  />
                </Col>
                <Col span={12}>
                  <Statistic
                    data-testid="ds-widget-stat-avg-machines"
                    title={t('ceph:dashboard.avgMachinesPerCluster')}
                    value={stats.avg_machines_per_cluster}
                    precision={1}
                  />
                </Col>
              </Row>
            </Flex>
          </Col>

          <Col xs={24} md={12}>
            <Flex vertical gap={8} data-testid="ds-widget-machine-utilization">
              <Typography.Text strong>{t('ceph:dashboard.machineUtilization')}</Typography.Text>
              <Progress
                data-testid="ds-widget-progress-utilization"
                percent={utilizationPercent}
                format={(percent) => `${percent}% ${t('common:utilized')}`}
              />
              <Typography.Text>
                {t('ceph:dashboard.utilizationDetails', {
                  used: stats.total_machines - stats.truly_available_machines,
                  total: stats.total_machines,
                })}
              </Typography.Text>
            </Flex>
          </Col>
        </Row>

        {(stats.team_breakdown?.length ?? 0) > 0 && (
          <Flex vertical gap={8} data-testid="ds-widget-team-breakdown">
            <Flex align="center" gap={8}>
              <Flex align="center" className="inline-flex">
                <TeamOutlined />
              </Flex>
              <Typography.Text strong>{t('ceph:dashboard.teamBreakdown')}</Typography.Text>
            </Flex>
            <List
              data-testid="ds-widget-team-list"
              size="small"
              dataSource={stats.team_breakdown ?? []}
              renderItem={renderTeamItem}
            />
          </Flex>
        )}
      </Flex>
    </Card>
  );
};

export default CephDashboardWidget;
