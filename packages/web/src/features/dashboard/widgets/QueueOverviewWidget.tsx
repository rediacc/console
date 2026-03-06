import type { OrganizationDashboardData } from '@rediacc/shared/types';
import { Alert, Card, Col, Empty, Flex, Row, Statistic, Typography } from 'antd';
import React from 'react';
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

interface QueueOverviewWidgetProps {
  queueStats?: OrganizationDashboardData['queueStats'];
}

const QueueOverviewWidget: React.FC<QueueOverviewWidgetProps> = ({ queueStats }) => {
  const { t } = useTranslation(['system', 'common']);

  if (!queueStats) {
    return (
      <Card
        title={
          <Flex align="center" wrap className="inline-flex">
            <RobotOutlined />
            <Typography.Text>{t('common:dashboard.widgets.queueOverview.title')}</Typography.Text>
          </Flex>
        }
        data-testid="dashboard-card-queue-overview-empty"
      >
        <Empty description={t('common:dashboard.widgets.queueOverview.noData')} />
      </Card>
    );
  }

  return (
    <Card
      title={
        <Flex align="center" wrap className="inline-flex">
          <RobotOutlined />
          <Typography.Text>{t('common:dashboard.widgets.queueOverview.title')}</Typography.Text>
        </Flex>
      }
      extra={
        <RouterLink
          to="/queue"
          data-testid="dashboard-queue-manage-link"
          // eslint-disable-next-line no-restricted-syntax
          style={{ fontWeight: 500 }}
        >
          {t('common:dashboard.widgets.queueOverview.manage')}
        </RouterLink>
      }
      data-testid="dashboard-card-queue-overview"
    >
      <Flex vertical className="w-full">
        <Row gutter={[16, 16]}>
          <Col xs={12} md={6}>
            <Statistic
              title={t('dashboard.pending')}
              value={queueStats.pendingCount ?? 0}
              prefix={<ClockCircleOutlined />}
              data-testid="dashboard-stat-pending"
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title={t('dashboard.processing')}
              value={queueStats.activeCount ?? 0}
              prefix={<SyncOutlined spin />}
              data-testid="dashboard-stat-processing"
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title={t('dashboard.completed')}
              value={queueStats.completedCount ?? 0}
              prefix={<CheckCircleOutlined />}
              data-testid="dashboard-stat-completed"
            />
          </Col>
          <Col xs={12} md={6}>
            <Statistic
              title={t('dashboard.failed')}
              value={queueStats.failedCount ?? 0}
              prefix={<ExclamationCircleOutlined />}
              data-testid="dashboard-stat-failed"
            />
          </Col>
        </Row>

        {(queueStats.hasStaleItems === true || queueStats.hasOldPendingItems === true) && (
          <Flex vertical className="gap-sm w-full">
            {queueStats.hasStaleItems === true && (
              <Alert
                message={t('common:dashboard.widgets.queueDetails.staleItems', {
                  count: queueStats.staleCount ?? 0,
                })}
                type="warning"
                icon={<WarningOutlined />}
                data-testid="dashboard-alert-stale-items"
              />
            )}
            {queueStats.hasOldPendingItems === true && (
              <Alert
                message={`Oldest: ${Math.floor((queueStats.oldestPendingAgeMinutes ?? 0) / 60)}h`}
                type="info"
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
