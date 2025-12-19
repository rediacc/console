import React from 'react';
import { Card, Col, Divider, Progress, Row, Space, Statistic } from 'antd';
import { useTranslation } from 'react-i18next';
import { RediaccAlert, RediaccText } from '@/components/ui';
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
              valueStyle={{
                color: isHighQueue ? 'var(--color-error)' : 'var(--color-text-primary)',
              }}
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
            <RediaccText color="secondary">Currently being processed on this machine</RediaccText>
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title={t('trace.processingCapacity')}
              value={`${machineStats.activeProcessingCount}/${machineStats.maxConcurrentTasks || 'N/A'}`}
              prefix={<DashboardOutlined />}
              valueStyle={{
                color: isAtCapacity ? 'var(--color-error)' : 'var(--color-text-primary)',
              }}
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
      <RediaccAlert
        data-testid="queue-trace-performance-alert"
        message="Performance Analysis"
        description={
          <Space direction="vertical">
            {isHighQueue && (
              <RediaccText>High queue depth detected. Tasks may experience delays.</RediaccText>
            )}
            {isAtCapacity && (
              <RediaccText>Machine at full capacity. New tasks will wait in queue.</RediaccText>
            )}
            {isIdle && (
              <RediaccText>Machine is idle and ready to process tasks immediately.</RediaccText>
            )}
          </Space>
        }
        variant={isHighQueue ? 'warning' : 'info'}
      />
    </>
  );
};
