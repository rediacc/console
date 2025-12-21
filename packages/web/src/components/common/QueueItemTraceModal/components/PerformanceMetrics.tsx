import React from 'react';
import { Alert, Card, Col, Divider, Progress, Row, Space, Statistic, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { DashboardOutlined, HourglassOutlined, SyncOutlined } from '@/utils/optimizedIcons';

interface MachineStats {
  currentQueueDepth: number;
  activeProcessingCount: number;
  maxConcurrentTasks?: number;
}

interface PerformanceMetricsProps {
  machineStats: MachineStats;
}

export const PerformanceMetrics: React.FC<PerformanceMetricsProps> = ({ machineStats }) => {
  const { t } = useTranslation(['queue', 'common']);

  const isHighQueue = machineStats.currentQueueDepth > 50;
  const isAtCapacity = machineStats.activeProcessingCount >= (machineStats.maxConcurrentTasks || 0);
  const isIdle = machineStats.currentQueueDepth === 0 && machineStats.activeProcessingCount === 0;

  return (
    <>
      <Row gutter={16}>
        <Col span={8}>
          <Card>
            <Statistic
              title={t('trace.queueDepth')}
              value={machineStats.currentQueueDepth}
              prefix={<HourglassOutlined />}
              suffix="tasks"
            />
            <Progress
              percent={Math.min(100, (machineStats.currentQueueDepth / 100) * 100)}
              showInfo={false}
              status={isHighQueue ? 'exception' : 'normal'}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title={t('trace.activeProcessing')}
              value={machineStats.activeProcessingCount}
              prefix={<SyncOutlined spin />}
              suffix="tasks"
            />
            <Typography.Text color="secondary" type="secondary">
              Currently being processed on this machine
            </Typography.Text>
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title={t('trace.processingCapacity')}
              value={`${machineStats.activeProcessingCount}/${machineStats.maxConcurrentTasks || 'N/A'}`}
              prefix={<DashboardOutlined />}
            />
            <Progress
              percent={
                machineStats.maxConcurrentTasks
                  ? Math.min(
                      100,
                      (machineStats.activeProcessingCount / machineStats.maxConcurrentTasks) * 100
                    )
                  : 0
              }
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
