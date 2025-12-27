import React from 'react';
import { Alert, Card, Col, Divider, Progress, Row, Space, Statistic, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { DashboardOutlined, HourglassOutlined, SyncOutlined } from '@/utils/optimizedIcons';

interface MachineStats {
  currentQueueDepth?: number | null;
  activeProcessingCount?: number | null;
  maxConcurrentTasks?: number | null;
}

interface PerformanceMetricsProps {
  machineStats: MachineStats | null;
}

export const PerformanceMetrics: React.FC<PerformanceMetricsProps> = ({ machineStats }) => {
  const { t } = useTranslation(['queue', 'common']);

  const queueDepth = machineStats?.currentQueueDepth ?? 0;
  const activeCount = machineStats?.activeProcessingCount ?? 0;
  const maxTasks = machineStats?.maxConcurrentTasks ?? 0;

  const isHighQueue = queueDepth > 50;
  const isAtCapacity = activeCount >= maxTasks && maxTasks > 0;
  const isIdle = queueDepth === 0 && activeCount === 0;

  return (
    <>
      <Row gutter={16}>
        <Col span={8}>
          <Card>
            <Statistic
              title={t('trace.queueDepth')}
              value={queueDepth}
              prefix={<HourglassOutlined />}
              suffix="tasks"
            />
            <Progress
              percent={Math.min(100, (queueDepth / 100) * 100)}
              showInfo={false}
              status={isHighQueue ? 'exception' : 'normal'}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title={t('trace.activeProcessing')}
              value={activeCount}
              prefix={<SyncOutlined spin />}
              suffix="tasks"
            />
            <Typography.Text type="secondary">
              Currently being processed on this machine
            </Typography.Text>
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title={t('trace.processingCapacity')}
              value={`${activeCount}/${maxTasks > 0 ? maxTasks : 'N/A'}`}
              prefix={<DashboardOutlined />}
            />
            <Progress
              percent={maxTasks > 0 ? Math.min(100, (activeCount / maxTasks) * 100) : 0}
              showInfo={false}
              status={isAtCapacity ? 'exception' : 'normal'}
            />
          </Card>
        </Col>
      </Row>
      <Divider />
      <Alert
        data-testid="queue-trace-performance-alert"
        message="Performance Analysis"
        description={
          <Space direction="vertical">
            {isHighQueue && (
              <Typography.Text>
                High queue depth detected. Tasks may experience delays.
              </Typography.Text>
            )}
            {isAtCapacity && (
              <Typography.Text>
                Machine at full capacity. New tasks will wait in queue.
              </Typography.Text>
            )}
            {isIdle && (
              <Typography.Text>
                Machine is idle and ready to process tasks immediately.
              </Typography.Text>
            )}
          </Space>
        }
        type={isHighQueue ? 'warning' : 'info'}
      />
    </>
  );
};
