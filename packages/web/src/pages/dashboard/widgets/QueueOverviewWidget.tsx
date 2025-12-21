import React from 'react';
import { Alert, Card, Col, Empty, Flex, Row, Statistic, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  FieldTimeOutlined,
  RobotOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import type { CompanyDashboardData } from '@rediacc/shared/types';

interface QueueOverviewWidgetProps {
  queueStats?: CompanyDashboardData['queueStats'];
}

const QueueOverviewWidget: React.FC<QueueOverviewWidgetProps> = ({ queueStats }) => {
  const { t } = useTranslation('system');

  if (!queueStats) {
    return (
      <Card
        title={
          <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
            <RobotOutlined />
            <Typography.Text>Queue Overview</Typography.Text>
          </Flex>
        }
        data-testid="dashboard-card-queue-overview-empty"
      >
        <Empty description="No queue data available" />
      </Card>
    );
  }

  return (
    <Card
      title={
        <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
          <RobotOutlined />
          <Typography.Text>Queue Overview</Typography.Text>
        </Flex>
      }
      extra={
        <RouterLink
          to="/queue"
          data-testid="dashboard-queue-manage-link"
          style={{ fontWeight: 500 }}
        >
          Manage
        </RouterLink>
      }
      data-testid="dashboard-card-queue-overview"
    >
      <Flex vertical gap={16} style={{ width: '100%' }}>
        <Row gutter={[16, 16]}>
          <Col xs={12} md={6}>
            <Statistic
              title={t('dashboard.pending')}
              value={queueStats.pendingCount || 0}
              prefix={<ClockCircleOutlined />}
              data-testid="dashboard-stat-pending"
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title={t('dashboard.processing')}
              value={queueStats.activeCount || 0}
              prefix={<SyncOutlined spin />}
              data-testid="dashboard-stat-processing"
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title={t('dashboard.completed')}
              value={queueStats.completedCount || 0}
              prefix={<CheckCircleOutlined />}
              data-testid="dashboard-stat-completed"
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title={t('dashboard.failed')}
              value={queueStats.failedCount || 0}
              prefix={<ExclamationCircleOutlined />}
              data-testid="dashboard-stat-failed"
            />
          </Col>
        </Row>

        {(queueStats.hasStaleItems === 1 || queueStats.hasOldPendingItems === 1) && (
          <Flex vertical gap={8} style={{ width: '100%' }}>
            {queueStats.hasStaleItems === 1 && (
              <Alert
                message={`${queueStats.staleCount || 0} stale items`}
                type="warning"
                showIcon
                icon={<WarningOutlined />}
                data-testid="dashboard-alert-stale-items"
              />
            )}
            {queueStats.hasOldPendingItems === 1 && (
              <Alert
                message={`Oldest: ${Math.floor((queueStats.oldestPendingAgeMinutes || 0) / 60)}h`}
                type="info"
                showIcon
                icon={<FieldTimeOutlined />}
                data-testid="dashboard-alert-old-pending"
              />
            )}
          </Flex>
        )}
      </Flex>
    </Card>
  );
};

export default QueueOverviewWidget;
