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
import type { GetOrganizationDashboard_ResultSet15 } from '@rediacc/shared/types';
import { CephDashboardWidgetProps } from './types';

const CephDashboardWidget: React.FC<CephDashboardWidgetProps> = ({ stats, teamBreakdown = [] }) => {
  const { t } = useTranslation(['common', 'ceph']);

  if (stats === null || stats === undefined) {
    return null;
  }

  const totalMachines = stats.totalMachines ?? 0;
  const trulyAvailable = stats.trulyAvailableMachines ?? 0;

  const assignmentData = [
    {
      type: 'available',
      label: t('ceph:assignmentStatus.available'),
      count: trulyAvailable,
      percentage: totalMachines > 0 ? Math.round((trulyAvailable / totalMachines) * 100) : 0,
      icon: <CloudServerOutlined />,
    },
    {
      type: 'cluster',
      label: t('ceph:assignmentStatus.cluster'),
      count: stats.clusterAssignedMachines ?? 0,
      percentage: stats.clusterPercentage ?? 0,
      icon: <DatabaseOutlined />,
    },
    {
      type: 'image',
      label: t('ceph:assignmentStatus.image'),
      count: stats.imageAssignedMachines,
      percentage: stats.imagePercentage ?? 0,
      icon: <HddOutlined />,
    },
    {
      type: 'clone',
      label: t('ceph:assignmentStatus.clone'),
      count: stats.cloneAssignedMachines,
      percentage: stats.clonePercentage ?? 0,
      icon: <CopyOutlined />,
    },
  ];

  const utilizationPercent =
    totalMachines > 0 ? Math.round(((totalMachines - trulyAvailable) / totalMachines) * 100) : 0;

  const renderTeamItem = (item: unknown) => {
    const team = item as GetOrganizationDashboard_ResultSet15 | null | undefined;
    if (team === null || team === undefined) {
      return null;
    }

    const teamKey = (team.teamName ?? '').toLowerCase().replace(/\s+/g, '-');

    return (
      <List.Item key={teamKey} data-testid={`ds-widget-team-item-${teamKey}`}>
        <Flex vertical className="w-full">
          <Flex align="center" justify="space-between">
            <Typography.Text strong>{team.teamName}</Typography.Text>
            <Typography.Text>
              {team.totalMachines} {t('common:dashboard.widgets.ceph.machines')}
            </Typography.Text>
          </Flex>
          <Flex align="center" wrap>
            <Tooltip title={t('ceph:assignmentStatus.available')}>
              <Tag data-testid={`ds-widget-team-tag-available-${teamKey}`}>
                {team.availableMachines} {t('common:dashboard.widgets.ceph.available')}
              </Tag>
            </Tooltip>
            {(team.clusterMachines ?? 0) > 0 && (
              <Tooltip title={t('ceph:assignmentStatus.cluster')}>
                <Tag data-testid={`ds-widget-team-tag-cluster-${teamKey}`}>
                  {team.clusterMachines} {t('common:dashboard.widgets.ceph.cluster')}
                </Tag>
              </Tooltip>
            )}
            {(team.imageMachines ?? 0) > 0 && (
              <Tooltip title={t('ceph:assignmentStatus.image')}>
                <Tag data-testid={`ds-widget-team-tag-image-${teamKey}`}>
                  {team.imageMachines} {t('common:dashboard.widgets.ceph.image')}
                </Tag>
              </Tooltip>
            )}
            {(team.cloneMachines ?? 0) > 0 && (
              <Tooltip title={t('ceph:assignmentStatus.clone')}>
                <Tag data-testid={`ds-widget-team-tag-clone-${teamKey}`}>
                  {team.cloneMachines} {t('common:dashboard.widgets.ceph.clone')}
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
        <Flex align="center" wrap className="inline-flex">
          <Flex align="center" className="inline-flex">
            <CloudServerOutlined />
          </Flex>
          <Typography.Text>{t('ceph:dashboard.title')}</Typography.Text>
        </Flex>
      }
      extra={
        <Typography.Text>{t('ceph:dashboard.subtitle', { total: totalMachines })}</Typography.Text>
      }
    >
      <Flex vertical className="w-full">
        <Row gutter={[16, 16]}>
          {assignmentData.map((item) => (
            <Col key={item.type} xs={12} sm={12} md={6}>
              <Card data-testid={`ds-widget-stat-${item.type}`} size="small">
                <Flex vertical align="center">
                  <Flex>{item.icon}</Flex>
                  <Statistic
                    data-testid={`ds-widget-stat-value-${item.type}`}
                    title={item.label}
                    value={item.count ?? 0}
                    suffix={<Typography.Text>({item.percentage}%)</Typography.Text>}
                  />
                </Flex>
              </Card>
            </Col>
          ))}
        </Row>

        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <Flex vertical className="gap-sm" data-testid="ds-widget-cluster-summary">
              <Typography.Text strong>{t('ceph:dashboard.clusterSummary')}</Typography.Text>
              <Row gutter={16}>
                <Col span={12}>
                  <Statistic
                    data-testid="ds-widget-stat-total-clusters"
                    title={t('ceph:dashboard.totalClusters')}
                    value={stats.totalClusters ?? 0}
                  />
                </Col>
                <Col span={12}>
                  <Statistic
                    data-testid="ds-widget-stat-avg-machines"
                    title={t('ceph:dashboard.avgMachinesPerCluster')}
                    value={stats.avgMachinesPerCluster ?? 0}
                    precision={1}
                  />
                </Col>
              </Row>
            </Flex>
          </Col>

          <Col xs={24} md={12}>
            <Flex vertical className="gap-sm" data-testid="ds-widget-machine-utilization">
              <Typography.Text strong>{t('ceph:dashboard.machineUtilization')}</Typography.Text>
              <Progress
                data-testid="ds-widget-progress-utilization"
                percent={utilizationPercent}
                format={(percent) => `${percent}% ${t('common:utilized')}`}
              />
              <Typography.Text>
                {t('ceph:dashboard.utilizationDetails', {
                  used: totalMachines - trulyAvailable,
                  total: totalMachines,
                })}
              </Typography.Text>
            </Flex>
          </Col>
        </Row>

        {teamBreakdown.length > 0 && (
          <Flex vertical className="gap-sm" data-testid="ds-widget-team-breakdown">
            <Flex align="center">
              <Flex align="center" className="inline-flex">
                <TeamOutlined />
              </Flex>
              <Typography.Text strong>{t('ceph:dashboard.teamBreakdown')}</Typography.Text>
            </Flex>
            <List
              data-testid="ds-widget-team-list"
              size="small"
              dataSource={teamBreakdown}
              renderItem={renderTeamItem}
            />
          </Flex>
        )}
      </Flex>
    </Card>
  );
};

export default CephDashboardWidget;
