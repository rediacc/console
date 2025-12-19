import React from 'react';
import { Alert, Col, Empty, Row } from 'antd';
import { useTranslation } from 'react-i18next';
import { RediaccCard, RediaccStack, RediaccStatistic } from '@/components/ui';
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
import { InlineLink, InlineStack } from '../styles';

interface QueueOverviewWidgetProps {
  queueStats?: CompanyDashboardData['queueStats'];
}

const QueueOverviewWidget: React.FC<QueueOverviewWidgetProps> = ({ queueStats }) => {
  const { t } = useTranslation('system');

  if (!queueStats) {
    return (
      <RediaccCard
        fullWidth
        title={
          <InlineStack>
            <RobotOutlined />
            <span>Queue Overview</span>
          </InlineStack>
        }
        data-testid="dashboard-card-queue-overview-empty"
      >
        <Empty description="No queue data available" />
      </RediaccCard>
    );
  }

  return (
    <RediaccCard
      fullWidth
      title={
        <InlineStack>
          <RobotOutlined />
          <span>Queue Overview</span>
        </InlineStack>
      }
      extra={
        <InlineLink to="/queue" data-testid="dashboard-queue-manage-link">
          Manage
        </InlineLink>
      }
      data-testid="dashboard-card-queue-overview"
    >
      <RediaccStack direction="vertical" gap="md" fullWidth>
        <Row gutter={[16, 16]}>
          <Col xs={12} md={6}>
            <RediaccStatistic
              title={t('dashboard.pending')}
              value={queueStats.pendingCount || 0}
              variant="warning"
              prefix={<ClockCircleOutlined />}
              data-testid="dashboard-stat-pending"
            />
          </Col>
          <Col xs={12} md={6}>
            <RediaccStatistic
              title={t('dashboard.processing')}
              value={queueStats.activeCount || 0}
              variant="info"
              prefix={<SyncOutlined spin />}
              data-testid="dashboard-stat-processing"
            />
          </Col>
          <Col xs={12} md={6}>
            <RediaccStatistic
              title={t('dashboard.completed')}
              value={queueStats.completedCount || 0}
              variant="success"
              prefix={<CheckCircleOutlined />}
              data-testid="dashboard-stat-completed"
            />
          </Col>
          <Col xs={12} md={6}>
            <RediaccStatistic
              title={t('dashboard.failed')}
              value={queueStats.failedCount || 0}
              variant="error"
              prefix={<ExclamationCircleOutlined />}
              data-testid="dashboard-stat-failed"
            />
          </Col>
        </Row>

        {(queueStats.hasStaleItems === 1 || queueStats.hasOldPendingItems === 1) && (
          <RediaccStack direction="vertical" gap="sm" fullWidth>
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
          </RediaccStack>
        )}
      </RediaccStack>
    </RediaccCard>
  );
};

export default QueueOverviewWidget;
